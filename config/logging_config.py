"""
커스텀 로깅 레벨 설정

DEBUG2 레벨을 추가하여 더 상세한 데이터 흐름을 추적할 수 있도록 합니다.

로그 레벨 계층 구조:
- CRITICAL (50): 시스템 치명적 오류
- ERROR (40): 실제 오류
- WARNING (30): 경고
- INFO (20): 일반 정보
- DEBUG (10): 디버깅 정보
- DEBUG2 (5): 매우 상세한 데이터 흐름 추적 (신규)

Usage:
    import logging
    from config.logging_config import setup_custom_logging_levels
    
    # 커스텀 레벨 설정
    setup_custom_logging_levels()
    
    # 사용
    logger = logging.getLogger(__name__)
    logger.debug2("DB 조회 결과: %s", data)

환경변수:
- LOG_MAX_LENGTH: 로그 출력 최대 길이 (기본값: 1000)
    프롬프트 등 긴 데이터를 로그에 출력할 때 최대 길이를 제한합니다.
    매우 긴 내용을 로그에 남기고 싶다면 이 값을 크게 설정하세요.
- DATA_FLOW_LOG_MAX_LENGTH: log_data_flow() 호출 시 사용할 최대 길이
    설정하지 않으면 LOG_MAX_LENGTH를 그대로 사용합니다.
    0 이하로 지정하면 데이터 길이를 제한하지 않습니다.
"""

import logging
import os
from typing import Optional

# 커스텀 로그 레벨 상수
DEBUG2_LEVEL_NUM = 5
DEBUG2_LEVEL_NAME = 'DEBUG2'

def _get_log_max_length() -> int:
    """
    로그 최대 길이를 환경변수에서 읽어 반환 (동적 읽기)
    
    Returns:
        int: LOG_MAX_LENGTH 환경변수 값 (기본값: 1000)
    """
    return int(os.getenv('LOG_MAX_LENGTH', '1000'))


def _get_data_flow_log_max_length() -> Optional[int]:
    """
    데이터 흐름 로깅 전용 최대 길이를 환경변수에서 읽어 반환
    
    Returns:
        Optional[int]: DATA_FLOW_LOG_MAX_LENGTH 값, 미설정 시 None
    """
    value = os.getenv('DATA_FLOW_LOG_MAX_LENGTH')
    if value is None:
        return None
    
    try:
        return int(value)
    except ValueError:
        logging.warning(
            "DATA_FLOW_LOG_MAX_LENGTH 값이 유효하지 않아 무시합니다: %s (정수 필요)", value
        )
        return None


def setup_custom_logging_levels():
    """
    커스텀 로깅 레벨을 설정합니다.
    
    DEBUG2 레벨 (5)을 추가하여 DEBUG(10)보다 더 상세한 로그를 출력할 수 있습니다.
    이 함수는 애플리케이션 시작 시 한 번만 호출되어야 합니다.
    """
    # DEBUG2 레벨이 이미 등록되어 있는지 확인
    if hasattr(logging, 'DEBUG2'):
        return
    
    # DEBUG2 레벨 추가
    logging.addLevelName(DEBUG2_LEVEL_NUM, DEBUG2_LEVEL_NAME)
    
    # logging 모듈에 상수 추가
    setattr(logging, 'DEBUG2', DEBUG2_LEVEL_NUM)
    
    # Logger 클래스에 debug2() 메서드 추가
    def debug2(self, message, *args, **kwargs):
        """
        DEBUG2 레벨로 로그 메시지를 기록합니다.
        
        Args:
            message: 로그 메시지 (포맷 문자열 가능)
            *args: 메시지 포맷 인자들
            **kwargs: 추가 로깅 옵션
        """
        if self.isEnabledFor(DEBUG2_LEVEL_NUM):
            self._log(DEBUG2_LEVEL_NUM, message, args, **kwargs)
    
    # Logger 클래스에 메서드 추가
    logging.Logger.debug2 = debug2
    
    # 로거 인스턴스에서 사용 가능하도록 설정
    logging.getLoggerClass().debug2 = debug2


def get_numeric_log_level(level: str) -> int:
    """
    로그 레벨 문자열을 숫자로 변환합니다.
    
    Args:
        level: 로그 레벨 문자열 (예: 'DEBUG2', 'DEBUG', 'INFO')
        
    Returns:
        int: 로그 레벨 숫자 값
        
    Raises:
        ValueError: 유효하지 않은 로그 레벨인 경우
    """
    level_upper = level.upper()
    
    # DEBUG2 처리
    if level_upper == 'DEBUG2':
        return DEBUG2_LEVEL_NUM
    
    # 표준 레벨 처리
    try:
        return getattr(logging, level_upper)
    except AttributeError:
        valid_levels = ['DEBUG2', 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        raise ValueError(f"Invalid log level: {level}. Must be one of {valid_levels}")


def format_data_for_log(data, max_length: Optional[int] = None, indent: int = 2) -> str:
    """
    로그 출력을 위해 데이터를 보기 좋게 포맷팅합니다.
    
    Args:
        data: 포맷팅할 데이터 (dict, list, str 등)
        max_length: 최대 출력 길이 (None이면 환경변수 사용, 너무 긴 경우 잘라냄)
        indent: JSON 들여쓰기 수준
        
    Returns:
        str: 포맷팅된 문자열
        
    환경변수:
        LOG_MAX_LENGTH: 로그 출력 최대 길이 (기본값: 1000)
    """
    import json
    
    # max_length가 None이면 환경변수 값 사용
    if max_length is None:
        max_length = _get_log_max_length()
    
    # indent가 None이면 기본값 2 사용
    if indent is None:
        indent = 2
    
    try:
        # 딕셔너리나 리스트인 경우 JSON으로 포맷
        if isinstance(data, (dict, list)):
            formatted = json.dumps(data, ensure_ascii=False, indent=indent, default=str)
        else:
            formatted = str(data)
        
        # 길이 제한
        if max_length > 0 and len(formatted) > max_length:
            return formatted[:max_length] + f"\n... (총 {len(formatted)}자, {max_length}자까지만 표시)"
        
        return formatted
    except Exception as e:
        return f"<포맷팅 오류: {e}>"


def log_data_flow(
    logger: logging.Logger,
    stage: str,
    data,
    level: str = 'DEBUG2',
    max_length: Optional[int] = None,
):
    """
    데이터 흐름을 로그로 기록하는 헬퍼 함수
    
    Args:
        logger: 로거 인스턴스
        stage: 처리 단계 이름 (예: "DB 조회", "데이터 변환")
        data: 기록할 데이터
        level: 로그 레벨 (기본: DEBUG2)
        max_length: 출력 길이 제한 (None이면 환경변수 사용)
    """
    level_num = get_numeric_log_level(level)
    
    if logger.isEnabledFor(level_num):
        separator = "=" * 80
        
        # max_length가 지정되지 않았다면 DATA_FLOW_LOG_MAX_LENGTH 우선 적용
        effective_max_length = max_length
        if effective_max_length is None:
            effective_max_length = _get_data_flow_log_max_length()
        
        formatted_data = format_data_for_log(data, max_length=effective_max_length)
        
        message = f"\n{separator}\n📊 [{stage}] 데이터\n{separator}\n{formatted_data}\n{separator}"
        logger.log(level_num, message)


def log_step(logger: logging.Logger, step_name: str, details: Optional[str] = None):
    """
    처리 단계를 로그로 기록하는 헬퍼 함수
    
    Args:
        logger: 로거 인스턴스
        step_name: 단계 이름
        details: 추가 설명 (선택사항)
    """
    if logger.isEnabledFor(DEBUG2_LEVEL_NUM):
        message = f"🔹 {step_name}"
        if details:
            message += f" - {details}"
        logger.debug2(message)


def log_at_debug2(logger: logging.Logger, message: str):
    """
    DEBUG2 레벨로 로그를 기록하는 헬퍼 함수
    
    Args:
        logger: 로거 인스턴스
        message: 로그 메시지
    """
    if logger.isEnabledFor(DEBUG2_LEVEL_NUM):
        logger.debug2(message)


# 모듈 로드 시 자동으로 커스텀 레벨 설정
setup_custom_logging_levels()

