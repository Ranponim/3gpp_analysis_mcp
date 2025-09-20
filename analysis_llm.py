"""
=====================================================================================
Cell 성능 LLM 분석기 (시간범위 입력 + PostgreSQL 집계 + 통합 분석 + HTML/백엔드 POST)
=====================================================================================

변경 사항 요약:
- 입력 형식 변경: LLM/사용자가 제공하는 시간 범위(n-1, n)를 받아 PostgreSQL에서 평균 집계
- 분석 관점 변경: PEG 단위가 아닌, 셀 단위 전체 PEG 데이터를 통합하여 종합 성능 평가
- 가정 반영: n-1과 n은 동일한 시험환경에서 수행되었다는 가정 하에 분석
- 결과 출력 확장: HTML 리포트 생성 + FastAPI 백엔드로 JSON POST 전송
- 특정 PEG 분석: preference(정확한 peg_name 목록)나 selected_pegs로 지정된 PEG만 묶어 별도 LLM 분석
- 파생 PEG 수식 지원: peg_definitions로 (pegA/pegB)*100 같은 수식을 정의해 파생 PEG를 계산/포함

사용 예시 (MCP tool 호출 request 예):
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
"""

from __future__ import annotations

import os
import io
import json
import base64
import datetime
import logging
import math
import time

# --- 글로벌 안전 상수 (요청으로 오버라이드 가능) ---
DEFAULT_MAX_PROMPT_TOKENS = 24000
DEFAULT_MAX_PROMPT_CHARS = 80000
DEFAULT_SPECIFIC_MAX_ROWS = 500
DEFAULT_MAX_RAW_STR = 4000
DEFAULT_MAX_RAW_ARRAY = 100

# --- 토큰/프롬프트 가드 유틸 ---
def estimate_prompt_tokens(text: str) -> int:
    """아주 단순한 휴리스틱으로 토큰 수를 추정합니다.
    - 영어/한글 혼합 환경에서 안전 측을 위해 평균 3.5 chars/token 가정
    - 실제 모델별 토크나이저와 차이가 있으므로 상한 체크용 보수 추정치
    """
    if not text:
        return 0
    try:
        return int(math.ceil(len(text) / 3.5))
    except Exception:
        return len(text) // 4

def clamp_prompt(text: str, max_chars: int) -> tuple[str, bool]:
    """문자 기반 상한으로 프롬프트를 잘라내 안전 가드.
    Returns: (clamped_text, was_clamped)
    """
    if text is None:
        return "", False
    if len(text) <= max_chars:
        return text, False
    head = text[: max_chars - 200]
    tail = "\n\n[...truncated due to safety guard...]\n"
    return head + tail, True


def build_results_overview(analysis: dict | str | None) -> dict:
    """LLM 결과에서 핵심 요약을 추출합니다."""
    overview: dict = {"summary": None, "key_findings": [], "recommended_actions": []}
    try:
        if isinstance(analysis, dict):
            summary = analysis.get("executive_summary") or analysis.get("summary") or None
            recs = analysis.get("recommended_actions") or analysis.get("actions") or []
            findings = analysis.get("issues") or analysis.get("alerts") or analysis.get("key_findings") or []
            if isinstance(recs, dict):
                recs = list(recs.values())
            if isinstance(findings, dict):
                findings = list(findings.values())
            overview["summary"] = summary if isinstance(summary, str) else None
            overview["recommended_actions"] = recs if isinstance(recs, list) else []
            overview["key_findings"] = findings if isinstance(findings, list) else []
        elif isinstance(analysis, str):
            overview["summary"] = analysis[:2000] + ("..." if len(analysis) > 2000 else "")
    except Exception:
        pass
    return overview


import subprocess
from typing import Dict, Tuple, Optional
import ast
import math
import re

import pandas as pd
import matplotlib
matplotlib.use("Agg")  # Headless 환경 렌더링
import matplotlib.pyplot as plt

import psycopg2
import psycopg2.extras
import requests
from fastmcp import FastMCP


# --- 로깅 기본 설정 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


# --- FastMCP 서버 인스턴스 생성 ---
mcp = FastMCP(name="Cell LLM 종합 분석기")


# --- 유틸: 시간 범위 파서 ---
def _get_default_tzinfo() -> datetime.tzinfo:
    """
    환경 변수 `DEFAULT_TZ_OFFSET`(예: "+09:00")를 읽어 tzinfo를 생성합니다.
    설정이 없거나 형식이 잘못되면 UTC를 반환합니다.
    """
    offset_text = os.getenv("DEFAULT_TZ_OFFSET", "+09:00").strip()
    try:
        sign = 1 if offset_text.startswith("+") else -1
        hh_mm = offset_text[1:].split(":")
        hours = int(hh_mm[0]) if len(hh_mm) > 0 else 0
        minutes = int(hh_mm[1]) if len(hh_mm) > 1 else 0
        delta = datetime.timedelta(hours=hours * sign, minutes=minutes * sign)
        return datetime.timezone(delta)
    except Exception:
        logging.warning("DEFAULT_TZ_OFFSET 파싱 실패, UTC 사용: %s", offset_text)
        return datetime.timezone.utc

def parse_time_range(range_text: str) -> Tuple[datetime.datetime, datetime.datetime]:
    """
    "YYYY-MM-DD_HH:MM~YYYY-MM-DD_HH:MM" 또는 "YYYY-MM-DD-HH:MM~YYYY-MM-DD-HH:MM" 또는 단일 날짜 "YYYY-MM-DD"를 받아
    (start_dt, end_dt) (둘 다 tz-aware) 튜플을 반환합니다.

    - 범위 형식: 주어진 시각 범위를 그대로 사용(유연한 포맷: _ 또는 - 구분자 허용).
    - 단일 날짜: 해당 날짜의 00:00:00 ~ 23:59:59 로 확장.

    입력에서 _와 - 모두 허용하지만, 내부적으로는 표준 _ 포맷으로 변환하여 처리합니다.
    형식/값/논리/타입 오류를 세분화하여 명확한 예외 메시지를 제공합니다.
    """
    logging.info("parse_time_range() 호출: 입력 문자열 파싱 시작: %s", range_text)

    # --- 타입 검증 ---
    if not isinstance(range_text, str):
        msg = {
            "code": "TYPE_ERROR",
            "message": "입력은 문자열(str)이어야 합니다",
            "input": str(range_text)
        }
        logging.error("parse_time_range() 타입 오류: %s", msg)
        raise TypeError(json.dumps(msg, ensure_ascii=False))

    # 전처리: 트리밍 및 기본 체크
    text = (range_text or "").strip()
    if text == "":
        msg = {
            "code": "FORMAT_ERROR",
            "message": "빈 문자열은 허용되지 않습니다",
            "input": range_text,
            "hint": "예: 2025-08-08_15:00~2025-08-08_19:00 또는 2025-08-08-15:00~2025-08-08-19:00 또는 2025-08-08"
        }
        logging.error("parse_time_range() 형식 오류: %s", msg)
        raise ValueError(json.dumps(msg, ensure_ascii=False))

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
            host=db.get("host", os.getenv("DB_HOST", "127.0.0.1")),
            port=db.get("port", os.getenv("DB_PORT", 5432)),
            user=db.get("user", os.getenv("DB_USER", "postgres")),
            password=db.get("password", os.getenv("DB_PASSWORD", "")),
            dbname=db.get("dbname", os.getenv("DB_NAME", "postgres")),
        )
        # 민감정보(password)는 로그에 남기지 않는다
        logging.info("DB 연결 성공 (host=%s, dbname=%s)", db.get("host", "127.0.0.1"), db.get("dbname", "postgres"))
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

# --- 처리: N-1/N 병합 + 변화율/차트 생성 ---
def process_and_visualize(n1_df: pd.DataFrame, n_df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, str]]:
    """
    두 기간의 PEG 집계 데이터를 병합해 diff/pct_change 를 계산하고, 비교 차트를 생성합니다.

    반환:
      - processed_df: ['peg_name', 'avg_n_minus_1', 'avg_n', 'diff', 'pct_change']
      - charts: {'overall': base64_png}
    """
    # 핵심 처리 단계: 병합 → 피벗 → 변화율 산출 → 차트 생성(Base64)
    logging.info("process_and_visualize() 호출: 데이터 병합 및 시각화 시작")
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

        # 차트: 모든 셀에 대해 N-1 vs N 비교 막대그래프 (단일 이미지)
        plt.figure(figsize=(10, 6))
        processed_df.set_index("peg_name")[['avg_n_minus_1', 'avg_n']].plot(kind='bar', ax=plt.gca())
        plt.title("All PEGs: Period N vs N-1", fontsize=12)
        plt.ylabel("Average Value")
        plt.xlabel("PEG Name")
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        png_bytes = buf.read()
        overall_b64 = base64.b64encode(png_bytes).decode('utf-8')
        plt.close()
        charts = {"overall": overall_b64}

        logging.info(
            "process_and_visualize() 완료: processed_df=%d행, 차트 1개 (PNG %d bytes)",
            len(processed_df), len(png_bytes)
        )
        return processed_df, charts
    except Exception as e:
        logging.exception("process_and_visualize() 실패: %s", e)
        raise


 


# --- LLM 프롬프트 생성 (고도화된 종합 분석) ---
def create_llm_analysis_prompt_enhanced(processed_df: pd.DataFrame, n1_range: str, n_range: str) -> str:
    """
    PEG 집계 데이터를 기반으로, 연쇄적 사고 진단 워크플로우를 적용한
    전문가 수준의 종합 분석 프롬프트를 생성합니다.

    가정:
    - n-1과 n 기간은 동일한 시험환경에서 수행됨.
    - 입력 데이터(processed_df)는 PEG 단위로 집계된 상태임 (셀 단위 데이터 아님).

    기대 출력 (JSON):
    - executive_summary: 최상위 요약
    - diagnostic_findings: 구조화된 진단 결과 목록
    - recommended_actions: 우선순위가 부여된 구체적인 실행 계획 목록
    """
    logging.info("create_llm_analysis_prompt_enhanced() 호출: 고도화된 프롬프트 생성 시작")
    preview_cols = [c for c in processed_df.columns if c in ("peg_name", "avg_value", "period")]
    if not preview_cols:
        preview_cols = list(processed_df.columns)[:5]
    preview_df = processed_df[preview_cols].head(200)
    data_preview = preview_df.to_string(index=False)

    prompt = f"""
[페르소나 및 임무]
당신은 Tier-1 이동통신사에서 20년 경력을 가진 수석 네트워크 진단 및 최적화 전략가입니다. 당신의 임무는 신속한 근본 원인 분석(RCA)을 수행하고, 고객 영향도에 따라 문제의 우선순위를 정하며, 현장 엔지니어링 팀을 위한 명확하고 실행 가능한 계획을 제공하는 것입니다. 당신의 분석은 3GPP 표준(TS 36/38.xxx 시리즈)과 운영 모범 사례에 부합해야 하며, 엄격하고 증거에 기반해야 합니다.

[컨텍스트 및 가정]
- 분석 대상은 두 기간 동안의 PEG(Performance Event Group) 카운터 변화입니다.
- 기간 n-1: {n1_range}
- 기간 n: {n_range}
- 핵심 가정: 두 기간은 동일한 시험환경(동일 하드웨어, 기본 파라미터, 트래픽 모델)에서 수행되었습니다.
- 입력 데이터는 PEG 단위로 집계된 평균값이며, 개별 셀(cell) 데이터는 포함되어 있지 않습니다. 따라서 셀 단위의 특정 문제 식별은 불가능하며, 집계 데이터 기반의 거시적 분석을 수행해야 합니다.

[입력 데이터]
- 컬럼 설명: peg_name(PEG 이름), avg_n_minus_1(기간 n-1 평균), avg_n(기간 n 평균), diff(변화량), pct_change(변화율)
- 데이터 테이블:
{data_preview}

[분석 워크플로우 지침]
아래의 4단계 연쇄적 사고(Chain-of-Thought) 진단 워크플로우를 엄격히 따라서 분석을 수행하십시오.

# 1단계: 문제 분류 및 중요도 평가 (Triage and Significance Assessment)
먼저, 입력 테이블의 모든 PEG를 검토하여 가장 심각한 '부정적' 변화를 보인 상위 3~5개의 PEG를 식별하십시오. '중요도'는 'pct_change'의 절대값 크기와 해당 PEG의 운영상 '고객 영향도'를 종합하여 판단합니다. 각 PEG가 영향을 미치는 3GPP 서비스 범주(Accessibility, Retainability, Mobility, Integrity, Latency)에 따라 영향도를 분류하고, 가장 시급하게 다루어야 할 문제를 선정하십시오.

# 2단계: 주제별 그룹화 및 핵심 가설 생성 (Thematic Grouping and Primary Hypothesis Generation)
1단계에서 식별된 우선순위가 높은 문제들에 대해, 연관된 PEG들을 논리적으로 그룹화하여 '진단 주제(Diagnostic Theme)'를 정의하십시오. (예: 다수의 접속 관련 PEG 악화 -> 'Accessibility Degradation' 주제). 각 주제에 대해, 3GPP 호 처리 절차(Call Flow) 및 운영 경험에 기반하여 가장 개연성 높은 단일 '핵심 가설(Primary Hypothesis)'을 수립하십시오. 이 가설은 구체적이고 검증 가능해야 합니다.

# 3단계: 시스템적 요인 분석 및 교란 변수 고려 (Systemic Factor Analysis & Confounding Variable Assessment)
수립한 핵심 가설을 검증하기 위해, 전체 데이터 테이블에서 가설을 뒷받침하거나(supporting evidence) 반박하는(contradictory evidence) 다른 PEG 변화를 분석하십시오. 또한, '동일 환경' 가정이 깨질 수 있는 잠재적 교란 요인(예: 라우팅 정책 변경, 소프트웨어 마이너 패치, 특정 파라미터 롤백, 단말기 믹스 변화)을 명시적으로 고려하고, 이러한 요인들이 현재 문제의 원인일 가능성이 높은지 낮은지, 그리고 그 판단의 근거는 무엇인지 논리적으로 기술하십시오.

# 4단계: 증거 기반의 검증 계획 수립 (Formulation of an Evidence-Based Verification Plan)
각 핵심 가설에 대해, 현장 엔지니어가 즉시 수행할 수 있는 구체적이고 우선순위가 부여된 '검증 계획'을 수립하십시오. 조치는 반드시 구체적이어야 합니다. (예: '로그 확인' 대신 '특정 카운터(pmRachAtt) 추이 분석'). 조치별로 P1(즉시 조치), P2(심층 조사), P3(정기 감사)와 같은 우선순위를 부여하고, 필요한 데이터(카운터, 파라미터 등)나 도구를 명시하십시오.

[출력 형식 제약]
- 분석 결과는 반드시 아래의 JSON 스키마를 정확히 준수하여 생성해야 합니다.
- 모든 문자열 값은 한국어로 작성하십시오.
- 각 필드에 대한 설명과 열거형(Enum) 값을 반드시 따르십시오.


{{
  "executive_summary": "네트워크 상태 변화와 식별된 가장 치명적인 문제에 대한 1-2 문장의 최상위 요약.",
  "diagnostic_findings": [
    {{
      "primary_hypothesis": "가장 가능성 높은 단일 근본 원인 가설.",
      "supporting_evidence": "데이터 테이블 내에서 가설을 뒷받침하는 다른 PEG 변화나 논리적 근거.",
      "confounding_factors_assessment": "교란 변수들의 가능성에 대한 평가 및 그 근거."
    }}
  ],
  "recommended_actions": [
    {{
      "priority": "P1|P2|P3",
      "action": "구체적 실행 항목",
      "details": "필요 데이터/도구 및 수행 방법"
    }}
  ]
}}
"""
    logging.info("create_llm_analysis_prompt_enhanced() 완료")
    return prompt


# --- LLM 프롬프트 생성 (특정 PEG 전용 분석) ---
def create_llm_analysis_prompt_specific_pegs(processed_df_subset: pd.DataFrame, selected_pegs: list[str], n1_range: str, n_range: str) -> str:
    """
    선택된 PEG 집합에 한정된 분석 프롬프트를 생성합니다.

    기대 출력(JSON):
    {
      "summary": "특정 PEG 집합에 대한 최상위 요약",
      "peg_insights": {"PEG_A": "설명", ...},
      "prioritized_actions": [{"priority": "P1|P2|P3", "action": "...", "details": "..."}]
    }
    """
    logging.info("create_llm_analysis_prompt_specific_pegs() 호출: 선택 PEG=%s, 행수=%d", selected_pegs, len(processed_df_subset))
    preview_cols = [c for c in processed_df_subset.columns if c in ("peg_name", "avg_value", "period")]
    if not preview_cols:
        preview_cols = list(processed_df_subset.columns)[:5]
    preview_df = processed_df_subset[preview_cols].head(200)
    data_preview = preview_df.to_string(index=False)

    prompt = f"""
[페르소나 및 임무]
당신은 Tier-1 이동통신사의 수석 네트워크 최적화 전문가입니다. 아래 표는 지정된 PEG 집합에 대해서만, 두 기간(n-1, n)의 평균값/변화량/변화율을 정리한 것입니다. 지정된 PEG에 '한정하여' 분석하십시오.

[컨텍스트]
- 대상 PEG: {', '.join(selected_pegs)}
- 기간 n-1: {n1_range}
- 기간 n: {n_range}
- 표 컬럼: peg_name, avg_n_minus_1, avg_n, diff, pct_change

[데이터 표]
{data_preview}

[분석 지침]
- 각 PEG 별 핵심 관찰/의미/가능한 원인 가설을 간결히 기술하십시오.
- 변화율의 방향/크기를 근거로 운영 영향도와 위험도를 평가하십시오.
- 즉시 실행 가능한 조치 항목을 우선순위(P1/P2/P3)로 제시하십시오.

[출력 형식(JSON)]
{{
  "summary": "특정 PEG 집합에 대한 최상위 요약 (한국어)",
  "peg_insights": {{"PEG_NAME": "해당 PEG에 대한 한국어 통찰/설명"}},
  "prioritized_actions": [
    {{"priority": "P1|P2|P3", "action": "구체 조치", "details": "필요 데이터/도구/수행 방법"}}
  ]
}}
"""
    logging.info("create_llm_analysis_prompt_specific_pegs() 완료")
    return prompt

# (모킹 제거)


# --- LLM API 호출 함수 (subprocess + curl) ---
def query_llm(prompt: str, enable_mock: bool = False) -> dict:
    """내부 vLLM 서버로 분석 요청. 응답 본문에서 JSON만 추출.
    실패 시 다음 엔드포인트로 페일오버.
    
    Args:
        prompt: LLM에게 보낼 프롬프트
        enable_mock: True면 LLM 서버 연결 실패 시 가상 응답 반환
    """
    # 장애 대비를 위해 복수 엔드포인트로 페일오버. 응답에서 JSON 블록만 추출
    logging.info("query_llm() 호출: vLLM 분석 요청 시작 (enable_mock=%s)", enable_mock)

    # 환경 변수에서 LLM 엔드포인트 목록을 읽어옴 (쉼표로 구분)
    llm_endpoints_str = os.getenv('LLM_ENDPOINTS', 'http://10.251.204.93:10000,http://100.105.188.117:8888')
    endpoints = [endpoint.strip() for endpoint in llm_endpoints_str.split(',') if endpoint.strip()]

    if not endpoints:
        raise ValueError("LLM_ENDPOINTS 환경 변수가 설정되지 않았거나 비어있습니다.")

    # 환경 변수에서 모델명 읽기 (기본값: Gemma-3-27B)
    llm_model = os.getenv('LLM_MODEL', 'Gemma-3-27B')

    payload = {
        "model": llm_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 4096,
    }
    json_payload = json.dumps(payload)
    logging.info("LLM 요청 준비: endpoints=%d, prompt_length=%d", len(endpoints), len(prompt))

    for endpoint in endpoints:
        try:
            logging.info("엔드포인트 접속 시도: %s", endpoint)
            command = [
                'curl', f'{endpoint}/v1/chat/completions',
                '-H', 'Content-Type: application/json',
                '-d', json_payload,
                '--max-time', '180'
            ]
            process = subprocess.run(command, capture_output=True, check=False, encoding='utf-8', errors='ignore')
            if process.returncode != 0:
                logging.error("curl 실패 (%s): %s", endpoint, process.stderr.strip())
                continue
            if not process.stdout:
                logging.error("응답(stdout)이 비어있습니다 (%s)", endpoint)
                continue
            response_json = json.loads(process.stdout)
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
            return analysis_result
        except json.JSONDecodeError as e:
            logging.error("JSON 파싱 실패: %s", e)
            logging.error("파싱 시도 내용(1000자): %s...", cleaned_json_str[:1000])
            continue
        except Exception as e:
            logging.error("예기치 못한 오류 (%s): %s", type(e).__name__, e, exc_info=True)
            continue
    
    # 모든 엔드포인트 실패 시 예외 발생 (모킹 제거)
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


        # 그 외 상태코드는 예외로 처리
        logging.error("백엔드 POST 실패: status=%s body=%s", resp.status_code, resp.text[:500])
        resp.raise_for_status()
        return None
    except Exception as e:
        logging.exception("백엔드 POST 실패: %s", e)
        return None


# --- MCP 도구 로직 ---
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
        # 기본 백엔드 업로드 URL: 요청값 > 환경변수 > 로컬 기본값 (복수형 컬렉션 엔드포인트로 수정)
        backend_url = request.get('backend_url') or os.getenv('BACKEND_ANALYSIS_URL') or 'http://165.213.69.30:8000/api/analysis/results/'

        db = request.get('db', {})
        table = request.get('table', 'summary')
        columns = request.get('columns', {"time": "datetime", "peg_name": "peg_name", "value": "value"})

        # 파라미터 요약 로그: 민감정보는 기록하지 않음
        logging.info(
            "요청 요약: output_dir=%s, backend_url=%s, table=%s, columns=%s",
            output_dir, bool(backend_url), table, columns
        )

        # 시간 범위 파싱
        n1_start, n1_end = parse_time_range(n1_text)
        n_start, n_end = parse_time_range(n_text)
        logging.info("시간 범위: N-1(%s~%s), N(%s~%s)", n1_start, n1_end, n_start, n_end)

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

        # 처리 & 시각화 (파생 포함) - 원본 데이터 직접 사용
        logging.info("원본 데이터 직접 사용: n-1=%d행, n=%d행", len(n1_df), len(n_df))

        processed_df, charts_base64 = process_and_visualize(n1_df, n_df)
        logging.info("처리 완료: processed_df=%d행, charts=%d", len(processed_df), len(charts_base64))

        # LLM 프롬프트 & 분석 (모킹 제거: 항상 실제 호출)
        test_mode = False
        prompt = create_llm_analysis_prompt_enhanced(processed_df, n1_text, n_text)
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

                sp_prompt = create_llm_analysis_prompt_specific_pegs(subset_df, unique_selected, n1_text, n_text)
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
            if payload_size > 1 * 1024 * 1024:
                logging.warning("payload 크기 1MB 초과: %dB", payload_size)
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
    """MCP 엔드포인트: 시간 범위 기반 통합 셀 성능 분석 실행"""
    return _analyze_cell_performance_logic(request)


if __name__ == '__main__':
    import sys
    
    # CLI 모드 지원: Backend에서 subprocess로 호출 시 사용
    if len(sys.argv) > 2 and sys.argv[1] == "--request":
        try:
            request_json = sys.argv[2]
            request_data = json.loads(request_json)
            
            logging.info("CLI 모드로 LLM 분석을 실행합니다.")
            logging.info("요청 데이터: %s", json.dumps(request_data, ensure_ascii=False, indent=2))
            
            # 분석 실행
            result = _analyze_cell_performance_logic(request_data)
            
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