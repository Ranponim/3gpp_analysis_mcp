"""
Request Validator

이 모듈은 MCP 요청 데이터의 검증과 정규화를 담당하는
RequestValidator 클래스를 제공합니다.

기존에 분산되어 있던 검증 로직들을 중앙 집중화하여
일관된 검증 시스템을 구축합니다.
"""

from __future__ import annotations

import logging
import os
import re

# 임시로 절대 import 사용 (나중에 패키지 구조 정리 시 수정)
import sys
from typing import Any, Dict, Optional, Union

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from exceptions import ValidationError
from utils import TimeParsingError, TimeRangeParser

# 로깅 설정
logger = logging.getLogger(__name__)


class RequestValidationError(ValidationError):
    """
    요청 검증 관련 오류 예외 클래스

    RequestValidator에서 발생하는 검증 오류를 처리합니다.
    """

    def __init__(
        self,
        message: str,
        field_name: Optional[str] = None,
        field_value: Optional[Any] = None,
        validation_rule: Optional[str] = None,
        details: Optional[Union[str, Dict[str, Any]]] = None,
    ) -> None:
        """
        RequestValidationError 초기화

        Args:
            message (str): 오류 메시지
            field_name (Optional[str]): 검증 실패 필드명
            field_value (Optional[Any]): 검증 실패 필드값
            validation_rule (Optional[str]): 적용된 검증 규칙
            details (Optional[Union[str, Dict[str, Any]]]): 추가 상세 정보
        """
        super().__init__(
            message=message,
            field_name=field_name,
            field_value=field_value,
            validation_rule=validation_rule,
            details=details,
        )

        logger.error("RequestValidationError 발생: %s (필드: %s)", message, field_name)


class RequestValidator:
    """
    요청 검증 클래스

    MCP 요청 데이터의 구조, 타입, 값 범위, 논리적 일관성을 검증합니다.
    기존에 분산되어 있던 검증 로직들을 중앙 집중화합니다.

    검증 범위:
    1. 필수 필드 존재 검증 (n_minus_1, n)
    2. 데이터 타입 검증 (dict, string, int, float)
    3. 시간 범위 형식 및 논리 검증
    4. DB 설정 검증 (host, port, credentials)
    5. 필터 조건 검증 (ne, cellid, host)
    6. PEG 설정 검증 (derived_pegs, selected_pegs)
    7. 범위 값 검증 (max_tokens, confidence_score)
    """

    def __init__(self, time_parser: Optional[TimeRangeParser] = None):
        """
        RequestValidator 초기화

        Args:
            time_parser (Optional[TimeRangeParser]): 시간 범위 파서
        """
        self.time_parser = time_parser or TimeRangeParser()
        self.logger = logging.getLogger(__name__ + ".RequestValidator")

        # 검증 단계 정의
        self.validation_steps = [
            "structure_validation",
            "required_fields",
            "data_types",
            "value_ranges",
            "time_ranges",
            "nested_structures",
        ]

        # 필수 필드 정의
        self.required_fields = ["n_minus_1", "n"]

        # 선택적 필드 기본값
        self.optional_field_defaults = {
            "output_dir": "./analysis_output",
            "table": "summary",
            "analysis_type": "enhanced",
            "enable_mock": False,
            "max_prompt_tokens": 8000,
            "max_prompt_chars": 32000,
        }

        self.logger.info("RequestValidator 초기화 완료")

    def get_validator_info(self) -> Dict[str, Any]:
        """검증기 정보 반환"""
        return {
            "validator_name": "RequestValidator",
            "validation_steps": self.validation_steps,
            "required_fields": self.required_fields,
            "optional_field_defaults": self.optional_field_defaults,
        }

    def validate_structure(self, request: Any) -> None:
        """
        요청 구조 기본 검증

        Args:
            request (Any): 검증할 요청 데이터

        Raises:
            RequestValidationError: 구조가 유효하지 않은 경우
        """
        self.logger.debug("validate_structure() 호출: 구조 검증")

        # 딕셔너리 타입 확인
        if not isinstance(request, dict):
            raise RequestValidationError(
                "요청은 딕셔너리 형태여야 합니다",
                field_name="request",
                field_value=type(request).__name__,
                validation_rule="type_check",
            )

        # 빈 요청 확인
        if not request:
            raise RequestValidationError(
                "요청이 비어있습니다", field_name="request", field_value=request, validation_rule="non_empty"
            )

        self.logger.info("구조 검증 통과: 딕셔너리 타입, %d개 키", len(request))

    def validate_required_fields(self, request: Dict[str, Any]) -> None:
        """
        필수 필드 존재 검증

        Args:
            request (Dict[str, Any]): 검증할 요청 데이터

        Raises:
            RequestValidationError: 필수 필드가 누락된 경우
        """
        self.logger.debug("validate_required_fields() 호출: 필수 필드 검증")

        missing_fields = []

        for field in self.required_fields:
            # n_minus_1의 별칭 지원 (n1)
            if field == "n_minus_1":
                if not request.get("n_minus_1") and not request.get("n1"):
                    missing_fields.append("n_minus_1 (또는 n1)")
            else:
                if not request.get(field):
                    missing_fields.append(field)

        if missing_fields:
            raise RequestValidationError(
                f"필수 필드가 누락되었습니다: {missing_fields}",
                field_name="required_fields",
                field_value=missing_fields,
                validation_rule="required_check",
            )

        self.logger.info("필수 필드 검증 통과: %s", self.required_fields)

    def validate_scalar_parameters(self, request: Dict[str, Any]) -> None:
        """
        스칼라 매개변수 검증 (타입 및 범위)

        Args:
            request (Dict[str, Any]): 검증할 요청 데이터

        Raises:
            RequestValidationError: 스칼라 매개변수가 유효하지 않은 경우
        """
        self.logger.debug("validate_scalar_parameters() 호출: 스칼라 매개변수 검증")

        # output_dir 검증
        if "output_dir" in request:
            output_dir = request["output_dir"]
            if not isinstance(output_dir, str):
                raise RequestValidationError(
                    "output_dir은 문자열이어야 합니다",
                    field_name="output_dir",
                    field_value=type(output_dir).__name__,
                    validation_rule="string_type",
                )

        # max_prompt_tokens 검증
        if "max_prompt_tokens" in request:
            max_tokens = request["max_prompt_tokens"]
            if not isinstance(max_tokens, int) or max_tokens <= 0:
                raise RequestValidationError(
                    "max_prompt_tokens는 양의 정수여야 합니다",
                    field_name="max_prompt_tokens",
                    field_value=max_tokens,
                    validation_rule="positive_integer",
                )

            if max_tokens > 50000:  # 상한선
                raise RequestValidationError(
                    "max_prompt_tokens가 너무 큽니다 (최대: 50000)",
                    field_name="max_prompt_tokens",
                    field_value=max_tokens,
                    validation_rule="max_limit",
                )

        # max_prompt_chars 검증
        if "max_prompt_chars" in request:
            max_chars = request["max_prompt_chars"]
            if not isinstance(max_chars, int) or max_chars <= 0:
                raise RequestValidationError(
                    "max_prompt_chars는 양의 정수여야 합니다",
                    field_name="max_prompt_chars",
                    field_value=max_chars,
                    validation_rule="positive_integer",
                )

        # analysis_type 검증
        if "analysis_type" in request:
            analysis_type = request["analysis_type"]
            valid_types = ["overall", "enhanced", "specific"]
            if analysis_type not in valid_types:
                raise RequestValidationError(
                    f"analysis_type은 {valid_types} 중 하나여야 합니다",
                    field_name="analysis_type",
                    field_value=analysis_type,
                    validation_rule="enum_check",
                )

        self.logger.info("스칼라 매개변수 검증 통과")

    def validate_time_ranges(self, request: Dict[str, Any]) -> None:
        """
        시간 범위 검증 (TimeRangeParser 활용)

        Args:
            request (Dict[str, Any]): 검증할 요청 데이터

        Raises:
            RequestValidationError: 시간 범위가 유효하지 않은 경우
        """
        self.logger.debug("validate_time_ranges() 호출: 시간 범위 검증")

        # 변수 초기화
        n1_text = request.get("n_minus_1") or request.get("n1")
        n_text = request.get("n")

        try:
            # n_minus_1 시간 범위 검증
            if n1_text:
                n1_start, n1_end = self.time_parser.parse(n1_text)
                self.logger.debug("n_minus_1 파싱 성공: %s ~ %s", n1_start, n1_end)

            # n 시간 범위 검증
            if n_text:
                n_start, n_end = self.time_parser.parse(n_text)
                self.logger.debug("n 파싱 성공: %s ~ %s", n_start, n_end)

            # 논리적 일관성 검증 (N-1 < N)
            if n1_text and n_text:
                # 다시 파싱 (로컬 변수 문제 해결)
                n1_start, n1_end = self.time_parser.parse(n1_text)
                n_start, n_end = self.time_parser.parse(n_text)

                if n1_end >= n_start:
                    self.logger.warning("시간 범위 중복 또는 역순: N-1 끝(%s) >= N 시작(%s)", n1_end, n_start)
                    # 경고만 하고 계속 진행 (비즈니스 로직에서 허용될 수 있음)

            self.logger.info("시간 범위 검증 통과")

        except TimeParsingError as e:
            raise RequestValidationError(
                f"시간 범위 형식 오류: {e.message}",
                field_name="time_ranges",
                field_value={"n_minus_1": n1_text, "n": n_text},
                validation_rule="time_format",
                details=e.to_dict(),
            ) from e

        except Exception as e:
            raise RequestValidationError(
                f"시간 범위 검증 중 예상치 못한 오류: {e}",
                field_name="time_ranges",
                field_value={"n_minus_1": n1_text, "n": n_text},
                validation_rule="time_validation",
            ) from e

    def validate_db_config(self, db_config: Dict[str, Any]) -> None:
        """
        데이터베이스 설정 검증

        Args:
            db_config (Dict[str, Any]): DB 설정

        Raises:
            RequestValidationError: DB 설정이 유효하지 않은 경우
        """
        self.logger.debug("validate_db_config() 호출: DB 설정 검증")

        if not isinstance(db_config, dict):
            raise RequestValidationError(
                "db 설정은 딕셔너리 형태여야 합니다",
                field_name="db",
                field_value=type(db_config).__name__,
                validation_rule="dict_type",
            )

        # 필수 DB 필드
        required_db_fields = ["host", "dbname"]
        missing_db_fields = [field for field in required_db_fields if not db_config.get(field)]

        if missing_db_fields:
            raise RequestValidationError(
                f"DB 설정에 필수 필드가 누락되었습니다: {missing_db_fields}",
                field_name="db",
                field_value=missing_db_fields,
                validation_rule="required_db_fields",
            )

        # 포트 번호 검증
        if "port" in db_config:
            port = db_config["port"]
            if not isinstance(port, int) or port <= 0 or port > 65535:
                raise RequestValidationError(
                    "port는 1-65535 범위의 정수여야 합니다",
                    field_name="db.port",
                    field_value=port,
                    validation_rule="port_range",
                )

        # 호스트 형식 검증 (기본적인 형식만)
        host = db_config.get("host", "")
        if not isinstance(host, str) or not host.strip():
            raise RequestValidationError(
                "host는 비어있지 않은 문자열이어야 합니다",
                field_name="db.host",
                field_value=host,
                validation_rule="non_empty_string",
            )

        self.logger.info("DB 설정 검증 통과: host=%s, port=%s", host, db_config.get("port", "default"))

    def validate_filters(self, filters: Dict[str, Any]) -> None:
        """
        필터 조건 검증

        Args:
            filters (Dict[str, Any]): 필터 설정

        Raises:
            RequestValidationError: 필터가 유효하지 않은 경우
        """
        self.logger.debug("validate_filters() 호출: 필터 검증")

        if not isinstance(filters, dict):
            raise RequestValidationError(
                "filters는 딕셔너리 형태여야 합니다",
                field_name="filters",
                field_value=type(filters).__name__,
                validation_rule="dict_type",
            )

        # 지원하는 필터 필드
        supported_filter_fields = ["ne", "cellid", "cell", "host"]

        for filter_name, filter_value in filters.items():
            if filter_name not in supported_filter_fields:
                self.logger.warning("지원하지 않는 필터 필드: %s", filter_name)
                continue

            # 필터 값 타입 검증 (문자열, 리스트, 또는 None)
            if filter_value is not None:
                if not isinstance(filter_value, (str, list)):
                    raise RequestValidationError(
                        f"필터 '{filter_name}'의 값은 문자열 또는 리스트여야 합니다",
                        field_name=f"filters.{filter_name}",
                        field_value=type(filter_value).__name__,
                        validation_rule="filter_value_type",
                    )

                # 리스트인 경우 내부 요소 검증
                if isinstance(filter_value, list):
                    for i, item in enumerate(filter_value):
                        if not isinstance(item, (str, int, float)):
                            raise RequestValidationError(
                                f"필터 '{filter_name}' 리스트의 {i}번째 요소는 문자열, 정수, 또는 실수여야 합니다",
                                field_name=f"filters.{filter_name}[{i}]",
                                field_value=type(item).__name__,
                                validation_rule="filter_item_type",
                            )

        self.logger.info("필터 검증 통과: %d개 필터", len(filters))

    def validate_peg_config(self, peg_config: Dict[str, Any]) -> None:
        """
        PEG 설정 검증

        Args:
            peg_config (Dict[str, Any]): PEG 설정

        Raises:
            RequestValidationError: PEG 설정이 유효하지 않은 경우
        """
        self.logger.debug("validate_peg_config() 호출: PEG 설정 검증")

        if not isinstance(peg_config, dict):
            raise RequestValidationError(
                "PEG 설정은 딕셔너리 형태여야 합니다",
                field_name="peg_config",
                field_value=type(peg_config).__name__,
                validation_rule="dict_type",
            )

        # selected_pegs 검증
        if "selected_pegs" in peg_config:
            selected_pegs = peg_config["selected_pegs"]
            if selected_pegs is not None:
                if not isinstance(selected_pegs, list):
                    raise RequestValidationError(
                        "selected_pegs는 리스트여야 합니다",
                        field_name="peg_config.selected_pegs",
                        field_value=type(selected_pegs).__name__,
                        validation_rule="list_type",
                    )

                # 리스트 내부 요소 검증
                for i, peg_name in enumerate(selected_pegs):
                    if not isinstance(peg_name, str) or not peg_name.strip():
                        raise RequestValidationError(
                            f"selected_pegs[{i}]는 비어있지 않은 문자열이어야 합니다",
                            field_name=f"peg_config.selected_pegs[{i}]",
                            field_value=peg_name,
                            validation_rule="non_empty_string",
                        )

        # peg_definitions 검증 (파생 PEG 수식)
        if "peg_definitions" in peg_config:
            peg_definitions = peg_config["peg_definitions"]
            if peg_definitions is not None:
                if not isinstance(peg_definitions, dict):
                    raise RequestValidationError(
                        "peg_definitions는 딕셔너리여야 합니다",
                        field_name="peg_config.peg_definitions",
                        field_value=type(peg_definitions).__name__,
                        validation_rule="dict_type",
                    )

                # 수식 기본 검증
                for peg_name, formula in peg_definitions.items():
                    if not isinstance(peg_name, str) or not peg_name.strip():
                        raise RequestValidationError(
                            "파생 PEG 이름은 비어있지 않은 문자열이어야 합니다",
                            field_name="peg_config.peg_definitions.key",
                            field_value=peg_name,
                            validation_rule="non_empty_string",
                        )

                    if not isinstance(formula, str) or not formula.strip():
                        raise RequestValidationError(
                            f"파생 PEG '{peg_name}'의 수식은 비어있지 않은 문자열이어야 합니다",
                            field_name=f"peg_config.peg_definitions.{peg_name}",
                            field_value=formula,
                            validation_rule="non_empty_string",
                        )

                    # 기본 수식 구문 검증 (간단한 정규식)
                    if not re.match(r"^[A-Za-z0-9_+\-*/().\s]+$", formula):
                        raise RequestValidationError(
                            f"파생 PEG '{peg_name}'의 수식에 허용되지 않은 문자가 포함되어 있습니다",
                            field_name=f"peg_config.peg_definitions.{peg_name}",
                            field_value=formula,
                            validation_rule="formula_syntax",
                        )

        self.logger.info("PEG 설정 검증 통과")

    def validate_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        전체 요청 검증 및 정규화

        Args:
            request (Dict[str, Any]): 검증할 요청 데이터

        Returns:
            Dict[str, Any]: 검증되고 정규화된 요청 데이터

        Raises:
            RequestValidationError: 검증 실패 시
        """
        self.logger.info("validate_request() 호출: 전체 요청 검증 시작")

        try:
            # 1단계: 구조 검증
            self.logger.info("1단계: 구조 검증")
            self.validate_structure(request)

            # 2단계: 필수 필드 검증
            self.logger.info("2단계: 필수 필드 검증")
            self.validate_required_fields(request)

            # 3단계: 스칼라 매개변수 검증
            self.logger.info("3단계: 스칼라 매개변수 검증")
            self.validate_scalar_parameters(request)

            # 4단계: 시간 범위 검증
            self.logger.info("4단계: 시간 범위 검증")
            self.validate_time_ranges(request)

            # 5단계: 중첩 구조 검증
            self.logger.info("5단계: 중첩 구조 검증")

            # DB 설정 검증 (선택적)
            if "db" in request and request["db"]:
                self.validate_db_config(request["db"])

            # 필터 검증 (선택적)
            if "filters" in request and request["filters"]:
                self.validate_filters(request["filters"])

            # PEG 설정 검증 (선택적)
            peg_config = {}
            if "selected_pegs" in request:
                peg_config["selected_pegs"] = request["selected_pegs"]
            if "peg_definitions" in request:
                peg_config["peg_definitions"] = request["peg_definitions"]
            if peg_config:
                self.validate_peg_config(peg_config)

            # 6단계: 정규화 (기본값 적용)
            self.logger.info("6단계: 요청 정규화")
            normalized_request = self._normalize_request(request)

            self.logger.info("전체 요청 검증 완료: %d개 필드", len(normalized_request))
            return normalized_request

        except RequestValidationError:
            # 이미 RequestValidationError인 경우 그대로 전파
            raise

        except Exception as e:
            # 예상치 못한 오류를 RequestValidationError로 변환
            raise RequestValidationError(
                f"요청 검증 중 예상치 못한 오류: {e}", field_name="unknown", validation_rule="unknown"
            ) from e

    def _normalize_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        요청 데이터 정규화 (기본값 적용)

        Args:
            request (Dict[str, Any]): 원본 요청

        Returns:
            Dict[str, Any]: 정규화된 요청
        """
        self.logger.debug("_normalize_request() 호출: 요청 정규화")

        normalized = request.copy()

        # 기본값 적용
        for field, default_value in self.optional_field_defaults.items():
            if field not in normalized or normalized[field] is None:
                normalized[field] = default_value
                self.logger.debug("기본값 적용: %s = %s", field, default_value)

        # n_minus_1 별칭 처리 (n1 → n_minus_1)
        if "n1" in normalized and "n_minus_1" not in normalized:
            normalized["n_minus_1"] = normalized["n1"]
            del normalized["n1"]
            self.logger.debug("별칭 변환: n1 → n_minus_1")

        # cellid 별칭 처리 (cell → cellid)
        if "filters" in normalized and isinstance(normalized["filters"], dict):
            filters = normalized["filters"]
            if "cell" in filters and "cellid" not in filters:
                filters["cellid"] = filters["cell"]
                del filters["cell"]
                self.logger.debug("필터 별칭 변환: cell → cellid")

        self.logger.info("요청 정규화 완료: %d개 필드", len(normalized))
        return normalized

    def get_validation_status(self) -> Dict[str, Any]:
        """검증 상태 정보 반환"""
        return {
            "validation_steps": self.validation_steps,
            "step_count": len(self.validation_steps),
            "required_fields": self.required_fields,
            "optional_defaults": len(self.optional_field_defaults),
            "is_ready": True,
        }
