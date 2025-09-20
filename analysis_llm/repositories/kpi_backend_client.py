"""
KPI Backend Client Repository

백엔드의 Choi 알고리즘 API(`/api/kpi/choi-analysis`)를 호출하는 리포지토리 모듈.

요구사항:
- 완전한 의존성 주입(settings)
- 견고한 오류 처리(타임아웃/재시도/HTTP 에러/스키마 오류)
- 함수별 상세 로깅(입력 요약, 시도 횟수, 응답 키, 소요시간)
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Optional

import requests
from requests import Response

from config.settings import get_settings


logger = logging.getLogger(__name__)


class BackendClientError(Exception):
    """백엔드 호출 관련 기본 예외."""


class BackendTimeoutError(BackendClientError):
    """타임아웃 발생."""


class BackendHTTPError(BackendClientError):
    """HTTP 상태 코드 오류."""


class BackendSchemaError(BackendClientError):
    """응답 스키마 오류."""


def _build_headers() -> Dict[str, str]:
    """
    인증/콘텐츠 헤더 구성.
    주석: 민감한 토큰 값은 로깅하지 않음.
    """
    settings = get_settings()
    headers = {
        "Content-Type": "application/json",
        **settings.get_backend_auth_header(),
    }
    return headers


def _validate_choi_response(payload: Dict[str, Any]) -> None:
    """
    백엔드 응답의 필수 키를 간단히 검증.
    상세 스키마는 점진적으로 강화 가능.
    """
    required_top_keys = [
        "algorithm_version",
        "kpi_judgement",
    ]
    for key in required_top_keys:
        if key not in payload:
            raise BackendSchemaError(f"Missing required key in response: {key}")


def run_choi_analysis(request_body: Dict[str, Any], timeout: Optional[int] = None) -> Dict[str, Any]:
    """
    백엔드 `/api/kpi/choi-analysis` 호출.

    Args:
        request_body: 백엔드가 요구하는 요청 페이로드(dict)
        timeout: 요청 타임아웃(초). 미지정 시 settings 값 사용

    Returns:
        Dict[str, Any]: 검증된 백엔드 응답 JSON

    Raises:
        BackendTimeoutError, BackendHTTPError, BackendSchemaError
    """
    settings = get_settings()
    base_url = str(settings.backend_service_url).rstrip("/")
    url = f"{base_url}/api/kpi/choi-analysis"

    # 재시도 정책
    max_retries = max(1, settings.llm_max_retries)
    retry_delay = max(0.2, settings.llm_retry_delay)
    request_timeout = timeout or settings.backend_timeout

    # 로깅: 입력 요약(민감정보 제외)
    safe_summary = {
        "cell_ids_len": len((request_body or {}).get("cell_ids", [])),
        "has_input_data": bool((request_body or {}).get("input_data")),
        "has_time_range": bool((request_body or {}).get("time_range")),
        "compare_mode": (request_body or {}).get("compare_mode", True),
    }
    logger.info("run_choi_analysis() 시작: url=%s, summary=%s", url, safe_summary)

    last_error: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        start_ts = time.time()
        try:
            resp: Response = requests.post(
                url,
                headers=_build_headers(),
                data=json.dumps(request_body or {}),
                timeout=request_timeout,
            )

            elapsed_ms = (time.time() - start_ts) * 1000.0

            # 상태 코드 검사
            if resp.status_code >= 500:
                logger.warning(
                    "백엔드 5xx 응답: code=%s, attempt=%d/%d, elapsed_ms=%.1f",
                    resp.status_code,
                    attempt,
                    max_retries,
                    elapsed_ms,
                )
                last_error = BackendHTTPError(f"HTTP {resp.status_code}: {resp.text[:500]}")
                time.sleep(retry_delay)
                continue
            if resp.status_code >= 400:
                logger.error(
                    "백엔드 4xx 응답: code=%s, attempt=%d/%d, body=%s",
                    resp.status_code,
                    attempt,
                    max_retries,
                    resp.text[:500],
                )
                raise BackendHTTPError(f"HTTP {resp.status_code}: {resp.text[:1000]}")

            # JSON 파싱
            try:
                payload = resp.json()
            except Exception as e:  # pragma: no cover
                logger.error("JSON 파싱 실패: %s, body-sample=%s", e, resp.text[:500])
                raise BackendSchemaError(f"Invalid JSON response: {e}")

            # 스키마 검증(간단)
            _validate_choi_response(payload)

            logger.info(
                "run_choi_analysis() 성공: elapsed_ms=%.1f, keys=%s",
                elapsed_ms,
                list(payload.keys())[:10],
            )
            return payload

        except requests.Timeout as e:
            elapsed_ms = (time.time() - start_ts) * 1000.0
            logger.error(
                "백엔드 타임아웃: attempt=%d/%d, timeout=%ss, elapsed_ms=%.1f",
                attempt,
                max_retries,
                request_timeout,
                elapsed_ms,
            )
            last_error = BackendTimeoutError(str(e))
            time.sleep(retry_delay)
        except (BackendHTTPError, BackendSchemaError) as e:
            # 재시도 불필요하거나 즉시 실패해야 하는 오류
            last_error = e
            break
        except Exception as e:  # pragma: no cover
            logger.error("백엔드 호출 중 예기치 못한 오류: %s", e, exc_info=True)
            last_error = e
            time.sleep(retry_delay)

    assert last_error is not None
    raise last_error


