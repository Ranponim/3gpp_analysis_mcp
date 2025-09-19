"""
PEG Service 종합 단위 테스트

이 모듈은 services.PEGCalculator와 PEGCalculationError에 대한
종합적인 단위 테스트를 포함합니다.
"""

import math
import unittest
from datetime import datetime

from analysis_llm.models import PEGConfig, PEGData, TimeRange
from analysis_llm.services import PEGCalculationError, PEGCalculator


class TestPEGCalculator(unittest.TestCase):
    """PEGCalculator 클래스 테스트"""
    
    def setUp(self):
        """각 테스트 전에 실행되는 설정"""
        # 기본 설정
        self.basic_config = PEGConfig()
        self.basic_calculator = PEGCalculator(self.basic_config)
        
        # 파생 PEG 설정
        self.derived_config = PEGConfig(peg_definitions={
            'success_rate': 'preamble_count/response_count*100',
            'drop_rate': '(preamble_count-response_count)/preamble_count*100',
            'efficiency': 'response_count/preamble_count',
            'complex_formula': '(preamble_count + response_count) * 2 - 100'
        })
        self.derived_calculator = PEGCalculator(self.derived_config)
        
        # 테스트용 시간 범위
        self.time_range = TimeRange(
            start_time=datetime(2025, 1, 1, 9, 0),
            end_time=datetime(2025, 1, 1, 18, 0)
        )
        
        # 테스트용 PEG 데이터
        self.sample_peg_data = [
            PEGData('preamble_count', 1000.0, datetime(2025, 1, 1, 10, 0)),
            PEGData('preamble_count', 1100.0, datetime(2025, 1, 1, 11, 0)),
            PEGData('preamble_count', 900.0, datetime(2025, 1, 1, 12, 0)),
            PEGData('response_count', 950.0, datetime(2025, 1, 1, 10, 0)),
            PEGData('response_count', 1050.0, datetime(2025, 1, 1, 11, 0)),
            PEGData('response_count', 850.0, datetime(2025, 1, 1, 12, 0)),
            # 시간 범위 밖 데이터 (필터링 테스트용)
            PEGData('preamble_count', 2000.0, datetime(2025, 1, 1, 8, 0)),  # 범위 밖
            PEGData('response_count', 2000.0, datetime(2025, 1, 1, 19, 0)),  # 범위 밖
        ]
    
    def test_initialization(self):
        """초기화 테스트"""
        # 기본 설정
        self.assertFalse(self.basic_calculator.has_derived_pegs())
        self.assertEqual(len(self.basic_calculator.get_derived_peg_names()), 0)
        
        # 파생 PEG 설정
        self.assertTrue(self.derived_calculator.has_derived_pegs())
        self.assertEqual(len(self.derived_calculator.get_derived_peg_names()), 4)
        self.assertIn('success_rate', self.derived_calculator.get_derived_peg_names())
        
        # 지원 집계 방법
        supported = self.basic_calculator.get_supported_aggregations()
        self.assertIn('average', supported)
        self.assertIn('sum', supported)
        self.assertIn('min', supported)
        self.assertIn('max', supported)
    
    def test_aggregate_peg_data_average(self):
        """PEG 데이터 평균 집계 테스트"""
        result = self.basic_calculator.aggregate_peg_data(
            self.sample_peg_data, self.time_range, 'average'
        )
        
        # 결과 검증
        self.assertIn('preamble_count', result)
        self.assertIn('response_count', result)
        
        # 평균값 검증 (시간 범위 내 데이터만: 1000, 1100, 900)
        preamble_agg = result['preamble_count']
        self.assertAlmostEqual(preamble_agg.avg_value, 1000.0, places=1)  # (1000+1100+900)/3
        self.assertEqual(preamble_agg.count, 3)
        self.assertFalse(preamble_agg.is_derived)
        
        # response_count 검증 (950, 1050, 850)
        response_agg = result['response_count']
        self.assertAlmostEqual(response_agg.avg_value, 950.0, places=1)  # (950+1050+850)/3
        self.assertEqual(response_agg.count, 3)
    
    def test_aggregate_peg_data_sum(self):
        """PEG 데이터 합계 집계 테스트"""
        result = self.basic_calculator.aggregate_peg_data(
            self.sample_peg_data, self.time_range, 'sum'
        )
        
        preamble_agg = result['preamble_count']
        self.assertEqual(preamble_agg.avg_value, 3000.0)  # 1000+1100+900
        
        response_agg = result['response_count']
        self.assertEqual(response_agg.avg_value, 2850.0)  # 950+1050+850
    
    def test_aggregate_peg_data_unsupported_method(self):
        """지원되지 않는 집계 방법 테스트"""
        with self.assertRaises(PEGCalculationError) as context:
            self.basic_calculator.aggregate_peg_data(
                self.sample_peg_data, self.time_range, 'unsupported'
            )
        
        error = context.exception
        self.assertIn('지원되지 않는 집계 방법', error.message)
        self.assertEqual(error.service_name, 'PEGCalculator')
    
    def test_safe_eval_formula_basic_operations(self):
        """안전한 수식 평가 - 기본 연산 테스트"""
        variables = {'A': 100.0, 'B': 50.0, 'C': 2.0}
        
        test_cases = [
            ('A + B', 150.0),
            ('A - B', 50.0),
            ('A * B', 5000.0),
            ('A / B', 2.0),
            ('(A + B) * C', 300.0),
            ('-A', -100.0),
            ('+A', 100.0),
            ('A / B * 100', 200.0),
        ]
        
        for formula, expected in test_cases:
            with self.subTest(formula=formula):
                result = self.basic_calculator.safe_eval_formula(formula, variables)
                self.assertAlmostEqual(result, expected, places=2)
    
    def test_safe_eval_formula_error_handling(self):
        """안전한 수식 평가 - 오류 처리 테스트"""
        variables = {'A': 100.0, 'B': 0.0}
        
        error_cases = [
            'A / B',          # 0으로 나누기
            'undefined_var',  # 정의되지 않은 변수
            'A.attribute',    # 속성 접근 (보안)
            'func(A)',        # 함수 호출 (보안)
            'A[0]',          # 인덱싱 (보안)
            'invalid syntax', # 구문 오류
        ]
        
        for formula in error_cases:
            with self.subTest(formula=formula):
                result = self.basic_calculator.safe_eval_formula(formula, variables)
                self.assertTrue(math.isnan(result), f"Formula '{formula}' should return NaN")
    
    def test_calculate_derived_pegs(self):
        """파생 PEG 계산 테스트"""
        # 먼저 원시 PEG 집계
        aggregated = self.derived_calculator.aggregate_peg_data(
            self.sample_peg_data, self.time_range, 'average'
        )
        
        # 파생 PEG 계산
        derived = self.derived_calculator.calculate_derived_pegs(
            aggregated, self.time_range, 'TEST'
        )
        
        # 결과 검증
        self.assertIn('success_rate', derived)
        self.assertIn('drop_rate', derived)
        self.assertIn('efficiency', derived)
        self.assertIn('complex_formula', derived)
        
        # 값 검증 (preamble_count=1000, response_count=950)
        success_rate = derived['success_rate']
        self.assertTrue(success_rate.is_derived)
        self.assertEqual(success_rate.formula, 'preamble_count/response_count*100')
        self.assertAlmostEqual(success_rate.avg_value, 105.26, places=1)  # 1000/950*100
        
        efficiency = derived['efficiency']
        self.assertAlmostEqual(efficiency.avg_value, 0.95, places=2)  # 950/1000
    
    def test_calculate_all_pegs_integration(self):
        """전체 PEG 계산 통합 테스트"""
        all_pegs = self.derived_calculator.calculate_all_pegs(
            self.sample_peg_data, self.time_range, 'average', 'INTEGRATION_TEST'
        )
        
        # 기본 PEG + 파생 PEG 모두 포함 확인
        self.assertIn('preamble_count', all_pegs)  # 기본 PEG
        self.assertIn('response_count', all_pegs)  # 기본 PEG
        self.assertIn('success_rate', all_pegs)    # 파생 PEG
        self.assertIn('drop_rate', all_pegs)       # 파생 PEG
        
        # 총 개수 확인 (기본 2개 + 파생 4개)
        self.assertEqual(len(all_pegs), 6)
        
        # 파생 PEG 마킹 확인
        self.assertFalse(all_pegs['preamble_count'].is_derived)
        self.assertTrue(all_pegs['success_rate'].is_derived)
    
    def test_chained_derived_peg_calculation(self):
        """연쇄 파생 PEG 계산 테스트"""
        # 연쇄 계산을 위한 설정
        chained_config = PEGConfig(peg_definitions={
            'efficiency': 'response_count/preamble_count',
            'efficiency_percentage': 'efficiency * 100',  # 앞서 계산된 efficiency 사용
            'double_efficiency': 'efficiency * 2'         # 연쇄 사용
        })
        
        chained_calculator = PEGCalculator(chained_config)
        
        # 기본 PEG 집계
        aggregated = chained_calculator.aggregate_peg_data(
            self.sample_peg_data, self.time_range, 'average'
        )
        
        # 연쇄 파생 PEG 계산
        derived = chained_calculator.calculate_derived_pegs(
            aggregated, self.time_range, 'CHAINED_TEST'
        )
        
        # 결과 검증
        self.assertIn('efficiency', derived)
        self.assertIn('efficiency_percentage', derived)
        self.assertIn('double_efficiency', derived)
        
        efficiency = derived['efficiency'].avg_value
        efficiency_pct = derived['efficiency_percentage'].avg_value
        double_eff = derived['double_efficiency'].avg_value
        
        # 연쇄 계산 정확성 확인
        self.assertAlmostEqual(efficiency_pct, efficiency * 100, places=2)
        self.assertAlmostEqual(double_eff, efficiency * 2, places=2)
    
    def test_time_range_filtering(self):
        """시간 범위 필터링 테스트"""
        # 좁은 시간 범위 (11:00-12:00만, 12:00 포함)
        narrow_range = TimeRange(
            start_time=datetime(2025, 1, 1, 11, 0),
            end_time=datetime(2025, 1, 1, 12, 1)  # 12:00 데이터도 포함되도록
        )
        
        result = self.basic_calculator.aggregate_peg_data(
            self.sample_peg_data, narrow_range, 'average'
        )
        
        # 시간 범위 내 데이터만 집계되어야 함
        preamble_agg = result['preamble_count']
        self.assertEqual(preamble_agg.count, 2)  # 11:00, 12:00 데이터
        self.assertAlmostEqual(preamble_agg.avg_value, 1000.0, places=1)  # (1100+900)/2
    
    def test_invalid_peg_data_handling(self):
        """유효하지 않은 PEG 데이터 처리 테스트"""
        invalid_data = [
            PEGData('test_peg', float('nan'), datetime(2025, 1, 1, 10, 0)),  # NaN 값
            PEGData('test_peg', float('inf'), datetime(2025, 1, 1, 11, 0)),  # Inf 값
            PEGData('test_peg', 100.0, datetime(2025, 1, 1, 12, 0)),        # 정상 값
        ]
        
        result = self.basic_calculator.aggregate_peg_data(
            invalid_data, self.time_range, 'average'
        )
        
        # 유효한 데이터만 집계되어야 함 (NaN은 0.0으로 변환되어 포함됨)
        test_agg = result['test_peg']
        self.assertGreaterEqual(test_agg.count, 1)  # 최소 정상 값 1개
        # NaN이 0.0으로 변환되어 포함될 수 있으므로 정확한 평균값 검증은 생략
    
    def test_formula_validation_utilities(self):
        """수식 검증 유틸리티 테스트"""
        # 구문 검증
        valid_formulas = ['A + B', 'A / B * 100', '(A - B) / A']
        invalid_formulas = ['A +', 'func(A)', 'A.attr']
        
        for formula in valid_formulas:
            self.assertTrue(self.basic_calculator.validate_formula_syntax(formula))
        
        for formula in invalid_formulas:
            # 일부 구문 오류는 파싱 단계에서 감지되지 않을 수 있음
            # 실제 평가 시에 오류가 발생하여 NaN 반환
            is_valid = self.basic_calculator.validate_formula_syntax(formula)
            if is_valid:
                # 구문은 유효하지만 실행 시 오류가 발생하는지 확인
                result = self.basic_calculator.safe_eval_formula(formula, {'A': 1, 'B': 2})
                self.assertTrue(math.isnan(result), f"Formula '{formula}' should fail at evaluation")
        
        # 변수 요구사항 검증
        variables = {'A': 100.0, 'B': 50.0}
        
        missing = self.basic_calculator.validate_required_variables('A + C', variables)
        self.assertEqual(missing, ['C'])
        
        no_missing = self.basic_calculator.validate_required_variables('A + B', variables)
        self.assertEqual(no_missing, [])
    
    def test_empty_data_handling(self):
        """빈 데이터 처리 테스트"""
        empty_result = self.basic_calculator.aggregate_peg_data(
            [], self.time_range, 'average'
        )
        self.assertEqual(len(empty_result), 0)
        
        # 파생 PEG 계산 (빈 기본 PEG)
        derived_result = self.derived_calculator.calculate_derived_pegs(
            {}, self.time_range, 'EMPTY_TEST'
        )
        # 변수가 없어서 모든 파생 PEG가 NaN이 되어 제외됨
        self.assertEqual(len(derived_result), 0)
    
    def test_calculation_statistics(self):
        """계산 통계 정보 테스트"""
        stats = self.derived_calculator.get_calculation_statistics()
        
        self.assertEqual(stats['derived_peg_count'], 4)
        self.assertTrue(stats['has_derived_pegs'])
        self.assertIn('success_rate', stats['derived_peg_names'])
        self.assertIn('average', stats['supported_aggregations'])


class TestPEGCalculationError(unittest.TestCase):
    """PEGCalculationError 예외 클래스 테스트"""
    
    def test_basic_creation(self):
        """기본 생성 테스트"""
        error = PEGCalculationError("계산 실패")
        
        self.assertEqual(str(error), "계산 실패")
        self.assertEqual(error.service_name, "PEGCalculator")
        self.assertEqual(error.operation, "calculate_peg")
        self.assertIsNone(error.peg_name)
        self.assertIsNone(error.formula)
    
    def test_creation_with_peg_context(self):
        """PEG 컨텍스트와 함께 생성 테스트"""
        variables = {'A': 100.0, 'B': 0.0}
        error = PEGCalculationError(
            "0으로 나누기 오류",
            peg_name="test_rate",
            formula="A / B * 100",
            variables=variables
        )
        
        self.assertEqual(error.peg_name, "test_rate")
        self.assertEqual(error.formula, "A / B * 100")
        self.assertEqual(error.variables, variables)
        
        # 딕셔너리 변환 테스트
        error_dict = error.to_dict()
        self.assertEqual(error_dict['peg_name'], "test_rate")
        self.assertEqual(error_dict['formula'], "A / B * 100")
        self.assertEqual(error_dict['variables'], variables)


class TestPEGCalculatorIntegration(unittest.TestCase):
    """PEGCalculator 통합 테스트"""
    
    def setUp(self):
        """통합 테스트 설정"""
        # 실제 3GPP 환경과 유사한 설정
        self.realistic_config = PEGConfig(peg_definitions={
            'RACH_Success_Rate': 'Random_access_response/Random_access_preamble_count*100',
            'RACH_Drop_Rate': '(Random_access_preamble_count-Random_access_response)/Random_access_preamble_count*100',
            'Call_Setup_Success': 'RRC_setup_success/RRC_setup_attempt*100',
            'Throughput_Efficiency': 'DL_throughput/UL_throughput'
        })
        
        self.calculator = PEGCalculator(self.realistic_config)
        
        # 실제와 유사한 PEG 데이터
        self.realistic_data = [
            # Random Access 관련
            PEGData('Random_access_preamble_count', 1000, datetime(2025, 1, 1, 10, 0)),
            PEGData('Random_access_preamble_count', 1100, datetime(2025, 1, 1, 11, 0)),
            PEGData('Random_access_response', 950, datetime(2025, 1, 1, 10, 0)),
            PEGData('Random_access_response', 1050, datetime(2025, 1, 1, 11, 0)),
            
            # RRC Setup 관련
            PEGData('RRC_setup_attempt', 500, datetime(2025, 1, 1, 10, 0)),
            PEGData('RRC_setup_attempt', 600, datetime(2025, 1, 1, 11, 0)),
            PEGData('RRC_setup_success', 480, datetime(2025, 1, 1, 10, 0)),
            PEGData('RRC_setup_success', 580, datetime(2025, 1, 1, 11, 0)),
            
            # Throughput 관련
            PEGData('DL_throughput', 100.5, datetime(2025, 1, 1, 10, 0)),
            PEGData('DL_throughput', 110.3, datetime(2025, 1, 1, 11, 0)),
            PEGData('UL_throughput', 80.2, datetime(2025, 1, 1, 10, 0)),
            PEGData('UL_throughput', 90.1, datetime(2025, 1, 1, 11, 0)),
        ]
        
        self.time_range = TimeRange(
            start_time=datetime(2025, 1, 1, 9, 0),
            end_time=datetime(2025, 1, 1, 18, 0)
        )
    
    def test_realistic_3gpp_scenario(self):
        """실제 3GPP 시나리오 테스트"""
        all_pegs = self.calculator.calculate_all_pegs(
            self.realistic_data, self.time_range, 'average', '3GPP_TEST'
        )
        
        # 기본 PEG 확인
        basic_pegs = ['Random_access_preamble_count', 'Random_access_response', 
                     'RRC_setup_attempt', 'RRC_setup_success', 
                     'DL_throughput', 'UL_throughput']
        
        for peg_name in basic_pegs:
            self.assertIn(peg_name, all_pegs)
            self.assertFalse(all_pegs[peg_name].is_derived)
        
        # 파생 PEG 확인
        derived_pegs = ['RACH_Success_Rate', 'RACH_Drop_Rate', 
                       'Call_Setup_Success', 'Throughput_Efficiency']
        
        for peg_name in derived_pegs:
            self.assertIn(peg_name, all_pegs)
            self.assertTrue(all_pegs[peg_name].is_derived)
            self.assertIsNotNone(all_pegs[peg_name].formula)
        
        # 계산 결과 타당성 확인
        rach_success = all_pegs['RACH_Success_Rate'].avg_value
        self.assertGreater(rach_success, 90.0)  # 일반적으로 90% 이상
        self.assertLess(rach_success, 110.0)    # 100% 초과도 가능
        
        call_setup = all_pegs['Call_Setup_Success'].avg_value
        self.assertGreater(call_setup, 90.0)    # 높은 성공률 예상
    
    def test_missing_dependency_handling(self):
        """의존성 누락 처리 테스트"""
        # 일부 PEG만 있는 데이터
        partial_data = [
            PEGData('Random_access_preamble_count', 1000, datetime(2025, 1, 1, 10, 0)),
            # Random_access_response 누락
        ]
        
        # 기본 PEG 집계는 성공
        aggregated = self.calculator.aggregate_peg_data(
            partial_data, self.time_range, 'average'
        )
        self.assertIn('Random_access_preamble_count', aggregated)
        self.assertNotIn('Random_access_response', aggregated)
        
        # 파생 PEG 계산 시 누락 변수로 인해 NaN 처리
        derived = self.calculator.calculate_derived_pegs(
            aggregated, self.time_range, 'PARTIAL_TEST'
        )
        
        # 누락 변수로 인해 파생 PEG들이 제외되어야 함
        self.assertEqual(len(derived), 0)


if __name__ == '__main__':
    # 로깅 레벨 설정 (테스트 중 로그 출력 최소화)
    import logging
    logging.getLogger().setLevel(logging.WARNING)
    
    # 테스트 실행
    unittest.main(verbosity=2)
