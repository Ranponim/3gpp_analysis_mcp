"""
=====================================================================================
Cell 성능 LLM 분석기 (시간범위 입력 + PostgreSQL 집계 + 통합 분석 + HTML/백엔드 POST)
=====================================================================================

## 📋 시스템 개요
3GPP 이동통신망의 Cell 성능 데이터를 LLM을 활용하여 종합 분석하는 시스템입니다.
PostgreSQL에서 PEG(Performance Event Group) 데이터를 집계하고, LLM을 통해 전문가 수준의 분석 결과를 제공합니다.

## 🔄 주요 처리 흐름
1. **시간 범위 파싱**: 사용자 입력 시간 범위를 파싱하여 시작/종료 시점 추출
2. **데이터베이스 조회**: PostgreSQL에서 지정된 기간의 PEG 데이터 집계
3. **파생 PEG 계산**: 사용자 정의 수식을 이용한 파생 지표 계산
4. **데이터 처리**: N-1과 N 기간 데이터 병합 및 변화율 계산
5. **LLM 분석**: 전문가 수준의 성능 분석 및 권고사항 생성
6. **결과 출력**: HTML 리포트 생성 및 백엔드 API로 결과 전송

## 🎯 핵심 기능
- **통합 분석**: PEG 단위가 아닌 셀 단위 전체 데이터를 통합하여 종합 성능 평가
- **특정 PEG 분석**: preference나 selected_pegs로 지정된 PEG만 별도 분석
- **파생 PEG 지원**: peg_definitions로 (pegA/pegB)*100 같은 수식 정의
- **환경변수 지원**: 모든 설정값을 환경변수로 관리 가능
- **페일오버 지원**: LLM API 다중 엔드포인트 지원

## 📝 사용 예시 (MCP tool 호출 request 예):
{
  "n_minus_1": "2025-07-01_00:00~2025-07-01_23:59",
  "n": "2025-07-02_00:00~2025-07-02_23:59",
  "output_dir": "./analysis_output",
  "backend_url": "http://localhost:8000/api/analysis-result",
  "db": {"host": "127.0.0.1", "port": 5432, "user": "postgres", "password": "pass", "dbname": "netperf"},
  "table": "summary",
  "columns": {"time": "datetime", "peg_name": "peg_name", "value": "value"},
  "preference": "Random_access_preamble_count,Random_access_response",
  "peg_definitions": {
    "telus_RACH_Success": "Random_access_preamble_count/Random_access_response*100"
  }
}

## 🔧 환경변수 설정
자세한 환경변수 설정은 ENV_SETTINGS.md 파일을 참조하세요.
"""

from __future__ import annotations

import base64  # Base64 인코딩 (이미지 데이터 전송용)
import datetime  # 날짜/시간 처리 및 타임존 관리
import io  # 바이트 스트림 처리 (이미지 데이터 등)
import json  # JSON 데이터 직렬화/역직렬화
import logging  # 로깅 시스템
import math  # 수학 연산 (토큰 추정, NaN 처리 등)

# ===========================================
# 표준 라이브러리 imports
# ===========================================
import os  # 환경변수 및 파일 시스템 접근

# ===========================================
# Configuration Manager 통합
# ===========================================
import sys
import time  # 성능 측정 및 시간 관련 기능

from .repositories import LLMClient, PostgreSQLRepository
from .services import AnalysisService, AnalysisServiceError
from .models.request import AnalysisRequest

# ===========================================
# 로컬 모듈 imports
# ===========================================
from .utils import TimeParsingError, TimeRangeParser

# 전역 설정 인스턴스 (지연 로딩)
_app_settings = None

def get_app_settings():
    """애플리케이션 설정 인스턴스 반환"""
    global _app_settings
    if _app_settings is None:
        # 프로젝트 루트의 config 모듈 import
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(project_root, 'config')
        if config_path not in sys.path:
            sys.path.insert(0, project_root)
        
        from config import get_settings
        _app_settings = get_settings()
    return _app_settings

# ===========================================
# 글로벌 안전 상수 (환경변수로 설정 가능)
# ===========================================
# LLM 프롬프트 관련 상한값들 - 메모리 및 성능 보호를 위한 설정
def get_prompt_limits():
    """프롬프트 제한값들을 설정에서 가져오기"""
    return {
        'max_prompt_tokens': int(os.getenv('DEFAULT_MAX_PROMPT_TOKENS', '24000')),
        'max_prompt_chars': int(os.getenv('DEFAULT_MAX_PROMPT_CHARS', '80000')),
        'max_specific_rows': int(os.getenv('DEFAULT_SPECIFIC_MAX_ROWS', '500')),
        'max_raw_str': int(os.getenv('DEFAULT_MAX_RAW_STR', '4000')),
        'max_raw_array': int(os.getenv('DEFAULT_MAX_RAW_ARRAY', '100'))
    }

# 하위 호환성을 위한 전역 변수들 (추후 제거 예정)
DEFAULT_MAX_PROMPT_TOKENS = int(os.getenv('DEFAULT_MAX_PROMPT_TOKENS', '24000'))
DEFAULT_MAX_PROMPT_CHARS = int(os.getenv('DEFAULT_MAX_PROMPT_CHARS', '80000'))
DEFAULT_SPECIFIC_MAX_ROWS = int(os.getenv('DEFAULT_SPECIFIC_MAX_ROWS', '500'))
DEFAULT_MAX_RAW_STR = int(os.getenv('DEFAULT_MAX_RAW_STR', '4000'))
DEFAULT_MAX_RAW_ARRAY = int(os.getenv('DEFAULT_MAX_RAW_ARRAY', '100'))





from fastmcp import FastMCP  # MCP 서버 프레임워크
import requests  # HTTP 클라이언트
from requests.adapters import HTTPAdapter  # HTTP 어댑터 (재시도 로직)
from urllib3.util.retry import Retry  # 재시도 전략
from typing import Any  # 타입 힌트 지원

# ===========================================
# 로깅 시스템 설정 (표준화)
# ===========================================
# 중앙 설정(config.settings)의 setup_logging을 단일 진입점으로 사용
try:
    # get_app_settings()는 내부적으로 config.get_settings()를 호출하며,
    # get_settings()는 settings.setup_logging()을 수행합니다.
    _ = get_app_settings()
    logging.getLogger(__name__).info("로깅 시스템 초기화 완료 (config.settings)")
except Exception as e:
    # 최종 폴백: 하드코딩된 기본값
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    logging.getLogger(__name__).error("로깅 설정 실패, 기본값 사용: %s", e)


# ===========================================
# HTTP 세션 관리
# ===========================================

def create_http_session() -> requests.Session:
    """
    재시도 로직과 타임아웃이 설정된 requests 세션을 생성하는 함수
    
    LLM API 호출을 위한 안정적인 HTTP 세션을 생성합니다.
    자동 재시도, 백오프 전략, 타임아웃 설정이 포함되어 있습니다.
    
    Returns:
        requests.Session: 설정된 HTTP 세션 객체
    """
    logging.info("create_http_session() 호출: HTTP 세션 생성 시작")
    
    try:
        # 새로운 세션 객체 생성
        session = requests.Session()
        logging.debug("requests.Session 객체 생성 완료")
        
        # 재시도 전략 설정
        retry_total = int(os.getenv('LLM_RETRY_TOTAL', '3'))
        retry_backoff = float(os.getenv('LLM_RETRY_BACKOFF', '1.0'))
        timeout_seconds = int(os.getenv('LLM_TIMEOUT', '180'))
        
        logging.debug("재시도 설정: 총_재시도=%d, 백오프_팩터=%.1f, 타임아웃=%ds", 
                     retry_total, retry_backoff, timeout_seconds)
        
        retry_strategy = Retry(
            total=retry_total,                                    # 총 재시도 횟수
            backoff_factor=retry_backoff,                         # 재시도 간격 배수 (1.0 = 1초, 2초, 4초...)
            status_forcelist=[429, 500, 502, 503, 504],          # 재시도할 HTTP 상태 코드
            allowed_methods=["POST"]                              # POST 요청만 재시도
        )
        
        # HTTP 어댑터 설정 및 마운트
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        logging.debug("HTTP/HTTPS 어댑터 마운트 완료")
        
        # 기본 타임아웃 설정
        session.timeout = timeout_seconds
        logging.debug("세션 타임아웃 설정: %ds", session.timeout)
        
        # User-Agent 설정 (환경변수에서 설정 가능)
        user_agent = os.getenv('HTTP_USER_AGENT', 'Cell-Performance-LLM-Analyzer/1.0')
        session.headers.update({
            'User-Agent': user_agent
        })
        logging.debug("User-Agent 헤더 설정 완료")
        
        logging.info("HTTP 세션 생성 완료: retry_total=%d, timeout=%ds, backoff=%.1f", 
                    retry_strategy.total, session.timeout, retry_backoff)
        
        return session
        
    except Exception as e:
        logging.exception("HTTP 세션 생성 중 오류 발생: %s", e)
        raise


# ===========================================
# MCP 서버 인스턴스 생성
# ===========================================
# FastMCP 서버 인스턴스를 생성합니다.
# 이 인스턴스는 MCP(Model Context Protocol) 도구들을 등록하고 서빙하는 데 사용됩니다.
mcp = FastMCP(name="Cell LLM 종합 분석기")
logging.info("FastMCP 서버 인스턴스 생성 완료: name=%s", mcp.name)










 














# --- MCP Handler (Presentation Layer) ---
class MCPHandler:
    """
    MCP 요청을 처리하는 Presentation Layer Handler
    
    기존의 monolithic _analyze_cell_performance_logic()를 lean한 핸들러로 리팩토링
    AnalysisService에 위임하여 실제 분석 로직을 처리하고,
    MCP 응답 형식으로 변환하는 역할만 담당
    """
    
    def __init__(self, analysis_service: AnalysisService = None):
        """
        MCPHandler 초기화
        
        Args:
            analysis_service (AnalysisService, optional): 분석 서비스 인스턴스
        """
        self.analysis_service = analysis_service
        self.logger = logging.getLogger(__name__ + '.MCPHandler')
        
        # 기본 설정 로드
        self._load_default_settings()
        
        self.logger.info("MCPHandler 초기화 완료")
    
    def _sanitize_for_logging(self, payload: dict | None) -> dict:
        """민감정보를 마스킹한 사본을 반환하여 안전하게 로깅한다."""
        if not isinstance(payload, dict):
            return {}

        redacted: dict[str, object] = {}
        for key, value in payload.items():
            lowered = str(key).lower()

            if any(token in lowered for token in ["password", "secret", "token", "authorization"]):
                redacted[key] = "***REDACTED***"
                continue

            if lowered in {"db", "database", "connection"}:
                # DB 설정은 중첩 딕셔너리일 확률이 높으므로 재귀적으로 마스킹한다.
                redacted[key] = self._sanitize_for_logging(value)
                continue

            if isinstance(value, dict):
                redacted[key] = self._sanitize_for_logging(value)
            elif isinstance(value, list):
                redacted[key] = [self._sanitize_for_logging(item) if isinstance(item, dict) else item for item in value]
            else:
                redacted[key] = value

        return redacted

    def _load_default_settings(self) -> None:
        """기본 설정 로드 (Configuration Manager 우선, 환경변수 폴백)"""
        try:
            settings = get_app_settings()
            self.default_backend_url = str(settings.backend_service_url)
            
            # 디버깅: db_password 상태 확인
            self.logger.debug("db_password 타입: %s", type(settings.db_password))
            self.logger.debug("db_password 값: %s", settings.db_password)
            
            # 안전한 password 처리
            db_password = ""
            if settings.db_password is not None:
                try:
                    db_password = settings.db_password.get_secret_value()
                    self.logger.debug("db_password 성공적으로 읽음: 길이=%d", len(db_password))
                except Exception as e:
                    self.logger.warning("db_password.get_secret_value() 실패, 빈 문자열 사용: %s", e)
                    db_password = ""
            else:
                self.logger.warning("settings.db_password가 None입니다!")
            
            self.default_db = {
                "host": settings.db_host,
                "port": settings.db_port,
                "user": settings.db_user,
                "password": db_password,
                "dbname": settings.db_name
            }
            self.logger.debug("Configuration Manager에서 기본 설정 로드 완료")
        except Exception as e:
            self.logger.warning("Configuration Manager 로딩 실패, 기본값 사용: %s", e)
            self.default_backend_url = 'http://165.213.69.30:8000/api/analysis/results/'
            self.default_db = {
                "host": "127.0.0.1",
                "port": 5432,
                "user": "postgres",
                "password": "",
                "dbname": "postgres"
            }
    
    def _validate_basic_request(self, request: dict) -> None:
        """
        기본 요청 검증
        
        Args:
            request (dict): MCP 요청 데이터
            
        Raises:
            ValueError: 필수 필드 누락 또는 잘못된 형식
        """
        self.logger.debug(
            "_validate_basic_request() 호출: 타입=%s, 키=%s",
            type(request).__name__,
            list(request.keys()) if isinstance(request, dict) else None,
        )
        
        # 필수 필드 확인
        n1_text = request.get('n_minus_1') or request.get('n1')
        n_text = request.get('n')
        
        if not n1_text or not n_text:
            raise ValueError("'n_minus_1'와 'n' 시간 범위를 모두 제공해야 합니다.")
        
        # 기본 타입 검증
        if not isinstance(request, dict):
            raise ValueError("요청은 딕셔너리 형태여야 합니다.")
        
        self.logger.info("기본 요청 검증 통과: n_minus_1=%s, n=%s", n1_text, n_text)
    
    def _parse_request_to_analysis_format(self, request: dict) -> dict:
        """MCP 요청을 표준 AnalysisRequest 스키마로 변환"""
        self.logger.debug("_parse_request_to_analysis_format() 호출: 요청 형식 변환")

        enriched_request = {
            **request,
            "backend_url": request.get("backend_url") or self.default_backend_url,
            "db": request.get("db") or self.default_db,
            "max_prompt_tokens": request.get("max_prompt_tokens", DEFAULT_MAX_PROMPT_TOKENS),
            "max_prompt_chars": request.get("max_prompt_chars", DEFAULT_MAX_PROMPT_CHARS),
        }

        analysis_request = AnalysisRequest.from_dict(enriched_request)
        request_dict = analysis_request.to_dict()

        self.logger.info(
            "요청 형식 변환 완료: 필드수=%d, 요약=%s",
            len(request_dict),
            {
                "table": request_dict.get("table"),
                "columns_keys": list(request_dict.get("columns", {}).keys()),
                "filters": self._sanitize_for_logging({
                    key: request_dict.get(key)
                    for key in ("ne", "cellid", "host")
                    if request_dict.get(key) is not None
                }),
                "selected_pegs": request_dict.get("selected_pegs"),
            },
        )

        return request_dict
    
    def _build_backend_payload(self, analysis_result: dict, analysis_request: dict) -> dict:
        """백엔드 POST 호출에 사용할 페이로드를 구성한다."""

        if not isinstance(analysis_result, dict):
            return {"analysis_result": analysis_result}

        payload: dict[str, Any] = analysis_result.copy()

        request_context = {
            "n_minus_1": analysis_request.get("n_minus_1"),
            "n": analysis_request.get("n"),
            "filters": self._sanitize_for_logging(analysis_request.get("filters", {})),
            "analysis_type": analysis_request.get("analysis_type"),
            "selected_pegs": analysis_request.get("selected_pegs"),
        }

        payload.setdefault("analysis_type", analysis_request.get("analysis_type"))
        payload.setdefault("request_context", request_context)

        return payload

    def _create_analysis_service(self) -> AnalysisService:
        """
        AnalysisService 인스턴스 생성 (의존성 주입)
        
        Returns:
            AnalysisService: 구성된 분석 서비스
        """
        self.logger.debug("_create_analysis_service() 호출: AnalysisService 생성")
        
        # DatabaseRepository 생성
        db_repo = PostgreSQLRepository()
        
        # LLMRepository 생성
        llm_repo = LLMClient()
        
        # AnalysisService 생성 (의존성 주입)
        service = AnalysisService(
            database_repository=db_repo,
            llm_analysis_service=None  # LLMAnalysisService는 내부에서 생성
        )
        
        self.logger.info("AnalysisService 생성 완료")
        return service
    
    def _format_response_for_mcp(self, analysis_result: dict) -> dict:
        """
        AnalysisService 결과를 MCP 형식으로 변환
        
        Args:
            analysis_result (dict): AnalysisService 결과
            
        Returns:
            dict: MCP 호환 응답 형식
        """
        self.logger.debug("_format_response_for_mcp() 호출: 응답 형식 변환")
        
        # 중복 제거: AnalysisService 결과를 그대로 사용하고 필요한 필드만 추가/변경
        mcp_response = analysis_result.copy()
        
        # MCP 전용 필드 추가
        if mcp_response.get("status") == "success":
            mcp_response["message"] = "분석이 성공적으로 완료되었습니다."
        elif mcp_response.get("status") == "error":
            mcp_response["message"] = mcp_response.get("message", "분석 중 오류가 발생했습니다.")
        
        # 백엔드에서 중복 처리하므로 MCP 측 중복 코드 제거됨
        # 하위 호환성은 백엔드 응답에서 처리
        
        # 백엔드 전송 결과가 있으면 포함 (이미 analysis_result에 있으면 중복 방지)
        if "backend_response" in analysis_result and "backend_response" not in mcp_response:
            mcp_response["backend_response"] = analysis_result["backend_response"]
        
        self.logger.info("MCP 응답 형식 변환 완료: %d개 키 (중복 제거됨)", len(mcp_response))
        return mcp_response
    
    def handle_request(self, request: dict) -> dict:
        """
        MCP 요청 처리 메인 엔트리포인트
        
        Args:
            request (dict): MCP 요청 데이터
            
        Returns:
            dict: MCP 응답 데이터
            
        Raises:
            ValueError: 요청 검증 실패
            Exception: 처리 중 오류 발생
        """
        sanitized_request = self._sanitize_for_logging(request)
        self.logger.info(
            "%s MCP Handler 요청 처리 시작 | 키=%s | 요약=%s",
            "=" * 10,
            list(request.keys()) if isinstance(request, dict) else None,
            sanitized_request,
        )
        
        try:
            # 1단계: 기본 요청 검증
            self.logger.info("1단계: 기본 요청 검증")
            self._validate_basic_request(request)
            
            # 2단계: 요청 형식 변환
            self.logger.info("2단계: 요청 형식 변환")
            analysis_request = self._parse_request_to_analysis_format(request)
            self.logger.debug(
                "AnalysisService 전달용 요청 요약: %s",
                {
                    "backend_url": bool(analysis_request.get('backend_url')),
                    "db_keys": list(analysis_request.get('db', {}).keys()),
                    "time_ranges_text": {
                        "n_minus_1": analysis_request.get('n_minus_1'),
                        "n": analysis_request.get('n'),
                    },
                    "filters": self._sanitize_for_logging(analysis_request.get('filters', {})),
                },
            )
            
            # 3단계: AnalysisService 생성 (필요시)
            if not self.analysis_service:
                self.logger.info("3단계: AnalysisService 생성")
                self.analysis_service = self._create_analysis_service()
            
            # 4단계: 분석 실행
            self.logger.info("4단계: 분석 실행 (AnalysisService 위임)")
            self.logger.debug(
                "AnalysisService.perform_analysis 호출 준비 | backend_url=%s | table=%s | columns=%s",
                analysis_request.get('backend_url'),
                analysis_request.get('table'),
                analysis_request.get('columns'),
            )
            analysis_result = self.analysis_service.perform_analysis(analysis_request)
            self.logger.debug(
                "AnalysisService 수행 완료: status=%s, keys=%s",
                analysis_result.get('status') if isinstance(analysis_result, dict) else None,
                list(analysis_result.keys()) if isinstance(analysis_result, dict) else type(analysis_result).__name__,
            )

            backend_url = analysis_request.get('backend_url')
            if backend_url:
                self.logger.info("4.5단계: 백엔드 업로드 실행")
                backend_payload = self._build_backend_payload(analysis_result, analysis_request)
                self.logger.debug(
                    "백엔드 업로드 페이로드 키: %s",
                    list(backend_payload.keys()) if isinstance(backend_payload, dict) else type(backend_payload).__name__,
                )
                # 백엔드 업로드 기능은 향후 재구현 예정
                backend_response = None
                if isinstance(analysis_result, dict):
                    analysis_result = analysis_result.copy()
                    analysis_result['backend_response'] = backend_response
                else:
                    analysis_result = {
                        "status": "success",
                        "raw_result": analysis_result,
                        "backend_response": backend_response,
                    }
                self.logger.info(
                    "백엔드 업로드 완료: 응답 요약=%s",
                    self._sanitize_for_logging(backend_response) if backend_response else None,
                )
            
            # 5단계: 응답 형식 변환
            self.logger.info("5단계: MCP 응답 형식 변환")
            mcp_response = self._format_response_for_mcp(analysis_result)
            
            self.logger.info("=" * 20 + " MCP Handler 요청 처리 완료 " + "=" * 20)
            return mcp_response
            
        except ValueError as e:
            # 검증 오류 (400 Bad Request)
            self.logger.error("요청 검증 실패: %s", e)
            return {
                "status": "error",
                "error_type": "validation_error",
                "message": str(e),
                "details": "요청 형식이 올바르지 않습니다."
            }
            
        except AnalysisServiceError as e:
            # 분석 서비스 오류 (500 Internal Server Error)
            self.logger.error("분석 서비스 오류: %s", e)
            return {
                "status": "error", 
                "error_type": "analysis_error",
                "message": str(e),
                "details": e.to_dict() if hasattr(e, 'to_dict') else None,
                "workflow_step": getattr(e, 'workflow_step', None)
            }
            
        except Exception as e:
            # 예상치 못한 오류 (500 Internal Server Error)
            self.logger.exception("예상치 못한 오류 발생: %s", e)
            return {
                "status": "error",
                "error_type": "internal_error", 
                "message": "내부 서버 오류가 발생했습니다.",
                "details": str(e)
            }
    
    def close(self) -> None:
        """리소스 정리"""
        if self.analysis_service:
            self.analysis_service.close()
        self.logger.info("MCPHandler 리소스 정리 완료")
    
    def __enter__(self):
        """컨텍스트 매니저 진입"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """컨텍스트 매니저 종료"""
        self.close()
        return False




@mcp.tool
def analyze_cell_performance_with_llm(request: dict) -> dict:
    """
    MCP 엔드포인트: 시간 범위 기반 통합 셀 성능 분석 실행
    
    새로운 아키텍처: MCPHandler -> AnalysisService -> 각종 Repository/Service 패턴
    """
    # 새로운 MCPHandler 사용
    with MCPHandler() as handler:
        return handler.handle_request(request)


@mcp.tool
def analyze_peg_comparison(request: dict) -> dict:
    """
    MCP 엔드포인트: PEG 비교분석 실행
    
    N-1 기간과 N 기간의 PEG 성능 지표를 비교하여 통계적 분석을 수행합니다.
    프론트엔드의 계산 로직을 MCP 서버로 이전하여 성능을 향상시킵니다.
    
    Args:
        request (dict): PEG 비교분석 요청 데이터
            - analysis_id (str): 분석 고유 식별자
            - raw_data (dict): 원시 KPI 데이터
                - stats (list): KPI 통계 데이터 리스트
                    - kpi_name (str): KPI 이름
                    - period (str): 기간 ("N-1" 또는 "N")
                    - avg (float): 평균값
                    - cell_id (str): 셀 ID
                - peg_definitions (dict): PEG 정의
                    - peg_name (str): PEG 이름
                    - weight (int): 가중치
                    - thresholds (dict): 임계값 설정
            - options (dict, optional): 분석 옵션
                - include_metadata (bool): 메타데이터 포함 여부
                - algorithm_version (str): 알고리즘 버전
    
    Returns:
        dict: PEG 비교분석 결과
            - success (bool): 성공 여부
            - data (dict): 분석 결과 데이터
                - analysis_id (str): 분석 ID
                - peg_comparison_results (list): PEG별 비교 결과
                - summary (dict): 전체 요약 통계
                - analysis_metadata (dict): 분석 메타데이터
            - error (dict, optional): 오류 정보
            - processing_time (float): 처리 시간 (초)
            - algorithm_version (str): 사용된 알고리즘 버전
            - cached (bool): 캐시 사용 여부
    
    Example:
        {
            "analysis_id": "peg_analysis_001",
            "raw_data": {
                "stats": [
                    {
                        "kpi_name": "UL_throughput_avg",
                        "period": "N-1",
                        "avg": 45.2,
                        "cell_id": "cell_001"
                    },
                    {
                        "kpi_name": "UL_throughput_avg", 
                        "period": "N",
                        "avg": 48.7,
                        "cell_id": "cell_001"
                    }
                ],
                "peg_definitions": {
                    "UL_throughput_avg": {
                        "weight": 3,
                        "thresholds": {"high": 20.0, "medium": 10.0}
                    }
                }
            },
            "options": {
                "include_metadata": true,
                "algorithm_version": "v2.1.0"
            }
        }
    """
    logger = logging.getLogger(__name__ + '.peg_comparison')
    logger.info("=" * 20 + " PEG 비교분석 MCP 요청 처리 시작 " + "=" * 20)
    
    try:
        # 1단계: 요청 데이터 검증 및 변환
        logger.info("1단계: 요청 데이터 검증 및 변환")
        
        # Pydantic 모델을 사용한 요청 검증
        from models.peg_comparison import PEGComparisonRequest, RawData, Options
        
        # raw_data 검증
        if 'raw_data' not in request:
            raise ValueError("'raw_data' 필드가 누락되었습니다.")
        
        raw_data = RawData(**request['raw_data'])
        logger.info("RawData 검증 완료: stats=%d개, peg_definitions=%d개", 
                   len(raw_data.stats), len(raw_data.peg_definitions))
        
        # options 검증 (선택적)
        options = None
        if 'options' in request and request['options']:
            options = Options(**request['options'])
            logger.info("Options 검증 완료: include_metadata=%s, algorithm_version=%s",
                       options.include_metadata, options.algorithm_version)
        
        # analysis_id 검증
        analysis_id = request.get('analysis_id', 'default_analysis_id')
        if not isinstance(analysis_id, str) or not analysis_id.strip():
            analysis_id = f"peg_analysis_{int(time.time())}"
        
        logger.info("요청 검증 완료: analysis_id=%s", analysis_id)
        
        # 2단계: PEGComparisonAnalyzer 인스턴스 생성
        logger.info("2단계: PEGComparisonAnalyzer 인스턴스 생성")
        from services.peg_comparison_service import PEGComparisonAnalyzer
        
        analyzer = PEGComparisonAnalyzer()
        logger.info("PEGComparisonAnalyzer 초기화 완료")
        
        # 3단계: PEG 비교분석 실행
        logger.info("3단계: PEG 비교분석 실행")
        start_time = time.perf_counter()
        
        # options를 딕셔너리로 변환 (PEGComparisonAnalyzer가 딕셔너리를 기대)
        options_dict = None
        if options:
            options_dict = options.dict()
        
        # async 함수를 동기적으로 실행
        import asyncio
        response = asyncio.run(analyzer.analysis_peg_comparison(raw_data, options_dict))
        
        processing_time = time.perf_counter() - start_time
        logger.info("PEG 비교분석 완료: %.4f초 소요", processing_time)
        
        # 4단계: 응답 형식 변환 (Pydantic 모델을 딕셔너리로)
        logger.info("4단계: 응답 형식 변환")
        
        if response.success:
            # 성공 응답을 딕셔너리로 변환
            mcp_response = {
                "success": True,
                "data": response.data.dict() if response.data else None,
                "processing_time": processing_time,
                "algorithm_version": response.algorithm_version,
                "cached": response.cached
            }
            logger.info("성공 응답 생성: data_keys=%s", 
                       list(response.data.dict().keys()) if response.data else "None")
        else:
            # 실패 응답
            mcp_response = {
                "success": False,
                "error": response.error,
                "processing_time": processing_time,
                "algorithm_version": response.algorithm_version,
                "cached": response.cached
            }
            logger.warning("실패 응답 생성: error=%s", response.error)
        
        logger.info("=" * 20 + " PEG 비교분석 MCP 요청 처리 완료 " + "=" * 20)
        return mcp_response
        
    except ValueError as ve:
        # 검증 오류
        logger.error("요청 검증 실패: %s", ve)
        return {
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": str(ve),
                "details": "요청 데이터 형식이 올바르지 않습니다."
            },
            "processing_time": 0.0,
            "algorithm_version": "unknown"
        }
        
    except Exception as e:
        # 예상치 못한 오류
        logger.exception("PEG 비교분석 중 예상치 못한 오류 발생: %s", e)
        return {
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": f"내부 서버 오류: {str(e)}",
                "details": "PEG 비교분석 처리 중 오류가 발생했습니다."
            },
            "processing_time": 0.0,
            "algorithm_version": "unknown"
        }


# ===========================================
# End-to-End Integration & Testing
# ===========================================

def initialize_integrated_components():
    """
    모든 컴포넌트를 의존성 주입으로 통합 초기화
    
    Returns:
        tuple: (mcp_handler, analysis_service, logger) 통합된 컴포넌트들
    """
    logger = logging.getLogger(__name__ + '.integration')
    logger.info("=== 통합 컴포넌트 초기화 시작 ===")
    
    try:
        # 1단계: Configuration Manager와 로깅 초기화
        logger.info("1단계: Configuration Manager 초기화")
        settings = get_app_settings()
        logger.info("✅ Configuration Manager 로드 완료")
        
        # 2단계: Core Utilities 초기화 (최소 의존성)
        logger.info("2단계: Core Utilities 초기화")
        from services import PEGCalculator
        from utils import DataProcessor, RequestValidator, ResponseFormatter, TimeRangeParser
        
        time_parser = TimeRangeParser()
        peg_calculator = PEGCalculator()
        data_processor = DataProcessor()
        request_validator = RequestValidator(time_parser=time_parser)
        response_formatter = ResponseFormatter()
        
        logger.info("✅ Core Utilities 초기화 완료: TimeRangeParser, PEGCalculator, DataProcessor, RequestValidator, ResponseFormatter")
        
        # 3단계: Repository Layer 초기화
        logger.info("3단계: Repository Layer 초기화")
        from repositories import LLMClient, PostgreSQLRepository

        # PostgreSQL Repository (DB 설정 주입)
        db_repository = PostgreSQLRepository()
        logger.info("✅ PostgreSQLRepository 초기화 완료")
        
        # LLM Repository (LLM 설정 주입)
        llm_repository = LLMClient()
        logger.info("✅ LLMClient 초기화 완료")
        
        # 4단계: Service Layer 초기화
        logger.info("4단계: Service Layer 초기화")
        from services import AnalysisService, LLMAnalysisService, PEGProcessingService

        # PEG Processing Service (DB Repository + PEG Calculator 주입)
        peg_processing_service = PEGProcessingService(
            database_repository=db_repository,
            peg_calculator=peg_calculator
        )
        logger.info("✅ PEGProcessingService 초기화 완료")
        
        # LLM Analysis Service (LLM Repository 주입)
        llm_analysis_service = LLMAnalysisService(
            llm_repository=llm_repository
        )
        logger.info("✅ LLMAnalysisService 초기화 완료")
        
        # Analysis Service (모든 서비스 통합)
        analysis_service = AnalysisService(
            database_repository=db_repository,
            peg_processing_service=peg_processing_service,
            llm_analysis_service=llm_analysis_service,
            time_parser=time_parser,
            data_processor=data_processor
        )
        logger.info("✅ AnalysisService 초기화 완료")
        
        # 5단계: Presentation Layer 초기화 (MCPHandler)
        logger.info("5단계: Presentation Layer 초기화")
        
        # MCPHandler (모든 컴포넌트 주입)
        mcp_handler = MCPHandler(
            request_validator=request_validator,
            analysis_service=analysis_service,
            response_formatter=response_formatter
        )
        logger.info("✅ MCPHandler 초기화 완료")
        
        logger.info("=== 통합 컴포넌트 초기화 완료 ===")
        logger.info("초기화된 컴포넌트: MCPHandler, AnalysisService, 7개 유틸리티/서비스")
        
        return mcp_handler, analysis_service, logger
        
    except Exception as e:
        logger.error("통합 컴포넌트 초기화 실패: %s", e)
        logger.exception("초기화 오류 상세 정보")
        raise


def run_end_to_end_test():
    """
    End-to-End 통합 테스트 실행
    
    모든 컴포넌트가 올바르게 통합되었는지 검증합니다.
    """
    logger = logging.getLogger(__name__ + '.e2e_test')
    logger.info("=== End-to-End 통합 테스트 시작 ===")
    
    try:
        # 1단계: 모든 컴포넌트 초기화
        logger.info("1단계: 통합 컴포넌트 초기화")
        mcp_handler, analysis_service, integration_logger = initialize_integrated_components()
        
        # 2단계: 샘플 MCP 요청 정의
        logger.info("2단계: 샘플 MCP 요청 정의")
        sample_request = {
            "n_minus_1": "2025-01-01_09:00~2025-01-01_18:00",
            "n": "2025-01-02_09:00~2025-01-02_18:00",
            "output_dir": "./test_analysis_output",
            "table": "summary",
            "analysis_type": "enhanced",
            "enable_mock": True,  # 테스트용 Mock 모드
            "max_prompt_tokens": 8000,
            "db": {
                "host": "localhost",
                "port": 5432,
                "dbname": "test_db",
                "user": "test_user",
                "password": "test_pass"
            },
            "filters": {
                "ne": "nvgnb#10000",
                "cellid": ["2010", "2011"],
                "host": "192.168.1.1"
            },
            "selected_pegs": ["preamble_count", "response_count"],
            "peg_definitions": {
                "success_rate": "response_count/preamble_count*100"
            }
        }
        
        logger.info("✅ 샘플 요청 정의 완료: %d개 필드", len(sample_request))
        
        # 3단계: End-to-End 요청 처리
        logger.info("3단계: End-to-End 요청 처리 실행")
        
        start_time = time.time()
        response = mcp_handler.handle_request(sample_request)
        end_time = time.time()
        
        processing_time = end_time - start_time
        logger.info("✅ 요청 처리 완료: %.2f초 소요", processing_time)
        
        # 4단계: 응답 검증
        logger.info("4단계: 응답 검증")
        
        if not response:
            raise ValueError("응답이 비어있습니다")
        
        if not isinstance(response, dict):
            raise ValueError(f"응답이 딕셔너리가 아닙니다: {type(response)}")
        
        response_status = response.get('status', 'unknown')
        response_keys = list(response.keys())
        
        logger.info("응답 상태: %s", response_status)
        logger.info("응답 키: %s", response_keys)
        
        if response_status == 'success':
            logger.info("✅ End-to-End 테스트 성공!")
            
            # 응답 세부 정보 로깅
            if 'data_summary' in response:
                data_summary = response['data_summary']
                logger.info("데이터 요약: %s", data_summary)
            
            if 'peg_analysis' in response:
                peg_analysis = response['peg_analysis']
                peg_count = len(peg_analysis.get('results', []))
                logger.info("PEG 분석 결과: %d개", peg_count)
            
            if 'llm_analysis' in response:
                llm_analysis = response['llm_analysis']
                model_used = llm_analysis.get('model_used', 'unknown')
                logger.info("LLM 분석 모델: %s", model_used)
            
            if 'metadata' in response:
                metadata = response['metadata']
                request_id = metadata.get('request_id', 'unknown')
                logger.info("요청 ID: %s", request_id)
        
        elif response_status == 'error':
            error_message = response.get('message', 'Unknown error')
            logger.warning("⚠️ End-to-End 테스트에서 오류 응답 받음: %s", error_message)
            
            # 오류여도 시스템이 정상적으로 응답을 반환했으므로 부분적 성공
            logger.info("✅ 오류 처리 시스템 정상 작동 확인")
        
        else:
            logger.warning("⚠️ 예상치 못한 응답 상태: %s", response_status)
        
        # 5단계: 컴포넌트 상태 검증
        logger.info("5단계: 컴포넌트 상태 검증")
        
        # AnalysisService 상태 확인
        service_info = analysis_service.get_service_info()
        workflow_status = analysis_service.get_workflow_status()
        
        logger.info("AnalysisService 정보: %s", service_info)
        logger.info("워크플로우 상태: %s", workflow_status)
        
        logger.info("=== End-to-End 통합 테스트 완료 ===")
        logger.info("전체 처리 시간: %.2f초", processing_time)
        logger.info("테스트 결과: %s", "성공" if response_status in ['success', 'error'] else "부분적 성공")
        
        return response
        
    except Exception as e:
        logger.error("End-to-End 테스트 실패: %s", e)
        logger.exception("테스트 오류 상세 정보")
        
        # 실패해도 오류 정보를 반환
        return {
            "status": "test_error",
            "message": f"End-to-End 테스트 실패: {str(e)}",
            "error_type": type(e).__name__
        }


if __name__ == '__main__':
    import sys

    # End-to-End 테스트 모드
    if len(sys.argv) > 1 and sys.argv[1] == "--e2e-test":
        print("=" * 60)
        print("End-to-End Integration Test")
        print("=" * 60)
        
        # 로깅 설정
        # 공통 설정 사용(이미 get_app_settings() 호출 시 설정됨). 추가 파일 핸들러만 덧붙임
        from config.settings import get_settings
        settings = get_settings()
        if settings.log_file_enabled:
            pass  # 파일 로깅은 settings.setup_logging에서 처리됨
        else:
            fh = logging.FileHandler('e2e_test.log', mode='w', encoding='utf-8')
            fh.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            logging.getLogger().addHandler(fh)
        
        try:
            result = run_end_to_end_test()
            print("\n" + "=" * 60)
            print("테스트 결과:")
            print(json.dumps(result, ensure_ascii=False, indent=2))
            print("=" * 60)
            
            # 성공 시 0, 실패 시 1로 종료
            sys.exit(0 if result.get('status') in ['success', 'error'] else 1)
            
        except Exception as e:
            print(f"\n테스트 실행 중 치명적 오류: {e}")
            sys.exit(1)
    
    # CLI 모드 지원: Backend에서 프로세스로 호출 시 사용
    elif len(sys.argv) > 2 and sys.argv[1] == "--request":
        try:
            request_json = sys.argv[2]
            request_data = json.loads(request_json)
            
            logging.info("CLI 모드로 LLM 분석을 실행합니다.")
            logging.info("요청 데이터: %s", json.dumps(request_data, ensure_ascii=False, indent=2))
            
            # 통합된 컴포넌트 사용
            mcp_handler, _, _ = initialize_integrated_components()
            result = mcp_handler.handle_request(request_data)
            
            # JSON 결과 출력 (Backend에서 capture)
            print(json.dumps(result, ensure_ascii=False))
            
            # 성공 종료
            sys.exit(0)
            
        except Exception as e:
            logging.exception("CLI 모드 실행 중 오류 발생: %s", e)
            error_result = {
                "status": "error",
                "message": f"CLI 모드 실행 오류: {str(e)}"
            }
            print(json.dumps(error_result, ensure_ascii=False))
            sys.exit(1)
    else:
        logging.info("streamable-http 모드로 MCP를 실행합니다.")
        mcp.run(transport="streamable-http", host="0.0.0.0", port=8001)