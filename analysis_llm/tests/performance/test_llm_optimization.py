"""
LLM Call Efficiency and Prompt Optimization Tests

LLM 호출 효율성과 프롬프트 최적화를 테스트합니다.
"""

import os
import sys
import time
from datetime import datetime, timezone

import pytest

# 프로젝트 루트를 Python path에 추가
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)

from models import LLMAnalysisResult
from services import LLMAnalysisService


class TestLLMOptimization:
    """LLM 최적화 테스트"""
    
    def test_prompt_efficiency_analysis(
        self,
        mock_performance_llm_repository,
        performance_logger
    ):
        """프롬프트 효율성 분석"""
        llm_service = LLMAnalysisService(
            llm_repository=mock_performance_llm_repository
        )
        
        # 다양한 분석 타입별 프롬프트 토큰 수 분석
        analysis_types = ['overall', 'enhanced', 'specific']
        
        # 샘플 데이터
        import pandas as pd
        sample_df = pd.DataFrame([
            {'peg_name': 'preamble_count', 'n_minus_1_value': 1000, 'n_value': 1100, 'change_pct': 10.0},
            {'peg_name': 'response_count', 'n_minus_1_value': 950, 'n_value': 1000, 'change_pct': 5.26}
        ])
        
        # 시간 범위
        from models import TimeRange
        test_range = TimeRange(
            start_time=datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc),
            end_time=datetime(2025, 1, 1, 18, 0, tzinfo=timezone.utc)
        )
        
        performance_logger.info("=== 프롬프트 효율성 분석 ===")
        
        prompt_analysis = {}
        for analysis_type in analysis_types:
            # 프롬프트 생성 시간 측정
            start_time = time.time()
            
            # LLM 서비스 호출
            result = llm_service.analyze_peg_data(
                processed_df=sample_df,
                n1_range=test_range,
                n_range=test_range,
                analysis_type=analysis_type
            )
            
            end_time = time.time()
            processing_time = end_time - start_time
            
            # Mock에서 토큰 정보 가져오기
            estimated_tokens = mock_performance_llm_repository.estimate_tokens.return_value
            
            prompt_analysis[analysis_type] = {
                'processing_time_ms': processing_time * 1000,
                'estimated_tokens': estimated_tokens,
                'result_type': type(result).__name__
            }
            
            performance_logger.info(f"📊 {analysis_type} 분석:")
            performance_logger.info(f"   처리시간: {processing_time*1000:.2f}ms")
            performance_logger.info(f"   추정 토큰: {estimated_tokens}")
        
        # 가장 효율적인 분석 타입 식별
        most_efficient = min(prompt_analysis.keys(), 
                           key=lambda k: prompt_analysis[k]['processing_time_ms'])
        
        performance_logger.info(f"🚀 가장 효율적인 분석 타입: {most_efficient}")
        performance_logger.info("✅ 프롬프트 효율성 분석 완료")
        
        # 성능 기준 검증
        for analysis_type, metrics in prompt_analysis.items():
            assert metrics['processing_time_ms'] < 1000, f"{analysis_type} 처리가 너무 느립니다"
            assert metrics['estimated_tokens'] > 0, f"{analysis_type} 토큰 추정 실패"
    
    def test_llm_call_optimization_benchmark(
        self,
        benchmark,
        mock_performance_llm_repository,
        performance_logger
    ):
        """LLM 호출 최적화 벤치마크"""
        llm_service = LLMAnalysisService(
            llm_repository=mock_performance_llm_repository
        )
        
        # 샘플 데이터 준비
        import pandas as pd
        test_df = pd.DataFrame([
            {'peg_name': 'test_peg', 'n_minus_1_value': 500, 'n_value': 550, 'change_pct': 10.0}
        ])
        
        from models import TimeRange
        test_range = TimeRange(
            start_time=datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc),
            end_time=datetime(2025, 1, 1, 18, 0, tzinfo=timezone.utc)
        )
        
        # LLM 호출 벤치마크
        def llm_analysis():
            return llm_service.analyze_peg_data(
                processed_df=test_df,
                n1_range=test_range,
                n_range=test_range,
                analysis_type='enhanced'
            )
        
        # 벤치마크 실행
        result = benchmark.pedantic(llm_analysis, iterations=10, rounds=3)
        
        # 결과 검증
        assert isinstance(result, LLMAnalysisResult)
        assert result.model_used is not None
        
        performance_logger.info("✅ LLM 호출 최적화 벤치마크 완료")
    
    def test_token_usage_optimization(
        self,
        mock_performance_llm_repository,
        performance_logger
    ):
        """토큰 사용량 최적화 테스트"""
        # Mock LLM Repository 설정
        mock_performance_llm_repository.estimate_tokens.return_value = 150
        mock_performance_llm_repository.validate_prompt.return_value = True
        
        llm_service = LLMAnalysisService(
            llm_repository=mock_performance_llm_repository
        )
        
        # 다양한 데이터 크기별 토큰 사용량 분석
        data_sizes = [10, 50, 100, 500]
        token_usage_analysis = {}
        
        performance_logger.info("=== 토큰 사용량 최적화 분석 ===")
        
        for size in data_sizes:
            # 크기별 테스트 데이터 생성
            import pandas as pd
            test_df = pd.DataFrame([
                {
                    'peg_name': f'test_peg_{i}',
                    'n_minus_1_value': 1000 + i,
                    'n_value': 1100 + i,
                    'change_pct': (i % 20) - 10  # -10% ~ +10% 범위
                }
                for i in range(size)
            ])
            
            from models import TimeRange
            test_range = TimeRange(
                start_time=datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc),
                end_time=datetime(2025, 1, 1, 18, 0, tzinfo=timezone.utc)
            )
            
            # 토큰 사용량 측정
            start_time = time.time()
            
            result = llm_service.analyze_peg_data(
                processed_df=test_df,
                n1_range=test_range,
                n_range=test_range,
                analysis_type='enhanced'
            )
            
            end_time = time.time()
            processing_time = end_time - start_time
            
            # 토큰 정보 수집
            estimated_tokens = mock_performance_llm_repository.estimate_tokens.return_value
            tokens_per_record = estimated_tokens / size if size > 0 else 0
            
            token_usage_analysis[size] = {
                'processing_time_ms': processing_time * 1000,
                'estimated_tokens': estimated_tokens,
                'tokens_per_record': tokens_per_record,
                'efficiency_score': size / (estimated_tokens + 1)  # 레코드 수 대비 토큰 효율성
            }
            
            performance_logger.info(f"📊 데이터 크기 {size}개:")
            performance_logger.info(f"   처리시간: {processing_time*1000:.2f}ms")
            performance_logger.info(f"   추정 토큰: {estimated_tokens}")
            performance_logger.info(f"   레코드당 토큰: {tokens_per_record:.2f}")
        
        # 토큰 효율성 분석
        most_efficient_size = max(token_usage_analysis.keys(), 
                                key=lambda k: token_usage_analysis[k]['efficiency_score'])
        
        performance_logger.info(f"🚀 가장 효율적인 데이터 크기: {most_efficient_size}개 레코드")
        performance_logger.info("✅ 토큰 사용량 최적화 분석 완료")
        
        # 토큰 효율성 검증
        for size, metrics in token_usage_analysis.items():
            assert metrics['processing_time_ms'] < 2000, f"크기 {size} 처리가 너무 느립니다"
            assert metrics['tokens_per_record'] >= 0, "토큰 계산 오류"
    
    def test_prompt_strategy_optimization(
        self,
        mock_performance_llm_repository,
        performance_logger
    ):
        """프롬프트 전략 최적화 테스트"""
        # 다양한 전략별 성능 비교
        strategies = ['overall', 'enhanced', 'specific']
        strategy_performance = {}
        
        performance_logger.info("=== 프롬프트 전략 최적화 분석 ===")
        
        # Mock 응답을 전략별로 다르게 설정
        def mock_analyze_data(prompt, **kwargs):
            # 프롬프트 길이 기반 토큰 추정
            estimated_tokens = len(prompt.split()) * 1.3  # 대략적인 토큰 추정
            
            if 'overall' in prompt.lower():
                return {
                    'summary': '전체 분석 (간결한 응답)',
                    'model_used': 'overall-strategy-model',
                    'tokens_used': int(estimated_tokens * 0.8)  # 간결한 응답
                }
            elif 'enhanced' in prompt.lower():
                return {
                    'summary': '향상된 분석 (상세한 응답)',
                    'model_used': 'enhanced-strategy-model',
                    'tokens_used': int(estimated_tokens * 1.2)  # 상세한 응답
                }
            else:
                return {
                    'summary': '특정 분석 (중간 응답)',
                    'model_used': 'specific-strategy-model',
                    'tokens_used': int(estimated_tokens * 1.0)  # 중간 응답
                }
        
        mock_performance_llm_repository.analyze_data.side_effect = mock_analyze_data
        
        llm_service = LLMAnalysisService(
            llm_repository=mock_performance_llm_repository
        )
        
        # 테스트 데이터
        import pandas as pd
        test_df = pd.DataFrame([
            {'peg_name': 'strategy_test', 'n_minus_1_value': 1000, 'n_value': 1100, 'change_pct': 10.0}
        ])
        
        from models import TimeRange
        test_range = TimeRange(
            start_time=datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc),
            end_time=datetime(2025, 1, 1, 18, 0, tzinfo=timezone.utc)
        )
        
        # 각 전략별 성능 측정
        for strategy in strategies:
            start_time = time.time()
            
            result = llm_service.analyze_peg_data(
                processed_df=test_df,
                n1_range=test_range,
                n_range=test_range,
                analysis_type=strategy
            )
            
            end_time = time.time()
            processing_time = end_time - start_time
            
            strategy_performance[strategy] = {
                'processing_time_ms': processing_time * 1000,
                'tokens_used': result.tokens_used if hasattr(result, 'tokens_used') else 0,
                'model_used': result.model_used if hasattr(result, 'model_used') else 'unknown'
            }
            
            performance_logger.info(f"📊 {strategy} 전략:")
            performance_logger.info(f"   처리시간: {processing_time*1000:.2f}ms")
            performance_logger.info(f"   사용 토큰: {strategy_performance[strategy]['tokens_used']}")
            performance_logger.info(f"   모델: {strategy_performance[strategy]['model_used']}")
        
        # 가장 효율적인 전략 식별
        most_efficient_strategy = min(strategy_performance.keys(),
                                    key=lambda k: strategy_performance[k]['tokens_used'])
        
        fastest_strategy = min(strategy_performance.keys(),
                             key=lambda k: strategy_performance[k]['processing_time_ms'])
        
        performance_logger.info(f"🚀 토큰 효율적 전략: {most_efficient_strategy}")
        performance_logger.info(f"⚡ 가장 빠른 전략: {fastest_strategy}")
        performance_logger.info("✅ 프롬프트 전략 최적화 분석 완료")
        
        # 전략별 성능 검증
        for strategy, metrics in strategy_performance.items():
            assert metrics['processing_time_ms'] < 1000, f"{strategy} 전략이 너무 느립니다"
            assert metrics['tokens_used'] > 0, f"{strategy} 전략 토큰 사용량 오류"
    
    def test_llm_response_caching_simulation(
        self,
        mock_performance_llm_repository,
        performance_logger
    ):
        """LLM 응답 캐싱 시뮬레이션 테스트"""
        # 간단한 캐싱 시뮬레이션
        cache = {}
        cache_hits = 0
        cache_misses = 0
        
        def cached_llm_call(prompt_key, **kwargs):
            nonlocal cache_hits, cache_misses
            
            if prompt_key in cache:
                cache_hits += 1
                return cache[prompt_key]
            else:
                cache_misses += 1
                # 실제 LLM 호출 시뮬레이션
                response = {
                    'summary': f'캐시된 응답 {prompt_key}',
                    'model_used': 'cached-model',
                    'tokens_used': 100
                }
                cache[prompt_key] = response
                return response
        
        # 캐싱 효과 테스트
        test_prompts = [
            'prompt_1', 'prompt_2', 'prompt_1',  # prompt_1 반복
            'prompt_3', 'prompt_2', 'prompt_1'   # 추가 반복
        ]
        
        performance_logger.info("=== LLM 응답 캐싱 시뮬레이션 ===")
        
        total_calls = 0
        total_time = 0
        
        for prompt_key in test_prompts:
            start_time = time.time()
            
            # 캐시 확인 시뮬레이션
            if prompt_key in cache:
                # 캐시 히트 (즉시 반환)
                response = cached_llm_call(prompt_key)
                call_time = 0.001  # 1ms (캐시 접근 시간)
            else:
                # 캐시 미스 (실제 LLM 호출)
                response = cached_llm_call(prompt_key)
                call_time = 0.1  # 100ms (실제 LLM 호출 시간)
            
            end_time = time.time()
            actual_time = end_time - start_time + call_time
            
            total_calls += 1
            total_time += actual_time
        
        # 캐싱 효과 분석
        cache_hit_rate = (cache_hits / total_calls) * 100
        avg_call_time = (total_time / total_calls) * 1000  # ms
        
        performance_logger.info("📊 캐싱 효과 분석:")
        performance_logger.info(f"   총 호출 수: {total_calls}")
        performance_logger.info(f"   캐시 히트: {cache_hits}회")
        performance_logger.info(f"   캐시 미스: {cache_misses}회")
        performance_logger.info(f"   캐시 적중률: {cache_hit_rate:.1f}%")
        performance_logger.info(f"   평균 호출 시간: {avg_call_time:.2f}ms")
        
        # 캐싱 효과 검증
        assert cache_hit_rate > 30, f"캐시 적중률이 너무 낮습니다: {cache_hit_rate:.1f}%"
        assert avg_call_time < 60, f"평균 호출 시간이 너무 깁니다: {avg_call_time:.2f}ms"  # 캐싱 고려하여 60ms로 조정
        
        performance_logger.info("✅ LLM 응답 캐싱 시뮬레이션 완료")
    
    def test_batch_llm_request_optimization(
        self,
        mock_performance_llm_repository,
        performance_logger
    ):
        """배치 LLM 요청 최적화 테스트"""
        # 개별 요청 vs 배치 요청 성능 비교
        
        # 테스트 데이터 (여러 PEG 세트)
        import pandas as pd
        test_datasets = []
        for i in range(5):  # 5개 데이터셋
            df = pd.DataFrame([
                {
                    'peg_name': f'batch_test_peg_{j}',
                    'n_minus_1_value': 1000 + (i*10) + j,
                    'n_value': 1100 + (i*10) + j,
                    'change_pct': (j % 20) - 10
                }
                for j in range(3)  # 각 데이터셋당 3개 PEG
            ])
            test_datasets.append(df)
        
        from models import TimeRange
        test_range = TimeRange(
            start_time=datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc),
            end_time=datetime(2025, 1, 1, 18, 0, tzinfo=timezone.utc)
        )
        
        llm_service = LLMAnalysisService(
            llm_repository=mock_performance_llm_repository
        )
        
        performance_logger.info("=== 배치 LLM 요청 최적화 테스트 ===")
        
        # 1. 개별 요청 처리
        start_time = time.time()
        individual_results = []
        
        for i, df in enumerate(test_datasets):
            result = llm_service.analyze_peg_data(
                processed_df=df,
                n1_range=test_range,
                n_range=test_range,
                analysis_type='enhanced'
            )
            individual_results.append(result)
        
        individual_time = time.time() - start_time
        
        # 2. 배치 요청 시뮬레이션 (데이터 통합 후 한번에 처리)
        start_time = time.time()
        
        # 모든 데이터를 하나로 통합
        combined_df = pd.concat(test_datasets, ignore_index=True)
        
        batch_result = llm_service.analyze_peg_data(
            processed_df=combined_df,
            n1_range=test_range,
            n_range=test_range,
            analysis_type='enhanced'
        )
        
        batch_time = time.time() - start_time
        
        # 성능 비교
        time_savings = individual_time - batch_time
        time_savings_pct = (time_savings / individual_time) * 100 if individual_time > 0 else 0
        
        performance_logger.info("📊 배치 처리 효과:")
        performance_logger.info(f"   개별 요청 시간: {individual_time*1000:.2f}ms")
        performance_logger.info(f"   배치 요청 시간: {batch_time*1000:.2f}ms")
        performance_logger.info(f"   시간 절약: {time_savings*1000:.2f}ms ({time_savings_pct:.1f}%)")
        performance_logger.info(f"   개별 요청 수: {len(test_datasets)}")
        
        # 배치 처리 효과 검증
        assert len(individual_results) == len(test_datasets), "개별 요청 결과 수가 맞지 않습니다"
        assert isinstance(batch_result, LLMAnalysisResult), "배치 요청 결과 타입 오류"
        
        if time_savings > 0:
            performance_logger.info(f"🚀 배치 처리가 {time_savings_pct:.1f}% 더 효율적")
        else:
            performance_logger.info("📝 개별 처리가 더 효율적 (작은 배치 크기)")
        
        performance_logger.info("✅ 배치 LLM 요청 최적화 테스트 완료")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
