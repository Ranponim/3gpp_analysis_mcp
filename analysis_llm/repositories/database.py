"""
Database Repository Interface and PostgreSQL Implementation

이 모듈은 데이터베이스 액세스를 위한 Repository 패턴을 구현합니다.
추상 인터페이스와 PostgreSQL 구체 구현을 제공합니다.

기존 main.py의 데이터베이스 연결 및 쿼리 로직을 모듈화한 것입니다.
"""

from __future__ import annotations

import logging
import os
import time

# 임시로 절대 import 사용 (나중에 패키지 구조 정리 시 수정)
import sys
from abc import ABC, abstractmethod
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
import psycopg2.extras
import psycopg2.pool

# config 모듈 지연 import
_config_get_settings = None


def get_config_settings():
    """Configuration Manager에서 설정 가져오기 (지연 로딩)"""
    global _config_get_settings
    if _config_get_settings is None:
        from config import get_settings

        _config_get_settings = get_settings
    return _config_get_settings()


from ..exceptions import DatabaseError

# 로깅 설정
logger = logging.getLogger(__name__)


class DatabaseRepository(ABC):
    """
    데이터베이스 Repository 추상 기본 클래스

    데이터베이스 액세스를 위한 공통 인터페이스를 정의합니다.
    구체적인 데이터베이스 구현체들은 이 인터페이스를 구현해야 합니다.

    주요 기능:
    1. 연결 관리 (connect, disconnect)
    2. 데이터 조회 (fetch_data)
    3. 쿼리 실행 (execute_query)
    4. 동적 쿼리 생성 지원
    """

    @abstractmethod
    def connect(self) -> None:
        """
        데이터베이스 연결 설정

        Raises:
            DatabaseError: 연결 실패 시
        """

    @abstractmethod
    def disconnect(self) -> None:
        """
        데이터베이스 연결 해제

        Raises:
            DatabaseError: 연결 해제 실패 시
        """

    @abstractmethod
    def fetch_data(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
        table_name: Optional[str] = None,
        columns: Optional[List[str]] = None,
        time_range: Optional[Tuple[datetime, datetime]] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        데이터 조회 (SELECT 쿼리)

        Args:
            query (str): 실행할 SQL 쿼리
            params (Optional[Dict[str, Any]]): 쿼리 매개변수
            table_name (Optional[str]): 동적 테이블명 (쿼리에 {table} 플레이스홀더 사용 시)
            columns (Optional[List[str]]): 동적 컬럼명 (쿼리에 {columns} 플레이스홀더 사용 시)
            time_range (Optional[Tuple[datetime, datetime]]): 시간 범위 필터
            limit (Optional[int]): 결과 개수 제한

        Returns:
            List[Dict[str, Any]]: 조회 결과 (딕셔너리 리스트)

        Raises:
            DatabaseError: 쿼리 실행 실패 시
        """

    @abstractmethod
    def execute_query(self, query: str, params: Optional[Dict[str, Any]] = None, commit: bool = True) -> int:
        """
        쿼리 실행 (INSERT, UPDATE, DELETE)

        Args:
            query (str): 실행할 SQL 쿼리
            params (Optional[Dict[str, Any]]): 쿼리 매개변수
            commit (bool): 트랜잭션 커밋 여부

        Returns:
            int: 영향받은 행 수

        Raises:
            DatabaseError: 쿼리 실행 실패 시
        """

    @abstractmethod
    def test_connection(self) -> bool:
        """
        연결 테스트

        Returns:
            bool: 연결 성공 여부
        """

    def build_dynamic_query(
        self,
        base_query: str,
        table_name: Optional[str] = None,
        columns: Optional[List[str]] = None,
        time_range: Optional[Tuple[datetime, datetime]] = None,
        additional_conditions: Optional[List[str]] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        동적 쿼리 생성 (공통 유틸리티)

        Args:
            base_query (str): 기본 쿼리 템플릿
            table_name (Optional[str]): 테이블명
            columns (Optional[List[str]]): 컬럼 목록
            time_range (Optional[Tuple[datetime, datetime]]): 시간 범위
            additional_conditions (Optional[List[str]]): 추가 조건들

        Returns:
            Tuple[str, Dict[str, Any]]: (완성된 쿼리, 매개변수)
        """
        params = {}

        # 테이블명 치환
        if table_name and "{table}" in base_query:
            # SQL 인젝션 방지를 위한 기본 검증
            if not table_name.replace("_", "").replace("-", "").isalnum():
                raise DatabaseError("유효하지 않은 테이블명", details={"table_name": table_name})
            base_query = base_query.replace("{table}", table_name)

        # 컬럼명 치환
        if columns and "{columns}" in base_query:
            # SQL 인젝션 방지를 위한 기본 검증
            for col in columns:
                if not col.replace("_", "").replace("-", "").isalnum():
                    raise DatabaseError("유효하지 않은 컬럼명", details={"column": col})
            columns_str = ", ".join(columns)
            base_query = base_query.replace("{columns}", columns_str)

        # 시간 범위 조건 추가
        conditions = []
        if time_range:
            start_time, end_time = time_range
            conditions.append("timestamp BETWEEN %(start_time)s AND %(end_time)s")
            params["start_time"] = start_time
            params["end_time"] = end_time

        # 추가 조건들
        if additional_conditions:
            conditions.extend(additional_conditions)

        # WHERE 절 추가
        if conditions:
            if "WHERE" in base_query.upper():
                base_query += " AND " + " AND ".join(conditions)
            else:
                base_query += " WHERE " + " AND ".join(conditions)

        logger.debug("동적 쿼리 생성: %s (매개변수: %d개)", base_query, len(params))
        return base_query, params


class PostgreSQLRepository(DatabaseRepository):
    """
    PostgreSQL 데이터베이스 Repository 구현체

    psycopg2를 사용하여 PostgreSQL 데이터베이스에 액세스합니다.
    연결 풀링, 오류 처리, 리소스 관리를 포함합니다.

    기존 main.py의 PostgreSQL 연결 로직을 모듈화한 것입니다.
    """

    def __init__(self, config_override: Optional[Dict[str, Any]] = None):
        """
        PostgreSQLRepository 초기화

        Args:
            config_override (Optional[Dict[str, Any]]): 설정 오버라이드 (테스트용)
        """
        # Configuration Manager에서 설정 로드
        try:
            settings = get_config_settings()
            self.config = {
                "host": settings.db_host,
                "port": settings.db_port,
                "database": settings.db_name,
                "user": settings.db_user,
                "password": settings.db_password.get_secret_value(),
                "pool_size": settings.db_pool_size,
            }
            logger.info("Configuration Manager에서 DB 설정 로드 완료")
        except Exception as e:
            logger.warning("Configuration Manager 로딩 실패, 기본값 사용: %s", e)
            self.config = {
                "host": os.getenv("DB_HOST", "localhost"),
                "port": int(os.getenv("DB_PORT", "5432")),
                "database": os.getenv("DB_NAME", "postgres"),
                "user": os.getenv("DB_USER", "postgres"),
                "password": os.getenv("DB_PASSWORD", ""),
                "pool_size": int(os.getenv("DB_POOL_SIZE", "5")),
            }

        # 설정 오버라이드 적용 (테스트용)
        if config_override:
            self.config.update(config_override)
            logger.debug("DB 설정 오버라이드 적용: %s", list(config_override.keys()))

        # 연결 풀 초기화 (지연 로딩)
        self._pool = None
        self._is_connected = False

        logger.info(
            "PostgreSQLRepository 초기화 완료: host=%s, database=%s", self.config["host"], self.config["database"]
        )

    def connect(self) -> None:
        """데이터베이스 연결 풀 초기화"""
        if self._is_connected:
            logger.debug("connect(): 이미 연결된 상태 - host=%s, db=%s, pool_size=%s",
                         self.config.get("host"), self.config.get("database"), self.config.get("pool_size"))
            return

        try:
            logger.info("connect(): 연결 풀 생성 시작 | host=%s, port=%s, db=%s, pool_size=%s",
                        self.config.get("host"), self.config.get("port"), self.config.get("database"), self.config.get("pool_size"))
            t0 = time.perf_counter()
            # 연결 풀 생성
            self._pool = psycopg2.pool.SimpleConnectionPool(
                minconn=1,
                maxconn=self.config["pool_size"],
                host=self.config["host"],
                port=self.config["port"],
                database=self.config["database"],
                user=self.config["user"],
                password=self.config["password"],
            )

            self._is_connected = True
            elapsed = (time.perf_counter() - t0) * 1000
            logger.info(
                "connect(): 연결 풀 생성 완료 | host=%s, db=%s, pool_size=%s, %.1fms",
                self.config["host"], self.config["database"], self.config["pool_size"], elapsed
            )

        except psycopg2.Error as e:
            raise DatabaseError(
                "PostgreSQL 연결 실패",
                details={
                    "host": self.config["host"],
                    "database": self.config["database"],
                    "error": str(e),
                },
                connection_info=self.get_connection_info(),
            ) from e

    def disconnect(self) -> None:
        """데이터베이스 연결 풀 해제"""
        if not self._is_connected or not self._pool:
            logger.debug("disconnect(): 연결되지 않은 상태 - 무시")
            return

        try:
            logger.info("disconnect(): 연결 풀 해제 시작")
            self._pool.closeall()
            self._pool = None
            self._is_connected = False
            logger.info("disconnect(): 연결 풀 해제 완료")

        except Exception as e:
            logger.error("연결 풀 해제 중 오류: %s", e)
            raise DatabaseError("연결 풀 해제 실패") from e

    @contextmanager
    def get_connection(self):
        """
        연결 풀에서 연결 획득 (컨텍스트 매니저)

        Yields:
            psycopg2.connection: 데이터베이스 연결
        """
        if not self._is_connected or not self._pool:
            raise DatabaseError("연결 풀이 초기화되지 않았습니다. connect()를 먼저 호출하세요")

        connection = None
        try:
            t0 = time.perf_counter()
            connection = self._pool.getconn()
            elapsed = (time.perf_counter() - t0) * 1000
            logger.debug("get_connection(): 연결 획득 완료 (%.1fms)", elapsed)
            yield connection

        except psycopg2.Error as e:
            if connection:
                connection.rollback()
            raise DatabaseError("데이터베이스 연결 오류") from e

        finally:
            if connection:
                self._pool.putconn(connection)
                logger.debug("get_connection(): 연결 반환 완료")

    def test_connection(self) -> bool:
        """연결 테스트"""
        try:
            if not self._is_connected:
                self.connect()

            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    result = cursor.fetchone()
                    success = result is not None

            logger.info("연결 테스트 %s", "성공" if success else "실패")
            return success

        except Exception as e:
            logger.error("연결 테스트 실패: %s", e)
            return False

    def fetch_data(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
        table_name: Optional[str] = None,
        columns: Optional[List[str]] = None,
        time_range: Optional[Tuple[datetime, datetime]] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        데이터 조회 (SELECT 쿼리)

        기존 main.py의 데이터베이스 조회 로직을 모듈화한 것입니다.
        """
        logger.debug(
            "fetch_data(): 호출 | query_len=%d, preview=%s, params_keys=%s, table=%s, time_range=%s, limit=%s",
            len(query or ""), (query or "")[:180].replace("\n", " "),
            list((params or {}).keys()), table_name, time_range, limit
        )

        if not self._is_connected:
            self.connect()

        # 동적 쿼리 생성
        if table_name or columns or time_range:
            query, dynamic_params = self.build_dynamic_query(query, table_name, columns, time_range)
            # 매개변수 병합
            if params:
                dynamic_params.update(params)
            params = dynamic_params

        # LIMIT 절 추가
        if limit and limit > 0:
            query += f" LIMIT {limit}"

        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                    # 쿼리 실행
                    t0 = time.perf_counter()
                    cursor.execute(query, params or {})

                    # 결과 조회
                    results = cursor.fetchall()

                    # RealDictRow를 일반 딕셔너리로 변환
                    data = [dict(row) for row in results]
                    elapsed = (time.perf_counter() - t0) * 1000
                    logger.info(
                        "fetch_data(): 조회 완료 | rows=%d, %.1fms, params_keys=%s",
                        len(data), elapsed, list((params or {}).keys())
                    )
                    return data

        except psycopg2.Error as e:
            error_msg = f"데이터 조회 실패: {e}"
            logger.error(error_msg)
            raise DatabaseError(
                error_msg,
                details={
                    "query": query[:200],
                    "params": params,
                    "error_code": e.pgcode if hasattr(e, "pgcode") else None,
                },
            ) from e

    def execute_query(self, query: str, params: Optional[Dict[str, Any]] = None, commit: bool = True) -> int:
        """
        쿼리 실행 (INSERT, UPDATE, DELETE)

        기존 main.py의 쿼리 실행 로직을 모듈화한 것입니다.
        """
        logger.debug(
            "execute_query(): 호출 | query_len=%d, preview=%s, commit=%s, params_keys=%s",
            len(query or ""), (query or "")[:180].replace("\n", " "), commit, list((params or {}).keys())
        )

        if not self._is_connected:
            self.connect()

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # 쿼리 실행
                    t0 = time.perf_counter()
                    cursor.execute(query, params or {})

                    # 영향받은 행 수
                    rowcount = cursor.rowcount

                    # 트랜잭션 처리
                    if commit:
                        conn.commit()
                        logger.debug("트랜잭션 커밋 완료")

                    elapsed = (time.perf_counter() - t0) * 1000
                    logger.info("execute_query(): 완료 | affected=%d, %.1fms", rowcount, elapsed)
                    return rowcount

        except psycopg2.Error as e:
            error_msg = f"쿼리 실행 실패: {e}"
            logger.error(error_msg)
            raise DatabaseError(
                error_msg,
                details={
                    "query": query[:200],
                    "params": params,
                    "error_code": e.pgcode if hasattr(e, "pgcode") else None,
                },
            ) from e

    def fetch_peg_data(
        self,
        table_name: str,
        columns: Dict[str, str],
        time_range: Tuple[datetime, datetime],
        filters: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        PEG 데이터 전용 조회 메서드 (기존 main.py 로직 기반)

        Args:
            table_name (str): 테이블명
            columns (Dict[str, str]): 컬럼 매핑 (time, peg_name, value, ne, cellid, host)
            time_range (Tuple[datetime, datetime]): 시간 범위
            filters (Optional[Dict[str, Any]]): 추가 필터 조건
            limit (Optional[int]): 결과 개수 제한

        Returns:
            List[Dict[str, Any]]: PEG 데이터 목록
        """
        logger.info("fetch_peg_data(): 호출 | table=%s, time_range=%s, filters_keys=%s",
                    table_name, time_range, list((filters or {}).keys()))

        # JSONB 기반 스키마 여부 판별 (values/family_name 존재 시)
        json_mode = ('values' in columns) or ('family_name' in columns)

        # WHERE 조건 구성 공통
        conditions: List[str] = []
        params: Dict[str, Any] = {}
        start_time, end_time = time_range

        if json_mode:
            time_col = columns.get('time', 'datetime')
            values_col = columns.get('values', 'values')
            family_col = columns.get('family_name', 'family_name')
            ne_col = columns.get('ne') or columns.get('ne_key') or 'ne_key'
            host_col = columns.get('host') or columns.get('name') or 'name'
            relver_col = columns.get('rel_ver', 'rel_ver')
            # 차원(alias) 매핑: JSONB index_name → 필터 키
            dimension_alias_map = {
                'cellid': 'CellIdentity',
                'qci': 'QCI',
                'bpu_id': 'BPU_ID',
            }
            logger.debug(
                "fetch_peg_data(): JSONB 모드 | cols={time:%s,family:%s,values:%s,ne:%s,host:%s,rel_ver:%s} | dims=%s",
                time_col, family_col, values_col, ne_col, host_col, relver_col, dimension_alias_map
            )

            # 두 단계 확장:
            # 1) 최상위 인덱스/키를 펼침 (idx)
            # 2) 객체면 내부 PEG를, 스칼라이면 (idx.key, idx.val)로 치환해 metric으로 펼침
            #    peg_name은 객체일 때 'metric.key[idx.key]' 형식으로 만들어 파이프라인 변경 없이 차원 포함
            peg_name_expr = (
                "(CASE WHEN jsonb_typeof(idx.val) = 'object' "
                "THEN (metric.key || '[' || idx.key || ']') "
                "ELSE metric.key END) AS peg_name"
            )

            select_parts: List[str] = [
                f"t.{time_col} AS timestamp",
                f"t.{family_col} AS family_name",
                peg_name_expr,
                "NULLIF(regexp_replace(metric.value, '[^0-9\\.\\-eE]', '', 'g'), '')::numeric AS value",
            ]

            # 선택적 컬럼들 추가 (존재 시)
            if ne_col:
                select_parts.append(f"t.{ne_col} AS ne")
            if host_col:
                select_parts.append(f"t.{host_col} AS host")
            if relver_col:
                select_parts.append(f"t.{relver_col} AS rel_ver")

            query = (
                f"SELECT {', '.join(select_parts)} FROM {table_name} t "
                f"CROSS JOIN LATERAL jsonb_each(t.{values_col}) AS idx(key, val) "
                f"CROSS JOIN LATERAL jsonb_each_text("
                f"CASE WHEN jsonb_typeof(idx.val) = 'object' THEN idx.val ELSE jsonb_build_object(idx.key, idx.val) END"
                f") AS metric(key, value)"
            )
            logger.debug("fetch_peg_data(): SELECT 구성 완료 | select_parts=%s", select_parts)

            # 시간 조건 (별칭 t.)
            conditions.append(f"t.{time_col} BETWEEN %(start_time)s AND %(end_time)s")
            params['start_time'] = start_time
            params['end_time'] = end_time

            # 추가 필터
            if filters:
                index_name_expr = f"jsonb_extract_path_text(t.{values_col}, 'index_name')"

                # 1) 차원 필터(cellid/qci/bpu_id 등):
                #    원칙 - 어떤 차원 필터가 와도 해당 index_name에는 key 조건을 적용하고,
                #           그 외 index_name은 항상 포함(무조건 파싱)되도록 OR 그룹 구성
                dim_filters = {k: v for k, v in filters.items() if k in dimension_alias_map and v is not None}
                if dim_filters:
                    logger.debug("fetch_peg_data(): 차원 필터 감지 | %s", {k: (v if isinstance(v, (list,tuple,set)) else [v]) for k,v in dim_filters.items()})
                    per_dim_clauses: List[str] = []
                    dim_in_names: List[str] = []
                    for dim_key, dim_value in dim_filters.items():
                        iname = dimension_alias_map[dim_key]
                        dim_in_names.append(iname)
                        pname_iname = f"{dim_key}_index_name"
                        params[pname_iname] = iname
                        if isinstance(dim_value, (list, tuple, set)) and dim_value:
                            placeholders = ",".join([f"%({dim_key}_{i})s" for i, _ in enumerate(dim_value)])
                            for i, v in enumerate(dim_value):
                                params[f"{dim_key}_{i}"] = str(v)
                            per_dim_clauses.append(f"( {index_name_expr} = %({pname_iname})s AND idx.key IN ({placeholders}) )")
                        else:
                            params[dim_key] = str(dim_value)
                            per_dim_clauses.append(f"( {index_name_expr} = %({pname_iname})s AND idx.key = %({dim_key})s )")

                    # others clause: index_name이 어떤 지정 iname에도 속하지 않거나 NULL인 경우 모두 포함
                    other_names_placeholders = ",".join([f"%(dim_iname_{i})s" for i in range(len(dim_in_names))])
                    for i, nm in enumerate(dim_in_names):
                        params[f"dim_iname_{i}"] = nm
                    others_clause = f"( {index_name_expr} IS NULL OR {index_name_expr} NOT IN ({other_names_placeholders}) )"

                    clause_preview = " OR ".join(per_dim_clauses + ["..."])
                    logger.debug("fetch_peg_data(): 차원 필터 WHERE 구성 | preview=%s", clause_preview[:160])
                    conditions.append("( " + " OR ".join(per_dim_clauses + [others_clause]) + " )")

                # 2) 테이블 컬럼 기반 필터 (columns 매핑된 키만 허용, t. 접두사 적용)
                for key, value in filters.items():
                    if value is None:
                        continue
                    col_name = columns.get(key)
                    if not col_name:
                        continue
                    qualified = f"t.{col_name}"
                    if isinstance(value, (list, tuple, set)) and value:
                        placeholders = ",".join([f"%({key}_{i})s" for i, _ in enumerate(value)])
                        conditions.append(f"{qualified} IN ({placeholders})")
                        for i, v in enumerate(value):
                            params[f"{key}_{i}"] = v
                    else:
                        conditions.append(f"{qualified} = %({key})s")
                        params[key] = value

            # 메타/비수치 값 제외 조건
            conditions.append("metric.key <> 'index_name'")
            conditions.append("NULLIF(regexp_replace(metric.value, '[^0-9\\.\\-eE]', '', 'g'), '') <> ''")

            if conditions:
                logger.debug("fetch_peg_data(): WHERE 구성 | %d개 조건", len(conditions))
                query += " WHERE " + " AND ".join(conditions)

            query += f" ORDER BY t.{time_col}"
            if limit and limit > 0:
                query += f" LIMIT {limit}"

            logger.info(
                "fetch_peg_data(): JSONB 2단계 확장 모드(A안) 쿼리 구성 완료 | sql_len=%d, params_keys=%s",
                len(query), list(params.keys())
            )
            return self.fetch_data(query, params)

        # 비-JSONB 레거시 스키마: 기존 경로 유지
        select_columns = [
            f"{columns['time']} as timestamp",
            f"{columns['peg_name']} as peg_name",
            f"{columns['value']} as value",
        ]

        # 선택적 컬럼들 추가
        optional_columns = ["ne", "cellid", "host"]
        for col_key in optional_columns:
            if col_key in columns and columns[col_key]:
                select_columns.append(f"{columns[col_key]} as {col_key}")

        # 쿼리 구성
        query = f"SELECT {', '.join(select_columns)} FROM {table_name}"

        # 시간 범위 조건
        conditions.append(f"{columns['time']} BETWEEN %(start_time)s AND %(end_time)s")
        params["start_time"] = start_time
        params["end_time"] = end_time

        # 추가 필터 조건 (컬럼 매핑된 키만)
        if filters:
            for key, value in filters.items():
                if key in columns and value is not None:
                    col_name = columns[key]
                    if isinstance(value, (list, tuple, set)) and value:
                        placeholders = ",".join([f"%({key}_{i})s" for i, _ in enumerate(value)])
                        conditions.append(f"{col_name} IN ({placeholders})")
                        for i, v in enumerate(value):
                            params[f"{key}_{i}"] = v
                    else:
                        conditions.append(f"{col_name} = %({key})s")
                        params[key] = value

        # WHERE 절 추가
        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        # 정렬 (시간순)
        query += f" ORDER BY {columns['time']}"

        # LIMIT 추가
        if limit and limit > 0:
            query += f" LIMIT {limit}"

        return self.fetch_data(query, params)

    def get_table_info(self, table_name: str) -> Dict[str, Any]:
        """
        테이블 정보 조회

        Args:
            table_name (str): 테이블명

        Returns:
            Dict[str, Any]: 테이블 정보 (컬럼, 인덱스 등)
        """
        logger.debug("get_table_info() 호출: table=%s", table_name)

        # 컬럼 정보 조회
        column_query = """
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns 
        WHERE table_name = %(table_name)s
        ORDER BY ordinal_position
        """

        columns = self.fetch_data(column_query, {"table_name": table_name})

        # 인덱스 정보 조회
        index_query = """
        SELECT indexname, indexdef
        FROM pg_indexes 
        WHERE tablename = %(table_name)s
        """

        indexes = self.fetch_data(index_query, {"table_name": table_name})

        return {
            "table_name": table_name,
            "columns": columns,
            "indexes": indexes,
            "column_count": len(columns),
            "index_count": len(indexes),
        }

    def get_connection_info(self) -> Dict[str, Any]:
        """연결 정보 반환 (민감 정보 제외)"""
        return {
            "host": self.config["host"],
            "port": self.config["port"],
            "database": self.config["database"],
            "user": self.config["user"],
            "pool_size": self.config["pool_size"],
            "is_connected": self._is_connected,
            "pool_status": "active" if self._pool else "inactive",
        }

    def __enter__(self):
        """컨텍스트 매니저 진입"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """컨텍스트 매니저 종료"""
        self.disconnect()

        # 예외 발생 시 로그 기록
        if exc_type:
            logger.error("컨텍스트 매니저에서 예외 발생: %s", exc_val)

        return False  # 예외를 다시 발생시킴
