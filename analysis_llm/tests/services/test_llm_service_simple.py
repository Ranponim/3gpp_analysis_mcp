"""
LLM Service 간단한 단위 테스트

LLM 관련 서비스들의 기본 기능을 테스트합니다.
"""

import os
import sys
import unittest
from unittest.mock import Mock, patch

# 프로젝트 루트를 Python path에 추가
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)

from models import LLMAnalysisResult
from repositories import LLMClient, LLMRepository
from services import LLMAnalysisError, LLMAnalysisService


class TestLLMAnalysisService(unittest.TestCase):
    """LLMAnalysisService 기본 테스트"""
    
    def setUp(self):
        """테스트 설정"""
        # Mock LLM Repository
        self.mock_llm_repo = Mock(spec=LLMRepository)
        self.service = LLMAnalysisService(llm_repository=self.mock_llm_repo)
    
    def test_initialization(self):
        """LLMAnalysisService 초기화 테스트"""
        self.assertIsInstance(self.service, LLMAnalysisService)
        self.assertEqual(self.service.llm_repository, self.mock_llm_repo)
        
        # 프롬프트 전략 확인
        self.assertIsNotNone(self.service.strategies)
        self.assertEqual(len(self.service.strategies), 3)  # Overall, Enhanced, Specific
    
    def test_service_info(self):
        """서비스 정보 확인 테스트"""
        service_info = self.service.get_service_info()
        
        self.assertIsInstance(service_info, dict)
        self.assertIn('service_name', service_info)
        self.assertIn('strategies', service_info)
        self.assertEqual(service_info['service_name'], 'LLMAnalysisService')
    
    def test_analyze_peg_data_success(self):
        """PEG 데이터 분석 성공 테스트"""
        # Mock Repository 응답 설정
        mock_llm_response = {
            'summary': '성능이 전반적으로 개선되었습니다.',
            'key_insights': 'Preamble count가 10% 증가했습니다.',
            'recommendations': '현재 설정을 유지하세요.',
            'model_used': 'gpt-3.5-turbo',
            'tokens_used': 150
        }
        self.mock_llm_repo.analyze_data.return_value = mock_llm_response
        
        # 테스트 PEG 데이터
        test_peg_data = [
            {'peg_name': 'preamble_count', 'avg_value': 1100.0, 'period': 'N'},
            {'peg_name': 'response_count', 'avg_value': 1000.0, 'period': 'N'}
        ]
        
        # 분석 실행
        result = self.service.analyze_peg_data(test_peg_data, analysis_type='enhanced')
        
        # 결과 검증
        self.assertIsInstance(result, LLMAnalysisResult)
        self.assertEqual(result.integrated_analysis, '성능이 전반적으로 개선되었습니다.')
        self.assertEqual(result.model_used, 'gpt-3.5-turbo')
        
        # Repository 호출 확인
        self.mock_llm_repo.analyze_data.assert_called_once()
    
    def test_analyze_peg_data_error(self):
        """PEG 데이터 분석 오류 테스트"""
        # Mock Repository에서 오류 발생
        from repositories import LLMError
        self.mock_llm_repo.analyze_data.side_effect = LLMError(
            message="LLM API 호출 실패",
            status_code=500,
            endpoint="http://test-api"
        )
        
        # 테스트 데이터
        test_peg_data = [{'peg_name': 'test_peg', 'avg_value': 100.0}]
        
        # 오류 발생 확인
        with self.assertRaises(LLMAnalysisError) as context:
            self.service.analyze_peg_data(test_peg_data)
        
        # 오류 세부 정보 확인
        error = context.exception
        self.assertIn("LLM 분석 실패", error.message)
    
    def test_strategy_selection(self):
        """프롬프트 전략 선택 테스트"""
        # Mock Repository 설정
        self.mock_llm_repo.analyze_data.return_value = {
            'summary': 'Strategy test',
            'model_used': 'test-model'
        }
        
        test_data = [{'peg_name': 'strategy_test', 'avg_value': 100.0}]
        
        # 다양한 분석 타입 테스트
        for analysis_type in ['overall', 'enhanced', 'specific']:
            result = self.service.analyze_peg_data(test_data, analysis_type=analysis_type)
            self.assertIsInstance(result, LLMAnalysisResult)
            
            # 적절한 전략이 선택되었는지 확인 (호출 횟수로 검증)
            self.mock_llm_repo.analyze_data.assert_called()


class TestLLMClient(unittest.TestCase):
    """LLMClient 기본 테스트"""
    
    @patch('requests.Session')
    def test_initialization(self, mock_session_class):
        """LLMClient 초기화 테스트"""
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        
        # Mock 설정
        mock_config = {
            'llm_api_key': 'test-api-key',
            'llm_provider': 'openai',
            'llm_model': 'gpt-3.5-turbo'
        }
        
        # LLMClient 생성
        client = LLMClient(config_override=mock_config)
        
        # 초기화 확인
        self.assertIsInstance(client, LLMClient)
        self.assertIsInstance(client, LLMRepository)
        
        # 세션 생성 확인
        mock_session_class.assert_called_once()
    
    @patch('requests.Session')
    def test_estimate_tokens(self, mock_session_class):
        """토큰 추정 테스트"""
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        
        client = LLMClient(config_override={
            'llm_api_key': 'test-key',
            'llm_provider': 'openai'
        })
        
        # 토큰 추정 실행
        test_prompt = "이것은 테스트 프롬프트입니다."
        estimated_tokens = client.estimate_tokens(test_prompt)
        
        # 결과 검증
        self.assertIsInstance(estimated_tokens, int)
        self.assertGreater(estimated_tokens, 0)
    
    @patch('requests.Session')
    def test_validate_prompt(self, mock_session_class):
        """프롬프트 검증 테스트"""
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        
        client = LLMClient(config_override={
            'llm_api_key': 'test-key',
            'llm_max_tokens': 8000
        })
        
        # 유효한 프롬프트
        valid_prompt = "짧은 테스트 프롬프트"
        self.assertTrue(client.validate_prompt(valid_prompt))
        
        # 빈 프롬프트
        self.assertFalse(client.validate_prompt(""))
        self.assertFalse(client.validate_prompt(None))
        
        # 너무 긴 프롬프트 (문자 수 기준)
        very_long_prompt = "매우 " * 10000  # 약 50000자
        self.assertFalse(client.validate_prompt(very_long_prompt))


class TestLLMIntegration(unittest.TestCase):
    """LLM 통합 테스트"""
    
    def test_llm_analysis_result_creation(self):
        """LLMAnalysisResult 생성 테스트"""
        result = LLMAnalysisResult(
            integrated_analysis="통합 분석 결과",
            specific_peg_analysis="특정 PEG 분석",
            recommendations="권고사항",
            confidence_score=0.85,
            model_used="test-model",
            tokens_used=200
        )
        
        # 기본 속성 확인
        self.assertEqual(result.integrated_analysis, "통합 분석 결과")
        self.assertEqual(result.confidence_score, 0.85)
        self.assertEqual(result.tokens_used, 200)
        
        # 타임스탬프 자동 생성 확인
        self.assertIsNotNone(result.analysis_timestamp)
    
    def test_llm_analysis_error_creation(self):
        """LLMAnalysisError 생성 테스트"""
        error = LLMAnalysisError(
            message="LLM 분석 오류",
            analysis_type="enhanced",
            prompt_preview="Test prompt..."
        )
        
        # 기본 속성 확인
        self.assertEqual(error.message, "LLM 분석 오류")
        self.assertEqual(error.analysis_type, "enhanced")
        self.assertEqual(error.prompt_preview, "Test prompt...")
        
        # 상속 관계 확인
        from exceptions import ServiceError
        self.assertIsInstance(error, ServiceError)


if __name__ == '__main__':
    # 테스트 실행
    unittest.main(verbosity=2)
