"""
Configuration package for 3GPP Cell Performance LLM Analyzer

이 패키지는 애플리케이션의 모든 설정 관리를 담당합니다.

Usage:
    # 기본 사용법
    from config import get_settings
    
    settings = get_settings()
    
    # 데이터베이스 연결
    db_url = settings.get_database_url()
    
    # LLM API 키
    api_key = settings.get_llm_api_key()
    
    # 개별 설정 섹션 접근
    log_level = settings.app.log_level
    db_host = settings.database.host
    llm_model = settings.llm.model
"""

from .settings import (
    Settings,
    AppConfig,
    DatabaseConfig,
    LLMConfig,
    BackendConfig,
    TimezoneConfig,
    PEGConfig,
    LoggingConfig,
    get_settings,
    reload_settings,
)

# 편의를 위한 __all__ 정의
__all__ = [
    # 메인 설정 클래스
    'Settings',
    
    # 개별 설정 모델들
    'AppConfig',
    'DatabaseConfig',
    'LLMConfig',
    'BackendConfig',
    'TimezoneConfig',
    'PEGConfig',
    'LoggingConfig',
    
    # 설정 인스턴스 관리 함수들
    'get_settings',
    'reload_settings',
]

# 버전 정보
__version__ = "1.0.0"
