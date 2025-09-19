"""
API Flow Integration Tests

MCPHandler와 AnalysisService 간의 상호작용을 검증하는 통합 테스트
"""

import os
import sys
from unittest.mock import Mock

import pytest

# 프로젝트 루트를 Python path에 추가
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)

from models import AnalysisResponse
from services import AnalysisService
from utils import RequestValidationError, RequestValidator, ResponseFormatter


class TestAPIFlowIntegration:
    """API 플로우 통합 테스트"""
    
    def test_request_validation_to_analysis_service_flow(
        self, 
        sample_analysis_request,
        mock_database_repository,
        mock_llm_repository,
        integration_test_logger
    ):
        """요청 검증 → 분석 서비스 플로우 테스트"""
        # 1단계: RequestValidator 초기화
        from utils import TimeRangeParser
        time_parser = TimeRangeParser()
        request_validator = RequestValidator(time_parser=time_parser)
        
        # 2단계: 요청 검증 실행
        normalized_request = request_validator.validate_request(sample_analysis_request)
        
        # 검증 결과 확인
        assert isinstance(normalized_request, dict)
        assert len(normalized_request) >= 10  # 기본값 적용으로 증가
        assert 'n_minus_1' in normalized_request
        assert 'n' in normalized_request
        
        integration_test_logger.info("✅ 요청 검증 완료: %d개 필드", len(normalized_request))
        
        # 3단계: Mock AnalysisService 설정
        mock_analysis_service = Mock(spec=AnalysisService)
        mock_analysis_service.perform_analysis.return_value = {
            'status': 'success',
            'data_summary': {'total_pegs': 2, 'complete_data_pegs': 2},
            'peg_analysis': {
                'results': [
                    {
                        'peg_name': 'preamble_count',
                        'n_minus_1_value': 1000.0,
                        'n_value': 1100.0,
                        'percentage_change': 10.0
                    }
                ]
            },
            'llm_analysis': {
                'integrated_analysis': 'API 플로우 테스트 성공',
                'model_used': 'mock-model'
            },
            'metadata': {'request_id': 'api-flow-test'}
        }
        
        # 4단계: 분석 서비스 호출
        analysis_result = mock_analysis_service.perform_analysis(normalized_request)
        
        # 분석 결과 확인
        assert analysis_result['status'] == 'success'
        assert 'data_summary' in analysis_result
        assert 'peg_analysis' in analysis_result
        
        integration_test_logger.info("✅ 분석 서비스 호출 완료")
        
        # 5단계: ResponseFormatter로 응답 포맷팅
        response_formatter = ResponseFormatter()
        formatted_response = response_formatter.format_analysis_response(analysis_result)
        
        # 포맷팅 결과 확인
        assert isinstance(formatted_response, AnalysisResponse)
        assert formatted_response.status == 'completed'
        assert len(formatted_response.peg_statistics) >= 1
        
        integration_test_logger.info("✅ 응답 포맷팅 완료: status=%s", formatted_response.status)
        
        # 6단계: 전체 플로우 검증
        integration_test_logger.info("✅ API 플로우 통합 테스트 성공")
    
    def test_validation_error_propagation(
        self,
        mock_database_repository,
        integration_test_logger
    ):
        """검증 오류 전파 테스트"""
        # 잘못된 요청 데이터
        invalid_request = {
            "n_minus_1": "잘못된 시간 형식",
            "n": "2025-01-02_09:00~18:00"
        }
        
        # RequestValidator 초기화
        from utils import TimeRangeParser
        time_parser = TimeRangeParser()
        request_validator = RequestValidator(time_parser=time_parser)
        
        # 검증 오류 발생 확인
        with pytest.raises(RequestValidationError) as exc_info:
            request_validator.validate_request(invalid_request)
        
        # 오류 세부 정보 확인
        error = exc_info.value
        assert "시간 범위 형식 오류" in error.message
        assert error.field_name == "time_ranges"
        assert error.validation_rule == "time_format"
        
        integration_test_logger.info("✅ 검증 오류 전파 테스트 성공")
    
    def test_end_to_end_mock_workflow(
        self,
        sample_analysis_request,
        mock_database_repository,
        mock_llm_repository,
        integration_test_logger
    ):
        """End-to-End Mock 워크플로우 테스트"""
        # 모든 컴포넌트를 Mock으로 구성하여 완전한 플로우 테스트
        
        # 1단계: 컴포넌트 초기화
        from services import AnalysisService, LLMAnalysisService, PEGCalculator, PEGProcessingService
        from utils import DataProcessor, RequestValidator, ResponseFormatter, TimeRangeParser
        
        time_parser = TimeRangeParser()
        request_validator = RequestValidator(time_parser=time_parser)
        response_formatter = ResponseFormatter()
        data_processor = DataProcessor()
        peg_calculator = PEGCalculator()
        
        # 2단계: 서비스 계층 구성 (Mock Repository 주입)
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
        
        integration_test_logger.info("✅ 모든 컴포넌트 초기화 완료")
        
        # 3단계: 통합 플로우 실행
        # 요청 검증
        normalized_request = request_validator.validate_request(sample_analysis_request)
        integration_test_logger.info("✅ 요청 검증 완료")
        
        # 분석 실행 (Mock 환경)
        analysis_result = analysis_service.perform_analysis(normalized_request)
        integration_test_logger.info("✅ 분석 실행 완료")
        
        # 응답 포맷팅
        formatted_response = response_formatter.format_analysis_response(analysis_result)
        integration_test_logger.info("✅ 응답 포맷팅 완료")
        
        # 4단계: 결과 검증
        assert isinstance(formatted_response, AnalysisResponse)
        assert formatted_response.status in ['completed', 'error']
        
        # Mock 호출 검증
        mock_database_repository.fetch_peg_data.assert_called()
        mock_llm_repository.analyze_data.assert_called()
        
        integration_test_logger.info("✅ End-to-End Mock 워크플로우 테스트 성공")
    
    def test_error_propagation_across_layers(
        self,
        sample_analysis_request,
        integration_test_logger
    ):
        """계층 간 오류 전파 테스트"""
        # Mock Repository에서 오류 발생 설정
        from exceptions import AnalysisError
        from repositories import DatabaseError
        
        error_db_repo = Mock()
        error_db_repo.fetch_peg_data.side_effect = DatabaseError(
            message="통합 테스트 DB 오류",
            query="SELECT * FROM test_table"
        )
        
        # 서비스 구성
        from services import AnalysisService, LLMAnalysisService, PEGCalculator, PEGProcessingService
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
        with pytest.raises((DatabaseError, AnalysisError)) as exc_info:
            analysis_service.perform_analysis(sample_analysis_request)
        
        # 오류가 적절히 전파되었는지 확인
        error = exc_info.value
        assert "오류" in str(error)
        
        integration_test_logger.info("✅ 오류 전파 테스트 성공: %s", type(error).__name__)


class TestMCPHandlerIntegration:
    """MCPHandler 통합 테스트"""
    
    def test_mcp_handler_full_workflow(
        self,
        sample_analysis_request,
        mock_database_repository,
        mock_llm_repository,
        integration_test_logger
    ):
        """MCPHandler 전체 워크플로우 테스트"""
        # MCPHandler 구성 (의존성 주입)
        from services import AnalysisService, LLMAnalysisService, PEGCalculator, PEGProcessingService
        from utils import DataProcessor, RequestValidator, ResponseFormatter, TimeRangeParser

        # 컴포넌트 초기화
        time_parser = TimeRangeParser()
        request_validator = RequestValidator(time_parser=time_parser)
        response_formatter = ResponseFormatter()
        data_processor = DataProcessor()
        peg_calculator = PEGCalculator()
        
        # 서비스 계층 구성
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
        
        # Mock MCPHandler 생성
        class IntegrationMCPHandler:
            def __init__(self, request_validator, analysis_service, response_formatter):
                self.request_validator = request_validator
                self.analysis_service = analysis_service
                self.response_formatter = response_formatter
                self.logger = integration_test_logger
            
            def handle_request(self, request):
                """통합 테스트용 요청 처리"""
                try:
                    # 요청 검증
                    normalized_request = self.request_validator.validate_request(request)
                    self.logger.info("요청 검증 완료")
                    
                    # 분석 실행
                    analysis_result = self.analysis_service.perform_analysis(normalized_request)
                    self.logger.info("분석 실행 완료")
                    
                    # 응답 포맷팅
                    formatted_response = self.response_formatter.format_analysis_response(analysis_result)
                    self.logger.info("응답 포맷팅 완료")
                    
                    return formatted_response.to_dict()
                    
                except Exception as e:
                    self.logger.error("요청 처리 실패: %s", e)
                    return {
                        'status': 'error',
                        'message': f'처리 오류: {str(e)}',
                        'error_type': type(e).__name__
                    }
        
        # MCPHandler 인스턴스 생성
        mcp_handler = IntegrationMCPHandler(
            request_validator=request_validator,
            analysis_service=analysis_service,
            response_formatter=response_formatter
        )
        
        # 전체 워크플로우 실행
        result = mcp_handler.handle_request(sample_analysis_request)
        
        # 결과 검증
        assert isinstance(result, dict)
        assert result.get('status') in ['completed', 'error']
        
        if result.get('status') == 'completed':
            assert 'analysis_id' in result
            assert 'peg_statistics' in result
            assert 'llm_analysis' in result
            integration_test_logger.info("✅ MCPHandler 성공 워크플로우 완료")
        else:
            integration_test_logger.info("✅ MCPHandler 오류 처리 워크플로우 완료")
        
        # Mock 호출 검증
        mock_database_repository.fetch_peg_data.assert_called()
        mock_llm_repository.analyze_data.assert_called()
    
    def test_invalid_request_handling(
        self,
        mock_database_repository,
        integration_test_logger
    ):
        """잘못된 요청 처리 테스트"""
        # 잘못된 요청 데이터
        invalid_request = {
            "n_minus_1": "invalid_time_format",
            "n": "2025-01-02_09:00~18:00"
        }
        
        # RequestValidator만 테스트 (분석 서비스까지 가지 않음)
        from utils import RequestValidator, TimeRangeParser
        
        time_parser = TimeRangeParser()
        request_validator = RequestValidator(time_parser=time_parser)
        
        # 검증 오류 발생 확인
        with pytest.raises(RequestValidationError) as exc_info:
            request_validator.validate_request(invalid_request)
        
        # 오류 세부 정보 확인
        error = exc_info.value
        assert isinstance(error, RequestValidationError)
        assert "시간 범위 형식 오류" in error.message
        
        integration_test_logger.info("✅ 잘못된 요청 처리 테스트 성공")
    
    def test_response_formatting_integration(
        self,
        integration_test_logger
    ):
        """응답 포맷팅 통합 테스트"""
        # Mock 분석 결과
        mock_analysis_result = {
            'status': 'success',
            'data_summary': {
                'total_pegs': 1,
                'complete_data_pegs': 1
            },
            'peg_analysis': {
                'results': [
                    {
                        'peg_name': 'integration_test_peg',
                        'n_minus_1_value': 500.0,
                        'n_value': 550.0,
                        'percentage_change': 10.0
                    }
                ]
            },
            'llm_analysis': {
                'integrated_analysis': '통합 테스트 분석 결과',
                'specific_peg_analysis': '개별 PEG 분석',
                'recommendations': '통합 테스트 권고사항',
                'model_used': 'integration-test-model'
            },
            'metadata': {
                'request_id': 'formatting-integration-test',
                'processing_time': 0.5
            }
        }
        
        # ResponseFormatter 초기화 및 실행
        response_formatter = ResponseFormatter()
        formatted_response = response_formatter.format_analysis_response(mock_analysis_result)
        
        # 포맷팅 결과 검증
        assert isinstance(formatted_response, AnalysisResponse)
        assert formatted_response.status == 'completed'
        assert 'formatting-integration-test' in formatted_response.analysis_id
        
        # PEG 통계 확인
        assert len(formatted_response.peg_statistics) == 1
        peg_stat = formatted_response.peg_statistics[0]
        assert peg_stat.peg_name == 'integration_test_peg'
        assert peg_stat.pct_change == 10.0
        
        # LLM 분석 확인
        assert formatted_response.llm_analysis.integrated_analysis == '통합 테스트 분석 결과'
        
        # 백엔드 형식 변환 테스트
        backend_format = response_formatter.format_for_backend(formatted_response)
        assert isinstance(backend_format, dict)
        assert 'analysis_id' in backend_format
        assert 'peg_data' in backend_format
        
        integration_test_logger.info("✅ 응답 포맷팅 통합 테스트 성공")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
