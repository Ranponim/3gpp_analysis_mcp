"""
도메인 데이터 모델

이 모듈은 비즈니스 도메인의 핵심 엔티티와 값 객체를 정의합니다.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

# 로깅 설정
logger = logging.getLogger(__name__)


@dataclass
class TimeRange:
    """시간 범위 값 객체"""

    start_time: datetime
    end_time: datetime
    timezone_offset: Optional[str] = None  # 환경변수에서 자동으로 가져옴

    def __post_init__(self):
        """시간 범위 검증"""
        if self.start_time >= self.end_time:
            raise ValueError("시작 시간은 종료 시간보다 이전이어야 합니다")

        # timezone_offset이 명시적으로 전달되지 않은 경우, datetime 객체의 tzinfo에서 추출
        if self.timezone_offset is None and self.start_time.tzinfo is not None:
            offset = self.start_time.utcoffset()
            if offset is not None:
                hours, remainder = divmod(int(offset.total_seconds()), 3600)
                minutes = remainder // 60
                self.timezone_offset = f"{hours:+03d}:{minutes:02d}"
            else:
                self.timezone_offset = "+00:00"  # UTC
        elif self.timezone_offset is None:
            self.timezone_offset = "+00:00"  # tzinfo가 없으면 UTC로 간주

        logger.debug("TimeRange 생성: %s ~ %s (tzinfo=%s)", self.start_time, self.end_time, self.timezone_offset)

    def duration_hours(self) -> float:
        """시간 범위의 길이(시간 단위)"""
        delta = self.end_time - self.start_time
        return delta.total_seconds() / 3600.0

    def duration_minutes(self) -> float:
        """시간 범위의 길이(분 단위)"""
        delta = self.end_time - self.start_time
        return delta.total_seconds() / 60.0

    def contains(self, timestamp: datetime) -> bool:
        """특정 시간이 범위에 포함되는지 확인"""
        return self.start_time <= timestamp <= self.end_time

    def to_string(self) -> str:
        """문자열 형태로 변환 (yyyy-mm-dd_hh:mm~yyyy-mm-dd_hh:mm)"""
        start_str = self.start_time.strftime("%Y-%m-%d_%H:%M")
        end_str = self.end_time.strftime("%Y-%m-%d_%H:%M")
        return f"{start_str}~{end_str}"


@dataclass
class PEGData:
    """기본 PEG 데이터"""

    peg_name: str
    value: float
    timestamp: datetime
    ne: Optional[str] = None
    cellid: Optional[str] = None
    host: Optional[str] = None
    dimensions: Optional[str] = None  # 차원 정보 (예: "CellIdentity=20,PLMN=0,gnb_ID=0,SPIDIncludingInvalid=0,QCI=0")

    def __post_init__(self):
        """PEG 데이터 검증"""
        if not self.peg_name:
            raise ValueError("PEG 이름은 필수입니다")
        if not isinstance(self.peg_name, str):
            raise ValueError("PEG 이름은 문자열이어야 합니다")

        # NaN 값 처리
        if self.value is not None and math.isnan(self.value):
            logger.warning("PEG %s의 값이 NaN입니다. 0.0으로 대체합니다.", self.peg_name)
            self.value = 0.0

        logger.debug(
            "PEGData 생성: %s = %.2f (%s)%s",
            self.peg_name,
            self.value if self.value is not None else 0.0,
            self.timestamp,
            f" [dimensions={self.dimensions}]" if self.dimensions else "",
        )

    def is_valid_value(self) -> bool:
        """유효한 값인지 확인"""
        if self.value is None:
            return False
        return not (math.isnan(self.value) or math.isinf(self.value))
    
    def parse_dimensions(self) -> Dict[str, str]:
        """
        차원 정보를 파싱하여 딕셔너리로 변환
        
        Returns:
            Dict[str, str]: 차원명 -> 값 매핑 (예: {"CellIdentity": "20", "PLMN": "0", ...})
        """
        if not self.dimensions:
            return {}
        
        result = {}
        for pair in self.dimensions.split(","):
            if "=" in pair:
                key, value = pair.split("=", 1)
                result[key.strip()] = value.strip()
        return result

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "peg_name": self.peg_name,
            "value": self.value,
            "timestamp": self.timestamp.isoformat(),
            "ne": self.ne,
            "cellid": self.cellid,
            "host": self.host,
            "dimensions": self.dimensions,
            "parsed_dimensions": self.parse_dimensions() if self.dimensions else None,
        }


@dataclass
class AggregatedPEGData:
    """집계된 PEG 데이터"""

    peg_name: str
    avg_value: float
    min_value: float
    max_value: float
    count: int
    time_range: TimeRange
    is_derived: bool = False
    formula: Optional[str] = None

    def __post_init__(self):
        """집계 데이터 검증"""
        if not self.peg_name:
            raise ValueError("PEG 이름은 필수입니다")
        if self.count < 0:
            raise ValueError("카운트는 0 이상이어야 합니다")

        # NaN 값 처리
        if math.isnan(self.avg_value):
            self.avg_value = 0.0
        if math.isnan(self.min_value):
            self.min_value = 0.0
        if math.isnan(self.max_value):
            self.max_value = 0.0

        logger.debug(
            "AggregatedPEGData 생성: %s (평균: %.2f, 개수: %d, 파생: %s)",
            self.peg_name,
            self.avg_value,
            self.count,
            self.is_derived,
        )

    def has_data(self) -> bool:
        """데이터가 있는지 확인"""
        return self.count > 0

    def get_variance_info(self) -> Dict[str, float]:
        """분산 정보 반환"""
        if not self.has_data():
            return {"range": 0.0, "spread_ratio": 0.0}

        value_range = self.max_value - self.min_value
        spread_ratio = value_range / self.avg_value if self.avg_value != 0 else 0.0

        return {"range": value_range, "spread_ratio": spread_ratio}

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "peg_name": self.peg_name,
            "avg_value": self.avg_value,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "count": self.count,
            "time_range": self.time_range.to_string(),
            "is_derived": self.is_derived,
            "formula": self.formula,
            "variance_info": self.get_variance_info(),
        }


@dataclass
class ProcessedPEGData:
    """처리된 PEG 데이터 (N-1과 N 기간 비교)"""

    peg_name: str
    n_minus_1_data: AggregatedPEGData
    n_data: AggregatedPEGData
    diff: float = field(init=False)
    pct_change: float = field(init=False)
    is_derived: bool = False

    def __post_init__(self):
        """처리된 데이터 계산"""
        if self.peg_name != self.n_minus_1_data.peg_name or self.peg_name != self.n_data.peg_name:
            raise ValueError("PEG 이름이 일치하지 않습니다")

        # 차이 계산
        self.diff = self.n_data.avg_value - self.n_minus_1_data.avg_value

        # 변화율 계산 (0으로 나누기 방지)
        if self.n_minus_1_data.avg_value != 0:
            self.pct_change = (self.diff / self.n_minus_1_data.avg_value) * 100.0
        else:
            self.pct_change = 0.0 if self.n_data.avg_value == 0 else float("inf")

        # 무한대 값 처리
        if math.isinf(self.pct_change):
            self.pct_change = 999.99 if self.diff > 0 else -999.99

        # 파생 PEG 여부 확인
        self.is_derived = self.n_minus_1_data.is_derived or self.n_data.is_derived

        logger.debug(
            "ProcessedPEGData 생성: %s (%.2f → %.2f, 변화율: %.2f%%)",
            self.peg_name,
            self.n_minus_1_data.avg_value,
            self.n_data.avg_value,
            self.pct_change,
        )

    def get_trend(self) -> str:
        """트렌드 문자열 반환"""
        if abs(self.pct_change) < 0.01:  # 0.01% 미만은 변화 없음으로 간주
            return "stable"
        elif self.pct_change > 0:
            return "increasing"
        else:
            return "decreasing"

    def is_significant_change(self, threshold_pct: float = 5.0) -> bool:
        """유의미한 변화인지 확인"""
        return abs(self.pct_change) >= threshold_pct

    def has_both_periods_data(self) -> bool:
        """양쪽 기간 모두 데이터가 있는지 확인"""
        return self.n_minus_1_data.has_data() and self.n_data.has_data()

    def get_analysis_summary(self) -> Dict[str, Any]:
        """분석 요약 정보"""
        return {
            "peg_name": self.peg_name,
            "n_minus_1_avg": self.n_minus_1_data.avg_value,
            "n_avg": self.n_data.avg_value,
            "difference": self.diff,
            "percent_change": self.pct_change,
            "trend": self.get_trend(),
            "is_significant": self.is_significant_change(),
            "is_derived": self.is_derived,
            "n_minus_1_count": self.n_minus_1_data.count,
            "n_count": self.n_data.count,
        }

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "peg_name": self.peg_name,
            "n_minus_1_data": self.n_minus_1_data.to_dict(),
            "n_data": self.n_data.to_dict(),
            "diff": self.diff,
            "pct_change": self.pct_change,
            "trend": self.get_trend(),
            "is_significant": self.is_significant_change(),
            "is_derived": self.is_derived,
            "analysis_summary": self.get_analysis_summary(),
        }


@dataclass
class AnalysisContext:
    """분석 컨텍스트 정보"""

    analysis_id: str
    n_minus_1_range: TimeRange
    n_range: TimeRange
    filter_conditions: Dict[str, Any] = field(default_factory=dict)
    derived_peg_definitions: Dict[str, str] = field(default_factory=dict)
    analysis_timestamp: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        """분석 컨텍스트 검증"""
        if not self.analysis_id:
            raise ValueError("분석 ID는 필수입니다")

        # 시간 범위 검증
        if self.n_minus_1_range.end_time >= self.n_range.start_time:
            logger.warning("N-1 기간과 N 기간이 겹칩니다")

        logger.info(
            "AnalysisContext 생성: ID=%s, N-1=%s, N=%s",
            self.analysis_id,
            self.n_minus_1_range.to_string(),
            self.n_range.to_string(),
        )

    def get_total_duration_hours(self) -> float:
        """전체 분석 기간 길이(시간)"""
        return self.n_minus_1_range.duration_hours() + self.n_range.duration_hours()

    def has_derived_pegs(self) -> bool:
        """파생 PEG가 정의되어 있는지 확인"""
        return bool(self.derived_peg_definitions)

    def has_filters(self) -> bool:
        """필터 조건이 있는지 확인"""
        return bool(self.filter_conditions)

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "analysis_id": self.analysis_id,
            "n_minus_1_range": self.n_minus_1_range.to_string(),
            "n_range": self.n_range.to_string(),
            "filter_conditions": self.filter_conditions,
            "derived_peg_definitions": self.derived_peg_definitions,
            "analysis_timestamp": self.analysis_timestamp.isoformat(),
            "total_duration_hours": self.get_total_duration_hours(),
            "has_derived_pegs": self.has_derived_pegs(),
            "has_filters": self.has_filters(),
        }
