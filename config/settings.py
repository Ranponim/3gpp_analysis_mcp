"""
Configuration Management for 3GPP Cell Performance LLM Analyzer

이 모듈은 애플리케이션의 모든 설정을 타입 안전하게 관리합니다.
환경 변수, 기본값, 검증 등을 Pydantic BaseSettings를 통해 처리합니다.

Usage:
    from config.settings import settings
    
    # 데이터베이스 연결
    db_url = settings.database.url
    
    # LLM API 설정
    api_key = settings.llm.api_key.get_secret_value()
    
    # 로깅 설정
    log_level = settings.app.log_level
"""

from __future__ import annotations
import logging
from typing import Dict, Any, Optional, List, Union
from pathlib import Path

from pydantic import BaseModel, Field, SecretStr, HttpUrl, validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 로깅 설정
logger = logging.getLogger(__name__)

# 프로젝트 루트 디렉토리
PROJECT_ROOT = Path(__file__).parent.parent


class AppConfig(BaseModel):
    """애플리케이션 기본 설정"""
    
    name: str = Field(default="3GPP Analysis MCP", description="애플리케이션 이름")
    version: str = Field(default="1.0.0", description="애플리케이션 버전")
    environment: str = Field(default="development", description="실행 환경 (development, production, testing)")
    debug: bool = Field(default=True, description="디버그 모드 활성화")
    log_level: str = Field(default="INFO", description="로깅 레벨")
    
    @validator('log_level')
    def validate_log_level(cls, v):
        """로깅 레벨 검증"""
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}")
        return v.upper()
    
    @validator('environment')
    def validate_environment(cls, v):
        """환경 검증"""
        valid_envs = ['development', 'production', 'testing']
        if v.lower() not in valid_envs:
            raise ValueError(f"environment must be one of {valid_envs}")
        return v.lower()


class DatabaseConfig(BaseModel):
    """데이터베이스 설정"""
    
    host: str = Field(..., env="DB_HOST", description="데이터베이스 호스트")
    port: int = Field(default=5432, env="DB_PORT", description="데이터베이스 포트")
    name: str = Field(..., env="DB_NAME", description="데이터베이스 이름")
    user: str = Field(..., env="DB_USER", description="데이터베이스 사용자")
    password: SecretStr = Field(..., env="DB_PASSWORD", description="데이터베이스 비밀번호")
    
    # 추가 연결 옵션
    pool_size: int = Field(default=5, env="DB_POOL_SIZE", description="연결 풀 크기")
    max_overflow: int = Field(default=10, env="DB_MAX_OVERFLOW", description="최대 오버플로우 연결")
    pool_timeout: int = Field(default=30, env="DB_POOL_TIMEOUT", description="연결 풀 타임아웃(초)")
    
    @property
    def url(self) -> str:
        """PostgreSQL 연결 URL 생성"""
        return (
            f"postgresql://{self.user}:{self.password.get_secret_value()}"
            f"@{self.host}:{self.port}/{self.name}"
        )
    
    @property
    def async_url(self) -> str:
        """비동기 PostgreSQL 연결 URL 생성"""
        return (
            f"postgresql+asyncpg://{self.user}:{self.password.get_secret_value()}"
            f"@{self.host}:{self.port}/{self.name}"
        )


class LLMConfig(BaseModel):
    """LLM (Large Language Model) 설정"""

    # 기본 LLM 제공업체 설정
    provider: str = Field(default="local", env="LLM_PROVIDER", description="LLM 제공업체")
    api_key: Optional[SecretStr] = Field(default=None, env="LLM_API_KEY", description="LLM API 키")
    model: str = Field(default="Gemma-3-27B", env="LLM_MODEL", description="사용할 모델")

    # API 요청 설정
    max_tokens: int = Field(default=2000, env="LLM_MAX_TOKENS", description="최대 토큰 수")
    temperature: float = Field(default=0.7, env="LLM_TEMPERATURE", description="생성 온도")
    timeout: int = Field(default=60, env="LLM_TIMEOUT", description="API 타임아웃(초)")

    # 재시도 설정
    max_retries: int = Field(default=3, env="LLM_MAX_RETRIES", description="최대 재시도 횟수")
    retry_delay: float = Field(default=1.0, env="LLM_RETRY_DELAY", description="재시도 지연(초)")

    @validator('provider')
    def validate_provider(cls, v):
        """LLM 제공업체 검증"""
        valid_providers = ['openai', 'anthropic', 'google', 'azure', 'local']
        if v.lower() not in valid_providers:
            raise ValueError(f"provider must be one of {valid_providers}")
        return v.lower()

    @validator('temperature')
    def validate_temperature(cls, v):
        """생성 온도 검증"""
        if not 0.0 <= v <= 2.0:
            raise ValueError("temperature must be between 0.0 and 2.0")
        return v

    @model_validator(mode='after')
    def validate_api_key_requirement(self):
        """API 키 요구사항 검증"""
        if self.provider != 'local' and not self.api_key:
            raise ValueError(f"API 키가 필요합니다. provider가 '{self.provider}'일 때는 LLM_API_KEY 환경변수를 설정해야 합니다.")
        return self


class BackendConfig(BaseModel):
    """백엔드 서비스 설정"""
    
    service_url: HttpUrl = Field(..., env="BACKEND_SERVICE_URL", description="백엔드 서비스 URL")
    timeout: int = Field(default=30, env="BACKEND_TIMEOUT", description="요청 타임아웃(초)")
    max_retries: int = Field(default=3, env="BACKEND_MAX_RETRIES", description="최대 재시도 횟수")
    
    # 인증 설정
    auth_token: Optional[SecretStr] = Field(default=None, env="BACKEND_AUTH_TOKEN", description="인증 토큰")
    auth_header: str = Field(default="Authorization", env="BACKEND_AUTH_HEADER", description="인증 헤더 이름")


class TimezoneConfig(BaseModel):
    """시간대 설정"""
    
    app_timezone: str = Field(default="UTC", env="APP_TIMEZONE", description="애플리케이션 기본 시간대")
    data_timezone: str = Field(default="UTC", env="DATA_TIMEZONE", description="데이터 기본 시간대")
    
    # 시간 형식 설정
    datetime_format: str = Field(default="%Y-%m-%d_%H:%M:%S", description="날짜시간 형식")
    date_format: str = Field(default="%Y-%m-%d", description="날짜 형식")
    time_format: str = Field(default="%H:%M:%S", description="시간 형식")
    
    @validator('app_timezone', 'data_timezone')
    def validate_timezone(cls, v):
        """시간대 검증"""
        try:
            import zoneinfo
            zoneinfo.ZoneInfo(v)
            return v
        except Exception:
            # 기본적인 시간대들만 허용
            valid_timezones = ['UTC', 'Asia/Seoul', 'America/New_York', 'Europe/London']
            if v not in valid_timezones:
                logger.warning(f"시간대 {v}를 검증할 수 없습니다. UTC를 사용합니다.")
                return 'UTC'
            return v


class PEGConfig(BaseModel):
    """PEG (Performance Event Group) 계산 설정"""
    
    # 기본 집계 설정
    default_aggregation_method: str = Field(default="average", description="기본 집계 방법")
    default_time_window: str = Field(default="1h", description="기본 시간 윈도우")
    
    # 파생 PEG 정의 (기본값들)
    derived_peg_definitions: Dict[str, str] = Field(
        default_factory=lambda: {
            "success_rate": "response_count/preamble_count*100",
            "drop_rate": "(preamble_count-response_count)/preamble_count*100",
            "efficiency": "response_count/preamble_count"
        },
        description="파생 PEG 수식 정의"
    )
    
    # 계산 옵션
    enable_derived_pegs: bool = Field(default=True, description="파생 PEG 계산 활성화")
    max_formula_complexity: int = Field(default=100, description="최대 수식 복잡도")
    
    @validator('default_aggregation_method')
    def validate_aggregation_method(cls, v):
        """집계 방법 검증"""
        valid_methods = ['sum', 'average', 'mean', 'min', 'max', 'count']
        if v.lower() not in valid_methods:
            raise ValueError(f"aggregation_method must be one of {valid_methods}")
        return v.lower()


class LoggingConfig(BaseModel):
    """로깅 설정"""
    
    level: str = Field(default="INFO", env="LOG_LEVEL", description="로깅 레벨")
    format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        env="LOG_FORMAT",
        description="로그 형식"
    )
    
    # 파일 로깅 설정
    file_enabled: bool = Field(default=False, env="LOG_FILE_ENABLED", description="파일 로깅 활성화")
    file_path: str = Field(default="logs/app.log", env="LOG_FILE_PATH", description="로그 파일 경로")
    file_max_size: int = Field(default=10485760, env="LOG_FILE_MAX_SIZE", description="로그 파일 최대 크기(바이트)")
    file_backup_count: int = Field(default=5, env="LOG_FILE_BACKUP_COUNT", description="로그 파일 백업 개수")
    
    # 콘솔 로깅 설정
    console_enabled: bool = Field(default=True, env="LOG_CONSOLE_ENABLED", description="콘솔 로깅 활성화")


class Settings(BaseSettings):
    """
    메인 설정 클래스
    
    모든 애플리케이션 설정을 통합 관리합니다.
    환경 변수와 .env 파일에서 설정을 로드하며,
    타입 안전성과 검증을 제공합니다.
    """
    
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore',  # 정의되지 않은 환경 변수 무시
        case_sensitive=False,  # 환경 변수 대소문자 구분 안함
    )
    
    # 애플리케이션 기본 설정
    app_name: str = Field(default="3GPP Analysis MCP", env="APP_NAME")
    app_version: str = Field(default="1.0.0", env="APP_VERSION")
    app_environment: str = Field(default="development", env="APP_ENVIRONMENT")
    app_debug: bool = Field(default=True, env="APP_DEBUG")
    app_log_level: str = Field(default="INFO", env="APP_LOG_LEVEL")
    
    # 데이터베이스 설정
    db_host: str = Field(..., env="DB_HOST")
    db_port: int = Field(default=5432, env="DB_PORT")
    db_name: str = Field(..., env="DB_NAME")
    db_user: str = Field(..., env="DB_USER")
    db_password: SecretStr = Field(..., env="DB_PASSWORD")
    db_pool_size: int = Field(default=5, env="DB_POOL_SIZE")
    
    # LLM 설정
    llm_provider: str = Field(default="local", env="LLM_PROVIDER")
    llm_api_key: Optional[SecretStr] = Field(default=None, env="LLM_API_KEY")
    llm_model: str = Field(default="Gemma-3-27B", env="LLM_MODEL")
    llm_max_tokens: int = Field(default=2000, env="LLM_MAX_TOKENS")
    llm_temperature: float = Field(default=0.7, env="LLM_TEMPERATURE")
    llm_timeout: int = Field(default=60, env="LLM_TIMEOUT")
    llm_max_retries: int = Field(default=3, env="LLM_MAX_RETRIES")
    llm_retry_delay: float = Field(default=1.0, env="LLM_RETRY_DELAY")
    
    # 백엔드 서비스 설정
    backend_service_url: HttpUrl = Field(..., env="BACKEND_SERVICE_URL")
    backend_timeout: int = Field(default=30, env="BACKEND_TIMEOUT")
    backend_auth_token: Optional[SecretStr] = Field(default=None, env="BACKEND_AUTH_TOKEN")
    
    # 시간대 설정
    app_timezone: str = Field(default="UTC", env="APP_TIMEZONE")
    data_timezone: str = Field(default="UTC", env="DATA_TIMEZONE")
    datetime_format: str = Field(default="%Y-%m-%d_%H:%M:%S", env="DATETIME_FORMAT")
    date_format: str = Field(default="%Y-%m-%d", env="DATE_FORMAT")
    time_format: str = Field(default="%H:%M:%S", env="TIME_FORMAT")
    
    # PEG 계산 설정
    peg_default_aggregation: str = Field(default="average", env="PEG_DEFAULT_AGGREGATION")
    peg_enable_derived: bool = Field(default=True, env="PEG_ENABLE_DERIVED")
    peg_default_time_window: str = Field(default="1h", env="PEG_DEFAULT_TIME_WINDOW")
    peg_max_formula_complexity: int = Field(default=100, env="PEG_MAX_FORMULA_COMPLEXITY")
    peg_use_choi: bool = Field(default=False, env="PEG_USE_CHOI")

    # CSV 기반 PEG 필터링 설정
    peg_filter_enabled: bool = Field(default=False, env="PEG_FILTER_ENABLED", description="CSV 필터링 활성화")
    peg_filter_dir_path: str = Field(default="config/peg_filters/", env="PEG_FILTER_DIR_PATH", description="PEG 필터 CSV 파일 디렉토리")
    peg_filter_default_file: str = Field(default="default.csv", env="PEG_FILTER_DEFAULT_FILE", description="기본 PEG 필터 파일명")
    
    # JSONB 파싱 설정
    jsonb_max_recursion_depth: int = Field(default=5, env="JSONB_MAX_RECURSION_DEPTH", description="JSONB 재귀 파싱 최대 깊이")
    
    # 로깅 설정
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_file_enabled: bool = Field(default=False, env="LOG_FILE_ENABLED")
    log_file_path: str = Field(default="logs/app.log", env="LOG_FILE_PATH")
    
    # 검증 메서드들
    @validator('app_log_level', 'log_level')
    def validate_log_level(cls, v):
        """로깅 레벨 검증"""
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}")
        return v.upper()
    
    @validator('app_environment')
    def validate_environment(cls, v):
        """환경 검증"""
        valid_envs = ['development', 'production', 'testing']
        if v.lower() not in valid_envs:
            raise ValueError(f"environment must be one of {valid_envs}")
        return v.lower()
    
    @validator('llm_provider')
    def validate_llm_provider(cls, v):
        """LLM 제공업체 검증"""
        valid_providers = ['openai', 'anthropic', 'google', 'azure', 'local']
        if v.lower() not in valid_providers:
            raise ValueError(f"llm_provider must be one of {valid_providers}")
        return v.lower()
    
    @validator('llm_temperature')
    def validate_temperature(cls, v):
        """생성 온도 검증"""
        if not 0.0 <= v <= 2.0:
            raise ValueError("llm_temperature must be between 0.0 and 2.0")
        return v
    
    @validator('peg_default_aggregation')
    def validate_aggregation_method(cls, v):
        """집계 방법 검증"""
        valid_methods = ['sum', 'average', 'mean', 'min', 'max', 'count']
        if v.lower() not in valid_methods:
            raise ValueError(f"peg_default_aggregation must be one of {valid_methods}")
        return v.lower()
    
    @validator('db_port', 'backend_timeout', 'llm_timeout', 'llm_max_retries', 'peg_max_formula_complexity', 'jsonb_max_recursion_depth')
    def validate_positive_integer(cls, v):
        """양수 검증"""
        if v <= 0:
            raise ValueError("Value must be a positive integer")
        return v
    
    @validator('llm_retry_delay')
    def validate_positive_float(cls, v):
        """양수 실수 검증"""
        if v <= 0.0:
            raise ValueError("Value must be a positive number")
        return v
    
    @validator('app_timezone', 'data_timezone')
    def validate_timezone(cls, v):
        """시간대 검증 (기본적인 시간대만 허용)"""
        valid_timezones = ['UTC', 'Asia/Seoul', 'America/New_York', 'Europe/London', 
                          'Asia/Tokyo', 'America/Los_Angeles', 'Europe/Berlin']
        if v not in valid_timezones:
            import warnings
            warnings.warn(f"시간대 {v}가 검증되지 않았습니다. 지원되는 시간대: {valid_timezones}")
        return v
    
    @model_validator(mode='after')
    def validate_production_settings(self):
        """프로덕션 환경 특별 검증"""
        if self.app_environment == 'production':
            # 프로덕션에서는 디버그 모드 비활성화 권장
            if self.app_debug:
                import warnings
                warnings.warn("Debug mode is enabled in production environment")

            # 프로덕션에서는 강력한 비밀번호 권장
            if len(self.db_password.get_secret_value()) < 8:
                import warnings
                warnings.warn("Database password should be at least 8 characters in production")

        return self

    @model_validator(mode='after')
    def validate_llm_api_key_requirement(self):
        """LLM API 키 요구사항 검증"""
        if self.llm_provider != 'local' and not self.llm_api_key:
            raise ValueError(f"API 키가 필요합니다. provider가 '{self.llm_provider}'일 때는 LLM_API_KEY 환경변수를 설정해야 합니다.")
        return self
    
    def __init__(self, **kwargs):
        """초기화 및 검증"""
        super().__init__(**kwargs)
        logger.info("설정 로드 완료: 환경=%s, 디버그=%s", self.app_environment, self.app_debug)
    
    def get_database_url(self, async_mode: bool = False) -> str:
        """데이터베이스 연결 URL 반환"""
        password = self.db_password.get_secret_value()
        if async_mode:
            return f"postgresql+asyncpg://{self.db_user}:{password}@{self.db_host}:{self.db_port}/{self.db_name}"
        else:
            return f"postgresql://{self.db_user}:{password}@{self.db_host}:{self.db_port}/{self.db_name}"
    
    def get_llm_api_key(self) -> str:
        """LLM API 키 반환 (보안 해제)"""
        return self.llm_api_key.get_secret_value()
    
    def get_backend_auth_header(self) -> Dict[str, str]:
        """백엔드 인증 헤더 반환"""
        if self.backend_auth_token:
            return {
                "Authorization": f"Bearer {self.backend_auth_token.get_secret_value()}"
            }
        return {}
    
    def get_peg_config_dict(self) -> Dict[str, Any]:
        """PEG 설정을 딕셔너리로 반환"""
        return {
            "default_aggregation_method": self.peg_default_aggregation,
            "enable_derived_pegs": self.peg_enable_derived,
            "default_time_window": self.peg_default_time_window,
            "max_formula_complexity": self.peg_max_formula_complexity,
            "jsonb_max_recursion_depth": self.jsonb_max_recursion_depth,
            "derived_peg_definitions": {
                "success_rate": "response_count/preamble_count*100",
                "drop_rate": "(preamble_count-response_count)/preamble_count*100",
                "efficiency": "response_count/preamble_count"
            }
        }
    
    def get_llm_config_dict(self) -> Dict[str, Any]:
        """LLM 설정을 딕셔너리로 반환 (API 키 제외)"""
        return {
            "provider": self.llm_provider,
            "model": self.llm_model,
            "max_tokens": self.llm_max_tokens,
            "temperature": self.llm_temperature,
            "timeout": self.llm_timeout,
            "max_retries": self.llm_max_retries,
            "retry_delay": self.llm_retry_delay
        }
    
    def get_timezone_config_dict(self) -> Dict[str, Any]:
        """시간대 설정을 딕셔너리로 반환"""
        return {
            "app_timezone": self.app_timezone,
            "data_timezone": self.data_timezone,
            "datetime_format": self.datetime_format,
            "date_format": self.date_format,
            "time_format": self.time_format
        }
    
    def is_production(self) -> bool:
        """프로덕션 환경 여부 확인"""
        return self.app_environment == 'production'
    
    def is_development(self) -> bool:
        """개발 환경 여부 확인"""
        return self.app_environment == 'development'
    
    def setup_logging(self) -> None:
        """로깅 설정 적용"""
        # 기본 로깅 설정
        log_level = getattr(logging, self.log_level.upper())
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        
        # 파일 로깅 설정 (필요시)
        if self.log_file_enabled:
            from logging.handlers import RotatingFileHandler
            import os
            
            # 로그 디렉토리 생성
            log_dir = Path(self.log_file_path).parent
            log_dir.mkdir(parents=True, exist_ok=True)
            
            # 파일 핸들러 추가
            file_handler = RotatingFileHandler(
                filename=self.log_file_path,
                maxBytes=10485760,  # 10MB
                backupCount=5,
                encoding='utf-8'
            )
            file_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
            
            root_logger = logging.getLogger()
            root_logger.addHandler(file_handler)
        
        logger.info("로깅 설정 완료: 레벨=%s, 파일로깅=%s", 
                   self.log_level, self.log_file_enabled)
    
    def validate_required_settings(self) -> None:
        """필수 설정 검증"""
        required_checks = [
            (self.db_host, "DB_HOST"),
            (self.db_name, "DB_NAME"),
            (self.db_user, "DB_USER"),
            (self.db_password.get_secret_value(), "DB_PASSWORD"),
            (str(self.backend_service_url), "BACKEND_SERVICE_URL"),
        ]

        # local provider가 아닐 때만 LLM API 키 검증
        if self.llm_provider != 'local':
            required_checks.append((self.llm_api_key.get_secret_value(), "LLM_API_KEY"))

        missing_settings = []
        for value, setting_name in required_checks:
            if not value or str(value).strip() == '':
                missing_settings.append(setting_name)

        if missing_settings:
            raise ValueError(
                f"필수 환경 변수가 설정되지 않았습니다: {', '.join(missing_settings)}"
            )

        logger.info("필수 설정 검증 완료")
    
    def to_dict(self, exclude_secrets: bool = True) -> Dict[str, Any]:
        """설정을 딕셔너리로 변환"""
        data = self.dict()
        
        # 비밀 정보 제외 처리
        if exclude_secrets:
            for key, value in data.items():
                if isinstance(value, SecretStr):
                    data[key] = "***"
                elif 'password' in key.lower() or 'token' in key.lower() or 'key' in key.lower():
                    data[key] = "***"
        
        return data


# 전역 설정 인스턴스 (지연 로딩)
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """
    전역 설정 인스턴스 반환
    
    애플리케이션 전반에서 사용할 수 있는 설정 인스턴스를 반환합니다.
    처음 호출 시에만 인스턴스를 생성하고, 이후에는 캐시된 인스턴스를 반환합니다.
    
    Returns:
        Settings: 설정 인스턴스
        
    Raises:
        ValueError: 필수 환경 변수가 누락된 경우
    """
    global _settings
    
    if _settings is None:
        logger.info("설정 인스턴스 생성 중...")
        _settings = Settings()
        _settings.validate_required_settings()
        _settings.setup_logging()
        logger.info("설정 인스턴스 생성 완료")
    
    return _settings


def reload_settings() -> Settings:
    """
    설정 인스턴스 재로드
    
    환경 변수가 변경된 경우 설정을 다시 로드합니다.
    주로 테스트나 개발 중에 사용됩니다.
    
    Returns:
        Settings: 새로운 설정 인스턴스
    """
    global _settings
    logger.info("설정 인스턴스 재로드 중...")
    _settings = None
    return get_settings()


# 편의를 위한 전역 설정 인스턴스 (import 시 자동 로드되지 않음)
# 사용법: from config.settings import settings
# settings = get_settings()  # 명시적 호출 필요
