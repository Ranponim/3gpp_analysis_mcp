"""
TimeRangeParser 종합 단위 테스트

이 모듈은 utils.TimeRangeParser와 utils.TimeParsingError에 대한
종합적인 단위 테스트를 포함합니다.
"""

import json
import os
import unittest
from datetime import timedelta, timezone

from analysis_llm.utils import TimeParsingError, TimeRangeParser


class TestTimeRangeParser(unittest.TestCase):
    """TimeRangeParser 클래스 테스트"""
    
    def setUp(self):
        """각 테스트 전에 실행되는 설정"""
        self.parser = TimeRangeParser()
        # 테스트용 타임존 설정
        os.environ['DEFAULT_TZ_OFFSET'] = '+09:00'
    
    def tearDown(self):
        """각 테스트 후에 실행되는 정리"""
        # 환경변수 초기화
        if 'DEFAULT_TZ_OFFSET' in os.environ:
            del os.environ['DEFAULT_TZ_OFFSET']
    
    def test_timezone_logic(self):
        """타임존 로직 테스트"""
        # 기본 +09:00 타임존
        tzinfo = self.parser._get_timezone()
        expected_offset = timedelta(hours=9)
        self.assertEqual(tzinfo.utcoffset(None), expected_offset)
        
        # 음수 타임존 테스트
        os.environ['DEFAULT_TZ_OFFSET'] = '-05:00'
        parser2 = TimeRangeParser()
        tzinfo2 = parser2._get_timezone()
        expected_offset2 = timedelta(hours=-5)
        self.assertEqual(tzinfo2.utcoffset(None), expected_offset2)
        
        # 잘못된 형식 - UTC 대체
        os.environ['DEFAULT_TZ_OFFSET'] = 'invalid'
        parser3 = TimeRangeParser()
        tzinfo3 = parser3._get_timezone()
        self.assertEqual(tzinfo3, timezone.utc)
    
    def test_supported_formats_parsing(self):
        """지원되는 모든 형식 파싱 테스트"""
        test_cases = [
            # 기본 _ 구분자 형식
            ('2025-01-01_09:00~2025-01-01_18:00', '09:00', '18:00'),
            # 대체 - 구분자 형식  
            ('2025-01-01-09:00~2025-01-01-18:00', '09:00', '18:00'),
            # 단일 날짜 (전체 하루)
            ('2025-01-01', '00:00:00', '23:59:59')
        ]
        
        for time_str, expected_start_time, expected_end_time in test_cases:
            with self.subTest(time_str=time_str):
                start, end = self.parser.parse(time_str)
                
                # 타임존 확인
                self.assertIsNotNone(start.tzinfo)
                self.assertIsNotNone(end.tzinfo)
                
                # 시간 확인
                start_time_str = start.strftime('%H:%M:%S' if len(expected_start_time) > 5 else '%H:%M')
                end_time_str = end.strftime('%H:%M:%S' if len(expected_end_time) > 5 else '%H:%M')
                self.assertEqual(start_time_str, expected_start_time)
                self.assertEqual(end_time_str, expected_end_time)
    
    def test_type_error_handling(self):
        """타입 오류 처리 테스트"""
        invalid_inputs = [123, None, [], {}]
        
        for invalid_input in invalid_inputs:
            with self.subTest(input=invalid_input):
                with self.assertRaises(TimeParsingError) as context:
                    self.parser.parse(invalid_input)
                
                error = context.exception
                self.assertTrue(error.is_type_error())
                self.assertEqual(error.error_code, 'TYPE_ERROR')
                self.assertIn('문자열', error.message)
    
    def test_format_error_handling(self):
        """형식 오류 처리 테스트"""
        invalid_formats = [
            '',  # 빈 문자열
            '잘못된형식',  # 완전히 잘못된 형식
            '2025-01-01 09:00~2025-01-01 18:00',  # 공백 구분자
            '2025-01-01_09-00~2025-01-01_18-00',  # 시간 부분에 - 사용
            '2025-01-01_09:00~~2025-01-01_18:00',  # 중복 ~
            '2025-01-01_09:00',  # 종료 시간 없음
        ]
        
        for invalid_format in invalid_formats:
            with self.subTest(format=invalid_format):
                with self.assertRaises(TimeParsingError) as context:
                    self.parser.parse(invalid_format)
                
                error = context.exception
                self.assertTrue(error.is_format_error())
                self.assertEqual(error.error_code, 'FORMAT_ERROR')
                # hint가 없는 경우도 있음 (일부 형식 오류에서는 hint가 제공되지 않음)
    
    def test_value_error_handling(self):
        """값 오류 처리 테스트"""
        invalid_values = [
            '2025-13-01',  # 잘못된 월
            '2025-01-32',  # 잘못된 일
            '2025-01-01_25:00~2025-01-01_26:00',  # 잘못된 시간
            '2025-01-01_09:70~2025-01-01_18:00',  # 잘못된 분
        ]
        
        for invalid_value in invalid_values:
            with self.subTest(value=invalid_value):
                with self.assertRaises(TimeParsingError) as context:
                    self.parser.parse(invalid_value)
                
                error = context.exception
                self.assertTrue(error.is_value_error())
                self.assertEqual(error.error_code, 'VALUE_ERROR')
    
    def test_logic_error_handling(self):
        """논리 오류 처리 테스트"""
        logic_errors = [
            '2025-01-01_09:00~2025-01-01_09:00',  # 동일한 시간
            '2025-01-01_18:00~2025-01-01_09:00',  # 시작 > 종료
        ]
        
        for logic_error in logic_errors:
            with self.subTest(logic=logic_error):
                with self.assertRaises(TimeParsingError) as context:
                    self.parser.parse(logic_error)
                
                error = context.exception
                self.assertTrue(error.is_logic_error())
                self.assertEqual(error.error_code, 'LOGIC_ERROR')
    
    def test_edge_cases(self):
        """경계 조건 테스트"""
        edge_cases = [
            # 윤년
            ('2024-02-29_09:00~2024-02-29_18:00', True),  # 윤년 2월 29일
            ('2023-02-29', False),  # 평년 2월 29일 (오류)
            
            # 월 경계
            ('2025-01-31_23:59~2025-02-01_00:01', True),  # 월 경계
            
            # 연도 경계
            ('2024-12-31_23:59~2025-01-01_00:01', True),  # 연도 경계
        ]
        
        for time_str, should_succeed in edge_cases:
            with self.subTest(time_str=time_str):
                if should_succeed:
                    try:
                        start, end = self.parser.parse(time_str)
                        self.assertLess(start, end)
                    except TimeParsingError:
                        self.fail(f"유효한 입력 '{time_str}'에서 오류 발생")
                else:
                    with self.assertRaises(TimeParsingError):
                        self.parser.parse(time_str)
    
    def test_timezone_variations(self):
        """다양한 타임존 테스트"""
        timezone_tests = [
            ('+09:00', 9),
            ('-05:00', -5),
            ('+00:00', 0),
            ('+12:30', 12.5),  # 30분 오프셋
        ]
        
        for tz_offset, expected_hours in timezone_tests:
            with self.subTest(timezone=tz_offset):
                os.environ['DEFAULT_TZ_OFFSET'] = tz_offset
                parser = TimeRangeParser()
                
                start, end = parser.parse('2025-01-01_09:00~2025-01-01_18:00')
                
                # 타임존 오프셋 확인
                expected_offset = timedelta(hours=expected_hours)
                self.assertEqual(start.tzinfo.utcoffset(None), expected_offset)
                self.assertEqual(end.tzinfo.utcoffset(None), expected_offset)
    
    def test_utility_methods(self):
        """유틸리티 메서드 테스트"""
        # get_supported_formats
        formats = self.parser.get_supported_formats()
        self.assertIsInstance(formats, list)
        self.assertGreater(len(formats), 0)
        
        # is_valid_format
        valid_formats = [
            '2025-01-01_09:00~2025-01-01_18:00',
            '2025-01-01-09:00~2025-01-01-18:00',
            '2025-01-01'
        ]
        
        invalid_formats = [
            '잘못된형식',
            '',
            123
        ]
        
        for valid_format in valid_formats:
            self.assertTrue(self.parser.is_valid_format(valid_format))
        
        for invalid_format in invalid_formats:
            self.assertFalse(self.parser.is_valid_format(invalid_format))
        
        # parse_safe
        result = self.parser.parse_safe('2025-01-01_09:00~2025-01-01_18:00')
        self.assertIsNotNone(result)
        
        result_error = self.parser.parse_safe('잘못된형식')
        self.assertIsNone(result_error)
    
    def test_json_error_compatibility(self):
        """JSON 오류 메시지 호환성 테스트"""
        try:
            self.parser.parse('잘못된형식')
        except TimeParsingError as e:
            json_error = e.to_json_error()
            
            # 필수 필드 확인
            self.assertIn('code', json_error)
            self.assertIn('message', json_error)
            self.assertIn('input', json_error)
            self.assertIn('hint', json_error)
            
            # JSON 직렬화 가능 확인
            json_str = json.dumps(json_error, ensure_ascii=False)
            self.assertIsInstance(json_str, str)
            
            # 역직렬화 확인
            restored = json.loads(json_str)
            self.assertEqual(restored['code'], 'FORMAT_ERROR')


class TestTimeParsingError(unittest.TestCase):
    """TimeParsingError 예외 클래스 테스트"""
    
    def test_basic_creation(self):
        """기본 생성 테스트"""
        error = TimeParsingError("테스트 메시지")
        
        self.assertEqual(str(error), "테스트 메시지")
        self.assertEqual(error.message, "테스트 메시지")
        self.assertIsNone(error.error_code)
        self.assertIsNone(error.hint)
    
    def test_creation_with_all_attributes(self):
        """모든 속성과 함께 생성 테스트"""
        error = TimeParsingError(
            message="형식 오류",
            details={"key": "value"},
            error_code="FORMAT_ERROR",
            hint="올바른 형식을 사용하세요",
            input_value="잘못된입력"
        )
        
        self.assertEqual(error.message, "형식 오류")
        self.assertEqual(error.error_code, "FORMAT_ERROR")
        self.assertEqual(error.hint, "올바른 형식을 사용하세요")
        self.assertEqual(error.input_value, "잘못된입력")
        self.assertEqual(error.details, {"key": "value"})
    
    def test_error_type_detection_methods(self):
        """오류 타입 감지 메서드 테스트"""
        error_types = [
            ("TYPE_ERROR", "is_type_error"),
            ("FORMAT_ERROR", "is_format_error"),
            ("VALUE_ERROR", "is_value_error"),
            ("LOGIC_ERROR", "is_logic_error")
        ]
        
        for error_code, method_name in error_types:
            with self.subTest(error_code=error_code):
                error = TimeParsingError("테스트", error_code=error_code)
                
                # 해당 타입 메서드는 True
                self.assertTrue(getattr(error, method_name)())
                
                # 다른 타입 메서드들은 False
                other_methods = [m for _, m in error_types if m != method_name]
                for other_method in other_methods:
                    self.assertFalse(getattr(error, other_method)())
    
    def test_json_error_conversion(self):
        """JSON 오류 변환 테스트"""
        error = TimeParsingError(
            "형식 오류",
            {"extra": "info"},
            "FORMAT_ERROR",
            "올바른 형식을 사용하세요",
            "잘못된입력"
        )
        
        json_error = error.to_json_error()
        
        expected = {
            'code': 'FORMAT_ERROR',
            'message': '형식 오류',
            'input': '잘못된입력',
            'hint': '올바른 형식을 사용하세요',
            'extra': 'info'
        }
        
        self.assertEqual(json_error, expected)
    
    def test_from_json_error_factory(self):
        """JSON 오류에서 객체 생성 테스트"""
        json_data = {
            'code': 'VALUE_ERROR',
            'message': '잘못된 값',
            'input': '2025-13-01',
            'hint': '올바른 날짜를 입력하세요',
            'extra_field': 'extra_value'
        }
        
        error = TimeParsingError.from_json_error(json_data)
        
        self.assertEqual(error.error_code, 'VALUE_ERROR')
        self.assertEqual(error.message, '잘못된 값')
        self.assertEqual(error.input_value, '2025-13-01')
        self.assertEqual(error.hint, '올바른 날짜를 입력하세요')
        self.assertEqual(error.details['extra_field'], 'extra_value')


class TestTimeParserIntegration(unittest.TestCase):
    """TimeRangeParser 통합 테스트"""
    
    def setUp(self):
        """테스트 설정"""
        self.parser = TimeRangeParser()
        os.environ['DEFAULT_TZ_OFFSET'] = '+09:00'
    
    def tearDown(self):
        """테스트 정리"""
        if 'DEFAULT_TZ_OFFSET' in os.environ:
            del os.environ['DEFAULT_TZ_OFFSET']
    
    def test_real_world_scenarios(self):
        """실제 사용 시나리오 테스트"""
        # 실제 분석에서 사용될 수 있는 시간 범위들
        real_scenarios = [
            '2025-01-01_00:00~2025-01-01_23:59',  # 하루 전체
            '2025-01-01_09:00~2025-01-01_17:00',  # 업무 시간
            '2025-01-01-00:00~2025-01-01-23:59',  # 대체 구분자
            '2025-01-01',  # 단일 날짜
        ]
        
        for scenario in real_scenarios:
            with self.subTest(scenario=scenario):
                start, end = self.parser.parse(scenario)
                
                # 기본 검증
                self.assertLess(start, end)
                self.assertIsNotNone(start.tzinfo)
                self.assertIsNotNone(end.tzinfo)
                
                # 타임존 일관성
                self.assertEqual(start.tzinfo, end.tzinfo)
    
    def test_error_message_structure(self):
        """오류 메시지 구조 테스트 (기존 main.py 호환성)"""
        error_scenarios = [
            (123, 'TYPE_ERROR'),
            ('', 'FORMAT_ERROR'),
            ('2025-13-01', 'VALUE_ERROR'),
            ('2025-01-01_18:00~2025-01-01_09:00', 'LOGIC_ERROR')
        ]
        
        for invalid_input, expected_code in error_scenarios:
            with self.subTest(input=invalid_input):
                with self.assertRaises(TimeParsingError) as context:
                    self.parser.parse(invalid_input)
                
                error = context.exception
                json_error = error.to_json_error()
                
                # 기존 main.py와 동일한 구조 확인
                self.assertEqual(json_error['code'], expected_code)
                self.assertIn('message', json_error)
                
                # JSON 직렬화 가능 확인
                json_str = json.dumps(json_error, ensure_ascii=False)
                self.assertIsInstance(json_str, str)
    
    def test_performance_with_precompiled_patterns(self):
        """사전 컴파일된 정규식 패턴 성능 테스트"""
        # 여러 번 파싱해서 성능 확인
        test_input = '2025-01-01_09:00~2025-01-01_18:00'
        
        # 10번 파싱해서 모두 동일한 결과 확인
        results = []
        for _ in range(10):
            result = self.parser.parse(test_input)
            results.append(result)
        
        # 모든 결과가 동일한지 확인
        first_result = results[0]
        for result in results[1:]:
            self.assertEqual(result[0], first_result[0])
            self.assertEqual(result[1], first_result[1])


if __name__ == '__main__':
    # 로깅 레벨 설정 (테스트 중 로그 출력 최소화)
    import logging
    logging.getLogger().setLevel(logging.CRITICAL)
    
    # 테스트 실행
    unittest.main(verbosity=2)
