"""
Memory Usage Analysis and Optimization Tests

메모리 사용량을 분석하고 최적화합니다.
"""

import gc
import os
import sys
import time

import numpy as np
import pandas as pd
import pytest

# 프로젝트 루트를 Python path에 추가
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)

from services import AnalysisService, LLMAnalysisService, PEGCalculator, PEGProcessingService
from utils import DataProcessor, TimeRangeParser


class TestMemoryOptimization:
    """메모리 사용량 최적화 테스트"""
    
    def test_analysis_service_memory_profiling(
        self,
        performance_analysis_request,
        mock_performance_database_repository,
        mock_performance_llm_repository,
        memory_tracker,
        performance_logger
    ):
        """AnalysisService 메모리 프로파일링"""
        # 초기 메모리 상태
        initial_memory = memory_tracker.get_memory_usage()
        performance_logger.info(f"초기 메모리: {initial_memory['current_mb']:.2f}MB")
        
        # 가비지 컬렉션 실행
        gc.collect()
        
        # 서비스 구성
        time_parser = TimeRangeParser()
        data_processor = DataProcessor()
        peg_calculator = PEGCalculator()
        
        memory_tracker.update_peak()
        setup_memory = memory_tracker.get_memory_usage()
        performance_logger.info(f"유틸리티 설정 후 메모리: {setup_memory['current_mb']:.2f}MB")
        
        peg_processing_service = PEGProcessingService(
            database_repository=mock_performance_database_repository,
            peg_calculator=peg_calculator
        )
        
        memory_tracker.update_peak()
        peg_service_memory = memory_tracker.get_memory_usage()
        performance_logger.info(f"PEG 서비스 설정 후 메모리: {peg_service_memory['current_mb']:.2f}MB")
        
        llm_analysis_service = LLMAnalysisService(
            llm_repository=mock_performance_llm_repository
        )
        
        memory_tracker.update_peak()
        llm_service_memory = memory_tracker.get_memory_usage()
        performance_logger.info(f"LLM 서비스 설정 후 메모리: {llm_service_memory['current_mb']:.2f}MB")
        
        analysis_service = AnalysisService(
            database_repository=mock_performance_database_repository,
            peg_processing_service=peg_processing_service,
            llm_analysis_service=llm_analysis_service,
            time_parser=time_parser,
            data_processor=data_processor
        )
        
        memory_tracker.update_peak()
        full_setup_memory = memory_tracker.get_memory_usage()
        performance_logger.info(f"전체 서비스 설정 후 메모리: {full_setup_memory['current_mb']:.2f}MB")
        
        # 분석 실행
        result = analysis_service.perform_analysis(performance_analysis_request)
        
        memory_tracker.update_peak()
        analysis_memory = memory_tracker.get_memory_usage()
        performance_logger.info(f"분석 실행 후 메모리: {analysis_memory['current_mb']:.2f}MB")
        
        # 가비지 컬렉션 후 메모리 확인
        gc.collect()
        final_memory = memory_tracker.get_memory_usage()
        
        # 메모리 사용량 분석
        setup_increase = full_setup_memory['current_mb'] - initial_memory['current_mb']
        analysis_increase = analysis_memory['current_mb'] - full_setup_memory['current_mb']
        total_increase = final_memory['current_mb'] - initial_memory['current_mb']
        
        performance_logger.info("=== 메모리 사용량 분석 ===")
        performance_logger.info(f"서비스 설정 증가: {setup_increase:.2f}MB")
        performance_logger.info(f"분석 실행 증가: {analysis_increase:.2f}MB")
        performance_logger.info(f"총 메모리 증가: {total_increase:.2f}MB")
        performance_logger.info(f"피크 메모리: {final_memory['peak_mb']:.2f}MB")
        
        # 결과 검증
        assert isinstance(result, dict)
        assert result.get('status') in ['success', 'completed']
        
        # 메모리 사용량 기준 검증
        assert total_increase < 100, f"총 메모리 증가량이 너무 큽니다: {total_increase:.2f}MB"
        assert final_memory['peak_mb'] < 300, f"피크 메모리가 너무 높습니다: {final_memory['peak_mb']:.2f}MB"
        
        performance_logger.info("✅ AnalysisService 메모리 프로파일링 완료")
    
    def test_dataframe_chunked_processing_optimization(
        self,
        memory_tracker,
        performance_logger
    ):
        """DataFrame 청크 처리 메모리 최적화"""
        # 대용량 DataFrame 생성 (10,000개 레코드)
        large_size = 10000
        
        performance_logger.info("=== DataFrame 청크 처리 최적화 ===")
        performance_logger.info(f"테스트 데이터 크기: {large_size:,}개 레코드")
        
        # 초기 메모리 상태
        memory_tracker.get_memory_usage()
        gc.collect()
        
        # 대용량 DataFrame 생성
        large_df = pd.DataFrame({
            'datetime': pd.date_range('2025-01-01', periods=large_size, freq='1min'),
            'peg_name': np.random.choice(['preamble_count', 'response_count', 'success_count'], large_size),
            'value': np.random.normal(1000, 200, large_size),
            'ne': np.random.choice([f'nvgnb#{10000+i}' for i in range(100)], large_size),
            'cellid': np.random.choice([f'cell_{i:03d}' for i in range(200)], large_size)
        })
        
        memory_tracker.update_peak()
        creation_memory = memory_tracker.get_memory_usage()
        df_memory_mb = large_df.memory_usage(deep=True).sum() / 1024 / 1024
        
        performance_logger.info(f"대용량 DataFrame 생성 후 메모리: {creation_memory['current_mb']:.2f}MB")
        performance_logger.info(f"DataFrame 자체 메모리: {df_memory_mb:.2f}MB")
        
        # 1. 전체 데이터 한번에 처리
        start_time = time.time()
        full_result = large_df.groupby(['peg_name', 'ne']).agg({
            'value': ['mean', 'sum', 'count', 'std']
        }).round(2)
        full_time = time.time() - start_time
        
        memory_tracker.update_peak()
        full_processing_memory = memory_tracker.get_memory_usage()
        
        # 2. 청크 단위 처리 (메모리 효율적)
        chunk_size = 1000
        chunk_results = []
        
        start_time = time.time()
        for i in range(0, len(large_df), chunk_size):
            chunk = large_df.iloc[i:i+chunk_size]
            
            # 청크별 집계
            chunk_agg = chunk.groupby(['peg_name', 'ne']).agg({
                'value': ['sum', 'count']
            })
            chunk_results.append(chunk_agg)
            
            # 중간 메모리 정리
            del chunk
        
        # 청크 결과 병합 및 최종 계산
        if chunk_results:
            combined = pd.concat(chunk_results).groupby(['peg_name', 'ne']).agg({
                ('value', 'sum'): 'sum',
                ('value', 'count'): 'sum'
            })
            combined[('value', 'mean')] = combined[('value', 'sum')] / combined[('value', 'count')]
        
        chunk_time = time.time() - start_time
        
        memory_tracker.update_peak()
        chunk_processing_memory = memory_tracker.get_memory_usage()
        
        # 메모리 정리
        del large_df, full_result, chunk_results
        gc.collect()
        
        final_memory = memory_tracker.get_memory_usage()
        
        # 성능 비교 분석
        performance_logger.info("📊 처리 방식별 성능 비교:")
        performance_logger.info(f"   전체 처리 시간: {full_time*1000:.2f}ms")
        performance_logger.info(f"   청크 처리 시간: {chunk_time*1000:.2f}ms")
        performance_logger.info(f"   청크 크기: {chunk_size:,}개")
        performance_logger.info(f"   청크 수: {len(range(0, large_size, chunk_size))}개")
        
        # 메모리 사용량 비교
        full_memory_increase = full_processing_memory['current_mb'] - creation_memory['current_mb']
        chunk_memory_increase = chunk_processing_memory['current_mb'] - creation_memory['current_mb']
        memory_savings = full_memory_increase - chunk_memory_increase
        
        performance_logger.info("📊 메모리 사용량 비교:")
        performance_logger.info(f"   전체 처리 메모리 증가: {full_memory_increase:.2f}MB")
        performance_logger.info(f"   청크 처리 메모리 증가: {chunk_memory_increase:.2f}MB")
        performance_logger.info(f"   메모리 절약: {memory_savings:.2f}MB")
        performance_logger.info(f"   피크 메모리: {final_memory['peak_mb']:.2f}MB")
        
        # 최적화 효과 검증
        if memory_savings > 0:
            savings_pct = (memory_savings / full_memory_increase) * 100 if full_memory_increase > 0 else 0
            performance_logger.info(f"🚀 청크 처리가 메모리 {savings_pct:.1f}% 절약")
        
        # 성능 기준 검증
        assert chunk_time <= full_time * 2.0, "청크 처리가 너무 느립니다"  # 2배 이내 허용
        assert final_memory['peak_mb'] < 500, f"피크 메모리가 너무 높습니다: {final_memory['peak_mb']:.2f}MB"
        
        performance_logger.info("✅ DataFrame 청크 처리 최적화 완료")
    
    def test_memory_leak_detection(
        self,
        performance_analysis_request,
        mock_performance_database_repository,
        mock_performance_llm_repository,
        memory_tracker,
        performance_logger
    ):
        """메모리 누수 감지 테스트"""
        performance_logger.info("=== 메모리 누수 감지 테스트 ===")
        
        # 초기 메모리 상태
        gc.collect()
        initial_memory = memory_tracker.get_memory_usage()
        performance_logger.info(f"초기 메모리: {initial_memory['current_mb']:.2f}MB")
        
        # 반복적인 분석 실행 (메모리 누수 확인)
        memory_measurements = []
        num_iterations = 5
        
        for i in range(num_iterations):
            # 서비스 구성 (매번 새로 생성)
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
            
            # 분석 실행
            result = analysis_service.perform_analysis(performance_analysis_request)
            
            # 메모리 측정
            memory_tracker.update_peak()
            current_memory = memory_tracker.get_memory_usage()
            memory_measurements.append(current_memory['current_mb'])
            
            # 명시적 정리
            del analysis_service, peg_processing_service, llm_analysis_service
            del time_parser, data_processor, peg_calculator, result
            
            # 가비지 컬렉션
            gc.collect()
            
            performance_logger.info(f"반복 {i+1}: {current_memory['current_mb']:.2f}MB")
        
        # 최종 메모리 상태
        final_memory = memory_tracker.get_memory_usage()
        
        # 메모리 누수 분석
        memory_trend = []
        for i in range(1, len(memory_measurements)):
            trend = memory_measurements[i] - memory_measurements[i-1]
            memory_trend.append(trend)
        
        avg_memory_increase = sum(memory_trend) / len(memory_trend) if memory_trend else 0
        total_memory_increase = final_memory['current_mb'] - initial_memory['current_mb']
        
        performance_logger.info("📊 메모리 누수 분석:")
        performance_logger.info(f"   반복 실행 수: {num_iterations}")
        performance_logger.info(f"   평균 반복당 메모리 증가: {avg_memory_increase:.2f}MB")
        performance_logger.info(f"   총 메모리 증가: {total_memory_increase:.2f}MB")
        performance_logger.info(f"   최종 메모리: {final_memory['current_mb']:.2f}MB")
        performance_logger.info(f"   피크 메모리: {final_memory['peak_mb']:.2f}MB")
        
        # 메모리 누수 검증
        assert avg_memory_increase < 5, f"반복당 메모리 증가량이 너무 큽니다: {avg_memory_increase:.2f}MB"
        assert total_memory_increase < 50, f"총 메모리 증가량이 너무 큽니다: {total_memory_increase:.2f}MB"
        
        # 메모리 사용 패턴 분석
        if avg_memory_increase < 1:
            performance_logger.info("🚀 메모리 누수 없음 - 우수한 메모리 관리")
        elif avg_memory_increase < 3:
            performance_logger.info("✅ 허용 가능한 메모리 증가 - 양호한 메모리 관리")
        else:
            performance_logger.warning("⚠️ 메모리 증가 주의 - 최적화 검토 필요")
        
        performance_logger.info("✅ 메모리 누수 감지 테스트 완료")
    
    def test_large_dataset_memory_efficiency(
        self,
        memory_tracker,
        performance_logger
    ):
        """대용량 데이터셋 메모리 효율성 테스트"""
        performance_logger.info("=== 대용량 데이터셋 메모리 효율성 테스트 ===")
        
        # 초기 메모리 상태
        gc.collect()
        memory_tracker.get_memory_usage()
        
        # 다양한 크기의 데이터셋으로 메모리 사용량 측정
        dataset_sizes = [1000, 5000, 10000, 20000]
        memory_usage_by_size = {}
        
        for size in dataset_sizes:
            gc.collect()  # 이전 테스트 정리
            size_start_memory = memory_tracker.get_memory_usage()
            
            # 데이터셋 생성
            test_df = pd.DataFrame({
                'datetime': pd.date_range('2025-01-01', periods=size, freq='1min'),
                'peg_name': np.random.choice(['preamble_count', 'response_count'], size),
                'value': np.random.normal(1000, 200, size),
                'ne': np.random.choice([f'nvgnb#{10000+i}' for i in range(50)], size),
                'cellid': np.random.choice([f'cell_{i:03d}' for i in range(100)], size)
            })
            
            memory_tracker.update_peak()
            
            # 데이터 타입 최적화
            optimized_df = test_df.copy()
            optimized_df['value'] = pd.to_numeric(optimized_df['value'], downcast='float')
            optimized_df['peg_name'] = optimized_df['peg_name'].astype('category')
            optimized_df['ne'] = optimized_df['ne'].astype('category')
            optimized_df['cellid'] = optimized_df['cellid'].astype('category')
            
            memory_tracker.update_peak()
            
            # 집계 연산 실행
            start_time = time.time()
            result = optimized_df.groupby(['peg_name', 'ne']).agg({
                'value': ['mean', 'count']
            })
            processing_time = time.time() - start_time
            
            memory_tracker.update_peak()
            size_end_memory = memory_tracker.get_memory_usage()
            
            # 메모리 사용량 계산
            original_df_memory = test_df.memory_usage(deep=True).sum() / 1024 / 1024
            optimized_df_memory = optimized_df.memory_usage(deep=True).sum() / 1024 / 1024
            memory_increase = size_end_memory['current_mb'] - size_start_memory['current_mb']
            
            memory_usage_by_size[size] = {
                'original_df_mb': original_df_memory,
                'optimized_df_mb': optimized_df_memory,
                'memory_savings_mb': original_df_memory - optimized_df_memory,
                'memory_savings_pct': ((original_df_memory - optimized_df_memory) / original_df_memory) * 100,
                'processing_time_ms': processing_time * 1000,
                'total_memory_increase_mb': memory_increase
            }
            
            performance_logger.info(f"📊 크기 {size:,}개 레코드:")
            performance_logger.info(f"   원본 DataFrame: {original_df_memory:.2f}MB")
            performance_logger.info(f"   최적화 DataFrame: {optimized_df_memory:.2f}MB")
            performance_logger.info(f"   메모리 절약: {original_df_memory - optimized_df_memory:.2f}MB "
                                  f"({((original_df_memory - optimized_df_memory) / original_df_memory) * 100:.1f}%)")
            performance_logger.info(f"   처리 시간: {processing_time*1000:.2f}ms")
            
            # 메모리 정리
            del test_df, optimized_df, result
            gc.collect()
        
        # 확장성 분석
        performance_logger.info("📊 확장성 분석:")
        for size, metrics in memory_usage_by_size.items():
            mb_per_1k_records = (metrics['optimized_df_mb'] / size) * 1000
            performance_logger.info(f"   {size:,}개: {mb_per_1k_records:.3f}MB/1k레코드")
        
        # 메모리 효율성 검증
        for size, metrics in memory_usage_by_size.items():
            assert metrics['memory_savings_pct'] > 50, f"크기 {size} 메모리 절약 효과가 미미합니다"
            assert metrics['processing_time_ms'] < 1000, f"크기 {size} 처리가 너무 느립니다"
        
        performance_logger.info("✅ 대용량 데이터셋 메모리 효율성 테스트 완료")
    
    def test_garbage_collection_optimization(
        self,
        memory_tracker,
        performance_logger
    ):
        """가비지 컬렉션 최적화 테스트"""
        performance_logger.info("=== 가비지 컬렉션 최적화 테스트 ===")
        
        # 초기 상태
        gc.collect()
        initial_memory = memory_tracker.get_memory_usage()
        initial_gc_stats = gc.get_stats()
        
        performance_logger.info(f"초기 메모리: {initial_memory['current_mb']:.2f}MB")
        performance_logger.info(f"초기 GC 통계: {initial_gc_stats}")
        
        # 메모리 집약적 작업 시뮬레이션
        memory_intensive_objects = []
        
        for i in range(10):
            # 대용량 DataFrame 생성 및 처리
            df = pd.DataFrame({
                'data': np.random.normal(0, 1, 5000),
                'category': np.random.choice(['A', 'B', 'C'], 5000)
            })
            
            # 집계 연산
            result = df.groupby('category').agg({
                'data': ['mean', 'std', 'count']
            })
            
            memory_intensive_objects.append((df, result))
            
            # 5번째마다 중간 정리
            if (i + 1) % 5 == 0:
                memory_tracker.update_peak()
                mid_memory = memory_tracker.get_memory_usage()
                performance_logger.info(f"중간 {i+1}: {mid_memory['current_mb']:.2f}MB")
                
                # 명시적 가비지 컬렉션
                collected = gc.collect()
                performance_logger.info(f"GC 수집 객체: {collected}개")
        
        # 작업 완료 후 메모리 상태
        before_cleanup_memory = memory_tracker.get_memory_usage()
        
        # 명시적 정리
        del memory_intensive_objects
        collected_objects = gc.collect()
        
        # 최종 메모리 상태
        final_memory = memory_tracker.get_memory_usage()
        final_gc_stats = gc.get_stats()
        
        # 가비지 컬렉션 효과 분석
        memory_before_gc = before_cleanup_memory['current_mb']
        memory_after_gc = final_memory['current_mb']
        gc_memory_freed = memory_before_gc - memory_after_gc
        
        performance_logger.info("📊 가비지 컬렉션 효과:")
        performance_logger.info(f"   정리 전 메모리: {memory_before_gc:.2f}MB")
        performance_logger.info(f"   정리 후 메모리: {memory_after_gc:.2f}MB")
        performance_logger.info(f"   해제된 메모리: {gc_memory_freed:.2f}MB")
        performance_logger.info(f"   수집된 객체: {collected_objects}개")
        performance_logger.info(f"   피크 메모리: {final_memory['peak_mb']:.2f}MB")
        
        # GC 통계 비교
        performance_logger.info("📊 GC 통계 변화:")
        for i, (initial, final) in enumerate(zip(initial_gc_stats, final_gc_stats)):
            performance_logger.info(f"   Gen {i}: {initial['collections']} → {final['collections']} "
                                  f"(+{final['collections'] - initial['collections']})")
        
        # 메모리 관리 효율성 검증
        assert gc_memory_freed >= 0, "가비지 컬렉션이 메모리를 해제하지 못했습니다"
        assert final_memory['peak_mb'] < 400, f"피크 메모리가 너무 높습니다: {final_memory['peak_mb']:.2f}MB"
        
        if gc_memory_freed > 10:
            performance_logger.info(f"🚀 효과적인 메모리 정리: {gc_memory_freed:.2f}MB 해제")
        else:
            performance_logger.info("✅ 메모리 사용량이 이미 효율적")
        
        performance_logger.info("✅ 가비지 컬렉션 최적화 테스트 완료")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
