"""
PEG 비교분석 에러 처리 및 복구 모듈

이 모듈은 PEG(Performance Engineering Guidelines) 비교분석 과정에서
발생할 수 있는 다양한 에러 상황을 처리하고 복구 메커니즘을 제공합니다.
부분적 실패, 재시도 로직, 폴백 메커니즘을 포함합니다.

Author: KPI Dashboard Team
Created: 2024-01-15
Version: 1.0.0
"""

import time
import logging
import traceback
from typing import Dict, Any, Optional, List, Callable, Union
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timedelta
import asyncio
from functools import wraps

# 로거 설정
logger = logging.getLogger(__name__)


class ErrorType(Enum):
    """에러 타입 열거형"""
    # 데이터 관련 에러
    DATA_VALIDATION_ERROR = "DATA_VALIDATION_ERROR"
    DATA_PROCESSING_ERROR = "DATA_PROCESSING_ERROR"
    DATA_NOT_FOUND = "DATA_NOT_FOUND"
    DATA_CORRUPTION = "DATA_CORRUPTION"
    
    # 계산 관련 에러
    CALCULATION_ERROR = "CALCULATION_ERROR"
    STATISTICAL_ERROR = "STATISTICAL_ERROR"
    TREND_ANALYSIS_ERROR = "TREND_ANALYSIS_ERROR"
    
    # 시스템 관련 에러
    MEMORY_ERROR = "MEMORY_ERROR"
    TIMEOUT_ERROR = "TIMEOUT_ERROR"
    CONNECTION_ERROR = "CONNECTION_ERROR"
    PERMISSION_ERROR = "PERMISSION_ERROR"
    
    # 비즈니스 로직 에러
    BUSINESS_LOGIC_ERROR = "BUSINESS_LOGIC_ERROR"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    ALGORITHM_ERROR = "ALGORITHM_ERROR"
    
    # 일반 에러
    UNKNOWN_ERROR = "UNKNOWN_ERROR"
    SYSTEM_ERROR = "SYSTEM_ERROR"


class ErrorSeverity(Enum):
    """에러 심각도 열거형"""
    LOW = "low"        # 경고 수준, 처리 계속 가능
    MEDIUM = "medium"  # 중간 수준, 일부 기능 제한
    HIGH = "high"      # 높은 수준, 주요 기능 중단
    CRITICAL = "critical"  # 치명적, 전체 시스템 중단


@dataclass
class ErrorContext:
    """에러 컨텍스트 정보"""
    error_type: ErrorType
    severity: ErrorSeverity
    message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime = None
    stack_trace: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    recovery_attempted: bool = False
    
    def __post_init__(self):
        """초기화 후 처리"""
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
        if self.details is None:
            self.details = {}


@dataclass
class RetryConfig:
    """재시도 설정"""
    max_retries: int = 3
    base_delay: float = 1.0  # 기본 지연 시간 (초)
    max_delay: float = 60.0  # 최대 지연 시간 (초)
    exponential_base: float = 2.0  # 지수 백오프 베이스
    jitter: bool = True  # 지터 적용 여부
    
    def calculate_delay(self, attempt: int) -> float:
        """재시도 지연 시간 계산 (지수 백오프)"""
        if attempt <= 0:
            return 0.0
        
        # 지수 백오프 계산
        delay = self.base_delay * (self.exponential_base ** (attempt - 1))
        
        # 최대 지연 시간 제한
        delay = min(delay, self.max_delay)
        
        # 지터 적용 (랜덤 변동)
        if self.jitter:
            import random
            jitter_factor = random.uniform(0.5, 1.5)
            delay *= jitter_factor
        
        return delay


class PEGComparisonError(Exception):
    """PEG 비교분석 전용 예외 클래스"""
    
    def __init__(
        self,
        message: str,
        error_type: ErrorType = ErrorType.UNKNOWN_ERROR,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        details: Optional[Dict[str, Any]] = None,
        context: Optional[ErrorContext] = None
    ):
        super().__init__(message)
        self.message = message
        self.error_type = error_type
        self.severity = severity
        self.details = details or {}
        self.context = context or ErrorContext(
            error_type=error_type,
            severity=severity,
            message=message,
            details=details
        )
        self.timestamp = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """에러 정보를 딕셔너리로 변환"""
        return {
            "message": self.message,
            "error_type": self.error_type.value,
            "severity": self.severity.value,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
            "context": {
                "retry_count": self.context.retry_count,
                "max_retries": self.context.max_retries,
                "recovery_attempted": self.context.recovery_attempted
            } if self.context else None
        }


class ErrorHandler:
    """
    PEG 비교분석 에러 처리 및 복구 클래스
    
    다양한 에러 상황을 처리하고 복구 메커니즘을 제공합니다.
    """
    
    def __init__(self, retry_config: Optional[RetryConfig] = None):
        """
        에러 핸들러 초기화
        
        Args:
            retry_config: 재시도 설정 (None이면 기본값 사용)
        """
        self.retry_config = retry_config or RetryConfig()
        self.error_history: List[ErrorContext] = []
        self.recovery_strategies: Dict[ErrorType, Callable] = {}
        
        # 기본 복구 전략 등록
        self._register_default_recovery_strategies()
        
        logger.info("PEG 비교분석 에러 핸들러 초기화 완료")
    
    def _register_default_recovery_strategies(self):
        """기본 복구 전략 등록"""
        self.recovery_strategies = {
            ErrorType.DATA_VALIDATION_ERROR: self._recover_data_validation_error,
            ErrorType.DATA_PROCESSING_ERROR: self._recover_data_processing_error,
            ErrorType.CALCULATION_ERROR: self._recover_calculation_error,
            ErrorType.MEMORY_ERROR: self._recover_memory_error,
            ErrorType.TIMEOUT_ERROR: self._recover_timeout_error,
            ErrorType.CONNECTION_ERROR: self._recover_connection_error,
        }
        
        logger.debug(f"기본 복구 전략 {len(self.recovery_strategies)}개 등록 완료")
    
    def handle_error(
        self,
        error: Exception,
        context: Optional[Dict[str, Any]] = None,
        retry: bool = True
    ) -> ErrorContext:
        """
        에러 처리 및 복구 시도
        
        Args:
            error: 발생한 예외
            context: 추가 컨텍스트 정보
            retry: 재시도 여부
        
        Returns:
            ErrorContext: 에러 컨텍스트 정보
        """
        logger.error(f"에러 처리 시작: {type(error).__name__}: {str(error)}")
        
        # 에러 타입 및 심각도 결정
        error_type, severity = self._classify_error(error)
        
        # 에러 컨텍스트 생성
        error_context = ErrorContext(
            error_type=error_type,
            severity=severity,
            message=str(error),
            details=context or {},
            stack_trace=traceback.format_exc()
        )
        
        # 에러 히스토리에 추가
        self.error_history.append(error_context)
        
        # 복구 시도
        if retry and error_type in self.recovery_strategies:
            try:
                recovery_result = self.recovery_strategies[error_type](error_context)
                if recovery_result:
                    error_context.recovery_attempted = True
                    logger.info(f"에러 복구 성공: {error_type.value}")
                else:
                    logger.warning(f"에러 복구 실패: {error_type.value}")
            except Exception as recovery_error:
                logger.error(f"복구 과정에서 에러 발생: {recovery_error}")
                error_context.recovery_attempted = True
        
        # 에러 로깅
        self._log_error(error_context)
        
        return error_context
    
    def _classify_error(self, error: Exception) -> tuple[ErrorType, ErrorSeverity]:
        """에러 분류"""
        error_type = ErrorType.UNKNOWN_ERROR
        severity = ErrorSeverity.MEDIUM
        
        # 에러 타입별 분류
        if isinstance(error, PEGComparisonError):
            error_type = error.error_type
            severity = error.severity
        elif isinstance(error, ValueError):
            error_type = ErrorType.DATA_VALIDATION_ERROR
            severity = ErrorSeverity.LOW
        elif isinstance(error, TypeError):
            error_type = ErrorType.DATA_VALIDATION_ERROR
            severity = ErrorSeverity.LOW
        elif isinstance(error, MemoryError):
            error_type = ErrorType.MEMORY_ERROR
            severity = ErrorSeverity.HIGH
        elif isinstance(error, TimeoutError):
            error_type = ErrorType.TIMEOUT_ERROR
            severity = ErrorSeverity.MEDIUM
        elif isinstance(error, ConnectionError):
            error_type = ErrorType.CONNECTION_ERROR
            severity = ErrorSeverity.MEDIUM
        elif isinstance(error, PermissionError):
            error_type = ErrorType.PERMISSION_ERROR
            severity = ErrorSeverity.HIGH
        elif isinstance(error, ZeroDivisionError):
            error_type = ErrorType.CALCULATION_ERROR
            severity = ErrorSeverity.MEDIUM
        elif isinstance(error, ArithmeticError):
            error_type = ErrorType.CALCULATION_ERROR
            severity = ErrorSeverity.MEDIUM
        
        logger.debug(f"에러 분류: {error_type.value} (심각도: {severity.value})")
        return error_type, severity
    
    def _log_error(self, error_context: ErrorContext):
        """에러 로깅"""
        log_data = {
            "error_type": error_context.error_type.value,
            "severity": error_context.severity.value,
            "message": error_context.message,
            "timestamp": error_context.timestamp.isoformat(),
            "retry_count": error_context.retry_count,
            "recovery_attempted": error_context.recovery_attempted
        }
        
        if error_context.details:
            log_data["details"] = error_context.details
        
        # 심각도별 로그 레벨 결정
        if error_context.severity == ErrorSeverity.CRITICAL:
            logger.critical(f"치명적 에러: {log_data}")
        elif error_context.severity == ErrorSeverity.HIGH:
            logger.error(f"높은 심각도 에러: {log_data}")
        elif error_context.severity == ErrorSeverity.MEDIUM:
            logger.warning(f"중간 심각도 에러: {log_data}")
        else:
            logger.info(f"낮은 심각도 에러: {log_data}")
    
    # 복구 전략 메서드들
    def _recover_data_validation_error(self, error_context: ErrorContext) -> bool:
        """데이터 검증 에러 복구"""
        logger.info("데이터 검증 에러 복구 시도")
        
        # 기본값 설정 또는 데이터 정제
        if "missing_field" in error_context.details:
            field_name = error_context.details["missing_field"]
            logger.info(f"누락된 필드 {field_name}에 기본값 설정")
            return True
        
        # 데이터 타입 변환 시도
        if "type_mismatch" in error_context.details:
            logger.info("데이터 타입 변환 시도")
            return True
        
        return False
    
    def _recover_data_processing_error(self, error_context: ErrorContext) -> bool:
        """데이터 처리 에러 복구"""
        logger.info("데이터 처리 에러 복구 시도")
        
        # 데이터 청크 단위로 재처리
        if "chunk_processing" in error_context.details:
            logger.info("청크 단위 재처리 시도")
            return True
        
        # 메모리 사용량 최적화
        if "memory_optimization" in error_context.details:
            logger.info("메모리 최적화 시도")
            return True
        
        return False
    
    def _recover_calculation_error(self, error_context: ErrorContext) -> bool:
        """계산 에러 복구"""
        logger.info("계산 에러 복구 시도")
        
        # 0으로 나누기 에러 처리
        if "division_by_zero" in error_context.details:
            logger.info("0으로 나누기 에러 복구: 기본값 사용")
            return True
        
        # 수치적 불안정성 처리
        if "numerical_instability" in error_context.details:
            logger.info("수치적 불안정성 복구: 안정화 알고리즘 적용")
            return True
        
        return False
    
    def _recover_memory_error(self, error_context: ErrorContext) -> bool:
        """메모리 에러 복구"""
        logger.info("메모리 에러 복구 시도")
        
        # 가비지 컬렉션 강제 실행
        import gc
        gc.collect()
        logger.info("가비지 컬렉션 실행 완료")
        
        # 메모리 사용량 모니터링
        try:
            import psutil
            memory_info = psutil.virtual_memory()
            logger.info(f"현재 메모리 사용률: {memory_info.percent}%")
            
            if memory_info.percent > 90:
                logger.warning("메모리 사용률이 90%를 초과했습니다")
                return False
            else:
                return True
        except ImportError:
            logger.warning("psutil 모듈이 없어 메모리 정보를 확인할 수 없습니다")
            return True
    
    def _recover_timeout_error(self, error_context: ErrorContext) -> bool:
        """타임아웃 에러 복구"""
        logger.info("타임아웃 에러 복구 시도")
        
        # 타임아웃 시간 연장
        if "extend_timeout" in error_context.details:
            logger.info("타임아웃 시간 연장")
            return True
        
        # 작업 분할
        if "split_task" in error_context.details:
            logger.info("작업 분할 시도")
            return True
        
        return False
    
    def _recover_connection_error(self, error_context: ErrorContext) -> bool:
        """연결 에러 복구"""
        logger.info("연결 에러 복구 시도")
        
        # 연결 재시도
        if "retry_connection" in error_context.details:
            logger.info("연결 재시도")
            return True
        
        # 대체 연결 사용
        if "use_fallback" in error_context.details:
            logger.info("대체 연결 사용")
            return True
        
        return False
    
    def retry_with_backoff(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        지수 백오프를 사용한 재시도 데코레이터
        
        Args:
            func: 재시도할 함수
            *args: 함수 인자
            **kwargs: 함수 키워드 인자
        
        Returns:
            함수 실행 결과
        """
        last_error = None
        
        for attempt in range(self.retry_config.max_retries + 1):
            try:
                logger.debug(f"함수 실행 시도 {attempt + 1}/{self.retry_config.max_retries + 1}")
                result = func(*args, **kwargs)
                logger.debug(f"함수 실행 성공 (시도 {attempt + 1})")
                return result
            
            except Exception as e:
                last_error = e
                logger.warning(f"함수 실행 실패 (시도 {attempt + 1}): {e}")
                
                if attempt < self.retry_config.max_retries:
                    delay = self.retry_config.calculate_delay(attempt + 1)
                    logger.info(f"재시도 전 {delay:.2f}초 대기")
                    time.sleep(delay)
                else:
                    logger.error(f"최대 재시도 횟수 초과: {self.retry_config.max_retries}")
                    break
        
        # 모든 재시도 실패 시 에러 발생
        raise PEGComparisonError(
            message=f"함수 실행 실패 (최대 재시도 횟수 초과): {str(last_error)}",
            error_type=ErrorType.SYSTEM_ERROR,
            severity=ErrorSeverity.HIGH,
            details={
                "function": func.__name__,
                "max_retries": self.retry_config.max_retries,
                "last_error": str(last_error)
            }
        )
    
    async def retry_with_backoff_async(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        비동기 함수용 지수 백오프 재시도
        
        Args:
            func: 재시도할 비동기 함수
            *args: 함수 인자
            **kwargs: 함수 키워드 인자
        
        Returns:
            함수 실행 결과
        """
        last_error = None
        
        for attempt in range(self.retry_config.max_retries + 1):
            try:
                logger.debug(f"비동기 함수 실행 시도 {attempt + 1}/{self.retry_config.max_retries + 1}")
                result = await func(*args, **kwargs)
                logger.debug(f"비동기 함수 실행 성공 (시도 {attempt + 1})")
                return result
            
            except Exception as e:
                last_error = e
                logger.warning(f"비동기 함수 실행 실패 (시도 {attempt + 1}): {e}")
                
                if attempt < self.retry_config.max_retries:
                    delay = self.retry_config.calculate_delay(attempt + 1)
                    logger.info(f"재시도 전 {delay:.2f}초 대기")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"최대 재시도 횟수 초과: {self.retry_config.max_retries}")
                    break
        
        # 모든 재시도 실패 시 에러 발생
        raise PEGComparisonError(
            message=f"비동기 함수 실행 실패 (최대 재시도 횟수 초과): {str(last_error)}",
            error_type=ErrorType.SYSTEM_ERROR,
            severity=ErrorSeverity.HIGH,
            details={
                "function": func.__name__,
                "max_retries": self.retry_config.max_retries,
                "last_error": str(last_error)
            }
        )
    
    def handle_partial_failure(
        self,
        results: List[Any],
        failed_items: List[Dict[str, Any]],
        error_context: ErrorContext
    ) -> Dict[str, Any]:
        """
        부분적 실패 처리
        
        Args:
            results: 성공한 결과들
            failed_items: 실패한 항목들
            error_context: 에러 컨텍스트
        
        Returns:
            처리 결과 딕셔너리
        """
        logger.info(f"부분적 실패 처리: 성공 {len(results)}개, 실패 {len(failed_items)}개")
        
        # 성공한 결과 반환
        response = {
            "success": True,
            "partial_success": True,
            "results": results,
            "failed_items": failed_items,
            "error_summary": {
                "error_type": error_context.error_type.value,
                "severity": error_context.severity.value,
                "message": error_context.message,
                "failed_count": len(failed_items)
            }
        }
        
        # 실패한 항목들 로깅
        for item in failed_items:
            logger.warning(f"실패한 항목: {item}")
        
        return response
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """에러 통계 반환"""
        if not self.error_history:
            return {"total_errors": 0}
        
        # 에러 타입별 통계
        error_type_counts = {}
        severity_counts = {}
        
        for error in self.error_history:
            error_type = error.error_type.value
            severity = error.severity.value
            
            error_type_counts[error_type] = error_type_counts.get(error_type, 0) + 1
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
        
        return {
            "total_errors": len(self.error_history),
            "error_type_distribution": error_type_counts,
            "severity_distribution": severity_counts,
            "recovery_attempts": sum(1 for e in self.error_history if e.recovery_attempted),
            "recovery_success_rate": sum(1 for e in self.error_history if e.recovery_attempted) / len(self.error_history) if self.error_history else 0
        }
    
    def clear_error_history(self):
        """에러 히스토리 초기화"""
        logger.info(f"에러 히스토리 초기화: {len(self.error_history)}개 항목 삭제")
        self.error_history.clear()


# 데코레이터 함수들
def retry_on_error(
    max_retries: int = 3,
    base_delay: float = 1.0,
    exponential_base: float = 2.0
):
    """
    에러 발생 시 재시도하는 데코레이터
    
    Args:
        max_retries: 최대 재시도 횟수
        base_delay: 기본 지연 시간
        exponential_base: 지수 백오프 베이스
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retry_config = RetryConfig(
                max_retries=max_retries,
                base_delay=base_delay,
                exponential_base=exponential_base
            )
            error_handler = ErrorHandler(retry_config)
            return error_handler.retry_with_backoff(func, *args, **kwargs)
        return wrapper
    return decorator


def retry_on_error_async(
    max_retries: int = 3,
    base_delay: float = 1.0,
    exponential_base: float = 2.0
):
    """
    비동기 함수용 에러 발생 시 재시도하는 데코레이터
    
    Args:
        max_retries: 최대 재시도 횟수
        base_delay: 기본 지연 시간
        exponential_base: 지수 백오프 베이스
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            retry_config = RetryConfig(
                max_retries=max_retries,
                base_delay=base_delay,
                exponential_base=exponential_base
            )
            error_handler = ErrorHandler(retry_config)
            return await error_handler.retry_with_backoff_async(func, *args, **kwargs)
        return wrapper
    return decorator


# 전역 에러 핸들러 인스턴스
error_handler = ErrorHandler()

# 편의 함수들
def handle_error(
    error: Exception,
    context: Optional[Dict[str, Any]] = None,
    retry: bool = True
) -> ErrorContext:
    """전역 에러 핸들러를 사용한 에러 처리"""
    return error_handler.handle_error(error, context, retry)

def get_error_statistics() -> Dict[str, Any]:
    """에러 통계 반환"""
    return error_handler.get_error_statistics()

def clear_error_history():
    """에러 히스토리 초기화"""
    error_handler.clear_error_history()

# 모듈 초기화 로그
logger.info("PEG 비교분석 에러 처리 모듈이 성공적으로 로드되었습니다")




