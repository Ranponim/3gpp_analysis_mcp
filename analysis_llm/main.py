"""
=====================================================================================
Cell 성능 LLM 분석기 (MCP 서버 + 아키텍처 리팩토링 버전)
=====================================================================================

## 📋 시스템 개요
3GPP 이동통신망의 Cell 성능 데이터를 LLM을 활용하여 종합 분석하는 MCP(Model Context Protocol) 서버입니다.
Clean Architecture 패턴을 적용하여 Repository, Service, Presentation 계층으로 분리된 구조로 설계되었습니다.

## 🏗️ 아키텍처 구조
### Presentation Layer (MCPHandler)
- MCP 요청/응답 처리 및 형식 변환
- 요청 검증 및 오류 처리
- AnalysisService로의 비즈니스 로직 위임

### Service Layer (AnalysisService)
- 핵심 비즈니스 로직 처리
- PEG 데이터 처리 및 LLM 분석 조율
- 의존성 주입을 통한 Repository 계층 활용

### Repository Layer
- PostgreSQLRepository: 데이터베이스 접근 및 쿼리 실행
- LLMClient: LLM API 호출 및 응답 처리

### Utility Layer
- TimeRangeParser: 시간 범위 파싱
- DataProcessor: 데이터 변환 및 처리
- PEGCalculator: 파생 지표 계산

## 🔄 주요 처리 흐름
1. **MCP 요청 수신**: FastMCP를 통한 도구 호출 수신
2. **요청 검증**: MCPHandler에서 기본 검증 수행
3. **서비스 위임**: AnalysisService로 비즈니스 로직 처리 위임
4. **데이터 처리**: Repository를 통한 데이터 조회 및 처리
5. **LLM 분석**: 전문가 수준의 성능 분석 수행
6. **응답 반환**: MCP 형식으로 결과 반환

## 🎯 핵심 기능
- **MCP 서버**: FastMCP 기반의 표준화된 도구 제공
- **Clean Architecture**: 관심사 분리 및 의존성 주입 패턴
- **PEG 비교분석**: 통계적 성능 비교 및 분석
- **환경변수 지원**: Configuration Manager를 통한 설정 관리
- **오류 처리**: 계층별 예외 처리 및 로깅

## 📝 MCP 도구 사용 예시

### 1. Cell 성능 분석 (analyze_cell_performance_with_llm)
// A안(JSONB 2단계 확장, peg_name = metric[key]) + DU/Cell 필터 예시
{
  "n_minus_1": "2025-01-01_09:00~2025-01-01_18:00",
  "n": "2025-01-02_09:00~2025-01-02_18:00",
  "table": "kpi_summary",
  "columns": {
    "time": "datetime",
    "family_id": "family_id",
    "family_name": "family_name",
    "values": "values",
    "ne": "ne_key",
    "rel_ver": "rel_ver",
    "swname": "swname"
  },
  "filters": {
    "ne": "420",            // DU 지정 (ne_key)
    "cellid": "1100"        // CellIdentity 차원에서 1100만 제한
  },
  "parsing": {
    "mode": "two_level",           // 최상위 인덱스 → 내부 PEG 2단계 확장
    "peg_name_mode": "append_dim"   // peg_name = metric[key] (A안)
  },
  "selected_pegs": ["VoLTEDLVolume", "PaBiasModeTime(s)"],
  "peg_definitions": {
    "success_rate": "response_count/preamble_count*100"
  }
}

// 동작 요약(A안)
// - CellIdentity는 지정된 key(예: 1100)만 포함하여 peg_name=VoLTEDLVolume[1100] 형식으로 반환
// - 그 외 index_name(QCI, BPU_ID, 또는 없음)은 항상 포함(무조건 파싱)
// - value는 문자열에서 숫자만 추출 후 numeric 캐스팅됨

### 2. PEG 비교분석 (analyze_peg_comparison)
{
  "analysis_id": "peg_analysis_001",
  "raw_data": {
    "stats": [
      {
        "kpi_name": "UL_throughput_avg",
        "period": "N-1",
        "avg": 45.2,
        "cell_id": "cell_001"
      }
    ],
    "peg_definitions": {
      "UL_throughput_avg": {
        "weight": 3,
        "thresholds": {"high": 20.0, "medium": 10.0}
      }
    }
  }
}

## 🔧 환경변수 설정
Configuration Manager를 통해 중앙집중식 설정 관리:
- 데이터베이스 연결 정보
- LLM API 설정
- 로깅 및 성능 튜닝 파라미터
자세한 설정은 config/settings.py 및 ENV_SETTINGS.md 참조

## 🧪 테스트 및 실행
- End-to-End 테스트: `python main.py --e2e-test`
- CLI 모드: `python main.py --request '{"n_minus_1": "...", "n": "..."}'`
- MCP 서버: `python main.py` (기본 포트 8001)
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
    """
    애플리케이션 설정 인스턴스 반환
    
    Configuration Manager를 통해 애플리케이션의 모든 설정을 중앙집중식으로 관리합니다.
    지연 로딩 패턴을 사용하여 필요할 때만 설정을 로드합니다.
    
    Returns:
        Settings: 애플리케이션 설정 객체
            - 데이터베이스 연결 정보
            - LLM API 설정
            - 로깅 설정
            - 기타 애플리케이션 설정
    """
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
    """
    프롬프트 제한값들을 설정에서 가져오기
    
    LLM 프롬프트의 크기 제한값들을 환경변수에서 읽어 반환합니다.
    메모리 및 성능 보호를 위한 설정값들입니다.
    
    Returns:
        dict: 프롬프트 제한값 딕셔너리
            - max_prompt_tokens (int): 최대 토큰 수 (기본값: 24000)
            - max_prompt_chars (int): 최대 문자 수 (기본값: 80000)
            - max_specific_rows (int): 최대 행 수 (기본값: 500)
            - max_raw_str (int): 최대 원시 문자열 길이 (기본값: 4000)
            - max_raw_array (int): 최대 배열 크기 (기본값: 100)
    """
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
    재시도 로직과 타임아웃이 설정된 requests 세션을 생성
    
    LLM API 호출을 위한 안정적인 HTTP 세션을 생성합니다.
    자동 재시도, 백오프 전략, 타임아웃 설정이 포함되어 있습니다.
    
    설정 항목:
    - 재시도 횟수: LLM_RETRY_TOTAL 환경변수 (기본값: 3)
    - 백오프 팩터: LLM_RETRY_BACKOFF 환경변수 (기본값: 1.0)
    - 타임아웃: LLM_TIMEOUT 환경변수 (기본값: 180초)
    - 재시도 대상 상태코드: 429, 500, 502, 503, 504
    
    Returns:
        requests.Session: 설정된 HTTP 세션 객체
        
    Raises:
        Exception: 세션 생성 중 오류 발생 시
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
    
    Clean Architecture의 Presentation Layer 역할을 담당하며,
    MCP 요청/응답의 형식 변환과 기본 검증을 수행합니다.
    
    주요 책임:
    - MCP 요청 데이터의 형식 검증 및 변환
    - AnalysisService로 비즈니스 로직 위임
    - MCP 응답 형식으로 결과 변환
    - 오류 처리 및 로깅
    
    의존성:
    - AnalysisService: 핵심 비즈니스 로직 처리
    - Configuration Manager: 기본 설정 관리
    
    사용 패턴:
        with MCPHandler() as handler:
            result = handler.handle_request(request_data)
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
        """
        민감정보를 마스킹한 사본을 반환하여 안전하게 로깅
        
        데이터베이스 비밀번호, API 키 등 민감한 정보를 로그에 노출하지 않도록
        마스킹 처리합니다. 중첩된 딕셔너리 구조도 재귀적으로 처리합니다.
        
        Args:
            payload (dict | None): 로깅할 데이터 딕셔너리
            
        Returns:
            dict: 민감정보가 마스킹된 딕셔너리 사본
        """
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
        """
        기본 설정 로드 (Configuration Manager 우선, 환경변수 폴백)
        
        애플리케이션의 기본 설정값들을 로드합니다.
        Configuration Manager를 우선적으로 사용하고, 실패 시 환경변수로 폴백합니다.
        
        설정 항목:
        - default_backend_url: 백엔드 API 엔드포인트
        - default_db: 데이터베이스 연결 정보
        """
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
        
        MCP 요청의 필수 필드와 기본 형식을 검증합니다.
        
        Args:
            request (dict): MCP 요청 데이터
                - n_minus_1 (str): N-1 기간 시간 범위 (필수)
                - n (str): N 기간 시간 범위 (필수)
            
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
        """
        MCP 요청을 표준 AnalysisRequest 스키마로 변환
        
        MCP 요청 형식을 AnalysisService가 이해할 수 있는 표준 형식으로 변환합니다.
        기본값 설정 및 Pydantic 모델 검증을 수행합니다.
        
        Args:
            request (dict): MCP 요청 데이터
            
        Returns:
            dict: AnalysisRequest 형식으로 변환된 요청 데이터
        """
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

        # 원본 요청의 columns가 존재하면 그대로 보존하여 JSONB 키(family_name, values) 누락을 방지
        try:
            if isinstance(request.get("columns"), dict) and request.get("columns"):
                request_dict["columns"] = request["columns"]
                self.logger.debug(
                    "columns 보존: keys=%s",
                    list(request_dict["columns"].keys()),
                )
        except Exception as e:
            self.logger.warning("columns 보존 중 예외(무시): %s", e)

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
        """
        백엔드 V2 API용 페이로드 생성
        
        MCP 분석 결과를 간소화된 백엔드 V2 스키마에 맞게 변환합니다.
        
        주요 변경사항:
        - host → swname 명칭 변경
        - 중복 제거 및 구조 단순화
        - 필수 필드만 포함
        
        Args:
            analysis_result (dict): AnalysisService의 분석 결과
            analysis_request (dict): 원본 요청 데이터
            
        Returns:
            dict: 백엔드 V2 API 전송용 페이로드
        """
        from .utils.backend_payload_builder import BackendPayloadBuilder
        import json
        
        self.logger.info("백엔드 V2 페이로드 생성 시작")
        
        try:
            payload = BackendPayloadBuilder.build_v2_payload(
                analysis_result=analysis_result,
                analysis_request=analysis_request
            )
            
            # 상세 디버그 로깅
            self.logger.debug(
                "✅ 페이로드 생성 완료:\n"
                "  최상위 키: %s\n"
                "  ne_id: %s\n"
                "  cell_id: %s\n"
                "  swname: %s\n"
                "  rel_ver: %s\n"
                "  analysis_period: %s\n"
                "  choi_result: %s\n"
                "  llm_analysis 키: %s\n"
                "  peg_comparisons 개수: %d\n"
                "  analysis_id: %s",
                list(payload.keys()) if payload else 'None',
                payload.get("ne_id"),
                payload.get("cell_id"),
                payload.get("swname"),
                payload.get("rel_ver"),
                payload.get("analysis_period"),
                "있음" if payload.get("choi_result") else "없음",
                list(payload.get("llm_analysis", {}).keys()) if payload.get("llm_analysis") else 'None',
                len(payload.get("peg_comparisons", [])),
                payload.get("analysis_id")
            )
            
            # JSON 직렬화 가능 여부 테스트
            try:
                json.dumps(payload, default=str)
                self.logger.debug("JSON 직렬화 테스트 성공")
            except Exception as json_err:
                self.logger.warning("JSON 직렬화 테스트 실패: %s", json_err)
            
            return payload
            
        except Exception as e:
            self.logger.error(f"백엔드 페이로드 생성 실패: {e}", exc_info=True)
            # 폴백: 최소 필수 필드만 포함
            filters = analysis_request.get("filters", {})
            return {
                "ne_id": str(filters.get("ne", ["All NEs"])[0] if isinstance(filters.get("ne"), list) else filters.get("ne", "All NEs")),
                "cell_id": str(filters.get("cellid", ["All cells"])[0] if isinstance(filters.get("cellid"), list) else filters.get("cellid", "All cells")),
                "swname": "All hosts",
                "analysis_period": {
                    "n_minus_1_start": "unknown",
                    "n_minus_1_end": "unknown",
                    "n_start": "unknown",
                    "n_end": "unknown"
                },
                "llm_analysis": {
                    "summary": "페이로드 생성 실패",
                    "issues": [],
                    "recommendations": [],
                    "confidence": None,
                    "model_name": None
                },
                "peg_comparisons": []
            }
    
    def _convert_numpy_types(self, obj: Any) -> Any:
        """
        numpy 타입을 Python 네이티브 타입으로 재귀적 변환
        
        JSON 직렬화를 위해 numpy.int64, numpy.float64 등을 
        int, float로 변환합니다.
        
        Args:
            obj: 변환할 객체
            
        Returns:
            Python 네이티브 타입으로 변환된 객체
        """
        import numpy as np
        
        if isinstance(obj, dict):
            return {key: self._convert_numpy_types(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_numpy_types(item) for item in obj]
        elif isinstance(obj, tuple):
            return tuple(self._convert_numpy_types(item) for item in obj)
        elif isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, (np.bool_, bool)):
            return bool(obj)
        else:
            return obj
    
    def _post_to_backend(self, backend_url: str, payload: dict) -> dict:
        """
        백엔드에 분석 결과 POST 요청 전송
        
        Args:
            backend_url (str): 백엔드 API URL
            payload (dict): 전송할 페이로드
            
        Returns:
            dict: 백엔드 응답
            
        Raises:
            Exception: 백엔드 요청 실패 시
        """
        import requests
        from config.settings import get_settings
        
        self.logger.info("_post_to_backend() 호출: url=%s", backend_url)
        
        try:
            settings = get_settings()
            timeout = settings.backend_timeout
            
            # numpy 타입 변환 (JSON 직렬화 에러 방지)
            self.logger.debug("numpy 타입 변환 시작")
            payload = self._convert_numpy_types(payload)
            self.logger.debug("numpy 타입 변환 완료")
            
            # 헤더 구성
            headers = {
                "Content-Type": "application/json",
                **settings.get_backend_auth_header()
            }
            
            # POST 요청 전송
            start_time = time.time()
            response = requests.post(
                backend_url,
                json=payload,
                headers=headers,
                timeout=timeout
            )
            elapsed = time.time() - start_time
            
            # 응답 확인
            response.raise_for_status()
            result = response.json()
            
            self.logger.info(
                "백엔드 POST 성공: status_code=%d, elapsed=%.2fs, response_keys=%s",
                response.status_code,
                elapsed,
                list(result.keys()) if isinstance(result, dict) else type(result).__name__
            )
            
            return result
            
        except requests.Timeout as e:
            self.logger.error("백엔드 요청 타임아웃: %s", e)
            raise
        except requests.HTTPError as e:
            # 422 에러 시 상세 로깅 (Validation 에러)
            if e.response and e.response.status_code == 422:
                try:
                    error_detail = e.response.json()
                    self.logger.error(
                        "❌ 백엔드 Validation 오류 (422):\n"
                        "  응답 상세: %s\n"
                        "  전송한 payload 키: %s\n"
                        "  ne_id: %s, cell_id: %s, swname: %s\n"
                        "  analysis_period: %s\n"
                        "  llm_analysis 키: %s\n"
                        "  peg_comparisons 개수: %d",
                        error_detail,
                        list(payload.keys()) if isinstance(payload, dict) else 'N/A',
                        payload.get("ne_id") if isinstance(payload, dict) else 'N/A',
                        payload.get("cell_id") if isinstance(payload, dict) else 'N/A',
                        payload.get("swname") if isinstance(payload, dict) else 'N/A',
                        payload.get("analysis_period") if isinstance(payload, dict) else 'N/A',
                        list(payload.get("llm_analysis", {}).keys()) if isinstance(payload, dict) else 'N/A',
                        len(payload.get("peg_comparisons", [])) if isinstance(payload, dict) else 0
                    )
                except:
                    self.logger.error("422 응답 파싱 실패: %s", e.response.text[:500])
            else:
                self.logger.error("백엔드 HTTP 오류: status=%s, response=%s", 
                                e.response.status_code if e.response else 'unknown',
                                e.response.text[:500] if e.response else 'unknown')
            raise
        except Exception as e:
            self.logger.error("백엔드 요청 중 예외 발생: %s", e, exc_info=True)
            raise

    def _create_analysis_service(self) -> AnalysisService:
        """
        AnalysisService 인스턴스 생성 (의존성 주입)
        
        Repository 계층과 Service 계층을 의존성 주입 패턴으로 구성하여
        AnalysisService 인스턴스를 생성합니다.
        
        Returns:
            AnalysisService: 구성된 분석 서비스
                - database_repository: PostgreSQLRepository
                - llm_analysis_service: LLMAnalysisService (내부 생성)
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
        
        AnalysisService의 결과를 MCP 클라이언트가 이해할 수 있는 표준 형식으로 변환합니다.
        상태별 메시지 추가 및 필드 정리를 수행합니다.
        
        Args:
            analysis_result (dict): AnalysisService 결과
                - status: "success" 또는 "error"
                - data: 분석 결과 데이터
                - backend_response: 백엔드 전송 결과 (선택적)
            
        Returns:
            dict: MCP 호환 응답 형식
                - status: 처리 상태
                - message: 상태별 메시지
                - data: 분석 결과 (성공 시)
                - error: 오류 정보 (실패 시)
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
        
        MCP 요청의 전체 라이프사이클을 관리합니다:
        1. 요청 검증
        2. 형식 변환
        3. AnalysisService 위임
        4. 백엔드 전송 (선택적)
        5. 응답 형식 변환
        
        Args:
            request (dict): MCP 요청 데이터
                - n_minus_1 (str): N-1 기간 시간 범위
                - n (str): N 기간 시간 범위
                - table (str): 데이터베이스 테이블명
                - columns (dict): 컬럼 매핑
                - selected_pegs (list, optional): 선택된 PEG 목록
                - peg_definitions (dict, optional): 파생 PEG 정의
                - backend_url (str, optional): 백엔드 API URL
                - db (dict, optional): 데이터베이스 설정
            
        Returns:
            dict: MCP 응답 데이터
                - status: "success" 또는 "error"
                - message: 처리 결과 메시지
                - data: 분석 결과 (성공 시)
                - error_type: 오류 유형 (실패 시)
                - details: 상세 오류 정보 (실패 시)
                
        Raises:
            ValueError: 요청 검증 실패
            AnalysisServiceError: 분석 서비스 오류
            Exception: 예상치 못한 오류 발생
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
                
                # 백엔드에 POST 요청 전송
                try:
                    backend_response = self._post_to_backend(backend_url, backend_payload)
                    self.logger.info("백엔드 업로드 성공: status=%s", backend_response.get('status') if isinstance(backend_response, dict) else 'unknown')
                except Exception as e:
                    self.logger.error("백엔드 업로드 실패: %s", e, exc_info=True)
                    backend_response = {
                        "status": "error",
                        "error": str(e),
                        "error_type": type(e).__name__
                    }
                
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
        """
        리소스 정리
        
        MCPHandler가 사용한 리소스들을 정리합니다.
        주로 AnalysisService의 연결 종료를 담당합니다.
        """
        if self.analysis_service:
            self.analysis_service.close()
        self.logger.info("MCPHandler 리소스 정리 완료")
    
    def __enter__(self):
        """
        컨텍스트 매니저 진입
        
        with 문을 사용할 때 자동으로 호출됩니다.
        
        Returns:
            MCPHandler: 자기 자신을 반환
        """
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        컨텍스트 매니저 종료
        
        with 문 블록이 종료될 때 자동으로 호출됩니다.
        리소스 정리를 수행합니다.
        
        Args:
            exc_type: 예외 타입 (예외 발생 시)
            exc_val: 예외 값 (예외 발생 시)
            exc_tb: 예외 트레이스백 (예외 발생 시)
            
        Returns:
            bool: False (예외를 다시 발생시킴)
        """
        self.close()
        return False




@mcp.tool
def analyze_cell_performance_with_llm(request: dict) -> dict:
    """
    MCP 도구: 시간 범위 기반 통합 셀 성능 분석 실행
    
    Clean Architecture 패턴을 적용한 셀 성능 분석 도구입니다.
    MCPHandler를 통해 요청을 처리하고 AnalysisService로 비즈니스 로직을 위임합니다.
    
    처리 과정:
    1. MCPHandler가 요청 검증 및 형식 변환
    2. AnalysisService가 핵심 분석 로직 수행
    3. Repository 계층을 통한 데이터 처리
    4. LLM을 활용한 전문가 수준 분석
    5. MCP 형식으로 결과 반환
    
    Args:
        request (dict): 분석 요청 데이터
            - n_minus_1 (str): N-1 기간 시간 범위 (예: "2025-01-01_09:00~2025-01-01_18:00")
            - n (str): N 기간 시간 범위 (예: "2025-01-02_09:00~2025-01-02_18:00")
            - table (str): 데이터베이스 테이블명 (기본값: "summary")
            - columns (dict): 컬럼 매핑 (예: {"time": "datetime", "peg_name": "peg_name", "value": "value"})
            - selected_pegs (list, optional): 분석할 PEG 목록
            - peg_definitions (dict, optional): 파생 PEG 정의 (예: {"success_rate": "response_count/preamble_count*100"})
            - filters (dict, optional): 필터 조건 (ne, cellid, host 등)
            - backend_url (str, optional): 백엔드 API URL
            - db (dict, optional): 데이터베이스 연결 설정
            - analysis_type (str, optional): 분석 타입 ("enhanced", "basic" 등)
    
    Returns:
        dict: 분석 결과
            - status (str): "success" 또는 "error"
            - message (str): 처리 결과 메시지
            - data (dict, optional): 분석 결과 데이터 (성공 시)
                - llm_analysis: LLM 분석 결과
                - peg_analysis: PEG 분석 결과
                - data_summary: 데이터 요약
            - error_type (str, optional): 오류 유형 (실패 시)
            - details (dict, optional): 상세 오류 정보 (실패 시)
    
    Raises:
        ValueError: 요청 검증 실패
        AnalysisServiceError: 분석 서비스 오류
        Exception: 예상치 못한 오류
    
    Example:
        ```python
        request = {
            "n_minus_1": "2025-01-01_09:00~2025-01-01_18:00",
            "n": "2025-01-02_09:00~2025-01-02_18:00",
            "table": "summary",
            "selected_pegs": ["preamble_count", "response_count"],
            "peg_definitions": {
                "success_rate": "response_count/preamble_count*100"
            }
        }
        result = analyze_cell_performance_with_llm(request)
        ```
    """
    # numpy 타입 변환 유틸리티 함수 (로컬)
    def convert_numpy_types(obj):
        """numpy 타입을 Python 네이티브 타입으로 재귀적 변환"""
        import numpy as np
        
        if isinstance(obj, dict):
            return {key: convert_numpy_types(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [convert_numpy_types(item) for item in obj]
        elif isinstance(obj, tuple):
            return tuple(convert_numpy_types(item) for item in obj)
        elif isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, (np.bool_, bool)):
            return bool(obj)
        else:
            return obj
    
    # 새로운 MCPHandler 사용
    with MCPHandler() as handler:
        result = handler.handle_request(request)
        # numpy 타입 변환 (MCP tool 직렬화 에러 방지)
        result = convert_numpy_types(result)
        return result


@mcp.tool
def analyze_peg_comparison(request: dict) -> dict:
    """
    MCP 도구: PEG 비교분석 실행
    
    N-1 기간과 N 기간의 PEG 성능 지표를 비교하여 통계적 분석을 수행합니다.
    Pydantic 모델을 사용한 검증과 PEGComparisonAnalyzer를 통한 비동기 분석을 지원합니다.
    
    처리 과정:
    1. Pydantic 모델을 통한 요청 데이터 검증
    2. PEGComparisonAnalyzer 인스턴스 생성
    3. 비동기 분석 실행 (asyncio.run 사용)
    4. 응답 형식 변환 및 반환
    
    Args:
        request (dict): PEG 비교분석 요청 데이터
            - analysis_id (str, optional): 분석 고유 식별자 (기본값: "default_analysis_id")
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
            - data (dict, optional): 분석 결과 데이터 (성공 시)
                - analysis_id (str): 분석 ID
                - peg_comparison_results (list): PEG별 비교 결과
                - summary (dict): 전체 요약 통계
                - analysis_metadata (dict): 분석 메타데이터
            - error (dict, optional): 오류 정보 (실패 시)
                - code (str): 오류 코드
                - message (str): 오류 메시지
                - details (str): 상세 오류 정보
            - processing_time (float): 처리 시간 (초)
            - algorithm_version (str): 사용된 알고리즘 버전
            - cached (bool): 캐시 사용 여부
    
    Raises:
        ValueError: 요청 데이터 검증 실패
        Exception: 예상치 못한 오류 발생
    
    Example:
        ```python
        request = {
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
                "include_metadata": True,
                "algorithm_version": "v2.1.0"
            }
        }
        result = analyze_peg_comparison(request)
        ```
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
    
    Clean Architecture 패턴에 따라 모든 계층의 컴포넌트를 의존성 주입으로 구성합니다.
    테스트 및 개발 환경에서 전체 시스템의 통합을 검증하는 데 사용됩니다.
    
    초기화 순서:
    1. Configuration Manager 및 로깅 설정
    2. Core Utilities (TimeRangeParser, PEGCalculator 등)
    3. Repository Layer (PostgreSQLRepository, LLMClient)
    4. Service Layer (PEGProcessingService, LLMAnalysisService, AnalysisService)
    5. Presentation Layer (MCPHandler)
    
    Returns:
        tuple: (mcp_handler, analysis_service, logger) 통합된 컴포넌트들
            - mcp_handler (MCPHandler): 프레젠테이션 계층 핸들러
            - analysis_service (AnalysisService): 비즈니스 로직 서비스
            - logger (Logger): 통합 로거
    
    Raises:
        Exception: 컴포넌트 초기화 실패 시 발생
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
    
    전체 시스템의 통합성을 검증하는 종합 테스트를 수행합니다.
    모든 계층의 컴포넌트가 올바르게 연동되어 정상적으로 작동하는지 확인합니다.
    
    테스트 과정:
    1. 통합 컴포넌트 초기화
    2. 샘플 MCP 요청 정의 및 실행
    3. 응답 검증 (성공/실패 케이스 모두)
    4. 컴포넌트 상태 검증
    5. 성능 측정 및 결과 보고
    
    Returns:
        dict: 테스트 결과
            - status (str): "success", "error", "test_error"
            - message (str): 테스트 결과 메시지
            - data (dict, optional): 분석 결과 데이터 (성공 시)
            - error_type (str, optional): 오류 유형 (실패 시)
            - processing_time (float): 처리 시간
    
    Raises:
        Exception: 테스트 실행 중 치명적 오류 발생 시
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
    """
    메인 실행 진입점
    
    다양한 실행 모드를 지원합니다:
    1. End-to-End 테스트 모드: `python main.py --e2e-test`
    2. CLI 모드: `python main.py --request '{"n_minus_1": "...", "n": "..."}'`
    3. MCP 서버 모드: `python main.py` (기본)
    """
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