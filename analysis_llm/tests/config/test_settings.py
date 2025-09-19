"""
Configuration Manager 종합 단위 테스트

이 모듈은 config.settings 모듈의 모든 기능에 대한
종합적인 단위 테스트를 포함합니다.
"""

import os

# 테스트를 위한 import 경로 설정
import sys
import unittest
import warnings
from unittest.mock import patch

from pydantic import ValidationError

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from config import Settings, get_settings, reload_settings


class TestSettings(unittest.TestCase):
    """Settings 클래스 기본 기능 테스트"""
    
    def setUp(self):
        """각 테스트 전에 실행되는 설정"""
        # 기본 필수 환경변수 설정
        self.required_env = {
            'DB_HOST': 'test_host',
            'DB_NAME': 'test_db',
            'DB_USER': 'test_user',
            'DB_PASSWORD': 'test_password',
            'LLM_API_KEY': 'test_api_key',
            'BACKEND_SERVICE_URL': 'http://localhost:8000'
        }
        
        # 환경변수 설정
        for key, value in self.required_env.items():
            os.environ[key] = value
    
    def tearDown(self):
        """각 테스트 후에 실행되는 정리"""
        # 테스트용 환경변수 정리
        for key in self.required_env.keys():
            os.environ.pop(key, None)
        
        # 선택적 환경변수들도 정리
        optional_vars = [
            'APP_NAME', 'APP_ENVIRONMENT', 'APP_DEBUG', 'LLM_PROVIDER',
            'LLM_MODEL', 'LLM_TEMPERATURE', 'PEG_DEFAULT_AGGREGATION'
        ]
        for key in optional_vars:
            os.environ.pop(key, None)
    
    def test_basic_settings_creation(self):
        """기본 설정 생성 테스트"""
        settings = Settings()
        
        # 기본값 확인
        self.assertEqual(settings.app_name, "3GPP Analysis MCP")
        self.assertEqual(settings.app_environment, "development")
        self.assertEqual(settings.app_debug, True)
        self.assertEqual(settings.llm_provider, "openai")
        self.assertEqual(settings.llm_model, "gpt-3.5-turbo")
        
        # 필수값 확인
        self.assertEqual(settings.db_host, "test_host")
        self.assertEqual(settings.db_name, "test_db")
        self.assertEqual(settings.db_user, "test_user")
    
    def test_environment_variable_override(self):
        """환경변수 오버라이드 테스트"""
        # 환경변수 설정
        os.environ['APP_NAME'] = 'Custom App'
        os.environ['APP_ENVIRONMENT'] = 'production'
        os.environ['LLM_PROVIDER'] = 'anthropic'
        os.environ['LLM_TEMPERATURE'] = '0.5'
        
        settings = Settings()
        
        # 환경변수 적용 확인
        self.assertEqual(settings.app_name, "Custom App")
        self.assertEqual(settings.app_environment, "production")
        self.assertEqual(settings.llm_provider, "anthropic")
        self.assertEqual(settings.llm_temperature, 0.5)
    
    def test_required_fields_validation(self):
        """필수 필드 검증 테스트"""
        # 필수 환경변수 제거
        for key in ['DB_HOST', 'DB_USER', 'LLM_API_KEY']:
            if key in os.environ:
                del os.environ[key]
        
        # ValidationError 발생 확인
        with self.assertRaises(ValidationError) as context:
            Settings()
        
        error = context.exception
        self.assertIn('db_host', str(error))
        self.assertIn('db_user', str(error))
        self.assertIn('llm_api_key', str(error))
    
    def test_database_url_generation(self):
        """데이터베이스 URL 생성 테스트"""
        settings = Settings()
        
        # 동기 URL
        sync_url = settings.get_database_url(async_mode=False)
        expected_sync = "postgresql://test_user:test_password@test_host:5432/test_db"
        self.assertEqual(sync_url, expected_sync)
        
        # 비동기 URL
        async_url = settings.get_database_url(async_mode=True)
        expected_async = "postgresql+asyncpg://test_user:test_password@test_host:5432/test_db"
        self.assertEqual(async_url, expected_async)
    
    def test_llm_api_key_access(self):
        """LLM API 키 접근 테스트"""
        settings = Settings()
        
        api_key = settings.get_llm_api_key()
        self.assertEqual(api_key, "test_api_key")
        
        # SecretStr 보안 확인
        self.assertNotEqual(str(settings.llm_api_key), "test_api_key")
    
    def test_backend_auth_header(self):
        """백엔드 인증 헤더 테스트"""
        settings = Settings()
        
        # 토큰 없을 때
        headers = settings.get_backend_auth_header()
        self.assertEqual(headers, {})
        
        # 토큰 있을 때
        os.environ['BACKEND_AUTH_TOKEN'] = 'test_token'
        settings = Settings()
        headers = settings.get_backend_auth_header()
        expected = {"Authorization": "Bearer test_token"}
        self.assertEqual(headers, expected)


class TestSettingsValidation(unittest.TestCase):
    """Settings 검증 로직 테스트"""
    
    def setUp(self):
        """테스트 설정"""
        # 기본 필수 환경변수 설정
        self.required_env = {
            'DB_HOST': 'test_host',
            'DB_NAME': 'test_db',
            'DB_USER': 'test_user',
            'DB_PASSWORD': 'test_password',
            'LLM_API_KEY': 'test_api_key',
            'BACKEND_SERVICE_URL': 'http://localhost:8000'
        }
        
        for key, value in self.required_env.items():
            os.environ[key] = value
    
    def tearDown(self):
        """테스트 정리"""
        for key in self.required_env.keys():
            os.environ.pop(key, None)
        
        # 테스트용 환경변수 정리
        test_vars = [
            'APP_ENVIRONMENT', 'LLM_PROVIDER', 'LLM_TEMPERATURE',
            'PEG_DEFAULT_AGGREGATION', 'LOG_LEVEL', 'DB_PORT'
        ]
        for key in test_vars:
            os.environ.pop(key, None)
    
    def test_environment_validation(self):
        """환경 검증 테스트"""
        # 유효한 환경
        for env in ['development', 'production', 'testing']:
            os.environ['APP_ENVIRONMENT'] = env
            settings = Settings()
            self.assertEqual(settings.app_environment, env)
        
        # 잘못된 환경
        os.environ['APP_ENVIRONMENT'] = 'invalid'
        with self.assertRaises(ValidationError):
            Settings()
    
    def test_llm_provider_validation(self):
        """LLM 제공업체 검증 테스트"""
        # 유효한 제공업체들
        for provider in ['openai', 'anthropic', 'google', 'azure', 'local']:
            os.environ['LLM_PROVIDER'] = provider
            settings = Settings()
            self.assertEqual(settings.llm_provider, provider)
        
        # 잘못된 제공업체
        os.environ['LLM_PROVIDER'] = 'invalid_provider'
        with self.assertRaises(ValidationError):
            Settings()
    
    def test_temperature_validation(self):
        """LLM 온도 검증 테스트"""
        # 유효한 온도값들
        for temp in [0.0, 0.5, 1.0, 2.0]:
            os.environ['LLM_TEMPERATURE'] = str(temp)
            settings = Settings()
            self.assertEqual(settings.llm_temperature, temp)
        
        # 잘못된 온도값들
        for temp in [-0.1, 2.1, 5.0]:
            os.environ['LLM_TEMPERATURE'] = str(temp)
            with self.assertRaises(ValidationError):
                Settings()
    
    def test_aggregation_method_validation(self):
        """집계 방법 검증 테스트"""
        # 유효한 집계 방법들
        for method in ['sum', 'average', 'mean', 'min', 'max', 'count']:
            os.environ['PEG_DEFAULT_AGGREGATION'] = method
            settings = Settings()
            self.assertEqual(settings.peg_default_aggregation, method)
        
        # 잘못된 집계 방법
        os.environ['PEG_DEFAULT_AGGREGATION'] = 'invalid_method'
        with self.assertRaises(ValidationError):
            Settings()
    
    def test_log_level_validation(self):
        """로그 레벨 검증 테스트"""
        # 유효한 로그 레벨들
        for level in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
            os.environ['LOG_LEVEL'] = level
            settings = Settings()
            self.assertEqual(settings.log_level, level)
        
        # 잘못된 로그 레벨
        os.environ['LOG_LEVEL'] = 'INVALID_LEVEL'
        with self.assertRaises(ValidationError):
            Settings()
    
    def test_positive_integer_validation(self):
        """양수 검증 테스트"""
        # 유효한 양수들
        os.environ['DB_PORT'] = '5432'
        settings = Settings()
        self.assertEqual(settings.db_port, 5432)
        
        # 잘못된 값들
        for invalid_value in ['0', '-1', 'abc']:
            os.environ['DB_PORT'] = invalid_value
            with self.assertRaises(ValidationError):
                Settings()
    
    def test_production_environment_warnings(self):
        """프로덕션 환경 경고 테스트"""
        os.environ['APP_ENVIRONMENT'] = 'production'
        os.environ['APP_DEBUG'] = 'true'
        os.environ['DB_PASSWORD'] = 'short'  # 8자 미만
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            Settings()
            
            # 경고 메시지 확인
            warning_messages = [str(warning.message) for warning in w]
            debug_warning = any("Debug mode" in msg for msg in warning_messages)
            password_warning = any("password" in msg.lower() for msg in warning_messages)
            
            self.assertTrue(debug_warning or password_warning, "프로덕션 환경 경고가 발생해야 함")


class TestSettingsUtilities(unittest.TestCase):
    """Settings 유틸리티 메서드 테스트"""
    
    def setUp(self):
        """테스트 설정"""
        # 필수 환경변수 설정
        self.required_env = {
            'DB_HOST': 'localhost',
            'DB_NAME': 'test_db',
            'DB_USER': 'test_user',
            'DB_PASSWORD': 'test_password',
            'LLM_API_KEY': 'test_api_key',
            'BACKEND_SERVICE_URL': 'http://localhost:8000'
        }
        
        for key, value in self.required_env.items():
            os.environ[key] = value
    
    def tearDown(self):
        """테스트 정리"""
        for key in self.required_env.keys():
            os.environ.pop(key, None)
    
    def test_environment_detection(self):
        """환경 감지 메서드 테스트"""
        # 개발 환경
        os.environ['APP_ENVIRONMENT'] = 'development'
        settings = Settings()
        self.assertTrue(settings.is_development())
        self.assertFalse(settings.is_production())
        
        # 프로덕션 환경
        os.environ['APP_ENVIRONMENT'] = 'production'
        settings = Settings()
        self.assertTrue(settings.is_production())
        self.assertFalse(settings.is_development())
    
    def test_config_dict_methods(self):
        """설정 딕셔너리 변환 메서드 테스트"""
        settings = Settings()
        
        # LLM 설정 딕셔너리
        llm_config = settings.get_llm_config_dict()
        expected_keys = ['provider', 'model', 'max_tokens', 'temperature', 
                        'timeout', 'max_retries', 'retry_delay']
        for key in expected_keys:
            self.assertIn(key, llm_config)
        
        # PEG 설정 딕셔너리
        peg_config = settings.get_peg_config_dict()
        expected_keys = ['default_aggregation_method', 'enable_derived_pegs', 
                        'default_time_window', 'max_formula_complexity', 
                        'derived_peg_definitions']
        for key in expected_keys:
            self.assertIn(key, peg_config)
        
        # 시간대 설정 딕셔너리
        timezone_config = settings.get_timezone_config_dict()
        expected_keys = ['app_timezone', 'data_timezone', 'datetime_format', 
                        'date_format', 'time_format']
        for key in expected_keys:
            self.assertIn(key, timezone_config)
    
    def test_secret_masking(self):
        """비밀 정보 마스킹 테스트"""
        settings = Settings()
        
        # 비밀 정보 제외
        config_dict = settings.to_dict(exclude_secrets=True)
        
        # 비밀 필드들이 마스킹되었는지 확인
        secret_fields = ['db_password', 'llm_api_key']
        for field in secret_fields:
            if field in config_dict:
                self.assertEqual(config_dict[field], "***")
        
        # 비밀 정보 포함
        config_dict_with_secrets = settings.to_dict(exclude_secrets=False)
        # 실제 SecretStr 객체가 포함되어야 함
        self.assertNotEqual(str(config_dict_with_secrets.get('db_password', '')), "***")
    
    @patch('logging.basicConfig')
    def test_logging_setup(self, mock_basic_config):
        """로깅 설정 테스트"""
        settings = Settings()
        
        # 로깅 설정 호출
        settings.setup_logging()
        
        # basicConfig가 호출되었는지 확인
        mock_basic_config.assert_called_once()
        
        # 호출 인자 확인
        call_args = mock_basic_config.call_args
        self.assertIn('level', call_args.kwargs)
        self.assertIn('format', call_args.kwargs)


class TestGlobalSettingsManagement(unittest.TestCase):
    """전역 설정 관리 테스트"""
    
    def setUp(self):
        """테스트 설정"""
        # 필수 환경변수 설정
        self.required_env = {
            'DB_HOST': 'global_test_host',
            'DB_NAME': 'global_test_db',
            'DB_USER': 'global_test_user',
            'DB_PASSWORD': 'global_test_password',
            'LLM_API_KEY': 'global_test_api_key',
            'BACKEND_SERVICE_URL': 'http://localhost:9000'
        }
        
        for key, value in self.required_env.items():
            os.environ[key] = value
    
    def tearDown(self):
        """테스트 정리"""
        for key in self.required_env.keys():
            os.environ.pop(key, None)
        
        # 전역 설정 인스턴스 초기화
        import config.settings
        config.settings._settings = None
    
    def test_get_settings_singleton(self):
        """get_settings 싱글톤 패턴 테스트"""
        # 첫 번째 호출
        settings1 = get_settings()
        
        # 두 번째 호출
        settings2 = get_settings()
        
        # 같은 인스턴스인지 확인
        self.assertIs(settings1, settings2)
        self.assertEqual(settings1.db_host, "global_test_host")
    
    def test_reload_settings(self):
        """설정 재로드 테스트"""
        # 첫 번째 설정 로드
        settings1 = get_settings()
        original_host = settings1.db_host
        
        # 환경변수 변경
        os.environ['DB_HOST'] = 'new_host'
        
        # 설정 재로드
        settings2 = reload_settings()
        
        # 새로운 값이 적용되었는지 확인
        self.assertEqual(settings2.db_host, 'new_host')
        self.assertNotEqual(settings2.db_host, original_host)
    
    def test_settings_validation_on_load(self):
        """설정 로드 시 검증 테스트"""
        # 유효한 설정으로 로드
        settings = get_settings()
        self.assertIsNotNone(settings)
        
        # 필수 설정 검증 호출
        try:
            settings.validate_required_settings()
        except ValueError:
            self.fail("필수 설정 검증이 실패했습니다")


class TestSettingsErrorHandling(unittest.TestCase):
    """Settings 오류 처리 테스트"""
    
    def test_missing_required_settings_error(self):
        """필수 설정 누락 오류 테스트"""
        # 모든 환경변수 제거
        env_keys_to_remove = ['DB_HOST', 'DB_NAME', 'DB_USER', 'DB_PASSWORD', 
                             'LLM_API_KEY', 'BACKEND_SERVICE_URL']
        
        for key in env_keys_to_remove:
            os.environ.pop(key, None)
        
        # Settings 생성 시 ValidationError 발생 확인
        with self.assertRaises(ValidationError):
            Settings()
    
    def test_invalid_url_validation(self):
        """잘못된 URL 검증 테스트"""
        # 필수 환경변수 설정
        os.environ.update({
            'DB_HOST': 'localhost',
            'DB_NAME': 'test_db',
            'DB_USER': 'test_user',
            'DB_PASSWORD': 'test_password',
            'LLM_API_KEY': 'test_api_key',
            'BACKEND_SERVICE_URL': 'invalid_url'  # 잘못된 URL
        })
        
        with self.assertRaises(ValidationError) as context:
            Settings()
        
        error_str = str(context.exception)
        self.assertIn('backend_service_url', error_str.lower())


if __name__ == '__main__':
    # 로깅 레벨 설정 (테스트 중 로그 출력 최소화)
    import logging
    logging.getLogger().setLevel(logging.WARNING)
    
    # 테스트 실행
    unittest.main(verbosity=2)
