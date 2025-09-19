"""
DataProcessor 단위 테스트

데이터 변환 및 정규화 로직의 모든 기능을 테스트합니다.
"""

import os
import sys
import unittest

import pandas as pd

# 프로젝트 루트를 Python path에 추가
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)

from models import LLMAnalysisResult
from utils import AnalyzedPEGResult, DataProcessingError, DataProcessor


class TestAnalyzedPEGResult(unittest.TestCase):
    """AnalyzedPEGResult 데이터클래스 테스트"""
    
    def test_basic_creation(self):
        """기본 생성 테스트"""
        result = AnalyzedPEGResult(
            peg_name="test_peg",
            n_minus_1_value=100.0,
            n_value=110.0,
            percentage_change=10.0,
            is_derived=False
        )
        
        # 기본 속성 확인
        self.assertEqual(result.peg_name, "test_peg")
        self.assertEqual(result.n_minus_1_value, 100.0)
        self.assertEqual(result.n_value, 110.0)
        self.assertEqual(result.percentage_change, 10.0)
        self.assertFalse(result.is_derived)
    
    def test_derived_peg_creation(self):
        """파생 PEG 생성 테스트"""
        derived_result = AnalyzedPEGResult(
            peg_name="success_rate",
            n_minus_1_value=85.5,
            n_value=90.2,
            percentage_change=5.5,
            is_derived=True
        )
        
        self.assertTrue(derived_result.is_derived)
        self.assertEqual(derived_result.peg_name, "success_rate")
    
    def test_to_dict_conversion(self):
        """딕셔너리 변환 테스트"""
        result = AnalyzedPEGResult(
            peg_name="conversion_test",
            n_minus_1_value=50.0,
            n_value=60.0,
            percentage_change=20.0,
            is_derived=True
        )
        
        result_dict = result.to_dict()
        
        # 필수 키 확인
        expected_keys = {
            'peg_name', 'n_minus_1_value', 'n_value', 
            'percentage_change', 'is_derived'
        }
        self.assertEqual(set(result_dict.keys()), expected_keys)
        
        # 값 확인
        self.assertEqual(result_dict['peg_name'], "conversion_test")
        self.assertEqual(result_dict['percentage_change'], 20.0)
        self.assertTrue(result_dict['is_derived'])


class TestDataProcessor(unittest.TestCase):
    """DataProcessor 단위 테스트"""
    
    def setUp(self):
        """테스트 설정"""
        self.processor = DataProcessor()
    
    def test_initialization(self):
        """DataProcessor 초기화 테스트"""
        self.assertIsInstance(self.processor, DataProcessor)
        
        # 로거 확인
        self.assertIsNotNone(self.processor.logger)
        self.assertEqual(self.processor.logger.name, 'utils.data_processor.DataProcessor')
    
    def test_dataframe_to_dict_conversion(self):
        """DataFrame을 딕셔너리로 변환 테스트"""
        # 테스트 DataFrame 생성
        test_df = pd.DataFrame([
            {'peg_name': 'preamble_count', 'avg_value': 1000.0, 'period': 'N-1'},
            {'peg_name': 'response_count', 'avg_value': 950.0, 'period': 'N-1'},
            {'peg_name': 'preamble_count', 'avg_value': 1100.0, 'period': 'N'},
            {'peg_name': 'response_count', 'avg_value': 1000.0, 'period': 'N'}
        ])
        
        # 변환 실행
        result_dict = self.processor._dataframe_to_dict(test_df)
        
        # 결과 검증
        self.assertIsInstance(result_dict, dict)
        self.assertIn('N-1', result_dict)
        self.assertIn('N', result_dict)
        
        # N-1 데이터 확인
        n1_data = result_dict['N-1']
        self.assertEqual(len(n1_data), 2)
        self.assertEqual(n1_data[0]['peg_name'], 'preamble_count')
        self.assertEqual(n1_data[0]['avg_value'], 1000.0)
    
    def test_merge_peg_data(self):
        """PEG 데이터 병합 테스트"""
        # 테스트 데이터 준비
        n1_data = [
            {'peg_name': 'preamble_count', 'avg_value': 1000.0},
            {'peg_name': 'response_count', 'avg_value': 950.0}
        ]
        
        n_data = [
            {'peg_name': 'preamble_count', 'avg_value': 1100.0},
            {'peg_name': 'response_count', 'avg_value': 1000.0}
        ]
        
        # 병합 실행
        merged_data = self.processor._merge_peg_data(n1_data, n_data)
        
        # 결과 검증
        self.assertIsInstance(merged_data, list)
        self.assertEqual(len(merged_data), 2)
        
        # 첫 번째 PEG 확인
        preamble_data = next(item for item in merged_data if item['peg_name'] == 'preamble_count')
        self.assertEqual(preamble_data['n_minus_1_value'], 1000.0)
        self.assertEqual(preamble_data['n_value'], 1100.0)
        
        # 두 번째 PEG 확인
        response_data = next(item for item in merged_data if item['peg_name'] == 'response_count')
        self.assertEqual(response_data['n_minus_1_value'], 950.0)
        self.assertEqual(response_data['n_value'], 1000.0)
    
    def test_calculate_change_rates(self):
        """변화율 계산 테스트"""
        # 테스트 데이터 준비
        merged_data = [
            {
                'peg_name': 'preamble_count',
                'n_minus_1_value': 1000.0,
                'n_value': 1100.0
            },
            {
                'peg_name': 'response_count',
                'n_minus_1_value': 950.0,
                'n_value': 1000.0
            },
            {
                'peg_name': 'zero_division_test',
                'n_minus_1_value': 0.0,
                'n_value': 100.0
            }
        ]
        
        # 변화율 계산 실행
        result_with_changes = self.processor._calculate_change_rates(merged_data)
        
        # 결과 검증
        self.assertEqual(len(result_with_changes), 3)
        
        # 정상 변화율 확인
        preamble_item = next(item for item in result_with_changes if item['peg_name'] == 'preamble_count')
        self.assertAlmostEqual(preamble_item['percentage_change'], 10.0, places=2)
        
        response_item = next(item for item in result_with_changes if item['peg_name'] == 'response_count')
        self.assertAlmostEqual(response_item['percentage_change'], 5.26, places=2)
        
        # 0으로 나누기 처리 확인
        zero_div_item = next(item for item in result_with_changes if item['peg_name'] == 'zero_division_test')
        self.assertEqual(zero_div_item['percentage_change'], 0.0)  # 안전한 기본값
    
    def test_integrate_llm_analysis(self):
        """LLM 분석 결과 통합 테스트"""
        # 테스트 데이터 준비
        peg_data = [
            {
                'peg_name': 'preamble_count',
                'n_minus_1_value': 1000.0,
                'n_value': 1100.0,
                'percentage_change': 10.0
            }
        ]
        
        # Mock LLM 분석 결과
        llm_result = LLMAnalysisResult(
            integrated_analysis="성능이 개선되었습니다",
            specific_peg_analysis="Preamble count가 증가했습니다",
            recommendations="현재 설정을 유지하세요",
            confidence_score=0.85,
            model_used="test-model",
            tokens_used=150
        )
        
        # 통합 실행
        integrated_data = self.processor._integrate_llm_analysis(peg_data, llm_result)
        
        # 결과 검증
        self.assertIsInstance(integrated_data, dict)
        self.assertIn('peg_data', integrated_data)
        self.assertIn('llm_analysis', integrated_data)
        
        # PEG 데이터 확인
        self.assertEqual(len(integrated_data['peg_data']), 1)
        self.assertEqual(integrated_data['peg_data'][0]['peg_name'], 'preamble_count')
        
        # LLM 분석 확인
        llm_data = integrated_data['llm_analysis']
        self.assertEqual(llm_data['integrated_analysis'], "성능이 개선되었습니다")
        self.assertEqual(llm_data['confidence_score'], 0.85)
    
    def test_process_data_full_workflow(self):
        """전체 데이터 처리 워크플로우 테스트"""
        # Mock DataFrame 생성
        test_df = pd.DataFrame([
            {'peg_name': 'preamble_count', 'avg_value': 1000.0, 'period': 'N-1'},
            {'peg_name': 'response_count', 'avg_value': 950.0, 'period': 'N-1'},
            {'peg_name': 'preamble_count', 'avg_value': 1100.0, 'period': 'N'},
            {'peg_name': 'response_count', 'avg_value': 1000.0, 'period': 'N'}
        ])
        
        # Mock LLM 분석 결과
        mock_llm_result = LLMAnalysisResult(
            integrated_analysis="전체 성능 향상",
            specific_peg_analysis="모든 PEG가 개선됨",
            recommendations="최적화 완료",
            confidence_score=0.9,
            model_used="workflow-test-model",
            tokens_used=200
        )
        
        # 전체 처리 실행
        result = self.processor.process_data(test_df, mock_llm_result)
        
        # 결과 검증
        self.assertIsInstance(result, dict)
        
        # 필수 키 확인
        expected_keys = {'peg_data', 'llm_analysis', 'summary_statistics'}
        self.assertTrue(expected_keys.issubset(result.keys()))
        
        # PEG 데이터 확인
        peg_data = result['peg_data']
        self.assertEqual(len(peg_data), 2)
        
        # 변화율이 계산되었는지 확인
        for peg in peg_data:
            self.assertIn('percentage_change', peg)
            self.assertIsInstance(peg['percentage_change'], (int, float))
        
        # LLM 분석 확인
        llm_analysis = result['llm_analysis']
        self.assertEqual(llm_analysis['model_used'], "workflow-test-model")
        
        # 요약 통계 확인
        summary_stats = result['summary_statistics']
        self.assertIn('total_pegs', summary_stats)
        self.assertIn('avg_change_rate', summary_stats)
    
    def test_create_summary_statistics(self):
        """요약 통계 생성 테스트"""
        # 테스트 PEG 데이터
        peg_data = [
            {'peg_name': 'peg1', 'percentage_change': 10.0, 'is_derived': False},
            {'peg_name': 'peg2', 'percentage_change': 5.0, 'is_derived': False},
            {'peg_name': 'derived_peg', 'percentage_change': 15.0, 'is_derived': True}
        ]
        
        # 요약 통계 생성
        summary = self.processor.create_summary_statistics(peg_data)
        
        # 결과 검증
        self.assertIsInstance(summary, dict)
        
        # 기본 통계 확인
        self.assertEqual(summary['total_pegs'], 3)
        self.assertEqual(summary['derived_pegs'], 1)
        self.assertEqual(summary['base_pegs'], 2)
        
        # 변화율 통계 확인
        self.assertAlmostEqual(summary['avg_change_rate'], 10.0, places=1)  # (10+5+15)/3
        self.assertEqual(summary['max_change_rate'], 15.0)
        self.assertEqual(summary['min_change_rate'], 5.0)
    
    def test_empty_data_handling(self):
        """빈 데이터 처리 테스트"""
        empty_df = pd.DataFrame()
        
        mock_llm_result = LLMAnalysisResult(
            integrated_analysis="빈 데이터",
            specific_peg_analysis="데이터 없음",
            recommendations="데이터 확인 필요",
            confidence_score=0.0,
            model_used="empty-test-model",
            tokens_used=0
        )
        
        # 빈 데이터 처리
        result = self.processor.process_data(empty_df, mock_llm_result)
        
        # 결과 검증
        self.assertIsInstance(result, dict)
        self.assertEqual(len(result['peg_data']), 0)
        self.assertEqual(result['summary_statistics']['total_pegs'], 0)
    
    def test_error_handling(self):
        """오류 처리 테스트"""
        # 잘못된 DataFrame 형식
        invalid_df = "not a dataframe"
        
        mock_llm_result = LLMAnalysisResult(
            integrated_analysis="오류 테스트",
            specific_peg_analysis="",
            recommendations="",
            confidence_score=0.0,
            model_used="error-test-model",
            tokens_used=0
        )
        
        # 오류 발생 확인
        with self.assertRaises(DataProcessingError) as context:
            self.processor.process_data(invalid_df, mock_llm_result)
        
        # 오류 세부 정보 확인
        error = context.exception
        self.assertIn("데이터 처리 실패", error.message)
    
    def test_missing_columns_handling(self):
        """필수 컬럼 누락 처리 테스트"""
        # 필수 컬럼이 누락된 DataFrame
        incomplete_df = pd.DataFrame([
            {'incomplete_column': 'test'}  # peg_name, avg_value, period 누락
        ])
        
        mock_llm_result = LLMAnalysisResult(
            integrated_analysis="누락 테스트",
            specific_peg_analysis="",
            recommendations="",
            confidence_score=0.0,
            model_used="missing-test-model",
            tokens_used=0
        )
        
        # 오류 발생 확인
        with self.assertRaises(DataProcessingError) as context:
            self.processor.process_data(incomplete_df, mock_llm_result)
        
        # 오류 메시지 확인
        error = context.exception
        self.assertIn("필수 컬럼 누락", error.message)
    
    def test_nan_value_handling(self):
        """NaN 값 처리 테스트"""
        import numpy as np

        # NaN 값이 포함된 DataFrame
        nan_df = pd.DataFrame([
            {'peg_name': 'test_peg', 'avg_value': np.nan, 'period': 'N-1'},
            {'peg_name': 'test_peg', 'avg_value': 100.0, 'period': 'N'}
        ])
        
        mock_llm_result = LLMAnalysisResult(
            integrated_analysis="NaN 처리 테스트",
            specific_peg_analysis="",
            recommendations="",
            confidence_score=0.5,
            model_used="nan-test-model",
            tokens_used=50
        )
        
        # 처리 실행
        result = self.processor.process_data(nan_df, mock_llm_result)
        
        # NaN 값이 적절히 처리되었는지 확인
        peg_data = result['peg_data']
        self.assertEqual(len(peg_data), 1)
        
        # NaN이 0.0으로 변환되었는지 확인
        processed_peg = peg_data[0]
        self.assertEqual(processed_peg['n_minus_1_value'], 0.0)
        self.assertEqual(processed_peg['n_value'], 100.0)


class TestDataProcessorEdgeCases(unittest.TestCase):
    """DataProcessor 엣지 케이스 테스트"""
    
    def setUp(self):
        """테스트 설정"""
        self.processor = DataProcessor()
    
    def test_duplicate_peg_names(self):
        """중복 PEG 이름 처리 테스트"""
        # 중복 PEG 이름이 있는 DataFrame
        duplicate_df = pd.DataFrame([
            {'peg_name': 'duplicate_peg', 'avg_value': 100.0, 'period': 'N-1'},
            {'peg_name': 'duplicate_peg', 'avg_value': 200.0, 'period': 'N-1'},  # 중복
            {'peg_name': 'duplicate_peg', 'avg_value': 150.0, 'period': 'N'}
        ])
        
        mock_llm_result = LLMAnalysisResult(
            integrated_analysis="중복 처리 테스트",
            specific_peg_analysis="",
            recommendations="",
            confidence_score=0.7,
            model_used="duplicate-test-model",
            tokens_used=75
        )
        
        # 처리 실행
        result = self.processor.process_data(duplicate_df, mock_llm_result)
        
        # 중복이 적절히 처리되었는지 확인 (마지막 값 사용 또는 평균)
        peg_data = result['peg_data']
        self.assertEqual(len(peg_data), 1)  # 중복 제거됨
        
        processed_peg = peg_data[0]
        self.assertEqual(processed_peg['peg_name'], 'duplicate_peg')
        # 중복 처리 로직에 따라 값 검증 (구현에 따라 다름)
    
    def test_large_dataset_performance(self):
        """대용량 데이터셋 성능 테스트"""
        import time

        # 대용량 테스트 데이터 생성 (1000개 행)
        large_data = []
        for i in range(500):
            large_data.extend([
                {'peg_name': f'peg_{i}', 'avg_value': float(i * 10), 'period': 'N-1'},
                {'peg_name': f'peg_{i}', 'avg_value': float(i * 11), 'period': 'N'}
            ])
        
        large_df = pd.DataFrame(large_data)
        
        mock_llm_result = LLMAnalysisResult(
            integrated_analysis="대용량 처리 테스트",
            specific_peg_analysis="500개 PEG 처리",
            recommendations="성능 최적화 필요",
            confidence_score=0.8,
            model_used="performance-test-model",
            tokens_used=1000
        )
        
        # 처리 시간 측정
        start_time = time.time()
        result = self.processor.process_data(large_df, mock_llm_result)
        end_time = time.time()
        
        processing_time = end_time - start_time
        
        # 결과 검증
        self.assertEqual(len(result['peg_data']), 500)
        
        # 성능 검증 (5초 이내)
        self.assertLess(processing_time, 5.0, f"처리 시간이 너무 오래 걸림: {processing_time:.2f}초")
        
        # 요약 통계 확인
        summary = result['summary_statistics']
        self.assertEqual(summary['total_pegs'], 500)


if __name__ == '__main__':
    # 테스트 실행
    unittest.main(verbosity=2)
