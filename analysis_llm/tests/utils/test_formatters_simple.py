"""
ResponseFormatter 간단한 단위 테스트

실제 구현에 맞춘 기본적인 기능 테스트
"""

import os
import sys
import unittest

# 프로젝트 루트를 Python path에 추가
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)

from models import AnalysisResponse, LLMAnalysisResult
from utils import ResponseFormatter, ResponseFormattingError


class TestResponseFormatter(unittest.TestCase):
    """ResponseFormatter 기본 기능 테스트"""
    
    def setUp(self):
        """테스트 설정"""
        self.formatter = ResponseFormatter()
    
    def test_initialization(self):
        """ResponseFormatter 초기화 테스트"""
        self.assertIsInstance(self.formatter, ResponseFormatter)
        self.assertIsNotNone(self.formatter.logger)
    
    def test_format_analysis_response_success(self):
        """성공적인 분석 응답 포맷팅 테스트"""
        # Mock 분석 결과
        mock_analysis_output = {
            'status': 'success',
            'data_summary': {
                'total_pegs': 2,
                'complete_data_pegs': 2
            },
            'peg_analysis': {
                'results': [
                    {
                        'peg_name': 'preamble_count',
                        'n_minus_1_value': 1000.0,
                        'n_value': 1100.0,
                        'percentage_change': 10.0
                    },
                    {
                        'peg_name': 'response_count',
                        'n_minus_1_value': 950.0,
                        'n_value': 1000.0,
                        'percentage_change': 5.26
                    }
                ]
            },
            'llm_analysis': {
                'integrated_analysis': '성능이 개선되었습니다.',
                'specific_peg_analysis': 'Preamble과 Response 모두 증가.',
                'recommendations': '현재 설정을 유지하세요.',
                'model_used': 'gpt-3.5-turbo'
            },
            'metadata': {
                'request_id': 'test-123',
                'processing_time': 1.5
            }
        }
        
        # 포맷팅 실행
        result = self.formatter.format_analysis_response(mock_analysis_output)
        
        # 결과 검증
        self.assertIsInstance(result, AnalysisResponse)
        self.assertEqual(result.status, 'completed')  # success → completed 변환
        self.assertIn('test-123', result.analysis_id)
        
        # PEG 통계 확인
        self.assertEqual(len(result.peg_statistics), 2)
        first_peg = result.peg_statistics[0]
        self.assertEqual(first_peg.peg_name, 'preamble_count')
        self.assertEqual(first_peg.pct_change, 10.0)
        
        # LLM 분석 확인
        self.assertIsInstance(result.llm_analysis, LLMAnalysisResult)
        self.assertEqual(result.llm_analysis.integrated_analysis, '성능이 개선되었습니다.')
    
    def test_format_error_response(self):
        """오류 응답 포맷팅 테스트"""
        # Mock 오류 결과
        mock_error_output = {
            'status': 'error',
            'message': '데이터베이스 연결 실패',
            'error_type': 'DatabaseError'
        }
        
        # 오류 포맷팅 실행
        result = self.formatter._format_error_response(
            mock_error_output, 
            'error-456'
        )
        
        # 결과 검증
        self.assertIsInstance(result, AnalysisResponse)
        self.assertEqual(result.status, 'error')
        self.assertEqual(result.message, '분석 중 오류가 발생했습니다.')
        self.assertIn('error-456', result.analysis_id)
        
        # 오류 세부 정보 확인
        self.assertIsNotNone(result.error_details)
        self.assertIn('데이터베이스 연결 실패', result.error_details)
    
    def test_to_dict_conversion(self):
        """딕셔너리 변환 테스트"""
        # 간단한 성공 응답
        mock_output = {
            'status': 'success',
            'data_summary': {'total_pegs': 1, 'complete_data_pegs': 1},
            'peg_analysis': {
                'results': [{
                    'peg_name': 'test_peg',
                    'n_minus_1_value': 100.0,
                    'n_value': 110.0,
                    'percentage_change': 10.0
                }]
            },
            'llm_analysis': {
                'integrated_analysis': 'Test analysis',
                'model_used': 'test-model'
            },
            'metadata': {'request_id': 'dict-test'}
        }
        
        # 포맷팅 및 변환
        response = self.formatter.format_analysis_response(mock_output)
        response_dict = self.formatter.to_dict(response)
        
        # 딕셔너리 구조 확인
        self.assertIsInstance(response_dict, dict)
        self.assertIn('status', response_dict)
        self.assertIn('analysis_id', response_dict)
        self.assertIn('peg_statistics', response_dict)
        self.assertIn('llm_analysis', response_dict)
        
        # 값 확인
        self.assertEqual(response_dict['status'], 'completed')
        self.assertEqual(len(response_dict['peg_statistics']), 1)
    
    def test_to_json_conversion(self):
        """JSON 변환 테스트"""
        import json

        # 간단한 응답
        mock_output = {
            'status': 'success',
            'data_summary': {'total_pegs': 1, 'complete_data_pegs': 1},
            'peg_analysis': {'results': []},
            'llm_analysis': {'integrated_analysis': 'JSON test'},
            'metadata': {'request_id': 'json-test'}
        }
        
        # JSON 변환
        response = self.formatter.format_analysis_response(mock_output)
        json_str = self.formatter.to_json(response)
        
        # JSON 구조 확인
        self.assertIsInstance(json_str, str)
        
        # JSON 파싱 가능한지 확인
        parsed_json = json.loads(json_str)
        self.assertIsInstance(parsed_json, dict)
        self.assertIn('status', parsed_json)
    
    def test_format_for_backend(self):
        """백엔드 형식 변환 테스트"""
        # 성공 응답
        mock_output = {
            'status': 'success',
            'data_summary': {'total_pegs': 2, 'complete_data_pegs': 2},
            'peg_analysis': {
                'results': [
                    {
                        'peg_name': 'peg1',
                        'n_minus_1_value': 100.0,
                        'n_value': 110.0,
                        'percentage_change': 10.0
                    }
                ]
            },
            'llm_analysis': {
                'integrated_analysis': 'Backend test analysis'
            },
            'metadata': {'request_id': 'backend-test'}
        }
        
        # 백엔드 형식 변환
        response = self.formatter.format_analysis_response(mock_output)
        backend_format = self.formatter.format_for_backend(response)
        
        # 백엔드 형식 확인
        self.assertIsInstance(backend_format, dict)
        self.assertIn('analysis_id', backend_format)
        self.assertIn('status', backend_format)
        self.assertIn('peg_data', backend_format)
        self.assertIn('summary', backend_format)
        
        # PEG 데이터 확인
        peg_data = backend_format['peg_data']
        self.assertIsInstance(peg_data, list)
        self.assertEqual(len(peg_data), 1)
        
        # 요약 정보 확인
        summary = backend_format['summary']
        self.assertIsInstance(summary, dict)
        self.assertIn('total_pegs', summary)


class TestResponseFormatterErrorHandling(unittest.TestCase):
    """ResponseFormatter 오류 처리 테스트"""
    
    def setUp(self):
        """테스트 설정"""
        self.formatter = ResponseFormatter()
    
    def test_invalid_input_handling(self):
        """잘못된 입력 처리 테스트"""
        # None 입력
        with self.assertRaises(ResponseFormattingError):
            self.formatter.format_analysis_response(None)
        
        # 문자열 입력
        with self.assertRaises(ResponseFormattingError):
            self.formatter.format_analysis_response("invalid input")
        
        # 빈 딕셔너리
        with self.assertRaises(ResponseFormattingError):
            self.formatter.format_analysis_response({})
    
    def test_missing_required_fields(self):
        """필수 필드 누락 처리 테스트"""
        # status 필드 누락
        incomplete_output = {
            'data_summary': {'total_pegs': 1},
            'peg_analysis': {'results': []},
            'metadata': {'request_id': 'incomplete-test'}
        }
        
        with self.assertRaises(ResponseFormattingError) as context:
            self.formatter.format_analysis_response(incomplete_output)
        
        # 오류 메시지 확인
        error = context.exception
        self.assertIn("필수 필드 누락", error.message)
    
    def test_malformed_peg_data(self):
        """잘못된 PEG 데이터 처리 테스트"""
        # 잘못된 PEG 분석 구조
        malformed_output = {
            'status': 'success',
            'data_summary': {'total_pegs': 1},
            'peg_analysis': {
                'results': [
                    {
                        # peg_name 누락
                        'n_minus_1_value': 100.0,
                        'percentage_change': 10.0
                    }
                ]
            },
            'llm_analysis': {'integrated_analysis': 'Test'},
            'metadata': {'request_id': 'malformed-test'}
        }
        
        with self.assertRaises(ResponseFormattingError) as context:
            self.formatter.format_analysis_response(malformed_output)
        
        # 오류 세부 정보 확인
        error = context.exception
        self.assertIn("PEG 통계 추출 실패", error.message)


if __name__ == '__main__':
    # 테스트 실행
    unittest.main(verbosity=2)
