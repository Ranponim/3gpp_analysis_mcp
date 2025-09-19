"""
Baseline Benchmarking and Initial Profiling Tests

AnalysisService의 기준 성능을 측정하고 초기 프로파일링을 수행합니다.
"""

import cProfile
import io
import os
import pstats
import sys
import time
from datetime import datetime

import pytest

# 프로젝트 루트를 Python path에 추가
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)

from services import AnalysisService, LLMAnalysisService, PEGCalculator, PEGProcessingService
from utils import DataProcessor, TimeRangeParser


class TestBaselineBenchmark:
    """기준 성능 벤치마킹 테스트"""
    
    def test_analysis_service_end_to_end_benchmark(
        self,
        benchmark,
        performance_analysis_request,
        mock_performance_database_repository,
        mock_performance_llm_repository,
        performance_logger
    ):
        """AnalysisService End-to-End 성능 벤치마크"""
        # 서비스 구성
        time_parser = TimeRangeParser()
        data_processor = DataProcessor()
        peg_calculator = PEGCalculator()
        
        peg_processing_service = PEGProcessingService(
            database_repository=mock_performance_database_repository,
            peg_calculator=peg_calculator
        )
        
        llm_analysis_service = LLMAnalysisService(
            llm_repository=mock_performance_llm_repository
        )
        
        analysis_service = AnalysisService(
            database_repository=mock_performance_database_repository,
            peg_processing_service=peg_processing_service,
            llm_analysis_service=llm_analysis_service,
            time_parser=time_parser,
            data_processor=data_processor
        )
        
        # 벤치마크 실행
        def run_analysis():
            return analysis_service.perform_analysis(performance_analysis_request)
        
        # pytest-benchmark를 사용한 성능 측정
        result = benchmark.pedantic(
            run_analysis,
            iterations=5,  # 5회 반복 실행
            rounds=3       # 3라운드 측정
        )
        
        # 결과 검증
        assert isinstance(result, dict)
        assert result.get('status') in ['success', 'completed']
        
        performance_logger.info("✅ End-to-End 벤치마크 완료")
        # benchmark.stats는 Metadata 객체이므로 stats 정보를 다른 방식으로 접근
        performance_logger.info(f"벤치마크 실행 완료 - 결과는 pytest-benchmark 리포트 참조")
    
    def test_analysis_service_profiling(
        self,
        performance_analysis_request,
        mock_performance_database_repository,
        mock_performance_llm_repository,
        performance_logger
    ):
        """AnalysisService cProfile 프로파일링"""
        # 서비스 구성
        time_parser = TimeRangeParser()
        data_processor = DataProcessor()
        peg_calculator = PEGCalculator()
        
        peg_processing_service = PEGProcessingService(
            database_repository=mock_performance_database_repository,
            peg_calculator=peg_calculator
        )
        
        llm_analysis_service = LLMAnalysisService(
            llm_repository=mock_performance_llm_repository
        )
        
        analysis_service = AnalysisService(
            database_repository=mock_performance_database_repository,
            peg_processing_service=peg_processing_service,
            llm_analysis_service=llm_analysis_service,
            time_parser=time_parser,
            data_processor=data_processor
        )
        
        # cProfile을 사용한 프로파일링
        profiler = cProfile.Profile()
        profiler.enable()
        
        # 분석 실행
        start_time = time.time()
        result = analysis_service.perform_analysis(performance_analysis_request)
        end_time = time.time()
        
        profiler.disable()
        
        # 프로파일링 결과 분석
        stats_buffer = io.StringIO()
        ps = pstats.Stats(profiler, stream=stats_buffer)
        ps.sort_stats('cumulative')
        ps.print_stats(20)  # 상위 20개 함수 출력
        
        profile_output = stats_buffer.getvalue()
        
        # 결과 검증 및 로깅
        assert isinstance(result, dict)
        assert result.get('status') in ['success', 'completed']
        
        execution_time = end_time - start_time
        performance_logger.info("✅ 프로파일링 완료")
        performance_logger.info(f"총 실행시간: {execution_time:.4f}초")
        performance_logger.info("=== 상위 20개 함수 프로파일링 결과 ===")
        performance_logger.info(f"\n{profile_output}")
        
        # 프로파일링 결과를 파일로 저장
        profile_filename = f"performance_profile_{datetime.now().strftime('%Y%m%d_%H%M%S')}.prof"
        profiler.dump_stats(profile_filename)
        performance_logger.info(f"프로파일링 결과 저장: {profile_filename}")
    
    def test_individual_component_benchmarks(
        self,
        benchmark,
        large_peg_dataset,
        mock_performance_database_repository,
        mock_performance_llm_repository,
        performance_logger
    ):
        """개별 컴포넌트 벤치마크"""
        # 1. TimeRangeParser 벤치마크
        time_parser = TimeRangeParser()
        
        def parse_time_ranges():
            n1_start, n1_end = time_parser.parse("2025-01-01_09:00~2025-01-01_18:00")
            n_start, n_end = time_parser.parse("2025-01-02_09:00~2025-01-02_18:00")
            return (n1_start, n1_end, n_start, n_end)
        
        time_result = benchmark.pedantic(parse_time_ranges, iterations=100, rounds=5)
        performance_logger.info("TimeRangeParser 벤치마크 완료")
        
        # 2. PEGCalculator 벤치마크
        peg_calculator = PEGCalculator()
        
        def calculate_pegs():
            return peg_calculator.aggregate_peg_data(
                large_peg_dataset,
                aggregation_method='mean'
            )
        
        peg_result = benchmark.pedantic(calculate_pegs, iterations=10, rounds=3)
        performance_logger.info("PEGCalculator 벤치마크 완료")
        
        # 3. DataProcessor 벤치마크
        data_processor = DataProcessor()
        
        # N-1과 N 데이터를 분리
        n1_data = large_peg_dataset[large_peg_dataset.get('period', 'N-1') == 'N-1'].to_dict('records')
        n_data = large_peg_dataset[large_peg_dataset.get('period', 'N') == 'N'].to_dict('records')
        
        if not n1_data:  # period 컬럼이 없는 경우 절반씩 분할
            mid_point = len(large_peg_dataset) // 2
            n1_data = large_peg_dataset.iloc[:mid_point].to_dict('records')
            n_data = large_peg_dataset.iloc[mid_point:].to_dict('records')
        
        def process_data():
            return data_processor.process_data(
                n_minus_1_data=n1_data,
                n_data=n_data,
                llm_analysis_results={'summary': 'test', 'insights': 'test'}
            )
        
        if n1_data and n_data:  # 데이터가 있는 경우에만 실행
            data_result = benchmark.pedantic(process_data, iterations=5, rounds=3)
            performance_logger.info("DataProcessor 벤치마크 완료")
        
        performance_logger.info("✅ 개별 컴포넌트 벤치마크 완료")
    
    def test_memory_baseline_measurement(
        self,
        performance_analysis_request,
        mock_performance_database_repository,
        mock_performance_llm_repository,
        memory_tracker,
        performance_logger
    ):
        """메모리 사용량 기준 측정"""
        # 초기 메모리 상태 기록
        initial_memory = memory_tracker.get_memory_usage()
        performance_logger.info(f"초기 메모리 사용량: {initial_memory['current_mb']:.2f}MB")
        
        # 서비스 구성
        time_parser = TimeRangeParser()
        data_processor = DataProcessor()
        peg_calculator = PEGCalculator()
        
        memory_tracker.update_peak()
        
        peg_processing_service = PEGProcessingService(
            database_repository=mock_performance_database_repository,
            peg_calculator=peg_calculator
        )
        
        llm_analysis_service = LLMAnalysisService(
            llm_repository=mock_performance_llm_repository
        )
        
        analysis_service = AnalysisService(
            database_repository=mock_performance_database_repository,
            peg_processing_service=peg_processing_service,
            llm_analysis_service=llm_analysis_service,
            time_parser=time_parser,
            data_processor=data_processor
        )
        
        memory_tracker.update_peak()
        setup_memory = memory_tracker.get_memory_usage()
        performance_logger.info(f"서비스 설정 후 메모리: {setup_memory['current_mb']:.2f}MB")
        
        # 분석 실행
        result = analysis_service.perform_analysis(performance_analysis_request)
        
        # 최종 메모리 상태 기록
        final_memory = memory_tracker.get_memory_usage()
        
        # 결과 검증 및 로깅
        assert isinstance(result, dict)
        assert result.get('status') in ['success', 'completed']
        
        performance_logger.info("✅ 메모리 기준 측정 완료")
        performance_logger.info(f"최종 메모리 사용량: {final_memory['current_mb']:.2f}MB")
        performance_logger.info(f"피크 메모리 사용량: {final_memory['peak_mb']:.2f}MB")
        performance_logger.info(f"메모리 증가량: {final_memory['increase_mb']:.2f}MB")
        
        # 메모리 사용량이 합리적인 범위 내에 있는지 확인
        assert final_memory['peak_mb'] < 500, f"메모리 사용량이 너무 높습니다: {final_memory['peak_mb']:.2f}MB"
    
    def test_throughput_benchmark(
        self,
        performance_analysis_request,
        mock_performance_database_repository,
        mock_performance_llm_repository,
        performance_logger
    ):
        """처리량 벤치마크 (동시 요청 시뮬레이션)"""
        # 서비스 구성
        time_parser = TimeRangeParser()
        data_processor = DataProcessor()
        peg_calculator = PEGCalculator()
        
        peg_processing_service = PEGProcessingService(
            database_repository=mock_performance_database_repository,
            peg_calculator=peg_calculator
        )
        
        llm_analysis_service = LLMAnalysisService(
            llm_repository=mock_performance_llm_repository
        )
        
        analysis_service = AnalysisService(
            database_repository=mock_performance_database_repository,
            peg_processing_service=peg_processing_service,
            llm_analysis_service=llm_analysis_service,
            time_parser=time_parser,
            data_processor=data_processor
        )
        
        # 연속 요청 처리 시간 측정
        num_requests = 10
        start_time = time.time()
        
        results = []
        for i in range(num_requests):
            # 각 요청마다 약간씩 다른 파라미터 사용
            request = performance_analysis_request.copy()
            request['filters']['cellid'] = [f"cell_{j:03d}" for j in range(i+1, i+4)]
            
            result = analysis_service.perform_analysis(request)
            results.append(result)
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # 모든 요청이 성공했는지 확인
        successful_requests = sum(1 for r in results if r.get('status') in ['success', 'completed'])
        
        # 처리량 계산
        throughput = successful_requests / total_time  # 요청/초
        avg_response_time = total_time / successful_requests  # 초/요청
        
        performance_logger.info("✅ 처리량 벤치마크 완료")
        performance_logger.info(f"총 요청 수: {num_requests}")
        performance_logger.info(f"성공한 요청 수: {successful_requests}")
        performance_logger.info(f"총 처리 시간: {total_time:.2f}초")
        performance_logger.info(f"처리량: {throughput:.2f} 요청/초")
        performance_logger.info(f"평균 응답 시간: {avg_response_time:.3f}초")
        
        # 성능 기준 검증
        assert successful_requests == num_requests, "모든 요청이 성공해야 합니다"
        assert avg_response_time < 2.0, f"평균 응답 시간이 너무 깁니다: {avg_response_time:.3f}초"
        assert throughput > 0.5, f"처리량이 너무 낮습니다: {throughput:.2f} 요청/초"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--benchmark-only'])
