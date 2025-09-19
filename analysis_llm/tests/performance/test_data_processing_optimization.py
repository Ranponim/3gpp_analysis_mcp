"""
Data Processing Algorithm Optimization Tests

DataProcessor와 PEGCalculator의 알고리즘 성능을 최적화합니다.
"""

import os
import sys
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

# 프로젝트 루트를 Python path에 추가
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)

from services import PEGCalculator
from utils import DataProcessor


class TestDataProcessingOptimization:
    """데이터 처리 알고리즘 최적화 테스트"""
    
    def test_peg_calculator_vectorized_operations(
        self,
        benchmark,
        large_peg_dataset,
        performance_logger
    ):
        """PEGCalculator 벡터화 연산 최적화 테스트"""
        peg_calculator = PEGCalculator()
        
        # 기본 집계 벤치마크
        def aggregate_basic():
            return peg_calculator.aggregate_peg_data(
                large_peg_dataset,
                aggregation_method='mean'
            )
        
        # 벤치마크 실행
        result = benchmark.pedantic(aggregate_basic, iterations=10, rounds=3)
        
        # 결과 검증
        assert isinstance(result, dict)
        assert len(result) > 0
        
        performance_logger.info("✅ PEGCalculator 벡터화 연산 벤치마크 완료")
        performance_logger.info("상세 결과는 pytest-benchmark 리포트 참조")
    
    def test_peg_calculator_algorithm_optimization(
        self,
        large_peg_dataset,
        performance_logger
    ):
        """PEG 계산 알고리즘 최적화 분석"""
        peg_calculator = PEGCalculator()
        
        # 다양한 집계 방법 성능 비교
        aggregation_methods = ['sum', 'mean', 'min', 'max', 'count']
        performance_results = {}
        
        for method in aggregation_methods:
            start_time = time.time()
            
            result = peg_calculator.aggregate_peg_data(
                large_peg_dataset,
                aggregation_method=method
            )
            
            end_time = time.time()
            execution_time = end_time - start_time
            
            performance_results[method] = {
                'execution_time_ms': execution_time * 1000,
                'result_count': len(result) if result else 0
            }
            
            performance_logger.info(f"📊 {method} 집계: {execution_time*1000:.2f}ms, 결과: {len(result) if result else 0}개")
        
        # 가장 빠른 집계 방법 식별
        fastest_method = min(performance_results.keys(), 
                           key=lambda k: performance_results[k]['execution_time_ms'])
        
        performance_logger.info("✅ PEG 계산 알고리즘 최적화 분석 완료")
        performance_logger.info(f"🚀 가장 빠른 집계 방법: {fastest_method} "
                              f"({performance_results[fastest_method]['execution_time_ms']:.2f}ms)")
        
        # 성능 기준 검증
        for method, metrics in performance_results.items():
            assert metrics['execution_time_ms'] < 100, f"{method} 집계가 너무 느립니다: {metrics['execution_time_ms']:.2f}ms"
    
    def test_data_processor_pandas_optimization(
        self,
        benchmark,
        large_peg_dataset,
        performance_logger
    ):
        """DataProcessor pandas 최적화 테스트"""
        data_processor = DataProcessor()
        
        # 데이터를 N-1과 N으로 분할
        mid_point = len(large_peg_dataset) // 2
        n1_data = large_peg_dataset.iloc[:mid_point].to_dict('records')
        n_data = large_peg_dataset.iloc[mid_point:].to_dict('records')
        
        # Mock LLM 분석 결과
        mock_llm_results = {
            'summary': '최적화 테스트: 데이터 처리 성능 분석',
            'insights': 'pandas 벡터화 연산을 통한 성능 개선'
        }
        
        def process_data():
            return data_processor.process_data(
                n_minus_1_data=n1_data,
                n_data=n_data,
                llm_analysis_results=mock_llm_results
            )
        
        # 벤치마크 실행
        result = benchmark.pedantic(process_data, iterations=5, rounds=3)
        
        # 결과 검증
        assert isinstance(result, list)
        assert len(result) > 0
        
        performance_logger.info("✅ DataProcessor pandas 최적화 벤치마크 완료")
    
    def test_memory_efficient_dataframe_operations(
        self,
        large_peg_dataset,
        memory_tracker,
        performance_logger
    ):
        """메모리 효율적인 DataFrame 연산 테스트"""
        # 초기 메모리 상태
        initial_memory = memory_tracker.get_memory_usage()
        performance_logger.info(f"초기 메모리: {initial_memory['current_mb']:.2f}MB")
        
        # DataFrame 최적화 기법 테스트
        performance_logger.info("=== DataFrame 메모리 최적화 테스트 ===")
        
        # 1. 데이터 타입 최적화
        optimized_df = large_peg_dataset.copy()
        
        # 메모리 사용량 측정 (최적화 전)
        memory_tracker.update_peak()
        memory_tracker.get_memory_usage()
        
        # 데이터 타입 최적화 적용
        if 'value' in optimized_df.columns:
            # float64 → float32로 다운캐스팅 (메모리 50% 절약)
            optimized_df['value'] = pd.to_numeric(optimized_df['value'], downcast='float')
        
        if 'peg_name' in optimized_df.columns:
            # object → category로 변환 (반복되는 문자열에 효과적)
            optimized_df['peg_name'] = optimized_df['peg_name'].astype('category')
        
        if 'cellid' in optimized_df.columns:
            optimized_df['cellid'] = optimized_df['cellid'].astype('category')
        
        if 'ne' in optimized_df.columns:
            optimized_df['ne'] = optimized_df['ne'].astype('category')
        
        # 메모리 사용량 측정 (최적화 후)
        memory_tracker.update_peak()
        memory_tracker.get_memory_usage()
        
        # 2. 벡터화 연산 테스트
        start_time = time.time()
        
        # 그룹별 집계 (벡터화 연산)
        aggregated_data = optimized_df.groupby(['peg_name']).agg({
            'value': ['mean', 'sum', 'count', 'std']
        }).round(2)
        
        end_time = time.time()
        aggregation_time = end_time - start_time
        
        # 3. 메모리 효율성 검증
        original_memory = large_peg_dataset.memory_usage(deep=True).sum() / 1024 / 1024  # MB
        optimized_memory = optimized_df.memory_usage(deep=True).sum() / 1024 / 1024  # MB
        memory_savings = original_memory - optimized_memory
        memory_savings_pct = (memory_savings / original_memory) * 100
        
        performance_logger.info("📊 DataFrame 메모리 최적화 결과:")
        performance_logger.info(f"   원본 DataFrame: {original_memory:.2f}MB")
        performance_logger.info(f"   최적화 DataFrame: {optimized_memory:.2f}MB")
        performance_logger.info(f"   메모리 절약: {memory_savings:.2f}MB ({memory_savings_pct:.1f}%)")
        performance_logger.info(f"   벡터화 집계 시간: {aggregation_time*1000:.2f}ms")
        
        # 최적화 효과 검증
        assert memory_savings > 0, "메모리 최적화 효과가 없습니다"
        assert memory_savings_pct > 10, f"메모리 절약 효과가 미미합니다: {memory_savings_pct:.1f}%"
        assert aggregation_time < 0.1, f"벡터화 집계가 너무 느립니다: {aggregation_time*1000:.2f}ms"
        
        performance_logger.info("✅ 메모리 효율적인 DataFrame 연산 테스트 완료")
    
    def test_chunked_data_processing(
        self,
        performance_logger
    ):
        """청크 단위 데이터 처리 최적화 테스트"""
        # 대용량 데이터 생성 (10,000개 레코드)
        large_dataset = generate_large_test_dataset(size=10000)
        
        performance_logger.info("=== 청크 단위 데이터 처리 테스트 ===")
        performance_logger.info(f"테스트 데이터 크기: {len(large_dataset)}개 레코드")
        
        # 1. 전체 데이터 한번에 처리
        start_time = time.time()
        full_result = large_dataset.groupby('peg_name').agg({
            'value': ['mean', 'sum', 'count']
        })
        full_processing_time = time.time() - start_time
        
        # 2. 청크 단위 처리
        chunk_size = 1000
        chunk_results = []
        
        start_time = time.time()
        for i in range(0, len(large_dataset), chunk_size):
            chunk = large_dataset.iloc[i:i+chunk_size]
            chunk_result = chunk.groupby('peg_name').agg({
                'value': ['mean', 'sum', 'count']
            })
            chunk_results.append(chunk_result)
        
        # 청크 결과 병합
        if chunk_results:
            # 가중 평균 계산을 위한 병합
            combined_result = pd.concat(chunk_results).groupby('peg_name').agg({
                ('value', 'sum'): 'sum',
                ('value', 'count'): 'sum'
            })
            combined_result[('value', 'mean')] = (
                combined_result[('value', 'sum')] / combined_result[('value', 'count')]
            )
        
        chunk_processing_time = time.time() - start_time
        
        # 결과 비교
        performance_logger.info("📊 처리 방식별 성능 비교:")
        performance_logger.info(f"   전체 처리: {full_processing_time*1000:.2f}ms")
        performance_logger.info(f"   청크 처리: {chunk_processing_time*1000:.2f}ms")
        performance_logger.info(f"   청크 크기: {chunk_size}개")
        performance_logger.info(f"   청크 수: {len(chunk_results)}개")
        
        # 성능 개선 여부 확인
        if chunk_processing_time < full_processing_time:
            improvement = ((full_processing_time - chunk_processing_time) / full_processing_time) * 100
            performance_logger.info(f"🚀 청크 처리가 {improvement:.1f}% 더 빠름")
        else:
            performance_logger.info("📝 전체 처리가 더 효율적 (작은 데이터셋)")
        
        performance_logger.info("✅ 청크 단위 데이터 처리 테스트 완료")
    
    def test_optimized_change_rate_calculation(
        self,
        benchmark,
        large_peg_dataset,
        performance_logger
    ):
        """최적화된 변화율 계산 테스트"""
        DataProcessor()
        
        # 데이터를 N-1과 N으로 분할
        mid_point = len(large_peg_dataset) // 2
        n1_data = large_peg_dataset.iloc[:mid_point].to_dict('records')
        n_data = large_peg_dataset.iloc[mid_point:].to_dict('records')
        
        # 변화율 계산 벤치마크
        def calculate_change_rates():
            # DataProcessor의 _merge_peg_data와 _calculate_change_rates 시뮬레이션
            n1_dict = {}
            n_dict = {}
            
            # N-1 데이터 그룹화 (벡터화)
            n1_df = pd.DataFrame(n1_data)
            if len(n1_df) > 0:
                n1_grouped = n1_df.groupby('peg_name')['value'].mean()
                n1_dict = n1_grouped.to_dict()
            
            # N 데이터 그룹화 (벡터화)
            n_df = pd.DataFrame(n_data)
            if len(n_df) > 0:
                n_grouped = n_df.groupby('peg_name')['value'].mean()
                n_dict = n_grouped.to_dict()
            
            # 변화율 계산 (벡터화)
            change_rates = {}
            for peg_name in set(list(n1_dict.keys()) + list(n_dict.keys())):
                n1_value = n1_dict.get(peg_name, 0)
                n_value = n_dict.get(peg_name, 0)
                
                if n1_value != 0:
                    change_rate = ((n_value - n1_value) / n1_value) * 100
                else:
                    change_rate = 0.0 if n_value == 0 else float('inf')
                
                change_rates[peg_name] = round(change_rate, 2)
            
            return change_rates
        
        # 벤치마크 실행
        result = benchmark.pedantic(calculate_change_rates, iterations=10, rounds=3)
        
        # 결과 검증
        assert isinstance(result, dict)
        assert len(result) > 0
        
        performance_logger.info("✅ 최적화된 변화율 계산 벤치마크 완료")
    
    def test_dataframe_memory_optimization(
        self,
        large_peg_dataset,
        memory_tracker,
        performance_logger
    ):
        """DataFrame 메모리 최적화 테스트"""
        # 초기 메모리 상태
        initial_memory = memory_tracker.get_memory_usage()
        
        performance_logger.info("=== DataFrame 메모리 최적화 테스트 ===")
        performance_logger.info(f"초기 메모리: {initial_memory['current_mb']:.2f}MB")
        
        # 원본 DataFrame 메모리 사용량
        original_memory = large_peg_dataset.memory_usage(deep=True).sum() / 1024 / 1024
        performance_logger.info(f"원본 DataFrame: {original_memory:.2f}MB")
        
        # 1. 데이터 타입 최적화
        optimized_df = large_peg_dataset.copy()
        
        # float64 → float32 다운캐스팅
        if 'value' in optimized_df.columns:
            optimized_df['value'] = pd.to_numeric(optimized_df['value'], downcast='float')
        
        # 반복되는 문자열을 category로 변환
        categorical_columns = ['peg_name', 'cellid', 'ne', 'host']
        for col in categorical_columns:
            if col in optimized_df.columns:
                optimized_df[col] = optimized_df[col].astype('category')
        
        # 최적화된 메모리 사용량
        optimized_memory = optimized_df.memory_usage(deep=True).sum() / 1024 / 1024
        memory_savings = original_memory - optimized_memory
        memory_savings_pct = (memory_savings / original_memory) * 100
        
        performance_logger.info("📊 메모리 최적화 결과:")
        performance_logger.info(f"   최적화 DataFrame: {optimized_memory:.2f}MB")
        performance_logger.info(f"   메모리 절약: {memory_savings:.2f}MB ({memory_savings_pct:.1f}%)")
        
        # 2. 연산 성능 비교
        # 원본 DataFrame 연산
        start_time = time.time()
        large_peg_dataset.groupby('peg_name')['value'].mean()
        original_time = time.time() - start_time
        
        # 최적화된 DataFrame 연산
        start_time = time.time()
        optimized_df.groupby('peg_name')['value'].mean()
        optimized_time = time.time() - start_time
        
        # 성능 비교
        if optimized_time < original_time:
            speed_improvement = ((original_time - optimized_time) / original_time) * 100
            performance_logger.info(f"🚀 연산 속도 개선: {speed_improvement:.1f}%")
        else:
            performance_logger.info("📝 연산 속도는 유사함")
        
        performance_logger.info(f"   원본 연산 시간: {original_time*1000:.2f}ms")
        performance_logger.info(f"   최적화 연산 시간: {optimized_time*1000:.2f}ms")
        
        # 최종 메모리 상태
        final_memory = memory_tracker.get_memory_usage()
        performance_logger.info(f"최종 메모리: {final_memory['current_mb']:.2f}MB")
        
        # 최적화 효과 검증
        assert memory_savings_pct > 20, f"메모리 절약 효과가 미미합니다: {memory_savings_pct:.1f}%"
        # 메모리 최적화가 주 목적이므로 약간의 성능 저하는 허용 (20% 이내)
        assert optimized_time <= original_time * 1.2, f"최적화 후 성능이 20% 이상 저하되었습니다: {optimized_time*1000:.2f}ms vs {original_time*1000:.2f}ms"
        
        performance_logger.info("✅ DataFrame 메모리 최적화 테스트 완료")


def generate_large_test_dataset(size: int = 10000) -> pd.DataFrame:
    """대용량 테스트 데이터셋 생성"""
    np.random.seed(42)  # 재현 가능한 결과
    
    base_time = datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc)
    
    data = {
        'datetime': [base_time + pd.Timedelta(minutes=i) for i in range(size)],
        'peg_name': np.random.choice([
            'preamble_count', 'response_count', 'success_count', 
            'failure_count', 'handover_count'
        ], size),
        'value': np.random.normal(1000, 200, size),
        'ne': np.random.choice([f'nvgnb#{10000+i}' for i in range(20)], size),
        'cellid': np.random.choice([f'cell_{i:03d}' for i in range(50)], size),
        'host': np.random.choice([f'192.168.1.{i}' for i in range(1, 21)], size)
    }
    
    return pd.DataFrame(data)


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--benchmark-only'])
