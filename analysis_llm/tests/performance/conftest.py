"""
Performance Test Configuration

성능 테스트를 위한 pytest fixtures와 설정을 제공합니다.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

# 프로젝트 루트를 Python path에 추가
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)


@pytest.fixture
def large_peg_dataset():
    """대용량 PEG 데이터셋 생성 (성능 테스트용)"""
    # 1000개 데이터 포인트 생성
    base_time = datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc)
    
    data = []
    peg_names = ['preamble_count', 'response_count', 'success_count', 'failure_count', 'handover_count']
    cell_ids = [f'cell_{i:03d}' for i in range(1, 21)]  # 20개 셀
    ne_list = [f'nvgnb#{10000 + i}' for i in range(1, 11)]  # 10개 NE
    
    # N-1 기간 데이터 (500개)
    for i in range(500):
        data.append({
            'datetime': base_time + timedelta(minutes=i*2),
            'peg_name': np.random.choice(peg_names),
            'value': np.random.normal(1000, 200),  # 평균 1000, 표준편차 200
            'ne': np.random.choice(ne_list),
            'cellid': np.random.choice(cell_ids),
            'host': f'192.168.1.{np.random.randint(1, 255)}',
            'period': 'N-1'
        })
    
    # N 기간 데이터 (500개)
    n_base_time = base_time + timedelta(days=1)
    for i in range(500):
        data.append({
            'datetime': n_base_time + timedelta(minutes=i*2),
            'peg_name': np.random.choice(peg_names),
            'value': np.random.normal(1100, 220),  # 약간 증가한 평균
            'ne': np.random.choice(ne_list),
            'cellid': np.random.choice(cell_ids),
            'host': f'192.168.1.{np.random.randint(1, 255)}',
            'period': 'N'
        })
    
    return pd.DataFrame(data)


@pytest.fixture
def performance_analysis_request():
    """성능 테스트용 분석 요청"""
    return {
        "n_minus_1": "2025-01-01_09:00~2025-01-01_18:00",
        "n": "2025-01-02_09:00~2025-01-02_18:00",
        "output_dir": "./performance_test_output",
        "table": "summary",
        "analysis_type": "enhanced",
        "enable_mock": True,
        "max_prompt_tokens": 8000,
        "db": {
            "host": "performance_test_host",
            "port": 5432,
            "dbname": "performance_test_db",
            "user": "performance_user",
            "password": "performance_pass"
        },
        "filters": {
            "ne": f"nvgnb#1000{np.random.randint(1, 10)}",
            "cellid": [f"cell_{i:03d}" for i in range(1, 6)],  # 5개 셀 선택
            "host": "192.168.1.100"
        },
        "selected_pegs": ["preamble_count", "response_count", "success_count"],
        "peg_definitions": {
            "success_rate": "response_count/preamble_count*100",
            "efficiency_ratio": "success_count/response_count*100"
        }
    }


@pytest.fixture
def mock_performance_database_repository():
    """성능 테스트용 Mock DatabaseRepository"""
    from unittest.mock import Mock
    
    mock_repo = Mock()
    
    def generate_performance_data(*args, **kwargs):
        """동적으로 성능 테스트 데이터 생성"""
        # 실제 시나리오를 시뮬레이션하는 대용량 데이터
        return generate_large_dataframe(size=1000)
    
    mock_repo.fetch_peg_data.side_effect = generate_performance_data
    mock_repo.test_connection.return_value = True
    mock_repo.close.return_value = None
    
    return mock_repo


@pytest.fixture
def mock_performance_llm_repository():
    """성능 테스트용 Mock LLMRepository"""
    from unittest.mock import Mock
    
    mock_repo = Mock()
    
    def generate_llm_response(*args, **kwargs):
        """성능 테스트용 LLM 응답 생성"""
        return {
            'summary': '성능 테스트: 대용량 데이터 분석 완료. 전반적인 성능 개선이 관찰됨.',
            'key_insights': '1000개 데이터포인트 처리 완료. 평균 응답시간 개선.',
            'recommendations': '현재 최적화 상태 유지. 추가 모니터링 권장.',
            'model_used': 'performance-test-model',
            'tokens_used': 350
        }
    
    mock_repo.analyze_data.side_effect = generate_llm_response
    mock_repo.estimate_tokens.return_value = 200
    mock_repo.validate_prompt.return_value = True
    mock_repo.test_connection.return_value = True
    
    return mock_repo


def generate_large_dataframe(size: int = 1000) -> pd.DataFrame:
    """대용량 DataFrame 생성 함수"""
    np.random.seed(42)  # 재현 가능한 결과를 위한 시드 설정
    
    base_time = datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc)
    
    data = {
        'datetime': [base_time + timedelta(minutes=i) for i in range(size)],
        'peg_name': np.random.choice(['preamble_count', 'response_count', 'success_count'], size),
        'value': np.random.normal(1000, 200, size),
        'ne': np.random.choice([f'nvgnb#{10000+i}' for i in range(10)], size),
        'cellid': np.random.choice([f'cell_{i:03d}' for i in range(20)], size),
        'host': np.random.choice([f'192.168.1.{i}' for i in range(1, 11)], size)
    }
    
    return pd.DataFrame(data)


@pytest.fixture
def performance_logger():
    """성능 테스트용 로거"""
    import logging

    # 성능 테스트 전용 로거 설정
    logger = logging.getLogger('performance_test')
    logger.setLevel(logging.INFO)
    
    # 핸들러가 없으면 추가
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - PERFORMANCE - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger


@pytest.fixture
def benchmark_environment():
    """벤치마킹 환경 설정"""
    import platform

    import psutil

    # 시스템 정보 수집
    system_info = {
        'cpu_count': psutil.cpu_count(),
        'memory_total_gb': psutil.virtual_memory().total / (1024**3),
        'platform': platform.platform(),
        'python_version': platform.python_version(),
        'architecture': platform.architecture()[0]
    }
    
    return system_info


@pytest.fixture
def memory_tracker():
    """메모리 사용량 추적용 fixture"""
    import os

    import psutil
    
    process = psutil.Process(os.getpid())
    
    class MemoryTracker:
        def __init__(self):
            self.initial_memory = process.memory_info().rss / 1024 / 1024  # MB
            self.peak_memory = self.initial_memory
            
        def update_peak(self):
            current_memory = process.memory_info().rss / 1024 / 1024  # MB
            if current_memory > self.peak_memory:
                self.peak_memory = current_memory
            return current_memory
            
        def get_memory_usage(self):
            current_memory = process.memory_info().rss / 1024 / 1024  # MB
            return {
                'initial_mb': self.initial_memory,
                'current_mb': current_memory,
                'peak_mb': self.peak_memory,
                'increase_mb': current_memory - self.initial_memory
            }
    
    return MemoryTracker()
