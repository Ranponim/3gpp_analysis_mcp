"""
Deterministic Judgement Service (Choi Adapter)

MCP 내에서 백엔드의 Choi 알고리즘 API를 호출하고, 결과를 표준 형태로 정규화한다.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from ..repositories.kpi_backend_client import run_choi_analysis, BackendClientError


logger = logging.getLogger(__name__)


class DeterministicJudgementError(Exception):
    """Choi 판정 어댑터에서 발생한 오류."""


def _normalize_choi_result(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    백엔드 응답을 MCP 표준 구조로 정규화한다.
    표준 구조 목표: peg_analysis.choi_judgement에 병합 가능한 dict
    """
    # 최소 키 추출 및 안전 변환
    kpi_judgement = raw.get("kpi_judgement", {}) or {}
    abnormal_detection = raw.get("abnormal_detection", {}) or {}
    warnings = raw.get("processing_warnings", []) or []

    normalized = {
        "overall": kpi_judgement.get("overall"),
        "reasons": kpi_judgement.get("reasons", []),
        "by_kpi": kpi_judgement.get("by_kpi", {}),
        "abnormal_detection": abnormal_detection,
        "warnings": warnings,
        "algorithm_version": raw.get("algorithm_version"),
        "processing_time_ms": raw.get("processing_time_ms"),
    }
    return normalized


def run_choi_judgement(request_body: Dict[str, Any], timeout: Optional[int] = None) -> Dict[str, Any]:
    """
    백엔드 Choi API 호출 후, 표준화된 choi_judgement 섹션 반환.

    Returns:
        Dict[str, Any]: peg_analysis.choi_judgement로 병합 가능한 사전
    """
    logger.info("run_choi_judgement() 시작: keys=%s", list((request_body or {}).keys()))
    try:
        raw = run_choi_analysis(request_body=request_body, timeout=timeout)
        normalized = _normalize_choi_result(raw)
        logger.info(
            "run_choi_judgement() 성공: overall=%s, by_kpi=%d",
            normalized.get("overall"),
            len((normalized.get("by_kpi") or {}).keys()),
        )
        return normalized
    except BackendClientError as e:
        logger.error("Choi 판정 백엔드 호출 실패: %s", e)
        raise DeterministicJudgementError(str(e))
    except Exception as e:  # pragma: no cover
        logger.error("Choi 판정 어댑터 오류: %s", e, exc_info=True)
        raise DeterministicJudgementError(str(e))


