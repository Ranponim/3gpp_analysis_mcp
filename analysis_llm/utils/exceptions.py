"""
Utility-specific Exception Classes

이 모듈은 utils 패키지에서 사용되는 특화된 예외 클래스들을 정의합니다.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Union

# ValidationError를 직접 import하는 대신 기본 Exception을 상속
# 나중에 통합할 때 ValidationError로 변경 예정

# 로깅 설정
logger = logging.getLogger(__name__)


class TimeParsingError(Exception):
    """
    시간 파싱 관련 오류 예외 클래스

    TimeRangeParser에서 발생하는 시간 문자열 파싱 오류를 처리합니다.
    기존 main.py의 구조화된 JSON 오류 메시지 형식을 유지합니다.
    """

    def __init__(
        self,
        message: str,
        details: Optional[Union[str, Dict[str, Any]]] = None,
        error_code: Optional[str] = None,
        hint: Optional[str] = None,
        input_value: Optional[str] = None,
    ) -> None:
        """
        TimeParsingError 초기화

        Args:
            message (str): 오류 메시지
            details (Optional[Union[str, Dict[str, Any]]]): 추가 상세 정보
            error_code (Optional[str]): 오류 코드 (TYPE_ERROR, FORMAT_ERROR, VALUE_ERROR, LOGIC_ERROR)
            hint (Optional[str]): 사용자를 위한 힌트 메시지
            input_value (Optional[str]): 파싱에 실패한 입력값

        Examples:
            >>> raise TimeParsingError(
            ...     "입력 형식이 올바르지 않습니다",
            ...     error_code="FORMAT_ERROR",
            ...     hint="예: 2025-01-01_09:00~2025-01-01_18:00",
            ...     input_value="잘못된형식"
            ... )
        """
        # Exception 부모 클래스 초기화
        super().__init__(message)

        # TimeParsingError 특화 속성
        self.message = message
        self.details = details
        self.error_code = error_code
        self.hint = hint
        self.input_value = input_value

        # 로깅: 시간 파싱 오류 상세 정보
        log_details = {"error_code": error_code, "input": input_value, "hint": hint}
        logger.error("TimeParsingError 발생: %s, 상세: %s", message, log_details)

    def __repr__(self) -> str:
        """개발자용 문자열 표현"""
        parts = [f"message='{self.message}'"]
        if self.error_code:
            parts.append(f"code='{self.error_code}'")
        if self.input_value:
            parts.append(f"input='{self.input_value}'")
        return f"TimeParsingError({', '.join(parts)})"

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리 형태로 변환 (기존 JSON 오류 메시지 형식 호환)"""
        return {
            "error_type": "TimeParsingError",
            "code": self.error_code,
            "message": self.message,
            "input": self.input_value,
            "hint": self.hint,
            "details": self.details,
        }

    def to_json_error(self) -> Dict[str, Any]:
        """기존 main.py와 호환되는 JSON 오류 메시지 형식"""
        result = {"code": self.error_code or "PARSING_ERROR", "message": self.message}

        if self.input_value is not None:
            result["input"] = self.input_value

        if self.hint:
            result["hint"] = self.hint

        # 추가 상세 정보가 있으면 포함
        if self.details:
            if isinstance(self.details, dict):
                result.update(self.details)
            else:
                result["details"] = self.details

        return result

    def is_type_error(self) -> bool:
        """타입 오류인지 확인"""
        return self.error_code == "TYPE_ERROR"

    def is_format_error(self) -> bool:
        """형식 오류인지 확인"""
        return self.error_code == "FORMAT_ERROR"

    def is_value_error(self) -> bool:
        """값 오류인지 확인"""
        return self.error_code == "VALUE_ERROR"

    def is_logic_error(self) -> bool:
        """논리 오류인지 확인"""
        return self.error_code == "LOGIC_ERROR"

    @classmethod
    def from_json_error(cls, json_error_dict: Dict[str, Any]) -> "TimeParsingError":
        """기존 JSON 오류 메시지에서 TimeParsingError 생성"""
        return cls(
            message=json_error_dict.get("message", "알 수 없는 오류"),
            error_code=json_error_dict.get("code"),
            hint=json_error_dict.get("hint"),
            input_value=json_error_dict.get("input"),
            details={k: v for k, v in json_error_dict.items() if k not in ["message", "code", "hint", "input"]},
        )
