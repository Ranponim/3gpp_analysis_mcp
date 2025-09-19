"""
응답 데이터 모델

이 모듈은 MCP 응답과 관련된 모든 데이터 모델을 정의합니다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

# 로깅 설정
logger = logging.getLogger(__name__)


@dataclass
class AnalysisStats:
    """분석 통계 정보"""

    total_pegs: int = 0
    processed_pegs: int = 0
    derived_pegs: int = 0
    analysis_duration_seconds: float = 0.0
    llm_tokens_used: int = 0

    def __post_init__(self):
        """통계 정보 검증"""
        if self.total_pegs < 0:
            raise ValueError("전체 PEG 수는 0 이상이어야 합니다")
        if self.processed_pegs < 0:
            raise ValueError("처리된 PEG 수는 0 이상이어야 합니다")
        if self.derived_pegs < 0:
            raise ValueError("파생 PEG 수는 0 이상이어야 합니다")
        if self.analysis_duration_seconds < 0:
            raise ValueError("분석 소요 시간은 0 이상이어야 합니다")

        logger.debug(
            "AnalysisStats 생성: total=%d, processed=%d, derived=%d",
            self.total_pegs,
            self.processed_pegs,
            self.derived_pegs,
        )


@dataclass
class PEGStatistics:
    """PEG 통계 데이터"""

    peg_name: str
    avg_n_minus_1: float
    avg_n: float
    diff: float
    pct_change: float
    is_derived: bool = False

    def __post_init__(self):
        """PEG 통계 검증"""
        if not self.peg_name:
            raise ValueError("PEG 이름은 필수입니다")

        # NaN 값 처리 (수학 연산에서 발생 가능)
        import math

        if math.isnan(self.avg_n_minus_1):
            self.avg_n_minus_1 = 0.0
        if math.isnan(self.avg_n):
            self.avg_n = 0.0
        if math.isnan(self.diff):
            self.diff = 0.0
        if math.isnan(self.pct_change):
            self.pct_change = 0.0

        logger.debug(
            "PEGStatistics 생성: %s (%.2f → %.2f, 변화율: %.2f%%)",
            self.peg_name,
            self.avg_n_minus_1,
            self.avg_n,
            self.pct_change,
        )

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "peg_name": self.peg_name,
            "avg_n_minus_1": self.avg_n_minus_1,
            "avg_n": self.avg_n,
            "diff": self.diff,
            "pct_change": self.pct_change,
            "is_derived": self.is_derived,
        }


@dataclass
class LLMAnalysisResult:
    """LLM 분석 결과"""

    integrated_analysis: str = ""
    specific_peg_analysis: str = ""
    recommendations: str = ""
    confidence_score: float = 0.0
    model_used: str = ""
    tokens_used: int = 0
    analysis_timestamp: Optional[datetime] = None

    def __post_init__(self):
        """LLM 분석 결과 검증"""
        if self.confidence_score < 0.0 or self.confidence_score > 1.0:
            logger.warning("신뢰도 점수가 범위를 벗어남: %.2f (0.0~1.0으로 조정)", self.confidence_score)
            self.confidence_score = max(0.0, min(1.0, self.confidence_score))

        if self.tokens_used < 0:
            raise ValueError("사용된 토큰 수는 0 이상이어야 합니다")

        if self.analysis_timestamp is None:
            self.analysis_timestamp = datetime.now()

        logger.debug(
            "LLMAnalysisResult 생성: model=%s, tokens=%d, confidence=%.2f",
            self.model_used,
            self.tokens_used,
            self.confidence_score,
        )

    def has_integrated_analysis(self) -> bool:
        """통합 분석이 있는지 확인"""
        return bool(self.integrated_analysis.strip())

    def has_specific_analysis(self) -> bool:
        """특정 PEG 분석이 있는지 확인"""
        return bool(self.specific_peg_analysis.strip())

    def has_recommendations(self) -> bool:
        """권고사항이 있는지 확인"""
        return bool(self.recommendations.strip())


@dataclass
class BackendResponse:
    """백엔드 전송 응답 정보"""

    success: bool = False
    status_code: Optional[int] = None
    response_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    upload_timestamp: Optional[datetime] = None

    def __post_init__(self):
        """백엔드 응답 정보 검증"""
        if self.upload_timestamp is None:
            self.upload_timestamp = datetime.now()

        logger.debug("BackendResponse 생성: success=%s, status_code=%s", self.success, self.status_code)

    def is_successful(self) -> bool:
        """전송 성공 여부 확인"""
        return self.success and (self.status_code is None or 200 <= self.status_code < 300)


@dataclass
class AnalysisResponse:
    """셀 성능 분석 응답"""

    status: str = "pending"  # pending, processing, completed, error
    message: str = ""
    analysis_id: Optional[str] = None
    request_timestamp: Optional[datetime] = None
    completion_timestamp: Optional[datetime] = None

    # 분석 결과 데이터
    peg_statistics: List[PEGStatistics] = field(default_factory=list)
    llm_analysis: Optional[LLMAnalysisResult] = None
    analysis_stats: Optional[AnalysisStats] = None

    # 파일 및 전송 정보
    output_files: List[str] = field(default_factory=list)
    backend_response: Optional[BackendResponse] = None

    # 오류 정보
    error_details: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        """응답 데이터 검증"""
        valid_statuses = ["pending", "processing", "completed", "error"]
        if self.status not in valid_statuses:
            raise ValueError(f"유효하지 않은 상태: {self.status} (허용값: {valid_statuses})")

        if self.request_timestamp is None:
            self.request_timestamp = datetime.now()

        logger.info("AnalysisResponse 생성: status=%s, peg_count=%d", self.status, len(self.peg_statistics))

    def mark_completed(self, message: str = "분석이 성공적으로 완료되었습니다") -> None:
        """분석 완료 상태로 변경"""
        self.status = "completed"
        self.message = message
        self.completion_timestamp = datetime.now()
        logger.info("분석 완료 처리: %s", message)

    def mark_error(self, error_message: str, error_details: Optional[Dict[str, Any]] = None) -> None:
        """오류 상태로 변경"""
        self.status = "error"
        self.message = error_message
        self.error_details = error_details or {}
        self.completion_timestamp = datetime.now()
        logger.error("분석 오류 처리: %s", error_message)

    def add_peg_statistic(self, peg_stat: PEGStatistics) -> None:
        """PEG 통계 추가"""
        if not isinstance(peg_stat, PEGStatistics):
            raise ValueError("PEGStatistics 객체가 필요합니다")
        self.peg_statistics.append(peg_stat)
        logger.debug("PEG 통계 추가: %s", peg_stat.peg_name)

    def add_output_file(self, file_path: str) -> None:
        """출력 파일 경로 추가"""
        if not file_path:
            raise ValueError("파일 경로는 필수입니다")
        self.output_files.append(file_path)
        logger.debug("출력 파일 추가: %s", file_path)

    def get_duration_seconds(self) -> float:
        """분석 소요 시간 계산 (초)"""
        if self.request_timestamp and self.completion_timestamp:
            delta = self.completion_timestamp - self.request_timestamp
            return delta.total_seconds()
        return 0.0

    def is_completed(self) -> bool:
        """분석 완료 여부 확인"""
        return self.status == "completed"

    def is_error(self) -> bool:
        """오류 상태 여부 확인"""
        return self.status == "error"

    def has_llm_analysis(self) -> bool:
        """LLM 분석 결과가 있는지 확인"""
        return self.llm_analysis is not None

    def has_backend_response(self) -> bool:
        """백엔드 응답이 있는지 확인"""
        return self.backend_response is not None

    def to_dict(self) -> Dict[str, Any]:
        """응답을 딕셔너리로 변환 (JSON 직렬화용)"""
        result = {
            "status": self.status,
            "message": self.message,
            "analysis_id": self.analysis_id,
            "request_timestamp": self.request_timestamp.isoformat() if self.request_timestamp else None,
            "completion_timestamp": self.completion_timestamp.isoformat() if self.completion_timestamp else None,
            "duration_seconds": self.get_duration_seconds(),
            "peg_statistics": [stat.to_dict() for stat in self.peg_statistics],
            "output_files": self.output_files,
        }

        # LLM 분석 결과
        if self.llm_analysis:
            result["llm_analysis"] = {
                "integrated_analysis": self.llm_analysis.integrated_analysis,
                "specific_peg_analysis": self.llm_analysis.specific_peg_analysis,
                "recommendations": self.llm_analysis.recommendations,
                "confidence_score": self.llm_analysis.confidence_score,
                "model_used": self.llm_analysis.model_used,
                "tokens_used": self.llm_analysis.tokens_used,
                "analysis_timestamp": (
                    self.llm_analysis.analysis_timestamp.isoformat() if self.llm_analysis.analysis_timestamp else None
                ),
            }

        # 분석 통계
        if self.analysis_stats:
            result["analysis_stats"] = {
                "total_pegs": self.analysis_stats.total_pegs,
                "processed_pegs": self.analysis_stats.processed_pegs,
                "derived_pegs": self.analysis_stats.derived_pegs,
                "analysis_duration_seconds": self.analysis_stats.analysis_duration_seconds,
                "llm_tokens_used": self.analysis_stats.llm_tokens_used,
            }

        # 백엔드 응답
        if self.backend_response:
            result["backend_response"] = {
                "success": self.backend_response.success,
                "status_code": self.backend_response.status_code,
                "response_data": self.backend_response.response_data,
                "error_message": self.backend_response.error_message,
                "upload_timestamp": (
                    self.backend_response.upload_timestamp.isoformat()
                    if self.backend_response.upload_timestamp
                    else None
                ),
            }

        # 오류 정보
        if self.error_details:
            result["error_details"] = self.error_details

        return result

    @classmethod
    def create_success_response(
        cls, message: str = "분석이 성공적으로 완료되었습니다", analysis_id: Optional[str] = None
    ) -> "AnalysisResponse":
        """성공 응답 생성"""
        response = cls(status="completed", message=message, analysis_id=analysis_id)
        response.completion_timestamp = datetime.now()
        return response

    @classmethod
    def create_error_response(
        cls, error_message: str, error_details: Optional[Dict[str, Any]] = None, analysis_id: Optional[str] = None
    ) -> "AnalysisResponse":
        """오류 응답 생성"""
        response = cls(
            status="error", message=error_message, analysis_id=analysis_id, error_details=error_details or {}
        )
        response.completion_timestamp = datetime.now()
        return response
