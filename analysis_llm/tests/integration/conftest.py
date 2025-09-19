"""
Integration Test Configuration

통합 테스트를 위한 pytest fixtures와 설정을 제공합니다.
"""

import os
import sys
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest

# 프로젝트 루트를 Python path에 추가
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)


@pytest.fixture
def mock_db_config():
    """Mock 데이터베이스 설정"""
    return {
        'db_host': 'integration_test_host',
        'db_port': 5432,
        'db_name': 'integration_test_db',
        'db_user': 'integration_user',
        'db_password': 'integration_pass'
    }


@pytest.fixture
def mock_llm_config():
    """Mock LLM 설정"""
    return {
        'llm_api_key': 'integration-test-api-key',
        'llm_provider': 'openai',
        'llm_model': 'gpt-3.5-turbo',
        'llm_max_tokens': 8000,
        'llm_temperature': 0.7
    }


@pytest.fixture
def sample_peg_data():
    """샘플 PEG 데이터"""
    return [
        {
            'datetime': datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            'peg_name': 'preamble_count',
            'value': 1000.0,
            'ne': 'nvgnb#10000',
            'cellid': '2010'
        },
        {
            'datetime': datetime(2025, 1, 1, 11, 0, tzinfo=timezone.utc),
            'peg_name': 'response_count',
            'value': 950.0,
            'ne': 'nvgnb#10000',
            'cellid': '2010'
        },
        {
            'datetime': datetime(2025, 1, 2, 10, 0, tzinfo=timezone.utc),
            'peg_name': 'preamble_count',
            'value': 1100.0,
            'ne': 'nvgnb#10000',
            'cellid': '2010'
        },
        {
            'datetime': datetime(2025, 1, 2, 11, 0, tzinfo=timezone.utc),
            'peg_name': 'response_count',
            'value': 1000.0,
            'ne': 'nvgnb#10000',
            'cellid': '2010'
        }
    ]


@pytest.fixture
def sample_analysis_request():
    """샘플 분석 요청"""
    return {
        "n_minus_1": "2025-01-01_09:00~2025-01-01_18:00",
        "n": "2025-01-02_09:00~2025-01-02_18:00",
        "output_dir": "./integration_test_output",
        "table": "summary",
        "analysis_type": "enhanced",
        "enable_mock": True,
        "max_prompt_tokens": 8000,
        "db": {
            "host": "integration_test_host",
            "port": 5432,
            "dbname": "integration_test_db",
            "user": "integration_user",
            "password": "integration_pass"
        },
        "filters": {
            "ne": "nvgnb#10000",
            "cellid": ["2010", "2011"],
            "host": "192.168.1.1"
        },
        "selected_pegs": ["preamble_count", "response_count"],
        "peg_definitions": {
            "success_rate": "response_count/preamble_count*100"
        }
    }


@pytest.fixture
def mock_llm_response():
    """Mock LLM API 응답"""
    return {
        'summary': '통합 테스트: 성능이 전반적으로 개선되었습니다.',
        'key_insights': 'Preamble count가 10% 증가하고 Response count가 5.26% 증가했습니다.',
        'recommendations': '현재 네트워크 설정을 유지하고 모니터링을 계속하세요.',
        'model_used': 'gpt-3.5-turbo',
        'tokens_used': 250,
        'confidence_score': 0.88
    }


@pytest.fixture
def mock_database_repository():
    """Mock DatabaseRepository fixture"""
    mock_repo = Mock()
    
    # fetch_peg_data 메서드 Mock 설정
    import pandas as pd
    mock_df = pd.DataFrame([
        {'datetime': datetime(2025, 1, 1, 10, 0), 'peg_name': 'preamble_count', 'value': 1000.0, 'period': 'N-1'},
        {'datetime': datetime(2025, 1, 1, 11, 0), 'peg_name': 'response_count', 'value': 950.0, 'period': 'N-1'},
        {'datetime': datetime(2025, 1, 2, 10, 0), 'peg_name': 'preamble_count', 'value': 1100.0, 'period': 'N'},
        {'datetime': datetime(2025, 1, 2, 11, 0), 'peg_name': 'response_count', 'value': 1000.0, 'period': 'N'}
    ])
    mock_repo.fetch_peg_data.return_value = mock_df
    
    # 기타 메서드들
    mock_repo.test_connection.return_value = True
    mock_repo.close.return_value = None
    
    return mock_repo


@pytest.fixture
def mock_llm_repository():
    """Mock LLMRepository fixture"""
    mock_repo = Mock()
    
    # analyze_data 메서드 Mock 설정
    mock_repo.analyze_data.return_value = {
        'summary': 'Mock LLM 분석 결과',
        'key_insights': 'Mock 인사이트',
        'recommendations': 'Mock 권고사항',
        'model_used': 'mock-gpt-3.5-turbo',
        'tokens_used': 200
    }
    
    # 기타 메서드들
    mock_repo.estimate_tokens.return_value = 150
    mock_repo.validate_prompt.return_value = True
    mock_repo.test_connection.return_value = True
    
    return mock_repo


@pytest.fixture
def integration_test_logger():
    """통합 테스트용 로거"""
    import logging

    # 통합 테스트 전용 로거 설정
    logger = logging.getLogger('integration_test')
    logger.setLevel(logging.INFO)
    
    # 핸들러가 없으면 추가
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger


@pytest.fixture
def mock_environment_variables():
    """Mock 환경변수 설정"""
    mock_env = {
        'DB_HOST': 'integration_test_host',
        'DB_NAME': 'integration_test_db',
        'DB_USER': 'integration_user',
        'DB_PASSWORD': 'integration_pass',
        'LLM_API_KEY': 'integration-test-key',
        'BACKEND_SERVICE_URL': 'http://localhost:8000/integration-test',
        'APP_ENV': 'integration_test',
        'ENABLE_MOCK_MODE': 'true'
    }
    
    with patch.dict(os.environ, mock_env):
        yield mock_env


@pytest.fixture
def mock_time_ranges():
    """Mock 시간 범위 데이터"""
    from models import TimeRange
    
    n_minus_1_range = TimeRange(
        start=datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc),
        end=datetime(2025, 1, 1, 18, 0, tzinfo=timezone.utc)
    )
    
    n_range = TimeRange(
        start=datetime(2025, 1, 2, 9, 0, tzinfo=timezone.utc),
        end=datetime(2025, 1, 2, 18, 0, tzinfo=timezone.utc)
    )
    
    return {
        'n_minus_1': n_minus_1_range,
        'n': n_range
    }
