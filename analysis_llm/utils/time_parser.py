"""
Time Range Parser Utility

이 모듈은 시간 범위 문자열 파싱을 담당하는 TimeRangeParser 클래스를 제공합니다.
기존 main.py의 parse_time_range() 및 _get_default_tzinfo() 로직을 모듈화한 것입니다.
"""

from __future__ import annotations

import datetime
import logging
import re
from typing import Optional, Tuple

from .exceptions import TimeParsingError

# 로깅 설정
logger = logging.getLogger(__name__)


class TimeRangeParser:
    """
    시간 범위 문자열 파싱 클래스

    기존 main.py의 parse_time_range() 함수 로직을 클래스로 모듈화하여
    재사용 가능하고 테스트 가능한 형태로 제공합니다.

    지원하는 형식:
    1. 범위 형식: "YYYY-MM-DD_HH:MM~YYYY-MM-DD_HH:MM" 또는 "YYYY-MM-DD-HH:MM~YYYY-MM-DD-HH:MM"
    2. 단일 날짜: "YYYY-MM-DD" (00:00:00 ~ 23:59:59로 자동 확장)

    특징:
    - 유연한 포맷: 날짜와 시간 구분자로 '_' 또는 '-' 허용
    - 타임존 지원: 환경변수 DEFAULT_TZ_OFFSET에서 타임존 정보 읽기
    - 상세한 오류 처리: 형식/값/논리/타입 오류를 세분화하여 명확한 예외 메시지 제공
    """

    def __init__(self):
        """TimeRangeParser 초기화"""
        logger.debug("TimeRangeParser 인스턴스 생성")

        # 정규식 패턴 미리 컴파일 (성능 최적화)
        self._date_pattern = re.compile(r"\d{4}-\d{2}-\d{2}")
        self._time_pattern = re.compile(r"\d{2}:\d{2}")
        self._datetime_pattern_flexible = re.compile(r"\d{4}-\d{2}-\d{2}[_-]\d{2}:\d{2}")

        logger.debug("TimeRangeParser 초기화 완료")

    def _get_timezone(self) -> datetime.tzinfo:
        """
        환경 변수에서 기본 타임존 정보를 생성하는 메서드

        기존 main.py의 _get_default_tzinfo() 함수와 동일한 로직입니다.
        환경 변수 `DEFAULT_TZ_OFFSET`(예: "+09:00")를 읽어서 tzinfo 객체를 생성합니다.
        설정이 없거나 형식이 잘못된 경우 UTC를 반환합니다.

        Returns:
            datetime.tzinfo: 타임존 정보 객체
        """
        logger.debug("_get_timezone() 호출: 기본 타임존 정보 생성 시작")

        # Configuration Manager에서 타임존 설정 가져오기
        try:
            # 상위 디렉토리에서 config 모듈 import
            import os
            import sys

            sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            from config import get_settings

            settings = get_settings()
            timezone_config = settings.get_timezone_config_dict()
            app_timezone = timezone_config["app_timezone"]

            # UTC가 아닌 경우 오프셋 계산 (간단한 매핑)
            timezone_offsets = {
                "UTC": "+00:00",
                "Asia/Seoul": "+09:00",
                "Asia/Tokyo": "+09:00",
                "America/New_York": "-05:00",  # EST (간단화)
                "Europe/London": "+00:00",  # GMT (간단화)
            }
            offset_text = timezone_offsets.get(app_timezone, "+09:00")
            logger.debug("Configuration Manager에서 타임존 오프셋: %s (from %s)", offset_text, app_timezone)

        except Exception as e:
            # 폴백: 환경변수 직접 사용
            offset_text = os.getenv("DEFAULT_TZ_OFFSET", "+09:00").strip()
            logger.debug("타임존 오프셋 환경변수 (폴백): %s", offset_text)

        try:
            # 부호 확인 (+ 또는 -)
            if offset_text.startswith("+"):
                sign = 1
                offset_clean = offset_text[1:]
            elif offset_text.startswith("-"):
                sign = -1
                offset_clean = offset_text[1:]
            else:
                # 부호가 없으면 양수로 처리
                sign = 1
                offset_clean = offset_text
                logger.debug("부호가 없는 타임존 오프셋, 양수로 처리: %s", offset_text)

            # HH:MM 형식 검증 및 파싱
            if ":" not in offset_clean:
                raise ValueError(f"타임존 오프셋에 ':' 구분자가 없습니다: {offset_clean}")

            time_parts = offset_clean.split(":")
            if len(time_parts) != 2:
                raise ValueError(f"타임존 오프셋 형식이 잘못되었습니다: {offset_clean}")

            try:
                hours = int(time_parts[0])
                minutes = int(time_parts[1])
            except ValueError as ve:
                raise ValueError(f"타임존 시간/분이 숫자가 아닙니다: {time_parts} ({ve})")

            # 값 범위 검증
            if hours < 0 or hours > 23:
                raise ValueError(f"잘못된 시간: {hours} (0-23 범위)")
            if minutes < 0 or minutes > 59:
                raise ValueError(f"잘못된 분: {minutes} (0-59 범위)")

            # timedelta 객체 생성
            delta = datetime.timedelta(hours=hours * sign, minutes=minutes * sign)
            tzinfo = datetime.timezone(delta)

            logger.info("타임존 정보 생성 성공: %s → %s", offset_text, tzinfo)
            return tzinfo

        except Exception as e:
            logger.warning("DEFAULT_TZ_OFFSET 파싱 실패, UTC 사용: %s (오류: %s)", offset_text, e)
            return datetime.timezone.utc

    def get_supported_formats(self) -> list[str]:
        """지원하는 시간 형식 목록 반환"""
        return ["YYYY-MM-DD_HH:MM~YYYY-MM-DD_HH:MM", "YYYY-MM-DD-HH:MM~YYYY-MM-DD-HH:MM", "YYYY-MM-DD"]

    def validate_input_type(self, range_text: any) -> None:
        """입력 타입 검증 (1단계)"""
        logger.debug("1단계: 타입 검증 시작")

        if not isinstance(range_text, str):
            raise TimeParsingError(
                message="입력은 문자열(str)이어야 합니다",
                error_code="TYPE_ERROR",
                input_value=str(range_text),
                details={"received_type": type(range_text).__name__},
            )

        logger.debug("타입 검증 통과: str 타입 확인됨")

    def preprocess_and_validate_format(self, range_text: str) -> str:
        """전처리 및 기본 형식 검증 (2단계)"""
        logger.debug("2단계: 전처리 및 기본 검증 시작")

        text = (range_text or "").strip()
        logger.debug("입력 문자열 전처리: 원본='%s' → 정제='%s'", range_text, text)

        if text == "":
            raise TimeParsingError(
                message="빈 시간 범위 문자열입니다",
                error_code="FORMAT_ERROR",
                hint="예: 2025-08-08_15:00~2025-08-08_19:00 또는 2025-08-08-15:00~2025-08-08-19:00 또는 2025-08-08",
                input_value=range_text,
            )

        logger.debug("기본 검증 통과: 빈 문자열 아님")
        return text

    def normalize_datetime_format(self, dt_str: str) -> str:
        """날짜-시간 구분자를 표준 '_' 포맷으로 변환"""
        # YYYY-MM-DD-HH:MM 형태를 YYYY-MM-DD_HH:MM로 변환
        # 마지막 '-'만 '_'로 바꾸기 위해 rsplit 사용
        if ":" in dt_str:
            # 시간 부분이 있는 경우
            if dt_str.count("-") >= 3:  # YYYY-MM-DD-HH:MM 형태 (- 구분자가 3개 이상)
                parts = dt_str.rsplit("-", 1)
                if len(parts) == 2 and ":" in parts[1]:
                    # 마지막 '-'가 시간 구분자인 경우에만 '_'로 변환
                    result = f"{parts[0]}_{parts[1]}"
                    logger.debug("날짜-시간 구분자 정규화: %s → %s", dt_str, result)
                    return result

        # 이미 '_' 형식이거나 변환이 불필요한 경우 그대로 반환
        return dt_str

    def parse_range_format(self, text: str, tzinfo: datetime.tzinfo) -> Tuple[datetime.datetime, datetime.datetime]:
        """범위 형식 파싱 (YYYY-MM-DD_HH:MM~YYYY-MM-DD_HH:MM)"""
        logger.debug("범위 형식 파싱 시작: %s", text)

        # '~'가 여러 개인 경우 오류
        if text.count("~") != 1:
            raise TimeParsingError(
                message="범위 구분자 '~'가 없거나 잘못되었습니다",
                error_code="FORMAT_ERROR",
                hint="예: 2025-08-08_15:00~2025-08-08_19:00 또는 2025-08-08-15:00~2025-08-08-19:00",
                input_value=text,
            )

        # 공백 허용 분리
        parts = [p.strip() for p in text.split("~")]
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise TimeParsingError(
                message="시작/종료 시각이 모두 필요합니다", error_code="FORMAT_ERROR", input_value=text
            )

        left, right = parts[0], parts[1]

        # 각 토큰 형식 검증 (유연한 패턴 사용)
        if not self._datetime_pattern_flexible.fullmatch(left):
            raise TimeParsingError(
                message="왼쪽 시각 형식이 올바르지 않습니다 (YYYY-MM-DD_HH:MM 또는 YYYY-MM-DD-HH:MM)",
                error_code="FORMAT_ERROR",
                input_value=left,
            )

        if not self._datetime_pattern_flexible.fullmatch(right):
            raise TimeParsingError(
                message="오른쪽 시각 형식이 올바르지 않습니다 (YYYY-MM-DD_HH:MM 또는 YYYY-MM-DD-HH:MM)",
                error_code="FORMAT_ERROR",
                input_value=right,
            )

        # 내부 처리를 위해 표준 _ 포맷으로 변환
        left_normalized = self.normalize_datetime_format(left)
        right_normalized = self.normalize_datetime_format(right)

        logger.info("입력 정규화: %s → %s, %s → %s", left, left_normalized, right, right_normalized)

        # 값 검증 (존재하지 않는 날짜/시간 등)
        try:
            start_dt = datetime.datetime.strptime(left_normalized, "%Y-%m-%d_%H:%M")
            end_dt = datetime.datetime.strptime(right_normalized, "%Y-%m-%d_%H:%M")
        except Exception as e:
            raise TimeParsingError(
                message=f"유효하지 않은 날짜/시간입니다: {e}", error_code="VALUE_ERROR", input_value=text
            )

        # 타임존 부여
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=tzinfo)
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=tzinfo)

        return start_dt, end_dt

    def parse_single_date_format(
        self, text: str, tzinfo: datetime.tzinfo
    ) -> Tuple[datetime.datetime, datetime.datetime]:
        """단일 날짜 형식 파싱 (YYYY-MM-DD)"""
        logger.debug("단일 날짜 형식 파싱 시작: %s", text)

        try:
            day = datetime.datetime.strptime(text, "%Y-%m-%d").date()
        except Exception as e:
            raise TimeParsingError(message=f"유효하지 않은 날짜입니다: {e}", error_code="VALUE_ERROR", input_value=text)

        start_dt = datetime.datetime.combine(day, datetime.time(0, 0, 0, tzinfo=tzinfo))
        end_dt = datetime.datetime.combine(day, datetime.time(23, 59, 59, tzinfo=tzinfo))

        logger.info("단일 날짜 확장: %s → %s ~ %s", text, start_dt, end_dt)
        return start_dt, end_dt

    def validate_time_logic(self, start_dt: datetime.datetime, end_dt: datetime.datetime, original_input: str) -> None:
        """시간 범위 논리 검증 (4단계)"""
        logger.debug("4단계: 논리 검증 시작")

        # 동일한 시각 범위 검증
        if start_dt == end_dt:
            raise TimeParsingError(
                message="동일한 시각 범위는 허용되지 않습니다", error_code="LOGIC_ERROR", input_value=original_input
            )

        # 시작 시간 < 종료 시간 검증
        if start_dt > end_dt:
            raise TimeParsingError(
                message="시작 시각은 종료 시각보다 빨라야 합니다", error_code="LOGIC_ERROR", input_value=original_input
            )

        logger.debug("논리 검증 통과: 시작(%s) < 종료(%s)", start_dt, end_dt)

    def provide_format_hint(self, text: str) -> str:
        """일반적인 오타에 대한 힌트 제공"""
        uses_space_instead_separator = re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", text) is not None
        time_with_dash = re.search(r"\d{2}-\d{2}", text) is not None and not self._datetime_pattern_flexible.search(
            text
        )

        hint = "예: 2025-08-08_15:00~2025-08-08_19:00 또는 2025-08-08-15:00~2025-08-08-19:00 또는 2025-08-08"

        if uses_space_instead_separator:
            hint = "날짜와 시간은 공백이 아니라 '_' 또는 '-'로 구분하세요"
        elif time_with_dash:
            hint = "시간은 '15-00'이 아니라 '15:00' 형식이어야 합니다"

        return hint

    def parse(self, range_text: str) -> Tuple[datetime.datetime, datetime.datetime]:
        """
        시간 범위 문자열을 파싱하여 시작/종료 datetime 객체를 반환

        기존 main.py의 parse_time_range() 함수와 동일한 로직입니다.

        Args:
            range_text (str): 파싱할 시간 범위 문자열

        Returns:
            Tuple[datetime.datetime, datetime.datetime]: (시작_시각, 종료_시각) - 둘 다 tz-aware

        Raises:
            TypeError: 입력이 문자열이 아닌 경우
            ValueError: 형식, 값, 논리 오류가 있는 경우
        """
        logger.info("parse() 호출: 입력 문자열 파싱 시작: %s", range_text)

        # 1단계: 타입 검증
        self.validate_input_type(range_text)

        # 2단계: 전처리 및 기본 검증
        text = self.preprocess_and_validate_format(range_text)

        # 타임존 정보 획득
        tzinfo = self._get_timezone()

        # 3단계: 형식별 파싱
        if "~" in text:
            # 범위 형식 처리
            start_dt, end_dt = self.parse_range_format(text, tzinfo)
        elif self._date_pattern.fullmatch(text):
            # 단일 날짜 형식 처리
            start_dt, end_dt = self.parse_single_date_format(text, tzinfo)
        else:
            # 여기까지 오면 형식 오류
            hint = self.provide_format_hint(text)
            raise TimeParsingError(
                message="입력 형식이 올바르지 않습니다 (YYYY-MM-DD_HH:MM~YYYY-MM-DD_HH:MM 또는 YYYY-MM-DD-HH:MM~YYYY-MM-DD-HH:MM 또는 YYYY-MM-DD)",
                error_code="FORMAT_ERROR",
                hint=hint,
                input_value=text,
            )

        # 4단계: 논리 검증
        self.validate_time_logic(start_dt, end_dt, range_text)

        logger.info("parse() 성공: %s ~ %s", start_dt, end_dt)
        return start_dt, end_dt

    def parse_safe(self, range_text: str) -> Optional[Tuple[datetime.datetime, datetime.datetime]]:
        """
        안전한 파싱 (예외를 발생시키지 않고 None 반환)

        Args:
            range_text (str): 파싱할 시간 범위 문자열

        Returns:
            Optional[Tuple[datetime.datetime, datetime.datetime]]: 성공 시 (시작, 종료), 실패 시 None
        """
        try:
            return self.parse(range_text)
        except TimeParsingError as e:
            logger.warning("parse_safe() 실패: %s", e)
            return None

    def is_valid_format(self, range_text: str) -> bool:
        """시간 범위 문자열이 유효한 형식인지 확인"""
        try:
            self.validate_input_type(range_text)
            text = self.preprocess_and_validate_format(range_text)

            # 범위 형식 또는 단일 날짜 형식 확인
            if "~" in text:
                parts = [p.strip() for p in text.split("~")]
                if len(parts) == 2 and parts[0] and parts[1]:
                    return self._datetime_pattern_flexible.fullmatch(
                        parts[0]
                    ) and self._datetime_pattern_flexible.fullmatch(parts[1])
            else:
                return self._date_pattern.fullmatch(text) is not None

            return False
        except TimeParsingError:
            return False
