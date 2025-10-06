"""
요청 데이터 모델

이 모듈은 MCP 요청과 관련된 모든 데이터 모델을 정의합니다.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

# 로깅 설정
logger = logging.getLogger(__name__)


_DEFAULT_DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
_DEFAULT_DB_PORT = int(os.getenv("DB_PORT", "5432"))
_DEFAULT_DB_USER = os.getenv("DB_USER", "postgres")
_DEFAULT_DB_PASSWORD = os.getenv("DB_PASSWORD", "")
_DEFAULT_DB_NAME = os.getenv("DB_NAME", "postgres")
_DEFAULT_TABLE = os.getenv("DB_TABLE", os.getenv("DEFAULT_TABLE", "summary"))


@dataclass
class DatabaseConfig:
    """데이터베이스 연결 설정"""

    host: str = _DEFAULT_DB_HOST
    port: int = _DEFAULT_DB_PORT
    user: str = _DEFAULT_DB_USER
    password: str = _DEFAULT_DB_PASSWORD
    dbname: str = _DEFAULT_DB_NAME

    def __post_init__(self):
        """데이터베이스 설정 검증"""
        if not self.host:
            raise ValueError("데이터베이스 호스트는 필수입니다")
        if not self.user:
            raise ValueError("데이터베이스 사용자는 필수입니다")
        if not self.dbname:
            raise ValueError("데이터베이스 이름은 필수입니다")

        logger.debug(
            "DatabaseConfig 생성: host=%s, port=%d, dbname=%s (환경변수 적용)",
            self.host,
            self.port,
            self.dbname,
        )


@dataclass
class TableConfig:
    """테이블 및 컬럼 설정"""

    table: str = _DEFAULT_TABLE
    time_column: str = "datetime"
    peg_name_column: str = "peg_name"
    value_column: str = "value"
    ne_column: str = "ne"
    cellid_column: str = "cellid"
    host_column: str = "host"

    def __post_init__(self):
        """테이블 설정 검증"""
        if not self.table:
            raise ValueError("테이블 이름은 필수입니다")
        if not self.time_column:
            raise ValueError("시간 컬럼명은 필수입니다")
        if not self.peg_name_column:
            raise ValueError("PEG 이름 컬럼명은 필수입니다")
        if not self.value_column:
            raise ValueError("값 컬럼명은 필수입니다")

        logger.debug("TableConfig 생성: table=%s", self.table)


@dataclass
class FilterConfig:
    """필터링 조건 설정"""

    ne: Optional[Union[str, List[str]]] = None
    cellid: Optional[Union[str, List[str]]] = None
    cell: Optional[Union[str, List[str]]] = None  # cellid의 별칭
    host: Optional[Union[str, List[str]]] = None
    preference: Optional[Union[str, List[str]]] = None
    selected_pegs: Optional[List[str]] = None

    def __post_init__(self):
        """필터 설정 정규화"""
        # cellid와 cell 필드 통합 (cell이 있으면 cellid로 변환)
        if self.cell is not None and self.cellid is None:
            self.cellid = self.cell

        # 문자열을 리스트로 변환 (쉼표 구분)
        self._normalize_string_to_list("ne")
        self._normalize_string_to_list("cellid")
        self._normalize_string_to_list("host")
        self._normalize_string_to_list("preference")

        logger.debug("FilterConfig 생성: ne=%s, cellid=%s, host=%s", self.ne, self.cellid, self.host)

    def _normalize_string_to_list(self, field_name: str) -> None:
        """문자열 필드를 리스트로 정규화"""
        value = getattr(self, field_name)
        if isinstance(value, str) and value:
            # 쉼표로 구분된 문자열을 리스트로 변환
            normalized = [item.strip() for item in value.split(",") if item.strip()]
            setattr(self, field_name, normalized if normalized else None)


@dataclass
class PEGConfig:
    """PEG 계산 및 파생 PEG 설정"""

    peg_definitions: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        """PEG 설정 검증"""
        if self.peg_definitions:
            for peg_name, formula in self.peg_definitions.items():
                if not peg_name or not isinstance(peg_name, str):
                    raise ValueError(f"PEG 이름이 유효하지 않습니다: {peg_name}")
                if not formula or not isinstance(formula, str):
                    raise ValueError(f"PEG 수식이 유효하지 않습니다: {formula}")

        logger.debug("PEGConfig 생성: %d개 파생 PEG 정의", len(self.peg_definitions))

    def has_derived_pegs(self) -> bool:
        """파생 PEG가 정의되어 있는지 확인"""
        return bool(self.peg_definitions)


@dataclass
class AnalysisRequest:
    """셀 성능 분석 요청"""

    n_minus_1: str  # "yyyy-mm-dd_hh:mm~yyyy-mm-dd_hh:mm"
    n: str  # "yyyy-mm-dd_hh:mm~yyyy-mm-dd_hh:mm"
    output_dir: str = "./analysis_output"
    backend_url: Optional[str] = None
    db_config: DatabaseConfig = field(default_factory=DatabaseConfig)
    table_config: TableConfig = field(default_factory=TableConfig)
    filter_config: FilterConfig = field(default_factory=FilterConfig)
    peg_config: PEGConfig = field(default_factory=PEGConfig)

    def __post_init__(self):
        """요청 데이터 검증"""
        if not self.n_minus_1:
            raise ValueError("n_minus_1 시간 범위는 필수입니다")
        if not self.n:
            raise ValueError("n 시간 범위는 필수입니다")
        if not self.output_dir:
            raise ValueError("출력 디렉토리는 필수입니다")

        # 시간 범위 형식 기본 검증 (상세 검증은 TimeRangeParser에서)
        if "~" not in self.n_minus_1:
            raise ValueError("n_minus_1 시간 범위 형식이 잘못되었습니다 (예: 2025-01-01_00:00~2025-01-01_23:59)")
        if "~" not in self.n:
            raise ValueError("n 시간 범위 형식이 잘못되었습니다 (예: 2025-01-01_00:00~2025-01-01_23:59)")

        logger.info("AnalysisRequest 생성: n_minus_1=%s, n=%s", self.n_minus_1, self.n)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AnalysisRequest":
        """딕셔너리에서 AnalysisRequest 객체 생성"""
        logger.debug("딕셔너리에서 AnalysisRequest 생성 시작")

        # 기본 필드 추출
        n_minus_1 = data.get("n_minus_1") or data.get("n1")
        n = data.get("n")
        output_dir = data.get("output_dir", "./analysis_output")
        backend_url = data.get("backend_url")

        # 데이터베이스 설정
        db_data = data.get("db") or {}
        db_config = DatabaseConfig(
            host=db_data.get("host", _DEFAULT_DB_HOST),
            port=int(db_data.get("port", _DEFAULT_DB_PORT)),
            user=db_data.get("user", _DEFAULT_DB_USER),
            password=db_data.get("password", _DEFAULT_DB_PASSWORD),
            dbname=db_data.get("dbname", _DEFAULT_DB_NAME),
        )

        # 테이블 설정
        table = data.get("table", _DEFAULT_TABLE)
        columns = data.get("columns", {})
        table_config = TableConfig(
            table=table,
            time_column=columns.get("time", "datetime"),
            peg_name_column=columns.get("peg_name", "peg_name"),
            value_column=columns.get("value", "value"),
            ne_column=columns.get("ne", "ne"),
            cellid_column=columns.get("cellid", "cellid"),
            host_column=columns.get("host", "host"),
        )

        # 필터 설정
        filter_config = FilterConfig(
            ne=data.get("ne"),
            cellid=data.get("cellid"),
            cell=data.get("cell"),
            host=data.get("host"),
            preference=data.get("preference"),
            selected_pegs=data.get("selected_pegs"),
        )

        # PEG 설정
        peg_config = PEGConfig(peg_definitions=data.get("peg_definitions", {}))

        request = cls(
            n_minus_1=n_minus_1,
            n=n,
            output_dir=output_dir,
            backend_url=backend_url,
            db_config=db_config,
            table_config=table_config,
            filter_config=filter_config,
            peg_config=peg_config,
        )

        logger.info("딕셔너리에서 AnalysisRequest 생성 완료")
        return request

    def to_dict(self) -> Dict[str, Any]:
        """AnalysisRequest를 딕셔너리로 변환"""
        return {
            "n_minus_1": self.n_minus_1,
            "n": self.n,
            "output_dir": self.output_dir,
            "backend_url": self.backend_url,
            "db": {
                "host": self.db_config.host,
                "port": self.db_config.port,
                "user": self.db_config.user,
                "password": self.db_config.password,
                "dbname": self.db_config.dbname,
            },
            "table": self.table_config.table,
            "columns": {
                "time": self.table_config.time_column,
                "peg_name": self.table_config.peg_name_column,
                "value": self.table_config.value_column,
                "ne": self.table_config.ne_column,
                "cellid": self.table_config.cellid_column,
                "host": self.table_config.host_column,
            },
            "ne": self.filter_config.ne,
            "cellid": self.filter_config.cellid,
            "host": self.filter_config.host,
            "preference": self.filter_config.preference,
            "selected_pegs": self.filter_config.selected_pegs,
            "peg_definitions": self.peg_config.peg_definitions,
        }
