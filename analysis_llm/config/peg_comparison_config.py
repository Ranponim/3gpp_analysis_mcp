"""
PEG 비교분석 설정 관리 모듈

이 모듈은 PEG(Performance Engineering Guidelines) 비교분석에 필요한
모든 설정값들을 중앙에서 관리합니다. 환경변수, 기본값, 그리고
런타임 설정을 통합적으로 처리합니다.

Author: KPI Dashboard Team
Created: 2024-01-15
Version: 1.0.0
"""

import os
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum

# 로거 설정
logger = logging.getLogger(__name__)


class TrendThreshold(Enum):
    """트렌드 판정 임계값 열거형"""
    STABLE = 5.0  # 5% 이하는 안정으로 판정
    SIGNIFICANT = 10.0  # 10% 이상은 중간 유의성
    HIGHLY_SIGNIFICANT = 20.0  # 20% 이상은 높은 유의성


class DataQualityLevel(Enum):
    """데이터 품질 레벨 열거형"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AlgorithmVersion(Enum):
    """알고리즘 버전 열거형"""
    V1_0_0 = "v1.0.0"
    V2_0_0 = "v2.0.0"
    V2_1_0 = "v2.1.0"
    CURRENT = V2_1_0


@dataclass
class PerformanceConfig:
    """성능 관련 설정"""
    # 메모리 관리
    max_memory_usage_mb: int = 512
    chunk_size: int = 1000
    max_concurrent_tasks: int = 4
    
    # 처리 시간 제한
    max_processing_time_seconds: float = 300.0  # 5분
    timeout_seconds: float = 30.0
    
    # 캐시 설정
    cache_ttl_seconds: int = 3600  # 1시간
    max_cache_size_mb: int = 100
    
    def __post_init__(self):
        """설정값 검증"""
        if self.max_memory_usage_mb <= 0:
            raise ValueError("최대 메모리 사용량은 0보다 커야 합니다")
        if self.chunk_size <= 0:
            raise ValueError("청크 크기는 0보다 커야 합니다")
        if self.max_concurrent_tasks <= 0:
            raise ValueError("최대 동시 작업 수는 0보다 커야 합니다")
        
        logger.debug(f"성능 설정 초기화 완료: 메모리 {self.max_memory_usage_mb}MB, 청크 {self.chunk_size}")


@dataclass
class ValidationConfig:
    """데이터 검증 관련 설정"""
    # 필수 필드
    required_fields: list = field(default_factory=lambda: [
        'kpi_name', 'period', 'avg', 'cell_id'
    ])
    
    # 유효한 기간값
    valid_periods: list = field(default_factory=lambda: ['N-1', 'N'])
    
    # 값 범위 제한
    min_avg_value: float = 0.0
    max_avg_value: float = 1000000.0
    
    # 가중치 범위
    min_weight: int = 1
    max_weight: int = 10
    
    # 이상치 탐지 설정
    outlier_detection_enabled: bool = True
    outlier_iqr_multiplier: float = 1.5
    min_data_points_for_outlier: int = 3
    
    def __post_init__(self):
        """설정값 검증"""
        if self.min_avg_value < 0:
            raise ValueError("최소 평균값은 0 이상이어야 합니다")
        if self.max_avg_value <= self.min_avg_value:
            raise ValueError("최대 평균값은 최소 평균값보다 커야 합니다")
        if self.min_weight < 1 or self.max_weight > 10:
            raise ValueError("가중치 범위는 1-10 사이여야 합니다")
        
        logger.debug(f"검증 설정 초기화 완료: 평균값 범위 {self.min_avg_value}-{self.max_avg_value}")


@dataclass
class AnalysisConfig:
    """분석 알고리즘 관련 설정"""
    # 트렌드 판정 임계값
    trend_threshold_percent: float = TrendThreshold.STABLE.value
    significant_threshold_percent: float = TrendThreshold.SIGNIFICANT.value
    highly_significant_threshold_percent: float = TrendThreshold.HIGHLY_SIGNIFICANT.value
    
    # 신뢰도 설정
    default_confidence: float = 0.85
    min_confidence: float = 0.0
    max_confidence: float = 1.0
    
    # 통계 계산 설정
    use_sample_std: bool = True  # 표본 표준편차 사용 여부
    rsd_calculation_method: str = "standard"  # "standard" 또는 "robust"
    
    # 데이터 품질 평가 기준
    high_quality_rsd_threshold: float = 5.0  # RSD 5% 이하는 고품질
    medium_quality_rsd_threshold: float = 15.0  # RSD 15% 이하는 중품질
    
    def __post_init__(self):
        """설정값 검증"""
        if not (0 < self.trend_threshold_percent < 100):
            raise ValueError("트렌드 임계값은 0-100% 사이여야 합니다")
        if not (0 < self.significant_threshold_percent < 100):
            raise ValueError("유의성 임계값은 0-100% 사이여야 합니다")
        if not (0 < self.highly_significant_threshold_percent < 100):
            raise ValueError("높은 유의성 임계값은 0-100% 사이여야 합니다")
        
        if self.trend_threshold_percent >= self.significant_threshold_percent:
            raise ValueError("트렌드 임계값은 유의성 임계값보다 작아야 합니다")
        if self.significant_threshold_percent >= self.highly_significant_threshold_percent:
            raise ValueError("유의성 임계값은 높은 유의성 임계값보다 작아야 합니다")
        
        logger.debug(f"분석 설정 초기화 완료: 트렌드 임계값 {self.trend_threshold_percent}%")


@dataclass
class LoggingConfig:
    """로깅 관련 설정"""
    # 로그 레벨
    log_level: str = "INFO"
    
    # 로그 포맷
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # 로그 파일 설정
    enable_file_logging: bool = False
    log_file_path: str = "logs/peg_comparison.log"
    max_log_file_size_mb: int = 10
    backup_count: int = 5
    
    # 성능 메트릭 로깅
    enable_performance_logging: bool = True
    performance_log_interval_seconds: int = 60
    
    def __post_init__(self):
        """설정값 검증"""
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if self.log_level.upper() not in valid_levels:
            raise ValueError(f"로그 레벨은 {valid_levels} 중 하나여야 합니다")
        
        if self.max_log_file_size_mb <= 0:
            raise ValueError("최대 로그 파일 크기는 0보다 커야 합니다")
        if self.backup_count < 0:
            raise ValueError("백업 개수는 0 이상이어야 합니다")
        
        logger.debug(f"로깅 설정 초기화 완료: 레벨 {self.log_level}")


@dataclass
class CacheConfig:
    """캐시 관련 설정"""
    # 캐시 활성화 여부
    enabled: bool = True
    
    # 캐시 백엔드
    backend: str = "memory"  # "memory", "redis", "file"
    
    # Redis 설정 (backend가 redis일 때)
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None
    
    # 파일 캐시 설정 (backend가 file일 때)
    cache_dir: str = "cache/peg_comparison"
    
    # TTL 설정
    default_ttl_seconds: int = 3600  # 1시간
    result_ttl_seconds: int = 7200  # 2시간
    metadata_ttl_seconds: int = 1800  # 30분
    
    def __post_init__(self):
        """설정값 검증"""
        valid_backends = ['memory', 'redis', 'file']
        if self.backend not in valid_backends:
            raise ValueError(f"캐시 백엔드는 {valid_backends} 중 하나여야 합니다")
        
        if self.redis_port <= 0 or self.redis_port > 65535:
            raise ValueError("Redis 포트는 1-65535 사이여야 합니다")
        if self.redis_db < 0:
            raise ValueError("Redis DB 번호는 0 이상이어야 합니다")
        
        logger.debug(f"캐시 설정 초기화 완료: 백엔드 {self.backend}")


class PEGComparisonConfig:
    """
    PEG 비교분석 통합 설정 클래스
    
    모든 설정을 중앙에서 관리하고 환경변수와 기본값을 통합합니다.
    """
    
    def __init__(self):
        """설정 초기화"""
        logger.info("PEG 비교분석 설정 초기화 시작")
        
        # 환경변수에서 설정값 로드
        self._load_from_environment()
        
        # 각 설정 카테고리 초기화
        self.performance = PerformanceConfig()
        self.validation = ValidationConfig()
        self.analysis = AnalysisConfig()
        self.logging = LoggingConfig()
        self.cache = CacheConfig()
        
        # 알고리즘 버전 설정
        self.algorithm_version = AlgorithmVersion.CURRENT.value
        
        # 전체 설정 검증
        self._validate_config()
        
        logger.info(f"PEG 비교분석 설정 초기화 완료: 버전 {self.algorithm_version}")
    
    def _load_from_environment(self):
        """환경변수에서 설정값 로드"""
        logger.debug("환경변수에서 설정값 로드 중")
        
        # 환경변수 매핑
        env_mappings = {
            # 성능 설정
            'PEG_MAX_MEMORY_MB': ('performance', 'max_memory_usage_mb', int),
            'PEG_CHUNK_SIZE': ('performance', 'chunk_size', int),
            'PEG_MAX_CONCURRENT_TASKS': ('performance', 'max_concurrent_tasks', int),
            'PEG_MAX_PROCESSING_TIME': ('performance', 'max_processing_time_seconds', float),
            'PEG_TIMEOUT': ('performance', 'timeout_seconds', float),
            
            # 분석 설정
            'PEG_TREND_THRESHOLD': ('analysis', 'trend_threshold_percent', float),
            'PEG_SIGNIFICANT_THRESHOLD': ('analysis', 'significant_threshold_percent', float),
            'PEG_HIGHLY_SIGNIFICANT_THRESHOLD': ('analysis', 'highly_significant_threshold_percent', float),
            'PEG_DEFAULT_CONFIDENCE': ('analysis', 'default_confidence', float),
            
            # 로깅 설정
            'PEG_LOG_LEVEL': ('logging', 'log_level', str),
            'PEG_ENABLE_FILE_LOGGING': ('logging', 'enable_file_logging', lambda x: x.lower() == 'true'),
            
            # 캐시 설정
            'PEG_CACHE_ENABLED': ('cache', 'enabled', lambda x: x.lower() == 'true'),
            'PEG_CACHE_BACKEND': ('cache', 'backend', str),
            'PEG_CACHE_TTL': ('cache', 'default_ttl_seconds', int),
            'PEG_REDIS_HOST': ('cache', 'redis_host', str),
            'PEG_REDIS_PORT': ('cache', 'redis_port', int),
            'PEG_REDIS_PASSWORD': ('cache', 'redis_password', str),
        }
        
        # 환경변수 값 적용
        for env_var, (category, attr, converter) in env_mappings.items():
            value = os.getenv(env_var)
            if value is not None:
                try:
                    converted_value = converter(value)
                    setattr(getattr(self, category), attr, converted_value)
                    logger.debug(f"환경변수 {env_var} 적용: {converted_value}")
                except (ValueError, TypeError) as e:
                    logger.warning(f"환경변수 {env_var} 변환 실패: {e}")
    
    def _validate_config(self):
        """전체 설정 검증"""
        logger.debug("전체 설정 검증 중")
        
        # 설정 간 일관성 검증
        if self.performance.max_processing_time_seconds <= self.performance.timeout_seconds:
            raise ValueError("최대 처리 시간은 타임아웃 시간보다 커야 합니다")
        
        # 메모리 사용량 검증
        if self.performance.max_memory_usage_mb < 64:
            logger.warning("최대 메모리 사용량이 64MB 미만입니다. 성능에 영향을 줄 수 있습니다")
        
        # 캐시 설정 검증
        if self.cache.enabled and self.cache.backend == 'redis':
            if not self.cache.redis_host:
                raise ValueError("Redis 백엔드 사용 시 호스트가 필요합니다")
        
        logger.debug("전체 설정 검증 완료")
    
    def get_trend_thresholds(self) -> Dict[str, float]:
        """트렌드 임계값 반환"""
        return {
            'stable': self.analysis.trend_threshold_percent,
            'significant': self.analysis.significant_threshold_percent,
            'highly_significant': self.analysis.highly_significant_threshold_percent
        }
    
    def get_data_quality_thresholds(self) -> Dict[str, float]:
        """데이터 품질 임계값 반환"""
        return {
            'high': self.analysis.high_quality_rsd_threshold,
            'medium': self.analysis.medium_quality_rsd_threshold
        }
    
    def get_performance_limits(self) -> Dict[str, Any]:
        """성능 제한값 반환"""
        return {
            'max_memory_mb': self.performance.max_memory_usage_mb,
            'chunk_size': self.performance.chunk_size,
            'max_concurrent_tasks': self.performance.max_concurrent_tasks,
            'max_processing_time': self.performance.max_processing_time_seconds,
            'timeout': self.performance.timeout_seconds
        }
    
    def get_cache_settings(self) -> Dict[str, Any]:
        """캐시 설정 반환"""
        return {
            'enabled': self.cache.enabled,
            'backend': self.cache.backend,
            'default_ttl': self.cache.default_ttl_seconds,
            'result_ttl': self.cache.result_ttl_seconds,
            'metadata_ttl': self.cache.metadata_ttl_seconds,
            'redis_host': self.cache.redis_host,
            'redis_port': self.cache.redis_port,
            'redis_db': self.cache.redis_db,
            'redis_password': self.cache.redis_password,
            'cache_dir': self.cache.cache_dir
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """설정을 딕셔너리로 변환"""
        return {
            'algorithm_version': self.algorithm_version,
            'performance': {
                'max_memory_usage_mb': self.performance.max_memory_usage_mb,
                'chunk_size': self.performance.chunk_size,
                'max_concurrent_tasks': self.performance.max_concurrent_tasks,
                'max_processing_time_seconds': self.performance.max_processing_time_seconds,
                'timeout_seconds': self.performance.timeout_seconds,
                'cache_ttl_seconds': self.performance.cache_ttl_seconds,
                'max_cache_size_mb': self.performance.max_cache_size_mb
            },
            'validation': {
                'required_fields': self.validation.required_fields,
                'valid_periods': self.validation.valid_periods,
                'min_avg_value': self.validation.min_avg_value,
                'max_avg_value': self.validation.max_avg_value,
                'min_weight': self.validation.min_weight,
                'max_weight': self.validation.max_weight,
                'outlier_detection_enabled': self.validation.outlier_detection_enabled,
                'outlier_iqr_multiplier': self.validation.outlier_iqr_multiplier,
                'min_data_points_for_outlier': self.validation.min_data_points_for_outlier
            },
            'analysis': {
                'trend_threshold_percent': self.analysis.trend_threshold_percent,
                'significant_threshold_percent': self.analysis.significant_threshold_percent,
                'highly_significant_threshold_percent': self.analysis.highly_significant_threshold_percent,
                'default_confidence': self.analysis.default_confidence,
                'min_confidence': self.analysis.min_confidence,
                'max_confidence': self.analysis.max_confidence,
                'use_sample_std': self.analysis.use_sample_std,
                'rsd_calculation_method': self.analysis.rsd_calculation_method,
                'high_quality_rsd_threshold': self.analysis.high_quality_rsd_threshold,
                'medium_quality_rsd_threshold': self.analysis.medium_quality_rsd_threshold
            },
            'logging': {
                'log_level': self.logging.log_level,
                'log_format': self.logging.log_format,
                'enable_file_logging': self.logging.enable_file_logging,
                'log_file_path': self.logging.log_file_path,
                'max_log_file_size_mb': self.logging.max_log_file_size_mb,
                'backup_count': self.logging.backup_count,
                'enable_performance_logging': self.logging.enable_performance_logging,
                'performance_log_interval_seconds': self.logging.performance_log_interval_seconds
            },
            'cache': self.get_cache_settings()
        }
    
    def update_config(self, updates: Dict[str, Any]) -> None:
        """설정 업데이트"""
        logger.info("설정 업데이트 시작")
        
        for category, values in updates.items():
            if hasattr(self, category) and isinstance(values, dict):
                config_obj = getattr(self, category)
                for key, value in values.items():
                    if hasattr(config_obj, key):
                        setattr(config_obj, key, value)
                        logger.debug(f"설정 업데이트: {category}.{key} = {value}")
                    else:
                        logger.warning(f"알 수 없는 설정 키: {category}.{key}")
            else:
                logger.warning(f"알 수 없는 설정 카테고리: {category}")
        
        # 업데이트 후 재검증
        self._validate_config()
        logger.info("설정 업데이트 완료")


# 전역 설정 인스턴스
config = PEGComparisonConfig()

# 설정 접근을 위한 편의 함수들
def get_config() -> PEGComparisonConfig:
    """전역 설정 인스턴스 반환"""
    return config

def get_trend_thresholds() -> Dict[str, float]:
    """트렌드 임계값 반환"""
    return config.get_trend_thresholds()

def get_data_quality_thresholds() -> Dict[str, float]:
    """데이터 품질 임계값 반환"""
    return config.get_data_quality_thresholds()

def get_performance_limits() -> Dict[str, Any]:
    """성능 제한값 반환"""
    return config.get_performance_limits()

def get_cache_settings() -> Dict[str, Any]:
    """캐시 설정 반환"""
    return config.get_cache_settings()

# 모듈 초기화 로그
logger.info("PEG 비교분석 설정 모듈이 성공적으로 로드되었습니다")




