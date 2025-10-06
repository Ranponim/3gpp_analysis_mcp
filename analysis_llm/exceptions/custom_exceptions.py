"""
Custom Exception Classes

이 모듈은 3GPP Cell Performance LLM 분석기에서 사용되는
커스텀 예외 클래스들을 정의합니다.

모든 예외는 기본 AnalysisError에서 상속되며, 디버깅을 위한
상세 정보를 포함할 수 있습니다.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Union

# 로깅 설정
logger = logging.getLogger(__name__)


class AnalysisError(Exception):
    """
    분석 시스템의 기본 예외 클래스

    모든 커스텀 예외의 부모 클래스로, 메시지와 상세 정보를 포함합니다.
    디버깅과 오류 추적을 위한 추가 컨텍스트 정보를 저장할 수 있습니다.
    """

    def __init__(self, message: str, details: Optional[Union[str, Dict[str, Any]]] = None) -> None:
        """
        AnalysisError 초기화

        Args:
            message (str): 사용자에게 표시할 오류 메시지
            details (Optional[Union[str, Dict[str, Any]]]):
                디버깅을 위한 추가 상세 정보. 문자열 또는 딕셔너리 형태

        Examples:
            >>> raise AnalysisError("분석 중 오류가 발생했습니다")
            >>> raise AnalysisError(
            ...     "데이터 처리 실패",
            ...     {"step": "aggregation", "count": 0}
            ... )
        """
        super().__init__(message)
        self.message = message
        self.details = details

        # 로깅: 예외 발생 시 디버그 정보 기록
        if details:
            logger.debug("AnalysisError 발생: %s, 상세: %s", message, details)
        else:
            logger.debug("AnalysisError 발생: %s", message)

    def __str__(self) -> str:
        """문자열 표현"""
        return self.message

    def __repr__(self) -> str:
        """개발자용 문자열 표현"""
        if self.details:
            return f"AnalysisError(message='{self.message}', details={self.details})"
        return f"AnalysisError(message='{self.message}')"

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리 형태로 변환 (JSON 직렬화용)"""
        return {"error_type": self.__class__.__name__, "message": self.message, "details": self.details}

    def has_details(self) -> bool:
        """상세 정보가 있는지 확인"""
        return self.details is not None

    def get_details_str(self) -> str:
        """상세 정보를 문자열로 반환"""
        if not self.details:
            return ""

        if isinstance(self.details, str):
            return self.details
        elif isinstance(self.details, dict):
            return ", ".join(f"{k}={v}" for k, v in self.details.items())
        else:
            return str(self.details)

    def get_full_message(self) -> str:
        """메시지와 상세 정보를 포함한 전체 메시지"""
        if self.has_details():
            details_str = self.get_details_str()
            return f"{self.message} (상세: {details_str})"
        return self.message


class DatabaseError(AnalysisError):
    """
    데이터베이스 관련 오류 예외 클래스

    PostgreSQL 연결, 쿼리 실행, 트랜잭션 처리 등
    데이터베이스 작업 중 발생하는 오류를 처리합니다.
    """

    def __init__(
        self,
        message: str,
        details: Optional[Union[str, Dict[str, Any]]] = None,
        query: Optional[str] = None,
        connection_info: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        DatabaseError 초기화

        Args:
            message (str): 오류 메시지
            details (Optional[Union[str, Dict[str, Any]]]): 추가 상세 정보
            query (Optional[str]): 실패한 SQL 쿼리
            connection_info (Optional[Dict[str, Any]]): 연결 정보 (비밀번호 제외)

        Examples:
            >>> raise DatabaseError("연결 실패", query="SELECT * FROM summary")
            >>> raise DatabaseError(
            ...     "쿼리 실행 오류",
            ...     {"table": "summary", "rows": 0},
            ...     "SELECT COUNT(*) FROM summary WHERE datetime > %s"
            ... )
        """
        super().__init__(message, details)
        self.query = query
        self.connection_info = connection_info or {}

        # 로깅: 데이터베이스 오류 상세 정보 (details 포함)
        log_details = {
            "query": query[:100] + "..." if query and len(query) > 100 else query,
            "connection": connection_info,
            "details": details,
        }
        logger.error("DatabaseError 발생: %s, 상세: %s", message, log_details)

    def __repr__(self) -> str:
        """개발자용 문자열 표현"""
        parts = [f"message='{self.message}'"]
        if self.details:
            parts.append(f"details={self.details}")
        if self.query:
            query_preview = self.query[:50] + "..." if len(self.query) > 50 else self.query
            parts.append(f"query='{query_preview}'")
        return f"DatabaseError({', '.join(parts)})"

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리 형태로 변환 (JSON 직렬화용)"""
        data = super().to_dict()
        data.update({"query": self.query, "connection_info": self.connection_info})
        return data

    def get_safe_query(self) -> Optional[str]:
        """안전한 쿼리 반환 (매개변수 값 제거)"""
        if not self.query:
            return None

        # 간단한 매개변수 마스킹 (실제로는 더 정교한 로직 필요)
        import re

        safe_query = re.sub(r"'[^']*'", "'***'", self.query)
        safe_query = re.sub(r"%s", "***", safe_query)
        return safe_query


class LLMError(AnalysisError):
    """
    LLM (Large Language Model) 관련 오류 예외 클래스

    LLM API 호출, 응답 파싱, 프롬프트 처리 등
    LLM 관련 작업 중 발생하는 오류를 처리합니다.
    """

    def __init__(
        self,
        message: str,
        details: Optional[Union[str, Dict[str, Any]]] = None,
        status_code: Optional[int] = None,
        endpoint: Optional[str] = None,
        model_name: Optional[str] = None,
        prompt_preview: Optional[str] = None,
    ) -> None:
        """
        LLMError 초기화

        Args:
            message (str): 오류 메시지
            details (Optional[Union[str, Dict[str, Any]]]): 추가 상세 정보
            status_code (Optional[int]): HTTP 상태 코드
            endpoint (Optional[str]): 호출한 API 엔드포인트
            model_name (Optional[str]): 사용한 모델명
            prompt_preview (Optional[str]): 프롬프트 미리보기 (보안상 일부만)

        Examples:
            >>> raise LLMError("API 호출 실패", status_code=500)
            >>> raise LLMError(
            ...     "응답 파싱 오류",
            ...     {"response_length": 0},
            ...     endpoint="http://localhost:10000/api/chat",
            ...     model_name="Gemma-3-27B"
            ... )
        """
        super().__init__(message, details)
        self.status_code = status_code
        self.endpoint = endpoint
        self.model_name = model_name
        self.prompt_preview = prompt_preview

        # 로깅: LLM 오류 상세 정보
        log_details = {
            "status_code": status_code,
            "endpoint": endpoint,
            "model": model_name,
            "prompt_length": len(prompt_preview) if prompt_preview else 0,
        }
        logger.error("LLMError 발생: %s, 상세: %s", message, log_details)

    def __repr__(self) -> str:
        """개발자용 문자열 표현"""
        parts = [f"message='{self.message}'"]
        if self.details:
            parts.append(f"details={self.details}")
        if self.status_code:
            parts.append(f"status_code={self.status_code}")
        if self.model_name:
            parts.append(f"model='{self.model_name}'")
        return f"LLMError({', '.join(parts)})"

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리 형태로 변환 (JSON 직렬화용)"""
        data = super().to_dict()
        data.update(
            {
                "status_code": self.status_code,
                "endpoint": self.endpoint,
                "model_name": self.model_name,
                "prompt_preview": self.prompt_preview,
            }
        )
        return data

    def is_client_error(self) -> bool:
        """클라이언트 오류인지 확인 (4xx 상태 코드)"""
        return self.status_code is not None and 400 <= self.status_code < 500

    def is_server_error(self) -> bool:
        """서버 오류인지 확인 (5xx 상태 코드)"""
        return self.status_code is not None and 500 <= self.status_code < 600

    def is_retryable(self) -> bool:
        """재시도 가능한 오류인지 확인"""
        # 서버 오류나 네트워크 관련 오류는 재시도 가능
        if self.is_server_error():
            return True

        # 특정 클라이언트 오류도 재시도 가능 (예: 429 Too Many Requests)
        if self.status_code in [408, 429]:  # Request Timeout, Too Many Requests
            return True

        return False


class ValidationError(AnalysisError):
    """
    입력 검증 관련 오류 예외 클래스

    요청 파라미터, 데이터 형식, 비즈니스 규칙 검증 등
    입력 데이터 유효성 검사 중 발생하는 오류를 처리합니다.
    """

    def __init__(
        self,
        message: str,
        details: Optional[Union[str, Dict[str, Any]]] = None,
        field_name: Optional[str] = None,
        field_value: Optional[Any] = None,
        validation_rule: Optional[str] = None,
    ) -> None:
        """
        ValidationError 초기화

        Args:
            message (str): 오류 메시지
            details (Optional[Union[str, Dict[str, Any]]]): 추가 상세 정보
            field_name (Optional[str]): 검증에 실패한 필드명
            field_value (Optional[Any]): 검증에 실패한 값
            validation_rule (Optional[str]): 위반된 검증 규칙

        Examples:
            >>> raise ValidationError("시간 범위 형식이 잘못되었습니다")
            >>> raise ValidationError(
            ...     "필수 필드가 누락되었습니다",
            ...     field_name="n_minus_1",
            ...     validation_rule="required"
            ... )
        """
        super().__init__(message, details)
        self.field_name = field_name
        self.field_value = field_value
        self.validation_rule = validation_rule

        # 로깅: 검증 오류 상세 정보
        log_details = {
            "field": field_name,
            "rule": validation_rule,
            "value_type": type(field_value).__name__ if field_value is not None else None,
        }
        logger.warning("ValidationError 발생: %s, 상세: %s", message, log_details)

    def __repr__(self) -> str:
        """개발자용 문자열 표현"""
        parts = [f"message='{self.message}'"]
        if self.field_name:
            parts.append(f"field='{self.field_name}'")
        if self.validation_rule:
            parts.append(f"rule='{self.validation_rule}'")
        return f"ValidationError({', '.join(parts)})"

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리 형태로 변환 (JSON 직렬화용)"""
        data = super().to_dict()
        data.update(
            {
                "field_name": self.field_name,
                "field_value": str(self.field_value) if self.field_value is not None else None,
                "validation_rule": self.validation_rule,
            }
        )
        return data

    def is_required_field_error(self) -> bool:
        """필수 필드 누락 오류인지 확인"""
        return self.validation_rule == "required"

    def is_format_error(self) -> bool:
        """형식 오류인지 확인"""
        return self.validation_rule in ["format", "pattern", "type"]


class ServiceError(AnalysisError):
    """
    서비스 레이어 관련 오류 예외 클래스

    비즈니스 로직 처리, 서비스 간 통신, 워크플로우 실행 등
    서비스 레이어에서 발생하는 오류를 처리합니다.
    """

    def __init__(
        self,
        message: str,
        details: Optional[Union[str, Dict[str, Any]]] = None,
        service_name: Optional[str] = None,
        operation: Optional[str] = None,
        retry_count: int = 0,
    ) -> None:
        """
        ServiceError 초기화

        Args:
            message (str): 오류 메시지
            details (Optional[Union[str, Dict[str, Any]]]): 추가 상세 정보
            service_name (Optional[str]): 오류가 발생한 서비스명
            operation (Optional[str]): 실패한 작업명
            retry_count (int): 재시도 횟수

        Examples:
            >>> raise ServiceError("분석 서비스 실행 실패")
            >>> raise ServiceError(
            ...     "PEG 처리 중 오류",
            ...     service_name="PEGProcessingService",
            ...     operation="aggregate_peg_data",
            ...     retry_count=2
            ... )
        """
        super().__init__(message, details)
        self.service_name = service_name
        self.operation = operation
        self.retry_count = retry_count

        # 로깅: 서비스 오류 상세 정보
        log_details = {"service": service_name, "operation": operation, "retry_count": retry_count}
        logger.error("ServiceError 발생: %s, 상세: %s", message, log_details)

    def __repr__(self) -> str:
        """개발자용 문자열 표현"""
        parts = [f"message='{self.message}'"]
        if self.service_name:
            parts.append(f"service='{self.service_name}'")
        if self.operation:
            parts.append(f"operation='{self.operation}'")
        if self.retry_count > 0:
            parts.append(f"retries={self.retry_count}")
        return f"ServiceError({', '.join(parts)})"

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리 형태로 변환 (JSON 직렬화용)"""
        data = super().to_dict()
        data.update({"service_name": self.service_name, "operation": self.operation, "retry_count": self.retry_count})
        return data

    def increment_retry(self) -> None:
        """재시도 횟수 증가"""
        self.retry_count += 1
        logger.debug("ServiceError 재시도 횟수 증가: %d", self.retry_count)

    def has_retries(self) -> bool:
        """재시도가 있었는지 확인"""
        return self.retry_count > 0


class RepositoryError(AnalysisError):
    """
    저장소 레이어 관련 일반 오류 예외 클래스

    데이터 접근, 외부 API 호출, 파일 시스템 작업 등
    저장소 레이어에서 발생하는 일반적인 오류를 처리합니다.

    Note: 구체적인 데이터베이스 오류는 DatabaseError,
          LLM 관련 오류는 LLMError를 사용하세요.
    """

    def __init__(
        self,
        message: str,
        details: Optional[Union[str, Dict[str, Any]]] = None,
        repository_name: Optional[str] = None,
        operation_type: Optional[str] = None,
        resource: Optional[str] = None,
    ) -> None:
        """
        RepositoryError 초기화

        Args:
            message (str): 오류 메시지
            details (Optional[Union[str, Dict[str, Any]]]): 추가 상세 정보
            repository_name (Optional[str]): 오류가 발생한 저장소명
            operation_type (Optional[str]): 작업 유형 (read, write, delete 등)
            resource (Optional[str]): 접근하려던 리소스 (파일명, URL 등)

        Examples:
            >>> raise RepositoryError("파일 읽기 실패")
            >>> raise RepositoryError(
            ...     "백엔드 API 호출 실패",
            ...     repository_name="BackendClient",
            ...     operation_type="POST",
            ...     resource="/api/analysis-result"
            ... )
        """
        super().__init__(message, details)
        self.repository_name = repository_name
        self.operation_type = operation_type
        self.resource = resource

        # 로깅: 저장소 오류 상세 정보
        log_details = {"repository": repository_name, "operation": operation_type, "resource": resource}
        logger.error("RepositoryError 발생: %s, 상세: %s", message, log_details)

    def __repr__(self) -> str:
        """개발자용 문자열 표현"""
        parts = [f"message='{self.message}'"]
        if self.repository_name:
            parts.append(f"repository='{self.repository_name}'")
        if self.operation_type:
            parts.append(f"operation='{self.operation_type}'")
        if self.resource:
            resource_preview = self.resource[:30] + "..." if len(self.resource) > 30 else self.resource
            parts.append(f"resource='{resource_preview}'")
        return f"RepositoryError({', '.join(parts)})"

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리 형태로 변환 (JSON 직렬화용)"""
        data = super().to_dict()
        data.update(
            {"repository_name": self.repository_name, "operation_type": self.operation_type, "resource": self.resource}
        )
        return data

    def is_read_operation(self) -> bool:
        """읽기 작업 오류인지 확인"""
        return self.operation_type and self.operation_type.upper() in ["READ", "GET", "SELECT"]

    def is_write_operation(self) -> bool:
        """쓰기 작업 오류인지 확인"""
        return self.operation_type and self.operation_type.upper() in ["WRITE", "POST", "PUT", "INSERT", "UPDATE"]

    def is_delete_operation(self) -> bool:
        """삭제 작업 오류인지 확인"""
        return self.operation_type and self.operation_type.upper() in ["DELETE", "REMOVE"]
