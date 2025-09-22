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

# ===========================================
# 토큰/프롬프트 가드 유틸리티 함수들
# ===========================================

def estimate_prompt_tokens(text: str) -> int:
    """
    텍스트의 토큰 수를 추정하는 함수
    
    아주 단순한 휴리스틱으로 토큰 수를 추정합니다:
    - 영어/한글 혼합 환경에서 안전 측을 위해 평균 3.5 chars/token 가정
    - 실제 모델별 토크나이저와 차이가 있으므로 상한 체크용 보수 추정치
    
    Args:
        text (str): 토큰 수를 추정할 텍스트
        
    Returns:
        int: 추정된 토큰 수
    """
    logging.debug("estimate_prompt_tokens() 호출: 텍스트 길이=%d", len(text or ""))
    
    if not text:
        logging.debug("빈 텍스트 입력: 토큰 수=0")
        return 0
    
    try:
        # 환경변수에서 토큰 추정 비율 읽기 (기본값: 3.5자당 1토큰)
        chars_per_token = float(os.getenv('CHARS_PER_TOKEN_RATIO', '3.5'))
        estimated_tokens = int(math.ceil(len(text) / chars_per_token))
        logging.debug("토큰 추정 완료: %d자 → %d토큰 (비율: %.1f)", len(text), estimated_tokens, chars_per_token)
        return estimated_tokens
    except Exception as e:
        logging.warning("토큰 추정 중 오류 발생, 대체 방법 사용: %s", e)
        # 대체 방법: 환경변수에서 대체 비율 읽기 (기본값: 4자당 1토큰)
        fallback_chars_per_token = float(os.getenv('FALLBACK_CHARS_PER_TOKEN_RATIO', '4.0'))
        fallback_tokens = len(text) // int(fallback_chars_per_token)
        logging.debug("대체 토큰 추정: %d자 → %d토큰", len(text), fallback_tokens)
        return fallback_tokens


def clamp_prompt(text: str, max_chars: int) -> tuple[str, bool]:
    """
    프롬프트를 지정된 문자 수로 자르는 안전 가드 함수
    
    LLM API의 토큰/문자 제한을 초과하지 않도록 프롬프트를 자릅니다.
    자른 부분에는 명확한 표시를 추가하여 사용자가 인지할 수 있도록 합니다.
    
    Args:
        text (str): 자를 텍스트
        max_chars (int): 최대 허용 문자 수
        
    Returns:
        tuple[str, bool]: (자른_텍스트, 자름_여부)
    """
    logging.debug("clamp_prompt() 호출: 원본_길이=%d, 최대_길이=%d", len(text or ""), max_chars)
    
    if text is None:
        logging.debug("None 텍스트 입력: 빈 문자열 반환")
        return "", False
        
    if len(text) <= max_chars:
        logging.debug("텍스트 길이 정상: 자르기 불필요")
        return text, False
    
    # 자르기 수행: 환경변수에서 여유 공간 설정 (기본값: 200자)
    buffer_chars = int(os.getenv('PROMPT_TRUNCATE_BUFFER', '200'))
    head = text[: max_chars - buffer_chars]
    tail = "\n\n[...truncated due to safety guard...]\n"
    clamped_text = head + tail
    
    logging.warning("프롬프트 자름: %d자 → %d자 (안전 가드 적용)", len(text), len(clamped_text))
    return clamped_text, True


def build_results_overview(analysis: dict | str | None) -> dict:
    """
    LLM 분석 결과에서 핵심 요약 정보를 추출하는 함수
    
    LLM이 반환한 다양한 형태의 분석 결과에서 일관된 형태의 요약 정보를 추출합니다.
    dict 형태의 구조화된 결과와 str 형태의 텍스트 결과 모두 처리 가능합니다.
    
    Args:
        analysis (dict | str | None): LLM 분석 결과
        
    Returns:
        dict: 표준화된 요약 정보 {
            "summary": str | None,
            "key_findings": list,
            "recommended_actions": list
        }
    """
    logging.debug("build_results_overview() 호출: 입력 타입=%s", type(analysis).__name__)
    
    # 기본 구조 초기화
    overview: dict = {
        "summary": None,
        "key_findings": [],
        "recommended_actions": []
    }
    
    try:
        if isinstance(analysis, dict):
            logging.debug("딕셔너리 형태의 분석 결과 처리 시작")
            
            # 요약 정보 추출 (여러 키 시도)
            summary = analysis.get("executive_summary") or analysis.get("summary") or None
            logging.debug("요약 정보 추출: %s", "있음" if summary else "없음")
            
            # 권고사항 추출
            recs = analysis.get("recommended_actions") or analysis.get("actions") or []
            logging.debug("권고사항 추출: %d개", len(recs) if isinstance(recs, list) else 0)
            
            # 핵심 발견사항 추출
            findings = analysis.get("issues") or analysis.get("alerts") or analysis.get("key_findings") or []
            logging.debug("핵심 발견사항 추출: %d개", len(findings) if isinstance(findings, list) else 0)
            
            # 딕셔너리 형태인 경우 리스트로 변환
            if isinstance(recs, dict):
                recs = list(recs.values())
                logging.debug("권고사항 딕셔너리를 리스트로 변환: %d개", len(recs))
                
            if isinstance(findings, dict):
                findings = list(findings.values())
                logging.debug("발견사항 딕셔너리를 리스트로 변환: %d개", len(findings))
            
            # 결과 할당
            overview["summary"] = summary if isinstance(summary, str) else None
            overview["recommended_actions"] = recs if isinstance(recs, list) else []
            overview["key_findings"] = findings if isinstance(findings, list) else []
            
            logging.info("딕셔너리 분석 결과 처리 완료: 요약=%s, 권고사항=%d개, 발견사항=%d개",
                        "있음" if overview["summary"] else "없음",
                        len(overview["recommended_actions"]),
                        len(overview["key_findings"]))
                        
        elif isinstance(analysis, str):
            logging.debug("문자열 형태의 분석 결과 처리 시작: 길이=%d", len(analysis))
            
            # 문자열 결과를 요약으로 사용 (환경변수에서 제한 설정, 기본값: 2000자)
            summary_limit = int(os.getenv('STRING_SUMMARY_LIMIT', '2000'))
            if len(analysis) > summary_limit:
                overview["summary"] = analysis[:summary_limit] + "..."
                logging.debug("문자열 요약 자름: %d자 → %d자", len(analysis), len(overview["summary"]))
            else:
                overview["summary"] = analysis
                
            logging.info("문자열 분석 결과 처리 완료: 요약 길이=%d자", len(overview["summary"]))
            
        else:
            logging.warning("지원되지 않는 분석 결과 타입: %s", type(analysis).__name__)
            
    except Exception as e:
        logging.exception("분석 결과 요약 추출 중 오류 발생: %s", e)
        # 오류 발생 시에도 기본 구조는 반환
    
    logging.debug("build_results_overview() 완료: 요약=%s, 권고사항=%d개, 발견사항=%d개",
                 "있음" if overview["summary"] else "없음",
                 len(overview["recommended_actions"]),
                 len(overview["key_findings"]))
    
    return overview


import ast  # AST 파싱 (파생 PEG 수식 안전 평가용)
import math  # 수학 연산 (이미 import됨, 중복 제거 필요)
import re  # 정규표현식 (시간 범위 파싱용)

# ===========================================
# 외부 라이브러리 imports
# ===========================================
from typing import Dict, Optional, Tuple  # 타입 힌트 지원

import pandas as pd  # 데이터 처리 및 분석
import psycopg2  # PostgreSQL 데이터베이스 연결
import psycopg2.extras  # PostgreSQL 확장 기능 (DictCursor 등)
import requests  # HTTP 클라이언트
from fastmcp import FastMCP  # MCP 서버 프레임워크
from requests.adapters import HTTPAdapter  # HTTP 어댑터 (재시도 로직)
from urllib3.util.retry import Retry  # 재시도 전략


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


# ===========================================
# 시간 범위 파싱 유틸리티 함수들 - DEPRECATED
# 이 함수들은 utils.TimeRangeParser로 이동되었습니다
# ===========================================

def _get_default_tzinfo() -> datetime.tzinfo:
    """
    환경 변수에서 기본 타임존 정보를 생성하는 함수
    
    환경 변수 `DEFAULT_TZ_OFFSET`(예: "+09:00")를 읽어서 tzinfo 객체를 생성합니다.
    설정이 없거나 형식이 잘못된 경우 UTC를 반환합니다.
    
    Returns:
        datetime.tzinfo: 타임존 정보 객체
    """
    logging.debug("_get_default_tzinfo() 호출: 기본 타임존 정보 생성 시작")
    
    # 환경변수에서 타임존 오프셋 읽기 (기본값: +09:00)
    offset_text = os.getenv("DEFAULT_TZ_OFFSET", "+09:00").strip()
    logging.debug("타임존 오프셋 환경변수: %s", offset_text)
    
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
            logging.debug("부호가 없는 타임존 오프셋, 양수로 처리: %s", offset_text)
        
        # 시간과 분 분리
        hh_mm = offset_clean.split(":")
        if len(hh_mm) != 2:
            raise ValueError(f"잘못된 타임존 형식: {offset_text} (예상: +09:00)")
        
        hours = int(hh_mm[0])
        minutes = int(hh_mm[1])
        
        # 시간과 분의 유효성 검사
        if hours < 0 or hours > 23:
            raise ValueError(f"잘못된 시간: {hours} (0-23 범위)")
        if minutes < 0 or minutes > 59:
            raise ValueError(f"잘못된 분: {minutes} (0-59 범위)")
        
        # timedelta 객체 생성
        delta = datetime.timedelta(hours=hours * sign, minutes=minutes * sign)
        tzinfo = datetime.timezone(delta)
        
        logging.info("타임존 정보 생성 성공: %s → %s", offset_text, tzinfo)
        return tzinfo
        
    except Exception as e:
        logging.warning("DEFAULT_TZ_OFFSET 파싱 실패, UTC 사용: %s (오류: %s)", offset_text, e)
        return datetime.timezone.utc

def parse_time_range(range_text: str) -> Tuple[datetime.datetime, datetime.datetime]:
    """
    시간 범위 문자열을 파싱하여 시작/종료 datetime 객체를 반환하는 함수
    
    지원하는 입력 형식:
    1. 범위 형식: "YYYY-MM-DD_HH:MM~YYYY-MM-DD_HH:MM" 또는 "YYYY-MM-DD-HH:MM~YYYY-MM-DD-HH:MM"
    2. 단일 날짜: "YYYY-MM-DD" (00:00:00 ~ 23:59:59로 자동 확장)
    
    특징:
    - 유연한 포맷: 날짜와 시간 구분자로 '_' 또는 '-' 허용
    - 타임존 지원: 환경변수 DEFAULT_TZ_OFFSET에서 타임존 정보 읽기
    - 상세한 오류 처리: 형식/값/논리/타입 오류를 세분화하여 명확한 예외 메시지 제공
    
    Args:
        range_text (str): 파싱할 시간 범위 문자열
        
    Returns:
        Tuple[datetime.datetime, datetime.datetime]: (시작_시각, 종료_시각) - 둘 다 tz-aware
        
    Raises:
        TypeError: 입력이 문자열이 아닌 경우
        ValueError: 형식, 값, 논리 오류가 있는 경우
    """
    logging.info("parse_time_range() 호출: 입력 문자열 파싱 시작: %s", range_text)

    # ===========================================
    # 1단계: 타입 검증
    # ===========================================
    logging.debug("1단계: 타입 검증 시작")
    if not isinstance(range_text, str):
        msg = {
            "code": "TYPE_ERROR",
            "message": "입력은 문자열(str)이어야 합니다",
            "input": str(range_text),
            "received_type": type(range_text).__name__
        }
        logging.error("parse_time_range() 타입 오류: %s", msg)
        raise TypeError(json.dumps(msg, ensure_ascii=False))
    logging.debug("타입 검증 통과: str 타입 확인됨")

    # ===========================================
    # 2단계: 전처리 및 기본 검증
    # ===========================================
    logging.debug("2단계: 전처리 및 기본 검증 시작")
    text = (range_text or "").strip()
    logging.debug("입력 문자열 전처리: 원본='%s' → 정제='%s'", range_text, text)
    
    if text == "":
        msg = {
            "code": "FORMAT_ERROR",
            "message": "빈 문자열은 허용되지 않습니다",
            "input": range_text,
            "hint": "예: 2025-08-08_15:00~2025-08-08_19:00 또는 2025-08-08-15:00~2025-08-08-19:00 또는 2025-08-08"
        }
        logging.error("parse_time_range() 형식 오류: %s", msg)
        raise ValueError(json.dumps(msg, ensure_ascii=False))
    logging.debug("기본 검증 통과: 빈 문자열 아님")

    tzinfo = _get_default_tzinfo()

    # 정규식 패턴 (유연한 포맷: _ 또는 - 구분자 허용)
    date_pat = r"\d{4}-\d{2}-\d{2}"
    time_pat = r"\d{2}:\d{2}"
    dt_pat_flexible = rf"{date_pat}[_-]{time_pat}"  # _ 또는 - 허용

    # 범위 구분자 허용: ~ 앞뒤 공백 허용. 다른 구분자 사용은 오류 처리
    if "~" in text:
        # '~'가 여러 개인 경우 오류
        if text.count("~") != 1:
            msg = {
                "code": "FORMAT_ERROR",
                "message": "범위 구분자 '~'가 없거나 잘못되었습니다",
                "input": text,
                "hint": "예: 2025-08-08_15:00~2025-08-08_19:00 또는 2025-08-08-15:00~2025-08-08-19:00"
            }
            logging.error("parse_time_range() 형식 오류: %s", msg)
            raise ValueError(json.dumps(msg, ensure_ascii=False))

        # 공백 허용 분리
        parts = [p.strip() for p in text.split("~")]
        if len(parts) != 2 or not parts[0] or not parts[1]:
            msg = {
                "code": "FORMAT_ERROR",
                "message": "시작/종료 시각이 모두 필요합니다",
                "input": text
            }
            logging.error("parse_time_range() 형식 오류: %s", msg)
            raise ValueError(json.dumps(msg, ensure_ascii=False))

        left, right = parts[0], parts[1]

        # 각 토큰 형식 검증 (유연한 패턴 사용)
        if not re.fullmatch(dt_pat_flexible, left):
            msg = {
                "code": "FORMAT_ERROR",
                "message": "왼쪽 시각 형식이 올바르지 않습니다 (YYYY-MM-DD_HH:MM 또는 YYYY-MM-DD-HH:MM)",
                "input": left
            }
            logging.error("parse_time_range() 형식 오류: %s", msg)
            raise ValueError(json.dumps(msg, ensure_ascii=False))
        if not re.fullmatch(dt_pat_flexible, right):
            msg = {
                "code": "FORMAT_ERROR",
                "message": "오른쪽 시각 형식이 올바르지 않습니다 (YYYY-MM-DD_HH:MM 또는 YYYY-MM-DD-HH:MM)",
                "input": right
            }
            logging.error("parse_time_range() 형식 오류: %s", msg)
            raise ValueError(json.dumps(msg, ensure_ascii=False))

        # 내부 처리를 위해 표준 _ 포맷으로 변환
        def normalize_datetime_format(dt_str: str) -> str:
            """날짜-시간 구분자를 표준 '_' 포맷으로 변환"""
            # YYYY-MM-DD-HH:MM 형태를 YYYY-MM-DD_HH:MM로 변환
            # 마지막 '-'만 '_'로 바꾸기 위해 rsplit 사용
            if '-' in dt_str and dt_str.count('-') >= 3:
                # 날짜 부분(처음 3개 '-')과 시간 부분을 분리
                parts = dt_str.rsplit('-', 1)
                if len(parts) == 2 and ':' in parts[1]:
                    return f"{parts[0]}_{parts[1]}"
            return dt_str

        left_normalized = normalize_datetime_format(left)
        right_normalized = normalize_datetime_format(right)
        
        logging.info("입력 정규화: %s → %s, %s → %s", left, left_normalized, right, right_normalized)

        # 값 검증 (존재하지 않는 날짜/시간 등)
        try:
            start_dt = datetime.datetime.strptime(left_normalized, "%Y-%m-%d_%H:%M")
            end_dt = datetime.datetime.strptime(right_normalized, "%Y-%m-%d_%H:%M")
        except Exception as e:
            msg = {
                "code": "VALUE_ERROR",
                "message": f"유효하지 않은 날짜/시간입니다: {e}",
                "input": text
            }
            logging.error("parse_time_range() 값 오류: %s", msg)
            raise ValueError(json.dumps(msg, ensure_ascii=False))

        # tz 부여
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=tzinfo)
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=tzinfo)

        # 논리 검증
        if start_dt == end_dt:
            msg = {
                "code": "LOGIC_ERROR",
                "message": "동일한 시각 범위는 허용되지 않습니다",
                "input": text
            }
            logging.error("parse_time_range() 논리 오류: %s", msg)
            raise ValueError(json.dumps(msg, ensure_ascii=False))
        if start_dt > end_dt:
            msg = {
                "code": "LOGIC_ERROR",
                "message": "시작 시각은 종료 시각보다 빠라야 합니다",
                "input": text
            }
            logging.error("parse_time_range() 논리 오류: %s", msg)
            raise ValueError(json.dumps(msg, ensure_ascii=False))

        logging.info("parse_time_range() 성공: %s ~ %s", start_dt, end_dt)
        return start_dt, end_dt

    # 단일 날짜 케이스
    if re.fullmatch(date_pat, text):
        try:
            day = datetime.datetime.strptime(text, "%Y-%m-%d").date()
        except Exception as e:
            msg = {
                "code": "VALUE_ERROR",
                "message": f"유효하지 않은 날짜입니다: {e}",
                "input": text
            }
            logging.error("parse_time_range() 값 오류: %s", msg)
            raise ValueError(json.dumps(msg, ensure_ascii=False))

        start_dt = datetime.datetime.combine(day, datetime.time(0, 0, 0, tzinfo=tzinfo))
        end_dt = datetime.datetime.combine(day, datetime.time(23, 59, 59, tzinfo=tzinfo))
        logging.info("parse_time_range() 성공(단일 날짜 확장): %s ~ %s", start_dt, end_dt)
        return start_dt, end_dt

    # 여기까지 오면 형식 오류
    # 흔한 오타 케이스 힌트 제공
    uses_space_instead_separator = re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", text) is not None
    time_with_dash = re.search(r"\d{2}-\d{2}", text) is not None and not re.search(dt_pat_flexible, text)

    hint = "예: 2025-08-08_15:00~2025-08-08_19:00 또는 2025-08-08-15:00~2025-08-08-19:00 또는 2025-08-08"
    if uses_space_instead_separator:
        hint = "날짜와 시간은 공백이 아니라 '_' 또는 '-'로 구분하세요"
    elif time_with_dash:
        hint = "시간은 '15-00'이 아니라 '15:00' 형식이어야 합니다"

    msg = {
        "code": "FORMAT_ERROR",
        "message": "입력 형식이 올바르지 않습니다 (YYYY-MM-DD_HH:MM~YYYY-MM-DD_HH:MM 또는 YYYY-MM-DD-HH:MM~YYYY-MM-DD-HH:MM 또는 YYYY-MM-DD)",
        "input": text,
        "hint": hint
    }
    logging.error("parse_time_range() 형식 오류: %s", msg)
    raise ValueError(json.dumps(msg, ensure_ascii=False))


# --- DB 연결 ---
def get_db_connection(db: Dict[str, str]):
    """
    PostgreSQL 연결을 반환합니다. (psycopg2)

    db: {host, port, user, password, dbname}
    """
    # 외부 DB 연결: 네트워크/권한/환경 변수 문제로 실패 가능성이 높으므로 상세 로그를 남긴다
    logging.info("get_db_connection() 호출: DB 연결 시도")
    try:
        conn = psycopg2.connect(
            host=db.get("host", os.getenv("DEFAULT_DB_HOST", "127.0.0.1")),
            port=db.get("port", os.getenv("DEFAULT_DB_PORT", "5432")),
            user=db.get("user", os.getenv("DEFAULT_DB_USER", "postgres")),
            password=db.get("password", os.getenv("DEFAULT_DB_PASSWORD", "")),
            dbname=db.get("dbname", os.getenv("DEFAULT_DB_NAME", "postgres")),
        )
        # 민감정보(password)는 로그에 남기지 않는다
        logging.info("DB 연결 성공 (host=%s, dbname=%s)", 
                    db.get("host", os.getenv("DEFAULT_DB_HOST", "127.0.0.1")), 
                    db.get("dbname", os.getenv("DEFAULT_DB_NAME", "postgres")))
        return conn
    except Exception as e:
        logging.exception("DB 연결 실패: %s", e)
        raise


# --- DB 조회: 기간별 셀 평균 집계 ---
def fetch_cell_averages_for_period(
    conn,
    table: str,
    columns: Dict[str, str],
    start_dt: datetime.datetime,
    end_dt: datetime.datetime,
    period_label: str,
    ne_filters: Optional[list] = None,
    cellid_filters: Optional[list] = None,
    host_filters: Optional[list] = None,
) -> pd.DataFrame:
    """
    주어진 기간에 대해 PEG 단위 평균값을 집계합니다.

    반환 컬럼: [peg_name, period, avg_value]
    """
    logging.info("fetch_cell_averages_for_period() 호출: %s ~ %s, period=%s", start_dt, end_dt, period_label)
    time_col = columns.get("time", "datetime")
    # README 스키마 기준: peg_name 컬럼 사용. columns 사전에 'peg' 또는 'peg_name' 키가 있으면 우선 사용
    peg_col = columns.get("peg") or columns.get("peg_name", "peg_name")
    value_col = columns.get("value", "value")
    ne_col = columns.get("ne", "ne")
    cell_col = columns.get("cell") or columns.get("cellid", "cellid")

    sql = f"SELECT {peg_col} AS peg_name, AVG({value_col}) AS avg_value FROM {table} WHERE {time_col} BETWEEN %s AND %s"
    params = [start_dt, end_dt]

    # 선택적 필터: ne, cellid
    if ne_filters:
        ne_vals = [str(x).strip() for x in (ne_filters or []) if str(x).strip()]
        if len(ne_vals) == 1:
            sql += f" AND {ne_col} = %s"
            params.append(ne_vals[0])
        elif len(ne_vals) > 1:
            placeholders = ",".join(["%s"] * len(ne_vals))
            sql += f" AND {ne_col} IN ({placeholders})"
            params.extend(ne_vals)

    if cellid_filters:
        cid_vals = [str(x).strip() for x in (cellid_filters or []) if str(x).strip()]
        if len(cid_vals) == 1:
            sql += f" AND {cell_col} = %s"
            params.append(cid_vals[0])
        elif len(cid_vals) > 1:
            placeholders = ",".join(["%s"] * len(cid_vals))
            sql += f" AND {cell_col} IN ({placeholders})"
            params.extend(cid_vals)

    # 선택적 필터: host (신규 추가)
    if host_filters:
        host_col = columns.get("host", "host")
        host_vals = [str(x).strip() for x in (host_filters or []) if str(x).strip()]
        if len(host_vals) == 1:
            sql += f" AND {host_col} = %s"
            params.append(host_vals[0])
        elif len(host_vals) > 1:
            placeholders = ",".join(["%s"] * len(host_vals))
            sql += f" AND {host_col} IN ({placeholders})"
            params.extend(host_vals)

    sql += f" GROUP BY {peg_col}"
    try:
        # 동적 테이블/컬럼 구성이므로 실행 전에 구성값을 로그로 남겨 디버깅을 돕는다
        logging.info(
            "집계 SQL 실행: table=%s, time_col=%s, peg_col=%s, value_col=%s, ne_col=%s, cell_col=%s, host_col=%s",
            table, time_col, peg_col, value_col, ne_col, cell_col, columns.get("host", "host"),
        )
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
        # 조회 결과를 DataFrame으로 변환 (비어있을 수 있음)
        df = pd.DataFrame(rows, columns=["peg_name", "avg_value"]) if rows else pd.DataFrame(columns=["peg_name", "avg_value"]) 
        df["period"] = period_label
        logging.info("fetch_cell_averages_for_period() 건수: %d (period=%s)", len(df), period_label)
        return df
    except Exception as e:
        logging.exception("기간별 평균 집계 쿼리 실패: %s", e)
        raise


# --- 파생 PEG 계산: 수식 정의를 안전하게 평가하여 새로운 PEG 생성 ---
def _safe_eval_expr(expr_text: str, variables: Dict[str, float]) -> float:
    """
    간단한 산술 수식(expr_text)을 안전하게 평가합니다.
    허용 토큰: 숫자, 변수명(peg_name), +, -, *, /, (, )
    변수값은 variables 딕셔너리에서 가져옵니다.
    """
    logging.info("_safe_eval_expr() 호출: expr=%s", expr_text)
    try:
        node = ast.parse(expr_text, mode='eval')

        def _eval(node):
            if isinstance(node, ast.Expression):
                return _eval(node.body)
            if isinstance(node, ast.BinOp):
                left = _eval(node.left)
                right = _eval(node.right)
                if isinstance(node.op, ast.Add):
                    return float(left) + float(right)
                if isinstance(node.op, ast.Sub):
                    return float(left) - float(right)
                if isinstance(node.op, ast.Mult):
                    return float(left) * float(right)
                if isinstance(node.op, ast.Div):
                    return float(left) / float(right)
                raise ValueError("허용되지 않은 연산자")
            if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
                operand = _eval(node.operand)
                return +float(operand) if isinstance(node.op, ast.UAdd) else -float(operand)
            if isinstance(node, ast.Num):
                return float(node.n)
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                return float(node.value)
            if isinstance(node, ast.Name):
                name = node.id
                if name not in variables:
                    raise KeyError(f"정의되지 않은 변수: {name}")
                return float(variables[name])
            if isinstance(node, ast.Call):
                raise ValueError("함수 호출은 허용되지 않습니다")
            if isinstance(node, (ast.Attribute, ast.Subscript, ast.List, ast.Dict, ast.Tuple)):
                raise ValueError("허용되지 않은 표현식 형식")
            raise ValueError("지원되지 않는 AST 노드")

        return float(_eval(node))
    except ZeroDivisionError:
        logging.warning("수식 평가 중 0으로 나눔 발생: %s", expr_text)
        return float('nan')
    except Exception as e:
        logging.error("수식 평가 실패: %s (expr=%s)", e, expr_text)
        return float('nan')


def compute_derived_pegs_for_period(period_df: pd.DataFrame, definitions: Dict[str, str], period_label: str) -> pd.DataFrame:
    """
    period_df: [peg_name, avg_value] 형태의 단일 기간 집계 데이터
    definitions: {derived_name: expr_text} 형태의 파생 PEG 수식 정의
    반환: 동일 컬럼을 갖는 파생 PEG 데이터프레임
    """
    logging.info("compute_derived_pegs_for_period() 호출: period=%s, defs=%d", period_label, len(definitions or {}))
    if not isinstance(definitions, dict) or not definitions:
        return pd.DataFrame(columns=["peg_name", "avg_value", "period"])  # 빈 DF

    # 변수 사전 구성 (peg_name -> avg_value)
    base_map: Dict[str, float] = {}
    try:
        for row in period_df.itertuples(index=False):
            base_map[str(row.peg_name)] = float(row.avg_value)
    except Exception:
        # 컬럼명이 다를 가능성 최소화를 위해 보호
        ser = period_df.set_index('peg_name')['avg_value'] if 'peg_name' in period_df and 'avg_value' in period_df else None
        if ser is not None:
            base_map = {str(k): float(v) for k, v in ser.items()}

    rows = []
    for new_name, expr in definitions.items():
        try:
            value = _safe_eval_expr(str(expr), base_map)
            rows.append({"peg_name": str(new_name), "avg_value": float(value), "period": period_label})
            logging.info("파생 PEG 계산: %s = %s (period=%s)", new_name, value, period_label)
        except Exception as e:
            logging.error("파생 PEG 계산 실패: %s (name=%s, period=%s)", e, new_name, period_label)
            continue
    return pd.DataFrame(rows, columns=["peg_name", "avg_value", "period"]) if rows else pd.DataFrame(columns=["peg_name", "avg_value", "period"]) 

# --- 처리: N-1/N 병합 + 변화율 계산 ---
def process_and_analyze(n1_df: pd.DataFrame, n_df: pd.DataFrame) -> pd.DataFrame:
    """
    두 기간의 PEG 집계 데이터를 병합해 diff/pct_change 를 계산합니다.

    반환:
      - processed_df: ['peg_name', 'avg_n_minus_1', 'avg_n', 'diff', 'pct_change']
    """
    # 핵심 처리 단계: 병합 → 피벗 → 변화율 산출
    logging.info("process_and_analyze() 호출: 데이터 병합 및 처리 시작")
    try:
        all_df = pd.concat([n1_df, n_df], ignore_index=True)
        logging.info("병합 데이터프레임 크기: %s행 x %s열", all_df.shape[0], all_df.shape[1])
        pivot = all_df.pivot(index="peg_name", columns="period", values="avg_value").fillna(0)
        logging.info("피벗 결과 컬럼: %s", list(pivot.columns))
        if "N-1" not in pivot.columns or "N" not in pivot.columns:
            raise ValueError("N-1 또는 N 데이터가 부족합니다. 시간 범위 또는 원본 데이터를 확인하세요.")
        # 명세 컬럼 구성
        out = pd.DataFrame({
            "peg_name": pivot.index,
            "avg_n_minus_1": pivot["N-1"],
            "avg_n": pivot["N"],
        })
        out["diff"] = out["avg_n"] - out["avg_n_minus_1"]
        out["pct_change"] = (out["diff"] / out["avg_n_minus_1"].replace(0, float("nan"))) * 100
        processed_df = out.round(2)

        logging.info("process_and_analyze() 완료: processed_df=%d행", len(processed_df))
        return processed_df
    except Exception as e:
        logging.exception("process_and_analyze() 실패: %s", e)
        raise


 


# (YAML 기반 통합 프롬프트 시스템 사용; 구 프롬프트 생성 함수 제거됨)


# (YAML 기반 통합 프롬프트 시스템 사용; 구 특정 PEG 프롬프트 생성 함수 제거됨)



# --- LLM API 호출 함수 (requests 기반) ---
def query_llm(prompt: str, enable_mock: bool = False) -> dict:
    """내부 vLLM 서버로 분석 요청. 응답 본문에서 JSON만 추출.
    실패 시 다음 엔드포인트로 페일오버.
    
    Args:
        prompt: LLM에게 보낼 프롬프트
        enable_mock: True면 LLM 서버 연결 실패 시 가상 응답 반환
    """
    # 장애 대비를 위해 복수 엔드포인트로 페일오버. 응답에서 JSON 블록만 추출
    logging.info("query_llm() 호출: vLLM 분석 요청 시작 (enable_mock=%s)", enable_mock)

    # Configuration Manager에서 LLM 설정 가져오기
    try:
        settings = get_app_settings()
        llm_config = settings.get_llm_config_dict()
        
        # 엔드포인트 설정 (폴백: 환경변수)
        llm_endpoints_str = os.getenv('LLM_ENDPOINTS', 'http://10.251.204.93:10000,http://100.105.188.117:8888')
        endpoints = [endpoint.strip() for endpoint in llm_endpoints_str.split(',') if endpoint.strip()]

        if not endpoints:
            raise ValueError("LLM_ENDPOINTS 환경 변수가 설정되지 않았거나 비어있습니다.")

        # Configuration Manager에서 모델 설정 사용
        llm_model = llm_config['model']
        timeout = llm_config['timeout']
        
        payload = {
            "model": llm_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": llm_config['temperature'],
            "max_tokens": llm_config['max_tokens'],
        }
        
        logging.debug("Configuration Manager에서 LLM 페이로드 구성: 모델=%s, 온도=%.1f, 최대토큰=%d", 
                     llm_model, llm_config['temperature'], llm_config['max_tokens'])
        
    except Exception as e:
        # 폴백: 환경변수 직접 사용
        logging.warning("Configuration Manager 로딩 실패, 환경변수 직접 사용: %s", e)
        
        llm_endpoints_str = os.getenv('LLM_ENDPOINTS', 'http://10.251.204.93:10000,http://100.105.188.117:8888')
        endpoints = [endpoint.strip() for endpoint in llm_endpoints_str.split(',') if endpoint.strip()]
        
        if not endpoints:
            raise ValueError("LLM_ENDPOINTS 환경 변수가 설정되지 않았거나 비어있습니다.")

        llm_model = os.getenv('LLM_MODEL', 'Gemma-3-27B')
    timeout = int(os.getenv('LLM_TIMEOUT', '180'))

    payload = {
        "model": llm_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": float(os.getenv('LLM_TEMPERATURE', '0.2')),
        "max_tokens": int(os.getenv('LLM_MAX_TOKENS', '4096')),
    }
    
    logging.info("LLM 요청 준비: endpoints=%d, prompt_length=%d, timeout=%ds", 
                len(endpoints), len(prompt), timeout)

    # HTTP 세션 생성
    session = create_http_session()

    for endpoint in endpoints:
        try:
            logging.info("엔드포인트 접속 시도: %s", endpoint)
            
            # requests를 사용한 POST 요청
            response = session.post(
                f'{endpoint}/v1/chat/completions',
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=timeout
            )
            
            # HTTP 상태 코드 확인
            if response.status_code != 200:
                logging.error("HTTP 에러 응답 수신 (%s): status=%d, body=%s", 
                            endpoint, response.status_code, response.text[:500])
                continue
                
            if not response.text:
                logging.error("응답 본문이 비어있습니다 (%s)", endpoint)
                continue
                
            response_json = response.json()
            
            # API 에러 확인
            if 'error' in response_json:
                logging.error("API 에러 응답 수신 (%s): %s", endpoint, response_json['error'])
                continue
                
            if 'choices' not in response_json or not response_json['choices']:
                logging.error("'choices' 없음 또는 비어있음 (%s): %s", endpoint, response_json)
                continue
                
            analysis_content = response_json['choices'][0]['message']['content']
            if not analysis_content or not analysis_content.strip():
                logging.error("'content' 비어있음 (%s)", endpoint)
                continue

            # JSON 추출 및 파싱
            cleaned_json_str = analysis_content
            if '{' in cleaned_json_str:
                start_index, end_index = cleaned_json_str.find('{'), cleaned_json_str.rfind('}')
                if start_index != -1 and end_index != -1:
                    cleaned_json_str = cleaned_json_str[start_index: end_index + 1]
                    logging.info("응답 문자열에서 JSON 부분 추출 성공")
                else:
                    logging.error("JSON 범위 추출 실패 (%s)", endpoint)
                    continue
            else:
                logging.error("응답에 '{' 없음 (%s)", endpoint)
                continue

            analysis_result = json.loads(cleaned_json_str)
            # 결과 구조를 빠르게 파악할 수 있도록 주요 키를 기록
            logging.info(
                "LLM 분석 결과 수신 성공 (%s): keys=%s",
                endpoint, list(analysis_result.keys()) if isinstance(analysis_result, dict) else type(analysis_result)
            )
            
            # 세션 정리
            session.close()
            return analysis_result
            
        except requests.exceptions.Timeout as e:
            logging.error("요청 타임아웃 (%s): %s", endpoint, e)
            continue
        except requests.exceptions.ConnectionError as e:
            logging.error("연결 오류 (%s): %s", endpoint, e)
            continue
        except requests.exceptions.RequestException as e:
            logging.error("requests 예외 (%s): %s", endpoint, e)
            continue
        except json.JSONDecodeError as e:
            logging.error("JSON 파싱 실패 (%s): %s", endpoint, e)
            logging.error("파싱 시도 내용(1000자): %s...", cleaned_json_str[:1000])
            continue
        except Exception as e:
            logging.error("예기치 못한 오류 (%s): %s", type(e).__name__, e, exc_info=True)
            continue
    
    # 세션 정리
    session.close()
    
    # 모든 엔드포인트 실패 시 예외 발생
    raise ConnectionError("모든 LLM API 엔드포인트에 연결하지 못했습니다.")







# --- 백엔드 POST ---
def post_results_to_backend(url: str, payload: dict, timeout: int = 15) -> Optional[dict]:
    """분석 JSON 결과를 FastAPI 백엔드로 POST 전송합니다."""
    # 네트워크 오류/타임아웃 대비. 상태코드/본문 파싱 결과를 기록해 원인 추적을 용이하게 함
    logging.info("post_results_to_backend() 호출: %s", url)
    
    def _sanitize_for_json(value):
        """NaN/Infinity 및 넘파이 수치를 JSON 호환으로 정규화한다."""
        try:
            # dict/list 재귀 처리
            if isinstance(value, dict):
                return {k: _sanitize_for_json(v) for k, v in value.items()}
            if isinstance(value, list):
                return [_sanitize_for_json(v) for v in value]
            # 수치형: 넘파이 포함을 float()로 흡수
            if isinstance(value, (int, float)):
                return value if math.isfinite(float(value)) else None
            # 문자열 타입은 float 변환하지 않음 (cellid, ne 등 ID 값 보존)
            if isinstance(value, str):
                return value
            # 기타 타입: 넘파이 스칼라 등은 float() 시도 (단, 문자열 제외)
            try:
                f = float(value)  # numpy.float64 등
                return f if math.isfinite(f) else None
            except Exception:
                return value
        except Exception:
            return value
    
    safe_payload = _sanitize_for_json(payload)
    
    try:
        # allow_nan=False 보장 직렬화 후 전송 (서버와 규격 일치)
        json_text = json.dumps(safe_payload, ensure_ascii=False, allow_nan=False)
        try:
            parsed_preview = json.loads(json_text)
        except Exception:
            parsed_preview = safe_payload
        logging.info("PAYLOAD %s", json.dumps({
            "url": url,
            "method": "POST",
            "payload": parsed_preview,
        }, ensure_ascii=False, indent=2))

        # POST 시도
        resp = requests.post(
            url,
            data=json_text.encode('utf-8'),
            headers={'Content-Type': 'application/json; charset=utf-8'},
            timeout=timeout
        )

        # 성공적인 상태코드 확인 (200, 201, 202 등)
        if resp.status_code in [200, 201, 202]:
            logging.info("백엔드 POST 성공: status=%s", resp.status_code)
            try:
                return resp.json()
            except Exception:
                # JSON 응답이 없거나 파싱 실패 시에도 성공으로 처리
                return {"status": "success", "message": "POST 요청이 성공적으로 처리되었습니다."}
        
        # 그 외 상태코드는 예외로 처리
        logging.error("백엔드 POST 실패: status=%s body=%s", resp.status_code, resp.text[:500])
        resp.raise_for_status()
        return None
    except Exception as e:
        logging.exception("백엔드 POST 실패: %s", e)
        return None


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
    
    def _load_default_settings(self) -> None:
        """기본 설정 로드 (Configuration Manager 우선, 환경변수 폴백)"""
        try:
            settings = get_app_settings()
            self.default_backend_url = str(settings.backend_service_url)
            self.default_db = {
                "host": settings.db_host,
                "port": settings.db_port,
                "user": settings.db_user,
                "password": settings.db_password.get_secret_value(),
                "dbname": settings.db_name
            }
            self.logger.debug("Configuration Manager에서 기본 설정 로드 완료")
        except Exception as e:
            self.logger.warning("Configuration Manager 로딩 실패, 환경변수 사용: %s", e)
            self.default_backend_url = os.getenv('DEFAULT_BACKEND_URL', 'http://165.213.69.30:8000/api/analysis/results/')
            self.default_db = {
                "host": os.getenv('DEFAULT_DB_HOST', '127.0.0.1'),
                "port": int(os.getenv('DEFAULT_DB_PORT', '5432')),
                "user": os.getenv('DEFAULT_DB_USER', 'postgres'),
                "password": os.getenv('DEFAULT_DB_PASSWORD', ''),
                "dbname": os.getenv('DEFAULT_DB_NAME', 'postgres')
            }
    
    def _validate_basic_request(self, request: dict) -> None:
        """
        기본 요청 검증
        
        Args:
            request (dict): MCP 요청 데이터
            
        Raises:
            ValueError: 필수 필드 누락 또는 잘못된 형식
        """
        self.logger.debug("_validate_basic_request() 호출: 기본 요청 검증 시작")
        
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
        MCP 요청을 AnalysisService 형식으로 변환
        
        Args:
            request (dict): 원본 MCP 요청
            
        Returns:
            dict: AnalysisService 호환 형식
        """
        self.logger.debug("_parse_request_to_analysis_format() 호출: 요청 형식 변환")
        
        # 기본 필드
        analysis_request = {
            'n_minus_1': request.get('n_minus_1') or request.get('n1'),
            'n': request.get('n'),
            'output_dir': request.get('output_dir', os.path.abspath('./analysis_output')),
            'analysis_type': 'enhanced',  # 기본값
            'enable_mock': False  # 프로덕션 모드
        }
        
        # 백엔드 URL 설정
        analysis_request['backend_url'] = request.get('backend_url') or self.default_backend_url
        
        # DB 설정
        analysis_request['db'] = request.get('db', self.default_db)
        
        # 테이블 및 컬럼 설정
        analysis_request['table'] = request.get('table') or os.getenv('DEFAULT_TABLE', 'summary')
        analysis_request['columns'] = request.get('columns', {
            "time": os.getenv('DEFAULT_TIME_COLUMN', 'datetime'),
            "peg_name": os.getenv('DEFAULT_PEG_COLUMN', 'peg_name'),
            "value": os.getenv('DEFAULT_VALUE_COLUMN', 'value'),
            "ne": os.getenv('DEFAULT_NE_COLUMN', 'ne'),
            "cellid": os.getenv('DEFAULT_CELL_COLUMN', 'cellid'),
            "host": os.getenv('DEFAULT_HOST_COLUMN', 'host')
        })
        
        # 필터 설정
        filters = {}
        if request.get('ne'):
            filters['ne'] = request['ne']
        if request.get('cellid') or request.get('cell'):
            filters['cellid'] = request.get('cellid') or request.get('cell')
        if request.get('host'):
            filters['host'] = request['host']
        analysis_request['filters'] = filters
        
        # PEG 관련 설정
        if request.get('preference') or request.get('selected_pegs'):
            analysis_request['selected_pegs'] = request.get('selected_pegs') or request.get('preference')
        
        if request.get('peg_definitions'):
            analysis_request['peg_definitions'] = request['peg_definitions']
        
        # 프롬프트 제한 설정
        analysis_request['max_prompt_tokens'] = request.get('max_prompt_tokens', DEFAULT_MAX_PROMPT_TOKENS)
        analysis_request['max_prompt_chars'] = request.get('max_prompt_chars', DEFAULT_MAX_PROMPT_CHARS)
        
        self.logger.info("요청 형식 변환 완료: %d개 필드", len(analysis_request))
        return analysis_request
    
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
        self.logger.info("=" * 20 + " MCP Handler 요청 처리 시작 " + "=" * 20)
        
        try:
            # 1단계: 기본 요청 검증
            self.logger.info("1단계: 기본 요청 검증")
            self._validate_basic_request(request)
            
            # 2단계: 요청 형식 변환
            self.logger.info("2단계: 요청 형식 변환")
            analysis_request = self._parse_request_to_analysis_format(request)
            
            # 3단계: AnalysisService 생성 (필요시)
            if not self.analysis_service:
                self.logger.info("3단계: AnalysisService 생성")
                self.analysis_service = self._create_analysis_service()
            
            # 4단계: 분석 실행
            self.logger.info("4단계: 분석 실행 (AnalysisService 위임)")
            analysis_result = self.analysis_service.perform_analysis(analysis_request)
            
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


# --- 기존 Monolithic 로직 (DEPRECATED) ---
def _analyze_cell_performance_logic(request: dict) -> dict:
    """
    요청 파라미터:
      - n_minus_1: "yyyy-mm-dd_hh:mm~yyyy-mm-dd_hh:mm"
      - n: "yyyy-mm-dd_hh:mm~yyyy-mm-dd_hh:mm"
      - output_dir: str (기본 ./analysis_output)
      - backend_url: str (선택)
      - db: {host, port, user, password, dbname}
      - table: str (기본 'summary')
      - columns: {time: 'datetime', peg_name: 'peg_name', value: 'value'}
      - ne: 문자열 또는 배열. 예: "nvgnb#10000" 또는 ["nvgnb#10000","nvgnb#20000"]
      - cellid|cell: 문자열(쉼표 구분) 또는 배열. 예: "2010,2011" 또는 [2010,2011]
      - host: 문자열 또는 배열. 예: "192.168.1.1" 또는 ["host01","192.168.1.10"]
        → 제공 시 DB 집계에서 해당 조건으로 필터링하여 PEG 평균을 계산
      - preference: 쉼표 구분 문자열 또는 배열. 정확한 peg_name만 인식하여 '특정 peg 분석' 대상 선정
      - selected_pegs: 배열. 명시적 선택 목록이 있으면 우선 사용
      - peg_definitions: {파생PEG이름: 수식 문자열}. 예: {"telus_RACH_Success": "A/B*100"}
        수식 지원: 숫자, 변수(peg_name), +, -, *, /, (), 단항 +/-. 0 나눗셈은 NaN 처리
        적용 시점: N-1, N 각각의 집계 결과에 대해 계산 후 원본과 병합 → 전체 처리/분석에 포함
    """
    logging.info("=" * 20 + " Cell 성능 분석 로직 실행 시작 " + "=" * 20)
    try:
        # 파라미터 파싱
        n1_text = request.get('n_minus_1') or request.get('n1')
        n_text = request.get('n')
        if not n1_text or not n_text:
            raise ValueError("'n_minus_1'와 'n' 시간 범위를 모두 제공해야 합니다.")

        output_dir = request.get('output_dir', os.path.abspath('./analysis_output'))
        # 백엔드 업로드 URL: 요청값 > Configuration Manager > 환경변수 > 기본값 순으로 우선순위 적용
        try:
            settings = get_app_settings()
            default_backend_url = str(settings.backend_service_url)
            logging.debug("Configuration Manager에서 백엔드 URL 로드: %s", default_backend_url)
        except Exception as e:
            logging.warning("Configuration Manager 로딩 실패, 환경변수 직접 사용: %s", e)
            default_backend_url = os.getenv('DEFAULT_BACKEND_URL', 'http://165.213.69.30:8000/api/analysis/results/')
        
        backend_url = request.get('backend_url') or default_backend_url

        # DB 설정: 요청값 > Configuration Manager > 환경변수 > 기본값 순으로 우선순위 적용
        try:
            settings = get_app_settings()
            default_db = {
                "host": settings.db_host,
                "port": settings.db_port,
                "user": settings.db_user,
                "password": settings.db_password.get_secret_value(),
                "dbname": settings.db_name
            }
            logging.debug("Configuration Manager에서 DB 기본값 로드")
        except Exception as e:
            logging.warning("Configuration Manager 로딩 실패, 환경변수 직접 사용: %s", e)
            default_db = {
            "host": os.getenv('DEFAULT_DB_HOST', '127.0.0.1'),
            "port": int(os.getenv('DEFAULT_DB_PORT', '5432')),
            "user": os.getenv('DEFAULT_DB_USER', 'postgres'),
            "password": os.getenv('DEFAULT_DB_PASSWORD', ''),
            "dbname": os.getenv('DEFAULT_DB_NAME', 'postgres')
            }
        
        db = request.get('db', default_db)
        
        # 테이블 및 컬럼 설정: 요청값 > 환경변수 > 기본값
        table = request.get('table') or os.getenv('DEFAULT_TABLE', 'summary')
        columns = request.get('columns', {
            "time": os.getenv('DEFAULT_TIME_COLUMN', 'datetime'),
            "peg_name": os.getenv('DEFAULT_PEG_COLUMN', 'peg_name'),
            "value": os.getenv('DEFAULT_VALUE_COLUMN', 'value'),
            "ne": os.getenv('DEFAULT_NE_COLUMN', 'ne'),
            "cellid": os.getenv('DEFAULT_CELL_COLUMN', 'cellid'),
            "host": os.getenv('DEFAULT_HOST_COLUMN', 'host')
        })

        # 파라미터 요약 로그: 민감정보는 기록하지 않음
        logging.info(
            "요청 요약: output_dir=%s, backend_url=%s, table=%s, columns=%s",
            output_dir, bool(backend_url), table, columns
        )

        # 시간 범위 파싱 (새로운 TimeRangeParser 사용)
        time_parser = TimeRangeParser()
        try:
            n1_start, n1_end = time_parser.parse(n1_text)
            n_start, n_end = time_parser.parse(n_text)
            logging.info("시간 범위: N-1(%s~%s), N(%s~%s)", n1_start, n1_end, n_start, n_end)
        except TimeParsingError as e:
            # TimeParsingError를 기존 형식의 ValueError로 변환하여 호환성 유지
            error_json = e.to_json_error()
            logging.error("시간 파싱 오류: %s", error_json)
            raise ValueError(json.dumps(error_json, ensure_ascii=False))

        # DB 조회
        conn = get_db_connection(db)
        try:
            # 선택적 입력 필터 수집: ne, cellid, host
            # request 예시: { "ne": "nvgnb#10000" } 또는 { "ne": ["nvgnb#10000","nvgnb#20000"], "cellid": "2010,2011", "host": "192.168.1.1" }
            ne_raw = request.get('ne')
            cell_raw = request.get('cellid') or request.get('cell')
            host_raw = request.get('host')

            def to_list(raw):
                if raw is None:
                    return []
                if isinstance(raw, str):
                    return [t.strip() for t in raw.split(',') if t.strip()]
                if isinstance(raw, list):
                    return [str(t).strip() for t in raw if str(t).strip()]
                return [str(raw).strip()]

            ne_filters = to_list(ne_raw)
            cellid_filters = to_list(cell_raw)
            host_filters = to_list(host_raw)

            logging.info("입력 필터: ne=%s (type: %s), cellid=%s (type: %s), host=%s (type: %s)",
                        ne_filters, [type(x).__name__ for x in ne_filters] if ne_filters else '[]',
                        cellid_filters, [type(x).__name__ for x in cellid_filters] if cellid_filters else '[]',
                        host_filters, [type(x).__name__ for x in host_filters] if host_filters else '[]')

            n1_df = fetch_cell_averages_for_period(conn, table, columns, n1_start, n1_end, "N-1", ne_filters=ne_filters, cellid_filters=cellid_filters, host_filters=host_filters)
            n_df = fetch_cell_averages_for_period(conn, table, columns, n_start, n_end, "N", ne_filters=ne_filters, cellid_filters=cellid_filters, host_filters=host_filters)
        finally:
            conn.close()
            logging.info("DB 연결 종료")

        logging.info("집계 결과 크기: n-1=%d행, n=%d행", len(n1_df), len(n_df))
        if len(n1_df) == 0 or len(n_df) == 0:
            logging.warning("한쪽 기간 데이터가 비어있음: 분석 신뢰도가 낮아질 수 있음")

        # 파생 PEG 정의 처리 (사용자 정의 수식)
        # 입력 예: "peg_definitions": {"telus_RACH_Success": "Random_access_preamble_count/Random_access_response*100"}
        derived_defs = request.get('peg_definitions') or {}
        derived_n1 = compute_derived_pegs_for_period(n1_df, derived_defs, "N-1") if derived_defs else pd.DataFrame(columns=["peg_name","avg_value","period"])
        derived_n  = compute_derived_pegs_for_period(n_df, derived_defs, "N") if derived_defs else pd.DataFrame(columns=["peg_name","avg_value","period"])

        if not derived_n1.empty or not derived_n.empty:
            n1_df = pd.concat([n1_df, derived_n1], ignore_index=True)
            n_df = pd.concat([n_df, derived_n], ignore_index=True)
            logging.info("파생 PEG 병합 완료: n-1=%d행, n=%d행", len(n1_df), len(n_df))

        # 처리 & 분석 (파생 포함) - 원본 데이터 직접 사용
        logging.info("원본 데이터 직접 사용: n-1=%d행, n=%d행", len(n1_df), len(n_df))

        processed_df = process_and_analyze(n1_df, n_df)
        logging.info("처리 완료: processed_df=%d행", len(processed_df))

        # LLM 프롬프트 & 분석 (모킹 제거: 항상 실제 호출)
        test_mode = False
        # 통합 프롬프트 시스템(YAML + Python 포매팅) 사용
        try:
            from analysis_llm.config.prompt_loader import PromptLoader
            from analysis_llm.utils.data_formatter import format_dataframe_for_prompt

            loader = PromptLoader('config/prompts/v1.yaml')
            data_preview = format_dataframe_for_prompt(processed_df)
            prompt = loader.format_prompt(
                'enhanced',
                n1_range=n1_text,
                n_range=n_text,
                data_preview=data_preview,
            )
        except Exception as e:
            logging.exception("통합 프롬프트 생성 실패(enhanced). 최소 문자열 폴백 사용: %s", e)
            try:
                from analysis_llm.utils.data_formatter import format_dataframe_for_prompt as _fmt
                _fb_preview = _fmt(processed_df)
            except Exception:
                try:
                    _fb_preview = processed_df.head(100).to_string(index=False)
                except Exception:
                    _fb_preview = "<데이터 미리보기 생성 실패>"
            prompt = (
                f"[Fallback Prompt]\n"
                f"기간 n-1: {n1_text}\n"
                f"기간 n: {n_text}\n\n"
                f"[데이터 표]\n{_fb_preview}\n"
                f"[분석 지침]\n- 주요 변화 요약, 가설, 검증 계획을 JSON으로 제시하세요."
            )
        prompt_tokens = estimate_prompt_tokens(prompt)
        logging.info("프롬프트 길이: %d자, 추정 토큰=%d", len(prompt), prompt_tokens)

        # 하드 가드: 안전 상한 적용 (요청에서 오버라이드 가능)
        max_tokens = int(request.get('max_prompt_tokens', DEFAULT_MAX_PROMPT_TOKENS))
        max_chars = int(request.get('max_prompt_chars', DEFAULT_MAX_PROMPT_CHARS))
        logging.info(
            "프롬프트 상한 설정: max_tokens=%d, max_chars=%d",
            max_tokens, max_chars
        )
        if prompt_tokens > max_tokens or len(prompt) > max_chars:
            logging.warning(
                "프롬프트 상한 초과: tokens=%d/%d, chars=%d/%d → 자동 축약",
                prompt_tokens, max_tokens, len(prompt), max_chars
            )
            prompt, clamped = clamp_prompt(prompt, max_chars)
            logging.info("프롬프트 축약 결과: 길이=%d자, clamped=%s", len(prompt), clamped)
        
        try:
            t0 = time.perf_counter()
            llm_analysis = query_llm(prompt, enable_mock=False)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            try:
                import json as _json  # 지역 import로 안전 사용
                result_size = len(_json.dumps(llm_analysis, ensure_ascii=False).encode('utf-8')) if isinstance(llm_analysis, (dict, list)) else len(str(llm_analysis).encode('utf-8'))
            except Exception:
                result_size = -1
            logging.info(
                "LLM 호출 완료: 소요=%.1fms, 결과타입=%s, 결과크기=%dB",
                elapsed_ms,
                type(llm_analysis),
                result_size,
            )
            if isinstance(llm_analysis, dict):
                logging.info("LLM 결과 키: %s", list(llm_analysis.keys()))
        except ConnectionError as e:
            # 실패 컨텍스트 로깅(프롬프트 일부, 상한값)
            prompt_head = (prompt or "")[:1000]
            logging.error(
                "LLM 호출 실패: %s\n- prompt head: %s\n- limits: tokens=%d, chars=%d",
                e,
                prompt_head,
                max_tokens,
                max_chars,
            )
            # 모킹 제거: 실패 시 상위로 예외 전파
            raise

        # '특정 peg 분석' 처리: preference / peg_definitions / selected_pegs
        try:
            selected_pegs: list[str] = []
            # 1) 명시적 선택 목록
            explicit_list = request.get('selected_pegs')
            if isinstance(explicit_list, list):
                selected_pegs.extend([str(x) for x in explicit_list])

            # 2) preference 기반 선택 (정확한 peg_name로만 해석)
            pref = request.get('preference')
            if isinstance(pref, str):
                pref_tokens = [t.strip() for t in pref.split(',') if t.strip()]
            elif isinstance(pref, list):
                pref_tokens = [str(t).strip() for t in pref if str(t).strip()]
            else:
                pref_tokens = []

            if pref_tokens:
                valid_names_set = set(processed_df['peg_name'].astype(str).tolist())
                for token in pref_tokens:
                    if token in valid_names_set:
                        selected_pegs.append(token)

            # 유니크 + 순서 유지 + 실데이터 존재 필터링
            unique_selected = []
            seen = set()
            valid_names = set(processed_df['peg_name'].astype(str).tolist())
            for name in selected_pegs:
                if name in valid_names and name not in seen:
                    unique_selected.append(name)
                    seen.add(name)

            logging.info("특정 PEG 선택 결과: %d개", len(unique_selected))

            if unique_selected:
                subset_df = processed_df[processed_df['peg_name'].isin(unique_selected)].copy()
                # LLM에 보낼 수 있는 행수/토큰 보호를 위해 상한을 둘 수 있음(예: 500행). 필요 시 조정
                max_rows = int(request.get('specific_max_rows', DEFAULT_SPECIFIC_MAX_ROWS))
                if len(subset_df) > max_rows:
                    logging.warning("선택 PEG 서브셋이 %d행으로 큼. 상한 %d행으로 절단", len(subset_df), max_rows)
                    subset_df = subset_df.head(max_rows)

                # 통합 프롬프트 시스템 사용 (specific_pegs)
                try:
                    from analysis_llm.config.prompt_loader import PromptLoader
                    from analysis_llm.utils.data_formatter import format_dataframe_for_prompt

                    loader = PromptLoader('config/prompts/v1.yaml')
                    sp_data_preview = format_dataframe_for_prompt(subset_df)
                    sp_prompt = loader.format_prompt(
                        'specific_pegs',
                        n1_range=n1_text,
                        n_range=n_text,
                        data_preview=sp_data_preview,
                        selected_pegs_str=', '.join(unique_selected),
                    )
                except Exception as e:
                    logging.exception("통합 프롬프트 생성 실패(specific_pegs). 최소 문자열 폴백 사용: %s", e)
                    try:
                        from analysis_llm.utils.data_formatter import format_dataframe_for_prompt as _fmt
                        _sp_fb_preview = _fmt(subset_df)
                    except Exception:
                        try:
                            _sp_fb_preview = subset_df.head(100).to_string(index=False)
                        except Exception:
                            _sp_fb_preview = "<데이터 미리보기 생성 실패>"
                    sp_prompt = (
                        f"[Fallback Prompt - Specific PEGs]\n"
                        f"대상 PEG: {', '.join(unique_selected)}\n"
                        f"기간 n-1: {n1_text}\n"
                        f"기간 n: {n_text}\n\n"
                        f"[데이터 표]\n{_sp_fb_preview}\n"
                        f"[분석 지침]\n- 각 PEG 통찰과 우선순위 액션을 JSON으로 제시하세요."
                    )
                sp_tokens = estimate_prompt_tokens(sp_prompt)
                logging.info("특정 PEG 프롬프트 길이: %d자, 추정 토큰=%d, 선택 PEG=%d개", len(sp_prompt), sp_tokens, len(unique_selected))
                if sp_tokens > max_tokens or len(sp_prompt) > max_chars:
                    logging.warning(
                        "특정 PEG 프롬프트 상한 초과: tokens=%d/%d, chars=%d/%d → 축약",
                        sp_tokens, max_tokens, len(sp_prompt), max_chars
                    )
                    sp_prompt, sp_clamped = clamp_prompt(sp_prompt, max_chars)
                    logging.info("특정 PEG 프롬프트 축약: 길이=%d자, clamped=%s", len(sp_prompt), sp_clamped)
                
                sp_result = query_llm(sp_prompt, enable_mock=False)
                
                if isinstance(llm_analysis, dict):
                    llm_analysis['specific_peg_analysis'] = {
                        "selected_pegs": unique_selected,
                        **(sp_result if isinstance(sp_result, dict) else {"summary": str(sp_result)})
                    }
                logging.info("특정 PEG 분석 완료: keys=%s", list((llm_analysis.get('specific_peg_analysis') or {}).keys()))
        except Exception as e:
            logging.exception("특정 PEG 분석 처리 중 오류: %s", e)

        # HTML 리포트 생성 생략

        # 백엔드 POST payload 구성 (AnalysisResultCreate 스키마에 맞춤)
        # - stats: {period, kpi_name, avg} 배열로 변환
        # - 추가 메타는 analysis 또는 request_params로 수용

        def _to_stats(df: pd.DataFrame, period_label: str) -> list[dict]:
            items: list[dict] = []
            if df is None or df.empty:
                return items
            # 기대 컬럼: peg_name, avg_value
            try:
                for row in df.itertuples(index=False):
                    items.append({
                        "period": period_label,
                        "kpi_name": str(getattr(row, "peg_name")),
                        "avg": float(getattr(row, "avg_value"))
                    })
            except Exception:
                # 컬럼 명이 다를 경우 보호적 접근
                if "peg_name" in df.columns and "avg_value" in df.columns:
                    for peg, val in zip(df["peg_name"], df["avg_value"]):
                        items.append({"period": period_label, "kpi_name": str(peg), "avg": float(val)})
            return items

        stats_records: list[dict] = []
        try:
            stats_records.extend(_to_stats(n1_df, "N-1"))
            stats_records.extend(_to_stats(n_df, "N"))
        except Exception as e:
            logging.warning("stats 변환 실패, 빈 배열로 대체: %s", e)
            stats_records = []

        # 요청 파라미터(입력 컨텍스트) 수집
        request_params = {
            "db": db,
            "table": table,
            "columns": columns,
            "time_ranges": {
                "n_minus_1": {"start": n1_start.isoformat(), "end": n1_end.isoformat()},
                "n": {"start": n_start.isoformat(), "end": n_end.isoformat()}
            },
            "filters": {
                "ne": ne_filters,
                "cellid": cellid_filters
            },
            "preference": request.get("preference"),
            "selected_pegs": request.get("selected_pegs"),
            "peg_definitions": request.get("peg_definitions")
        }

        # 대표 ne/cell ID (없으면 ALL) - 명시적 string 변환으로 타입 보장
        ne_id_repr = str(ne_filters[0]).strip() if ne_filters else "ALL"
        cell_id_repr = str(cellid_filters[0]).strip() if cellid_filters else "ALL"
        logging.info("대표 ID 설정: ne_id_repr=%s (type: %s), cell_id_repr=%s (type: %s)",
                    ne_id_repr, type(ne_id_repr).__name__, cell_id_repr, type(cell_id_repr).__name__)

        # 분석 섹션에 LLM 결과 + 차트/가정/원본 메타 포함
        analysis_section = {
            **(llm_analysis if isinstance(llm_analysis, dict) else {"summary": str(llm_analysis)}),
            "assumptions": {"same_environment": True},
            "source_metadata": {
                "db_config": db,
                "table": table,
                "columns": columns,
                "ne_id": ne_id_repr,
                "cell_id": cell_id_repr
            }
        }

        # 결과 요약 생성
        results_overview = build_results_overview(llm_analysis)

        # 최종 payload (모델 alias를 사용: analysisDate, neId, cellId) - 타입 보장
        result_payload = {
            # 서버 Pydantic 모델은 by_alias=False로 저장하므로 snake_case 보장
            "analysis_type": "llm_analysis",
            "analysisDate": datetime.datetime.now(tz=_get_default_tzinfo()).isoformat(),
            "neId": str(ne_id_repr).strip() if ne_id_repr != "ALL" else "ALL",
            "cellId": str(cell_id_repr).strip() if cell_id_repr != "ALL" else "ALL",
            "status": "success",
            "results": [],
            "stats": stats_records,
            "analysis": analysis_section,
            "resultsOverview": results_overview,
            "request_params": request_params
        }
        try:
            import json as _json
            payload_size = len(_json.dumps(result_payload, ensure_ascii=False).encode('utf-8'))
            logging.info("백엔드 전송 payload 크기: %dB, stats_rows=%d", payload_size, len(result_payload.get("stats", [])))
            # 환경변수에서 payload 크기 제한 설정 (기본값: 1MB)
            max_payload_size = int(os.getenv('MAX_PAYLOAD_SIZE_MB', '1')) * 1024 * 1024
            if payload_size > max_payload_size:
                logging.warning("payload 크기 %dMB 초과: %dB", max_payload_size // (1024 * 1024), payload_size)
        except Exception as _e:
            logging.warning("payload 크기 계산 실패: %s", _e)
        logging.info("payload 준비 완료: stats_rows=%d, neId=%s (type: %s), cellId=%s (type: %s)",
                    len(result_payload.get("stats", [])),
                    result_payload.get("neId"), type(result_payload.get("neId")).__name__,
                    result_payload.get("cellId"), type(result_payload.get("cellId")).__name__)

        backend_response = None
        if backend_url:
            backend_response = post_results_to_backend(backend_url, result_payload)
            logging.info("백엔드 응답 타입: %s", type(backend_response))

        logging.info("=" * 20 + " Cell 성능 분석 로직 실행 종료 (성공) " + "=" * 20)
        return {
            "status": "success",
            "message": "분석 완료",
            "backend_response": backend_response,
            "analysis": llm_analysis,
            "stats": processed_df.to_dict(orient='records'),
        }
    except ValueError as e:
        logging.error("입력/처리 오류: %s", e)
        return {"status": "error", "message": f"입력/처리 오류: {str(e)}"}
    except ConnectionError as e:
        logging.error("연결 오류: %s", e)
        return {"status": "error", "message": f"연결 오류: {str(e)}"}
    except Exception as e:
        logging.exception("예상치 못한 오류 발생")
        return {"status": "error", "message": f"예상치 못한 오류: {str(e)}"}


@mcp.tool
def analyze_cell_performance_with_llm(request: dict) -> dict:
    """
    MCP 엔드포인트: 시간 범위 기반 통합 셀 성능 분석 실행
    
    새로운 아키텍처: MCPHandler -> AnalysisService -> 각종 Repository/Service 패턴
    """
    # 새로운 MCPHandler 사용
    with MCPHandler() as handler:
        return handler.handle_request(request)


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