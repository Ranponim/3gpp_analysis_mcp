"""
LLM Repository Interface and Client Implementation

이 모듈은 LLM API 호출을 위한 Repository 패턴을 구현합니다.
추상 인터페이스와 구체적인 LLM Client 구현을 제공합니다.

기존 main.py의 query_llm() 및 관련 LLM 로직을 모듈화한 것입니다.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re

# 임시로 절대 import 사용 (나중에 패키지 구조 정리 시 수정)
import sys
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
import urllib3

# config 모듈 지연 import
_config_get_settings = None


def get_config_settings():
    """Configuration Manager에서 설정 가져오기 (지연 로딩)"""
    global _config_get_settings
    if _config_get_settings is None:
        from config import get_settings

        _config_get_settings = get_settings
    return _config_get_settings()


from ..exceptions import LLMError

# 로깅 설정
logger = logging.getLogger(__name__)

# SSL 경고 비활성화
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class LLMRepository(ABC):
    """
    LLM Repository 추상 기본 클래스

    LLM API 호출을 위한 공통 인터페이스를 정의합니다.
    구체적인 LLM 구현체들은 이 인터페이스를 구현해야 합니다.

    주요 기능:
    1. 프롬프트 생성 및 최적화
    2. LLM API 호출 및 응답 처리
    3. 멀티 엔드포인트 페일오버
    4. 응답 검증 및 파싱
    """

    @abstractmethod
    def analyze_data(self, prompt: str, enable_mock: bool = False, **kwargs) -> Dict[str, Any]:
        """
        데이터 분석 요청

        Args:
            prompt (str): LLM에게 전달할 프롬프트
            enable_mock (bool): 모킹 모드 활성화
            **kwargs: 추가 설정

        Returns:
            Dict[str, Any]: 분석 결과

        Raises:
            LLMError: LLM API 호출 실패 시
        """

    @abstractmethod
    def estimate_tokens(self, text: str) -> int:
        """
        텍스트의 토큰 수 추정

        Args:
            text (str): 토큰 수를 추정할 텍스트

        Returns:
            int: 추정 토큰 수
        """

    @abstractmethod
    def validate_prompt(self, prompt: str) -> bool:
        """
        프롬프트 유효성 검증

        Args:
            prompt (str): 검증할 프롬프트

        Returns:
            bool: 유효성 여부
        """

    @abstractmethod
    def test_connection(self, endpoint: Optional[str] = None) -> bool:
        """
        LLM API 연결 테스트

        Args:
            endpoint (Optional[str]): 테스트할 엔드포인트 (None이면 모든 엔드포인트)

        Returns:
            bool: 연결 성공 여부
        """


class LLMClient(LLMRepository):
    """
    LLM Client 구현체

    기존 main.py의 query_llm() 로직을 모듈화하여
    재사용 가능하고 테스트 가능한 형태로 제공합니다.

    주요 기능:
    1. 멀티 엔드포인트 페일오버
    2. HTTP 세션 재사용 및 재시도 로직
    3. JSON 응답 파싱 및 검증
    4. 프롬프트 토큰 제한 및 안전 가드
    5. 모킹 지원
    """

    def __init__(self, config_override: Optional[Dict[str, Any]] = None):
        """
        LLMClient 초기화

        Args:
            config_override (Optional[Dict[str, Any]]): 설정 오버라이드 (테스트용)
        """
        # Configuration Manager에서 설정 로드
        try:
            settings = get_config_settings()
            llm_config = settings.get_llm_config_dict()

            # API 키는 환경변수에서 직접 읽기 (Configuration Manager 우회)
            api_key = os.getenv("LLM_API_KEY", "")
            self.config = {
                "provider": llm_config["provider"],
                "model": llm_config["model"],
                "max_tokens": llm_config["max_tokens"],
                "temperature": llm_config["temperature"],
                "timeout": llm_config["timeout"],
                "max_retries": llm_config["max_retries"],
                "retry_delay": llm_config["retry_delay"],
                "api_key": api_key,
                "endpoints": self._load_endpoints(),
                "mock_enabled": False,  # 기본값
            }
            logger.info("Configuration Manager에서 LLM 설정 로드 완료")
            logger.debug("API 키 로드 상태: %s", "있음" if api_key else "없음")

        except Exception as e:
            logger.warning("Configuration Manager 로딩 실패, 기본값 사용: %s", e)
            self.config = {
                "provider": os.getenv("LLM_PROVIDER", "local"),
                "model": os.getenv("LLM_MODEL", "Gemma-3-27B"),
                "max_tokens": int(os.getenv("LLM_MAX_TOKENS", "4096")),
                "temperature": float(os.getenv("LLM_TEMPERATURE", "0.2")),
                "timeout": int(os.getenv("LLM_TIMEOUT", "180")),
                "max_retries": int(os.getenv("LLM_MAX_RETRIES", "3")),
                "retry_delay": float(os.getenv("LLM_RETRY_DELAY", "1.0")),
                "api_key": os.getenv("LLM_API_KEY", ""),
                "endpoints": self._load_endpoints(),
                "mock_enabled": False,
            }

        # 설정 오버라이드 적용 (테스트용)
        if config_override:
            self.config.update(config_override)
            logger.debug("LLM 설정 오버라이드 적용: %s", list(config_override.keys()))

        # HTTP 세션 초기화 (지연 로딩)
        self._session = None

        logger.info(
            "LLMClient 초기화 완료: provider=%s, model=%s, endpoints=%d개",
            self.config["provider"],
            self.config["model"],
            len(self.config["endpoints"]),
        )

    def _load_endpoints(self) -> List[str]:
        """엔드포인트 목록 로드"""
        endpoints_str = os.getenv("LLM_ENDPOINTS", "http://10.251.204.93:10000,http://100.105.188.117:8888")
        endpoints = [endpoint.strip() for endpoint in endpoints_str.split(",") if endpoint.strip()]

        if not endpoints:
            logger.warning("LLM 엔드포인트가 설정되지 않았습니다")
            return ["http://localhost:8000"]  # 기본값

        logger.debug("LLM 엔드포인트 로드: %d개", len(endpoints))
        return endpoints

    def _get_session(self) -> requests.Session:
        """HTTP 세션 획득 (지연 로딩)"""
        if self._session is None:
            self._session = self._create_session()
        return self._session

    def _create_session(self) -> requests.Session:
        """
        재시도 로직과 타임아웃이 설정된 requests 세션 생성
        (기존 main.py의 create_requests_session() 로직)
        """
        logger.debug("requests.Session 객체 생성 중")

        session = requests.Session()

        # 재시도 전략 설정
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        retry_strategy = Retry(
            total=self.config["max_retries"],
            backoff_factor=self.config["retry_delay"],
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        # 타임아웃 설정
        session.timeout = self.config["timeout"]

        # 기본 헤더 설정
        user_agent = os.getenv("HTTP_USER_AGENT", "Cell-Performance-LLM-Analyzer/1.0")
        headers = {
            "User-Agent": user_agent,
            "Content-Type": "application/json"
        }
        
        # local provider가 아닌 경우에만 Authorization 헤더 추가
        provider = self.config.get("provider", "").lower()
        api_key = self.config.get("api_key", "")
        
        if provider != "local" and api_key:
            logger.debug("API 키를 Authorization 헤더에 추가 (provider: %s)", provider)
            headers["Authorization"] = f"Bearer {api_key}"
        elif api_key:
            # local provider이지만 API 키가 있으면 헤더에 추가 (vLLM 서버가 인증을 요구할 수 있음)
            logger.debug("local provider이지만 API 키가 있어 Authorization 헤더에 추가")
            headers["Authorization"] = f"Bearer {api_key}"
        else:
            logger.debug("API 키 없음 - Authorization 헤더 생략")
        
        session.headers.update(headers)

        logger.debug("HTTP 세션 생성 완료: 재시도=%d, 타임아웃=%ds, provider=%s", 
                    self.config["max_retries"], self.config["timeout"], provider)
        return session

    def estimate_tokens(self, text: str) -> int:
        """
        텍스트의 토큰 수 추정 (기존 main.py의 estimate_prompt_tokens 로직)
        """
        try:
            # 환경변수에서 토큰 추정 비율 읽기 (기본값: 3.5자당 1토큰)
            chars_per_token = float(os.getenv("CHARS_PER_TOKEN_RATIO", "3.5"))
            estimated_tokens = int(math.ceil(len(text) / chars_per_token))
            logger.debug("토큰 추정 완료: %d자 → %d토큰 (비율: %.1f)", len(text), estimated_tokens, chars_per_token)
            return estimated_tokens

        except Exception as e:
            logger.warning("토큰 추정 중 오류 발생, 대체 방법 사용: %s", e)
            # 대체 방법: 환경변수에서 대체 비율 읽기 (기본값: 4자당 1토큰)
            fallback_chars_per_token = float(os.getenv("FALLBACK_CHARS_PER_TOKEN_RATIO", "4.0"))
            fallback_tokens = len(text) // int(fallback_chars_per_token)
            logger.debug("대체 토큰 추정: %d자 → %d토큰", len(text), fallback_tokens)
            return fallback_tokens

    def validate_prompt(self, prompt: str) -> bool:
        """프롬프트 유효성 검증"""
        if not prompt or not isinstance(prompt, str):
            return False

        # 토큰 제한 확인
        estimated_tokens = self.estimate_tokens(prompt)
        if estimated_tokens > self.config["max_tokens"]:
            logger.warning("프롬프트 토큰 수 초과: %d > %d", estimated_tokens, self.config["max_tokens"])
            return False

        # 문자 수 제한 확인
        max_chars = int(os.getenv("DEFAULT_MAX_PROMPT_CHARS", "80000"))
        if len(prompt) > max_chars:
            logger.warning("프롬프트 문자 수 초과: %d > %d", len(prompt), max_chars)
            return False

        return True

    def truncate_prompt_if_needed(self, prompt: str) -> str:
        """
        프롬프트 자르기 (기존 main.py의 truncate_prompt_safely 로직)
        """
        max_chars = int(os.getenv("DEFAULT_MAX_PROMPT_CHARS", "80000"))

        if len(prompt) <= max_chars:
            return prompt

        logger.warning("프롬프트가 %d자로 제한을 초과하여 자릅니다 (최대: %d자)", len(prompt), max_chars)

        # 자르기 수행: 환경변수에서 여유 공간 설정 (기본값: 200자)
        buffer_chars = int(os.getenv("PROMPT_TRUNCATE_BUFFER", "200"))
        head = prompt[: max_chars - buffer_chars]
        tail = "\\n\\n[...truncated due to safety guard...]\\n"

        truncated = head + tail
        logger.debug("프롬프트 자르기 완료: %d자 → %d자", len(prompt), len(truncated))

        return truncated

    def _extract_json_from_response(self, response_text: str) -> Dict[str, Any]:
        """
        LLM 응답에서 JSON 블록 추출 (기존 main.py 로직)
        """
        logger.debug("JSON 추출 시작: 응답 길이=%d자", len(response_text))

        # JSON 블록 패턴 검색
        json_patterns = [
            r"```json\s*(\{.*?\})\s*```",  # ```json { ... } ```
            r"```\s*(\{.*?\})\s*```",  # ``` { ... } ```
            r"(\{[^{}]*\{[^{}]*\}[^{}]*\})",  # 중첩 JSON
            r"(\{[^{}]+\})",  # 단순 JSON
        ]

        for pattern in json_patterns:
            matches = re.findall(pattern, response_text, re.DOTALL)
            for match in matches:
                try:
                    parsed = json.loads(match.strip())
                    logger.debug("JSON 추출 성공: 패턴=%s", pattern)
                    return parsed
                except json.JSONDecodeError:
                    continue

        # JSON 블록을 찾지 못한 경우, 전체 응답을 JSON으로 파싱 시도
        try:
            parsed = json.loads(response_text.strip())
            logger.debug("전체 응답 JSON 파싱 성공")
            return parsed
        except json.JSONDecodeError as e:
            logger.error("JSON 파싱 실패: %s", e)
            raise LLMError(
                "LLM 응답에서 유효한 JSON을 찾을 수 없습니다", details={"response_preview": response_text[:500]}
            )

    def _create_mock_response(self, prompt: str) -> Dict[str, Any]:
        """모킹 응답 생성"""
        logger.info("모킹 응답 생성: 프롬프트 길이=%d자", len(prompt))

        return {
            "summary": "모킹 모드: 실제 LLM 분석이 아닌 테스트 응답입니다",
            "key_findings": ["모킹 데이터 - 실제 분석 결과가 아님", "테스트 환경에서 생성된 가상 응답"],
            "recommendations": ["실제 환경에서는 enable_mock=False로 설정하세요"],
            "technical_analysis": {
                "overall_status": "MOCK_OK",
                "critical_issues": [],
                "performance_trends": "모킹 데이터",
            },
            "cells_with_significant_change": {},
            "_mock": True,
            "_timestamp": datetime.now().isoformat(),
        }

    def test_connection(self, endpoint: Optional[str] = None) -> bool:
        """LLM API 연결 테스트"""
        endpoints_to_test = [endpoint] if endpoint else self.config["endpoints"]

        session = self._get_session()

        for test_endpoint in endpoints_to_test:
            try:
                # 간단한 health check 요청
                response = session.get(f"{test_endpoint}/health", timeout=10)
                if response.status_code == 200:
                    logger.info("LLM 엔드포인트 연결 성공: %s", test_endpoint)
                    return True
                else:
                    logger.warning("LLM 엔드포인트 응답 오류: %s (status: %d)", test_endpoint, response.status_code)
            except Exception as e:
                logger.warning("LLM 엔드포인트 연결 실패: %s (%s)", test_endpoint, e)

        return False

    def analyze_data(self, prompt: str, enable_mock: bool = False, **kwargs) -> Dict[str, Any]:
        """
        데이터 분석 요청 (기존 main.py의 query_llm() 로직)
        """
        logger.info("analyze_data() 호출: 프롬프트=%d자, 모킹=%s", len(prompt), enable_mock)

        # 모킹 모드 처리
        if enable_mock or self.config.get("mock_enabled", False):
            return self._create_mock_response(prompt)

        # 프롬프트 검증 및 자르기
        if not self.validate_prompt(prompt):
            prompt = self.truncate_prompt_if_needed(prompt)
            logger.info("프롬프트 자르기 적용: %d자로 단축", len(prompt))

        # 페이로드 구성
        payload = {
            "model": self.config["model"],
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.config["temperature"],
            "max_tokens": self.config["max_tokens"],
        }

        # 페이로드의 총 토큰 수 계산 및 로깅
        try:
            # messages 리스트의 모든 content 길이 합계 계산
            total_chars = sum(
                len(msg.get("content", "")) 
                for msg in payload.get("messages", [])
            )
            # 토큰 수 추정 (estimate_tokens 메서드 사용)
            total_estimated_tokens = self.estimate_tokens(
                "".join(msg.get("content", "") for msg in payload.get("messages", []))
            )
            logger.info(
                "LLM POST 요청 페이로드 토큰 수: 총_문자=%d자, 추정_토큰=%d토큰, max_tokens=%d토큰",
                total_chars,
                total_estimated_tokens,
                payload.get("max_tokens", 0)
            )
        except Exception as e:
            logger.warning("토큰 수 계산 중 오류 발생: %s", e)

        # 멀티 엔드포인트 페일오버 실행
        return self._execute_with_failover(payload)

    def _execute_with_failover(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        멀티 엔드포인트 페일오버 실행 (기존 main.py 로직)
        """
        session = self._get_session()
        endpoints = self.config["endpoints"]

        logger.info("LLM 요청 시작: endpoints=%d개, timeout=%ds", len(endpoints), self.config["timeout"])

        last_error = None

        for i, endpoint in enumerate(endpoints):
            try:
                logger.info("LLM API 호출 시도 %d/%d: %s", i + 1, len(endpoints), endpoint)

                # API 호출 전 디버깅 정보
                logger.debug("POST 요청 URL: %s", f"{endpoint}/v1/chat/completions")
                logger.debug("POST 요청 헤더: %s", dict(session.headers))
                logger.debug("POST 요청 페이로드: %s", payload)
                
                # API 호출
                response = session.post(f"{endpoint}/v1/chat/completions", json=payload, timeout=self.config["timeout"])
                
                # 응답 헤더도 로깅
                logger.debug("응답 상태 코드: %d", response.status_code)
                logger.debug("응답 헤더: %s", dict(response.headers))
                if response.status_code != 200:
                    logger.debug("응답 본문: %s", response.text[:500])

                # 응답 상태 확인
                if response.status_code == 200:
                    response_data = response.json()

                    # OpenAI 형식 응답에서 content 추출
                    if "choices" in response_data and response_data["choices"]:
                        content = response_data["choices"][0]["message"]["content"]
                    else:
                        content = response_data.get("content", str(response_data))

                    # JSON 추출 및 파싱
                    analysis_result = self._extract_json_from_response(content)

                    logger.info(
                        "LLM 분석 성공 (%s): keys=%s",
                        endpoint,
                        list(analysis_result.keys()) if isinstance(analysis_result, dict) else type(analysis_result),
                    )

                    return analysis_result

                else:
                    error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
                    logger.warning("LLM API 오류 응답 (%s): %s", endpoint, error_msg)
                    last_error = LLMError(
                        f"LLM API 오류 응답: {response.status_code}",
                        status_code=response.status_code,
                        endpoint=endpoint,
                        details={"response_text": response.text[:500]},
                    )

            except requests.exceptions.RequestException as e:
                error_msg = f"네트워크 오류: {e}"
                logger.warning("LLM API 네트워크 오류 (%s): %s", endpoint, error_msg)
                last_error = LLMError(f"LLM API 네트워크 오류", endpoint=endpoint, details={"network_error": str(e)})

            except json.JSONDecodeError as e:
                error_msg = f"JSON 파싱 오류: {e}"
                logger.warning("LLM 응답 JSON 파싱 실패 (%s): %s", endpoint, error_msg)
                last_error = LLMError(f"LLM 응답 JSON 파싱 실패", endpoint=endpoint, details={"json_error": str(e)})

            except Exception as e:
                error_msg = f"예상치 못한 오류: {e}"
                logger.error("LLM API 예상치 못한 오류 (%s): %s", endpoint, error_msg)
                last_error = LLMError(
                    f"LLM API 예상치 못한 오류", endpoint=endpoint, details={"unexpected_error": str(e)}
                )

        # 모든 엔드포인트 실패
        session.close()

        error_msg = f"모든 LLM API 엔드포인트({len(endpoints)}개)에 연결하지 못했습니다"
        logger.error(error_msg)

        raise LLMError(
            error_msg, details={"endpoints": endpoints, "last_error": str(last_error) if last_error else None}
        )

    def get_client_info(self) -> Dict[str, Any]:
        """클라이언트 정보 반환 (민감 정보 제외)"""
        return {
            "provider": self.config["provider"],
            "model": self.config["model"],
            "max_tokens": self.config["max_tokens"],
            "temperature": self.config["temperature"],
            "timeout": self.config["timeout"],
            "max_retries": self.config["max_retries"],
            "endpoints_count": len(self.config["endpoints"]),
            "mock_enabled": self.config.get("mock_enabled", False),
            "session_active": self._session is not None,
        }

    def close(self) -> None:
        """리소스 정리"""
        if self._session:
            self._session.close()
            self._session = None
            logger.info("LLMClient 세션 정리 완료")

    def __enter__(self):
        """컨텍스트 매니저 진입"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """컨텍스트 매니저 종료"""
        self.close()

        # 예외 발생 시 로그 기록
        if exc_type:
            logger.error("LLMClient 컨텍스트에서 예외 발생: %s", exc_val)

        return False  # 예외를 다시 발생시킴
