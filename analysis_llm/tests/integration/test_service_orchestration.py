"""
Service Orchestration Integration Tests

AnalysisService의 오케스트레이션 로직과 하위 서비스들 간의 상호작용을 검증
"""

import os
import sys
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

# 프로젝트 루트를 Python path에 추가
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)

from models import LLMAnalysisResult
from services import AnalysisService, LLMAnalysisService, PEGProcessingService
from utils import DataProcessor, TimeRangeParser


class TestAnalysisServiceOrchestration:
    """AnalysisService 오케스트레이션 통합 테스트"""
    
    def test_service_initialization_with_dependencies(
        self,
        mock_database_repository,
        mock_llm_repository,
        integration_test_logger
    ):
        """의존성 주입으로 서비스 초기화 테스트"""
        # 의존성 컴포넌트 초기화
        from services import PEGCalculator
        
        time_parser = TimeRangeParser()
        data_processor = DataProcessor()
        peg_calculator = PEGCalculator()
        
        # 하위 서비스 초기화
        peg_processing_service = PEGProcessingService(
            database_repository=mock_database_repository,
            peg_calculator=peg_calculator
        )
        
        llm_analysis_service = LLMAnalysisService(
            llm_repository=mock_llm_repository
        )
        
        # AnalysisService 초기화
        analysis_service = AnalysisService(
            database_repository=mock_database_repository,
            peg_processing_service=peg_processing_service,
            llm_analysis_service=llm_analysis_service,
            time_parser=time_parser,
            data_processor=data_processor
        )
        
        # 초기화 검증
        assert isinstance(analysis_service, AnalysisService)
        
        # 서비스 정보 확인
        service_info = analysis_service.get_service_info()
        assert service_info['service_name'] == 'AnalysisService'
        assert len(service_info['workflow_steps']) == 6
        
        # 워크플로우 상태 확인
        workflow_status = analysis_service.get_workflow_status()
        dependencies_ready = workflow_status['dependencies_ready']
        
        # 모든 의존성이 준비되었는지 확인
        expected_dependencies = {
            'peg_processing_service', 'llm_analysis_service', 
            'time_parser', 'data_processor', 'database_repository'
        }
        assert set(dependencies_ready.keys()) == expected_dependencies
        assert all(dependencies_ready.values())  # 모든 의존성이 True
        
        integration_test_logger.info("✅ 서비스 초기화 및 의존성 검증 완료")
    
    def test_analysis_workflow_orchestration(
        self,
        sample_analysis_request,
        mock_database_repository,
        mock_llm_repository,
        integration_test_logger
    ):
        """분석 워크플로우 오케스트레이션 테스트"""
        # Mock 데이터 설정
        import pandas as pd
        mock_peg_df = pd.DataFrame([
            {'datetime': datetime(2025, 1, 1, 10, 0), 'peg_name': 'preamble_count', 'value': 1000.0, 'period': 'N-1'},
            {'datetime': datetime(2025, 1, 2, 10, 0), 'peg_name': 'preamble_count', 'value': 1100.0, 'period': 'N'}
        ])
        mock_database_repository.fetch_peg_data.return_value = mock_peg_df
        
        # Mock LLM 응답
        mock_llm_repository.analyze_data.return_value = {
            'summary': '오케스트레이션 테스트 분석',
            'key_insights': 'PEG 성능 개선 확인',
            'recommendations': '현재 설정 유지',
            'model_used': 'orchestration-test-model',
            'tokens_used': 180
        }
        
        # 서비스 구성
        from services import PEGCalculator
        from utils import DataProcessor, TimeRangeParser
        
        time_parser = TimeRangeParser()
        data_processor = DataProcessor()
        peg_calculator = PEGCalculator()
        
        peg_processing_service = PEGProcessingService(
            database_repository=mock_database_repository,
            peg_calculator=peg_calculator
        )
        
        llm_analysis_service = LLMAnalysisService(
            llm_repository=mock_llm_repository
        )
        
        analysis_service = AnalysisService(
            database_repository=mock_database_repository,
            peg_processing_service=peg_processing_service,
            llm_analysis_service=llm_analysis_service,
            time_parser=time_parser,
            data_processor=data_processor
        )
        
        # 분석 실행
        result = analysis_service.perform_analysis(sample_analysis_request)
        
        # 결과 검증
        assert isinstance(result, dict)
        assert result.get('status') in ['success', 'completed']
        
        # 하위 서비스 호출 확인
        mock_database_repository.fetch_peg_data.assert_called()
        mock_llm_repository.analyze_data.assert_called()
        
        integration_test_logger.info("✅ 분석 워크플로우 오케스트레이션 테스트 성공")
    
    def test_service_to_service_data_flow(
        self,
        mock_database_repository,
        mock_llm_repository,
        sample_peg_data,
        integration_test_logger
    ):
        """서비스 간 데이터 흐름 테스트"""
        # PEG 데이터를 DataFrame으로 변환
        import pandas as pd
        peg_df = pd.DataFrame(sample_peg_data)
        mock_database_repository.fetch_peg_data.return_value = peg_df
        
        # 서비스 구성
        from services import PEGCalculator
        from utils import DataProcessor
        
        peg_calculator = PEGCalculator()
        DataProcessor()
        
        # PEGProcessingService 테스트
        peg_processing_service = PEGProcessingService(
            database_repository=mock_database_repository,
            peg_calculator=peg_calculator
        )
        
        # 시간 범위 설정
        from models import TimeRange
        n1_range = TimeRange(
            start=datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc),
            end=datetime(2025, 1, 1, 18, 0, tzinfo=timezone.utc)
        )
        n_range = TimeRange(
            start=datetime(2025, 1, 2, 9, 0, tzinfo=timezone.utc),
            end=datetime(2025, 1, 2, 18, 0, tzinfo=timezone.utc)
        )
        
        # PEG 처리 실행
        peg_result = peg_processing_service.process_peg_data(
            n1_range=n1_range,
            n_range=n_range,
            table='summary',
            filters={'ne': 'nvgnb#10000'}
        )
        
        # PEG 처리 결과 검증
        assert isinstance(peg_result, pd.DataFrame)
        assert len(peg_result) > 0
        
        integration_test_logger.info("✅ PEGProcessingService 데이터 처리 완료")
        
        # LLMAnalysisService 테스트
        llm_analysis_service = LLMAnalysisService(
            llm_repository=mock_llm_repository
        )
        
        # Mock LLM 응답 설정
        mock_llm_repository.analyze_data.return_value = {
            'summary': '서비스 간 데이터 흐름 테스트',
            'model_used': 'data-flow-test-model'
        }
        
        # LLM 분석 실행
        llm_result = llm_analysis_service.analyze_peg_data(
            processed_df=peg_result,
            n1_range=n1_range,
            n_range=n_range,
            analysis_type='enhanced'
        )
        
        # LLM 분석 결과 검증
        assert isinstance(llm_result, LLMAnalysisResult)
        assert llm_result.model_used == 'data-flow-test-model'
        
        integration_test_logger.info("✅ LLMAnalysisService 분석 완료")
        
        # 서비스 간 데이터 전달 확인
        mock_database_repository.fetch_peg_data.assert_called()
        mock_llm_repository.analyze_data.assert_called()
        
        integration_test_logger.info("✅ 서비스 간 데이터 흐름 테스트 성공")
    
    def test_error_handling_orchestration(
        self,
        sample_analysis_request,
        integration_test_logger
    ):
        """오케스트레이션 오류 처리 테스트"""
        # 오류를 발생시키는 Mock Repository
        from repositories import DatabaseError
        from services import PEGProcessingError
        
        error_db_repo = Mock()
        error_db_repo.fetch_peg_data.side_effect = DatabaseError(
            message="오케스트레이션 테스트 DB 오류",
            query="SELECT * FROM summary"
        )
        
        # 서비스 구성
        from services import PEGCalculator
        from utils import DataProcessor, TimeRangeParser
        
        time_parser = TimeRangeParser()
        data_processor = DataProcessor()
        peg_calculator = PEGCalculator()
        
        mock_llm_repo = Mock()
        
        peg_processing_service = PEGProcessingService(
            database_repository=error_db_repo,
            peg_calculator=peg_calculator
        )
        
        llm_analysis_service = LLMAnalysisService(
            llm_repository=mock_llm_repo
        )
        
        analysis_service = AnalysisService(
            database_repository=error_db_repo,
            peg_processing_service=peg_processing_service,
            llm_analysis_service=llm_analysis_service,
            time_parser=time_parser,
            data_processor=data_processor
        )
        
        # 오류 전파 확인
        with pytest.raises((DatabaseError, PEGProcessingError)) as exc_info:
            analysis_service.perform_analysis(sample_analysis_request)
        
        # 오류 세부 정보 확인
        error = exc_info.value
        assert "오류" in str(error)
        
        integration_test_logger.info("✅ 오케스트레이션 오류 처리 테스트 성공: %s", type(error).__name__)
    
    def test_service_state_management(
        self,
        mock_database_repository,
        mock_llm_repository,
        integration_test_logger
    ):
        """서비스 상태 관리 테스트"""
        # 서비스 구성
        from services import PEGCalculator
        from utils import DataProcessor, TimeRangeParser
        
        time_parser = TimeRangeParser()
        data_processor = DataProcessor()
        peg_calculator = PEGCalculator()
        
        peg_processing_service = PEGProcessingService(
            database_repository=mock_database_repository,
            peg_calculator=peg_calculator
        )
        
        llm_analysis_service = LLMAnalysisService(
            llm_repository=mock_llm_repository
        )
        
        analysis_service = AnalysisService(
            database_repository=mock_database_repository,
            peg_processing_service=peg_processing_service,
            llm_analysis_service=llm_analysis_service,
            time_parser=time_parser,
            data_processor=data_processor
        )
        
        # 초기 상태 확인
        initial_workflow_status = analysis_service.get_workflow_status()
        assert initial_workflow_status['step_count'] == 6
        assert len(initial_workflow_status['dependencies_ready']) == 5
        
        # 서비스 정보 확인
        service_info = analysis_service.get_service_info()
        assert 'workflow_steps' in service_info
        assert 'dependencies' in service_info
        
        # 의존성 정보 검증
        dependencies = service_info['dependencies']
        expected_deps = {
            'peg_processing_service', 'llm_analysis_service',
            'time_parser', 'data_processor', 'database_repository'
        }
        assert set(dependencies.keys()) == expected_deps
        
        integration_test_logger.info("✅ 서비스 상태 관리 테스트 성공")


class TestPEGProcessingServiceIntegration:
    """PEGProcessingService 통합 테스트"""
    
    def test_peg_service_with_calculator_integration(
        self,
        mock_database_repository,
        sample_peg_data,
        mock_time_ranges,
        integration_test_logger
    ):
        """PEG 서비스와 계산기 통합 테스트"""
        # PEG 데이터를 DataFrame으로 설정
        import pandas as pd
        peg_df = pd.DataFrame(sample_peg_data)
        mock_database_repository.fetch_peg_data.return_value = peg_df
        
        # PEGCalculator와 PEGProcessingService 구성
        from services import PEGCalculator
        
        peg_calculator = PEGCalculator()
        peg_processing_service = PEGProcessingService(
            database_repository=mock_database_repository,
            peg_calculator=peg_calculator
        )
        
        # PEG 처리 실행
        result = peg_processing_service.process_peg_data(
            n1_range=mock_time_ranges['n_minus_1'],
            n_range=mock_time_ranges['n'],
            table='summary',
            filters={'ne': 'nvgnb#10000', 'cellid': ['2010']}
        )
        
        # 결과 검증
        assert isinstance(result, pd.DataFrame)
        assert len(result) > 0
        
        # 필수 컬럼 확인
        expected_columns = ['datetime', 'peg_name', 'value']
        for col in expected_columns:
            assert col in result.columns
        
        # Mock 호출 확인
        mock_database_repository.fetch_peg_data.assert_called()
        
        integration_test_logger.info("✅ PEG 서비스-계산기 통합 테스트 성공")
    
    def test_peg_service_error_handling(
        self,
        mock_time_ranges,
        integration_test_logger
    ):
        """PEG 서비스 오류 처리 통합 테스트"""
        # 오류를 발생시키는 Mock Repository
        from repositories import DatabaseError
        from services import PEGProcessingError
        
        error_repo = Mock()
        error_repo.fetch_peg_data.side_effect = DatabaseError(
            message="PEG 서비스 통합 테스트 DB 오류",
            query="SELECT * FROM summary"
        )
        
        # PEG 서비스 구성
        from services import PEGCalculator
        
        peg_calculator = PEGCalculator()
        peg_processing_service = PEGProcessingService(
            database_repository=error_repo,
            peg_calculator=peg_calculator
        )
        
        # 오류 발생 확인
        with pytest.raises((DatabaseError, PEGProcessingError)) as exc_info:
            peg_processing_service.process_peg_data(
                n1_range=mock_time_ranges['n_minus_1'],
                n_range=mock_time_ranges['n'],
                table='summary'
            )
        
        # 오류 전파 확인
        error = exc_info.value
        assert "오류" in str(error)
        
        integration_test_logger.info("✅ PEG 서비스 오류 처리 테스트 성공")


class TestLLMAnalysisServiceIntegration:
    """LLMAnalysisService 통합 테스트"""
    
    def test_llm_service_with_repository_integration(
        self,
        mock_llm_repository,
        sample_peg_data,
        mock_time_ranges,
        integration_test_logger
    ):
        """LLM 서비스와 Repository 통합 테스트"""
        # Mock LLM 응답 설정
        mock_llm_repository.analyze_data.return_value = {
            'summary': 'LLM 서비스 통합 테스트 분석',
            'key_insights': 'Repository 통합 성공',
            'recommendations': 'Mock 환경에서 정상 작동',
            'model_used': 'llm-integration-test-model',
            'tokens_used': 220
        }
        
        # LLMAnalysisService 구성
        llm_analysis_service = LLMAnalysisService(
            llm_repository=mock_llm_repository
        )
        
        # PEG 데이터를 DataFrame으로 변환
        import pandas as pd
        processed_df = pd.DataFrame(sample_peg_data)
        
        # LLM 분석 실행
        result = llm_analysis_service.analyze_peg_data(
            processed_df=processed_df,
            n1_range=mock_time_ranges['n_minus_1'],
            n_range=mock_time_ranges['n'],
            analysis_type='enhanced'
        )
        
        # 결과 검증
        assert isinstance(result, LLMAnalysisResult)
        assert result.integrated_analysis == 'LLM 서비스 통합 테스트 분석'
        assert result.model_used == 'llm-integration-test-model'
        assert result.tokens_used == 220
        
        # Repository 호출 확인
        mock_llm_repository.analyze_data.assert_called_once()
        
        integration_test_logger.info("✅ LLM 서비스-Repository 통합 테스트 성공")
    
    def test_llm_service_strategy_integration(
        self,
        mock_llm_repository,
        integration_test_logger
    ):
        """LLM 서비스 전략 패턴 통합 테스트"""
        # 다양한 분석 타입별 Mock 응답 설정
        def mock_analyze_data(prompt, **kwargs):
            if 'overall' in prompt.lower():
                return {
                    'summary': '전체 분석 전략 테스트',
                    'model_used': 'overall-strategy-model'
                }
            elif 'enhanced' in prompt.lower():
                return {
                    'summary': '향상된 분석 전략 테스트',
                    'model_used': 'enhanced-strategy-model'
                }
            else:
                return {
                    'summary': '특정 분석 전략 테스트',
                    'model_used': 'specific-strategy-model'
                }
        
        mock_llm_repository.analyze_data.side_effect = mock_analyze_data
        
        # LLMAnalysisService 구성
        llm_analysis_service = LLMAnalysisService(
            llm_repository=mock_llm_repository
        )
        
        # 샘플 데이터
        import pandas as pd
        test_df = pd.DataFrame([
            {'peg_name': 'strategy_test', 'value': 100.0}
        ])
        
        # 시간 범위
        from models import TimeRange
        test_range = TimeRange(
            start=datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc),
            end=datetime(2025, 1, 1, 18, 0, tzinfo=timezone.utc)
        )
        
        # 다양한 전략으로 테스트
        for analysis_type in ['overall', 'enhanced', 'specific']:
            result = llm_analysis_service.analyze_peg_data(
                processed_df=test_df,
                n1_range=test_range,
                n_range=test_range,
                analysis_type=analysis_type
            )
            
            assert isinstance(result, LLMAnalysisResult)
            assert f'{analysis_type}-strategy-model' in result.model_used
            
            integration_test_logger.info("✅ %s 전략 테스트 성공", analysis_type)
        
        # 모든 전략이 호출되었는지 확인
        assert mock_llm_repository.analyze_data.call_count == 3
        
        integration_test_logger.info("✅ LLM 서비스 전략 통합 테스트 성공")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
