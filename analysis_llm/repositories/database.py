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
from typing import Any, Dict, List, Optional, Set, Tuple

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
                "host": os.getenv("DB_HOST", "165.213.69.30"),
                "port": int(os.getenv("DB_PORT", "5442")),
                "database": os.getenv("DB_NAME", "pvt_db"),
                "user": os.getenv("DB_USER", "testuser"),
                "password": os.getenv("DB_PASSWORD", "1234qwer"),
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

            # --- [수정] 환경변수(APP_TIMEZONE)를 읽어 세션 타임존 설정 ---
            try:
                settings = get_config_settings()
                app_timezone = settings.app_timezone
                if app_timezone:
                    with connection.cursor() as cursor:
                        # SQL 인젝션 방지를 위해 파라미터화된 쿼리 사용
                        cursor.execute("SET TIME ZONE %(timezone)s", {'timezone': app_timezone})
                    logger.debug("세션 타임존 설정 완료: %s", app_timezone)
            except Exception as e:
                logger.warning("세션 타임존 설정 중 오류 발생 (APP_TIMEZONE): %s", e)
            # --- [수정] ---

            elapsed = (time.perf_counter() - t0) * 1000
            logger.debug("get_connection(): 연결 획득 완료 (%.1fms)", elapsed)
            yield connection

        except psycopg2.Error as e:
            if connection:
                connection.rollback()
            raise DatabaseError(
                "데이터베이스 연결 오류",
                details={"error": str(e)},
                connection_info=self.get_connection_info(),
            ) from e

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
                    first_keys = list(data[0].keys()) if data else []
                    logger.info(
                        "fetch_data(): 조회 완료 | rows=%d, %.1fms, table=%s, window=%s, limit=%s, params_keys=%s, first_keys=%s",
                        len(data), elapsed, table_name, time_range, limit, list((params or {}).keys()), first_keys
                    )
                    return data

        except DatabaseError as e:
            # 연결 획득 단계에서 발생한 DatabaseError에 쿼리/파라미터/연결정보를 보강
            error_msg = getattr(e, "message", "데이터베이스 오류")
            logger.error("fetch_data(): 연결 오류 | %s", error_msg)
            raise DatabaseError(
                error_msg,
                details={
                    "original": getattr(e, "details", None),
                    "query": (query or "")[:1000],
                    "params": params,
                },
                query=query,
                connection_info=self.get_connection_info(),
            ) from e
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
                query=query,
                connection_info=self.get_connection_info(),
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

        except DatabaseError as e:
            # 연결 획득 단계에서 발생한 DatabaseError에 쿼리/파라미터/연결정보를 보강
            error_msg = getattr(e, "message", "데이터베이스 오류")
            logger.error("execute_query(): 연결 오류 | %s", error_msg)
            raise DatabaseError(
                error_msg,
                details={
                    "original": getattr(e, "details", None),
                    "query": (query or "")[:1000],
                    "params": params,
                },
                query=query,
                connection_info=self.get_connection_info(),
            ) from e
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
                query=query,
                connection_info=self.get_connection_info(),
            ) from e

    def fetch_peg_data(
        self,
        table_name: str,
        columns: Dict[str, str],
        time_range: Tuple[datetime, datetime],
        filters: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
        peg_filter: Optional[Dict[int, Set[str]]] = None,
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
        # 입력 딕셔너리 보호: filters를 수정하지 않도록 복사본 생성
        # 버그 수정: del filters['ne']로 입력 딕셔너리를 직접 수정하는 것을 방지
        if filters is not None:
            filters = filters.copy()  # None이 아닌 경우 복사 (빈 딕셔너리 포함)
        
        logger.info("fetch_peg_data(): 호출 | table=%s, time_range=%s, filters_keys=%s",
                    table_name, time_range, list((filters or {}).keys()))
        # 컨텍스트 요약 로그
        try:
            logger.info(
                "fetch_peg_data(): 컨텍스트 | table=%s | start=%s | end=%s | columns_keys=%s | filters=%s | limit=%s",
                table_name,
                time_range[0] if time_range else None,
                time_range[1] if time_range else None,
                list((columns or {}).keys()),
                (filters or {}),
                limit,
            )
        except Exception:
            logger.debug("fetch_peg_data(): 컨텍스트 로깅 스킵")
        # Columns 매핑 디버그 로그 (키/값과 JSONB 감지 결과 출력)
        try:
            logger.debug(
                "fetch_peg_data(): columns keys=%s, values=%s",
                list((columns or {}).keys()), list((columns or {}).values()),
            )
        except Exception:
            logger.debug("fetch_peg_data(): columns 로깅 실패 (비정형 입력)")

        # JSONB 기반 스키마 여부 판별 (values 존재 시)
        json_mode = (
            ('values' in (columns or {}))
            or ('values' in list((columns or {}).values()))
            or ('family_id' in (columns or {}))
        )
        logger.debug("fetch_peg_data(): JSONB 감지 결과 | json_mode=%s", json_mode)

        # WHERE 조건 구성 공통
        conditions: List[str] = []
        params: Dict[str, Any] = {}
        start_time, end_time = time_range

        if json_mode:
            # 설정에서 재귀 깊이 제한 가져오기
            try:
                settings = get_config_settings()
                max_recursion_depth = settings.jsonb_max_recursion_depth
                logger.debug("fetch_peg_data(): 재귀 깊이 제한=%d (from settings)", max_recursion_depth)
            except Exception as e:
                max_recursion_depth = 5  # 기본값
                logger.warning("fetch_peg_data(): 설정 로드 실패, 기본 재귀 깊이=%d 사용 (%s)", max_recursion_depth, e)
            
            time_col = columns.get('time', 'datetime')
            values_col = columns.get('values', 'values')
            # DB 컬럼: family_id (int), family_name (char)
            # CSV에서 로드된 family_id는 정수로 유지됨
            family_id_col = columns.get('family_id', 'family_id')
            family_name_col = columns.get('family_name', 'family_name')
            ne_col = columns.get('ne') or columns.get('ne_key') or 'ne_key'
            swname_col = columns.get('swname', 'swname')
            relver_col = columns.get('rel_ver', 'rel_ver')
            # 차원(alias) 매핑: JSONB index_name → 필터 키
            dimension_alias_map = {
                'cellid': 'CellIdentity',
                'qci': 'QCI',
                'bpu_id': 'BPU_ID',
            }
            logger.debug(
                "fetch_peg_data(): JSONB 모드 | cols={time:%s,family_id:%s,family_name:%s,values:%s,ne:%s,swname:%s,rel_ver:%s} | dims=%s",
                time_col, family_id_col, family_name_col, values_col, ne_col, swname_col, relver_col, dimension_alias_map
            )

            # WHERE 조건 구성 (CTE Anchor용)
            cte_anchor_conditions = [f"t.{time_col} BETWEEN %(start_time)s AND %(end_time)s"]

            # --- [CSV 필터 로직] ---
            # 1. family_id 필터링 (CSV의 family_id는 정수로 유지됨)
            if peg_filter:
                family_ids_to_filter = list(peg_filter.keys())
                if family_ids_to_filter:
                    # family_id_col은 DB의 family_id 컬럼 (int)
                    # peg_filter의 키는 CSV에서 로드한 family_id 정수 (예: 5002)
                    placeholders = ",".join([f"%(family_filter_{i})s" for i, _ in enumerate(family_ids_to_filter)])
                    cte_anchor_conditions.append(f"t.{family_id_col} IN ({placeholders})")
                    for i, v in enumerate(family_ids_to_filter):
                        params[f"family_filter_{i}"] = int(v)  # 명시적 정수 변환
                    logger.info("CSV 필터 적용: %d개 family_id로 필터링 (값: %s)", len(family_ids_to_filter), family_ids_to_filter[:5])
            # --- [로직 완료] ---
            params['start_time'] = start_time
            params['end_time'] = end_time

            # ne_id 필터를 CTE anchor로 이동
            if filters and 'ne' in filters and filters['ne']:
                ne_values = filters['ne']
                ne_col_name = columns.get('ne') or columns.get('ne_key') or 'ne_key'
                
                logger.info("🔍 ne 필터 적용: 컬럼=%s, 값=%s", ne_col_name, ne_values)
                
                if isinstance(ne_values, (list, tuple, set)):
                    # ne_id가 여러 개일 경우 IN 사용
                    placeholders = ",".join([f"%(ne_filter_{i})s" for i, _ in enumerate(ne_values)])
                    cte_anchor_conditions.append(f"t.{ne_col_name} IN ({placeholders})")
                    for i, v in enumerate(ne_values):
                        # ne_key 컬럼은 정수이므로 변환
                        try:
                            params[f"ne_filter_{i}"] = int(v)
                        except (ValueError, TypeError):
                            # 변환 실패 시 원본 값 사용 (로깅)
                            logger.warning("ne 필터 값 변환 실패: %s (원본 사용)", v)
                            params[f"ne_filter_{i}"] = v
                    logger.debug("ne 필터: IN 조건으로 %d개 값 적용", len(ne_values))
                else:
                    # ne_id가 단일 값일 경우
                    cte_anchor_conditions.append(f"t.{ne_col_name} = %(ne_filter)s")
                    # ne_key 컬럼은 정수이므로 변환
                    try:
                        params['ne_filter'] = int(ne_values)
                    except (ValueError, TypeError):
                        # 변환 실패 시 원본 값 사용 (로깅)
                        logger.warning("ne 필터 값 변환 실패: %s (원본 사용)", ne_values)
                        params['ne_filter'] = ne_values
                    logger.debug("ne 필터: 단일 값 조건 적용")
                
                # 처리된 필터는 나중에 중복 적용되지 않도록 제거
                del filters['ne']
            else:
                logger.debug("ne 필터: 적용되지 않음 (filters=%s)", filters.get('ne') if filters else None)

            # index_name 키는 메타데이터이므로 모든 레벨에서 제외
            cte_anchor_conditions.append("kv.key <> 'index_name'")
            cte_anchor_where_clause = " AND ".join(cte_anchor_conditions)

            # 재귀적 JSONB 확장 (중첩된 index_name 구조 완전히 펼치기)
            # 
            # 🔑 핵심: index_name은 형제 노드로 존재하므로 부모 객체도 함께 전달
            # 예시 구조: {"20": {...}, "36": {...}, "index_name": "CellIdentity"}
            recursive_cte = f"""
            WITH RECURSIVE flattened AS (
                -- 초기: 최상위 values에서 키-값 쌍 추출
                SELECT 
                    t.{time_col} AS timestamp,
                    t.{family_id_col} AS family_id,
                    t.{family_name_col} AS family_name,
                    {"t." + ne_col + " AS ne," if ne_col else ""}
                    {"t." + swname_col + " AS swname," if swname_col else ""}
                    {"t." + relver_col + " AS rel_ver," if relver_col else ""}
                    kv.key AS path_key,
                    kv.value AS current_val,
                    t.{values_col} AS parent_obj,  -- 부모 객체 보존 (형제 index_name 접근용)
                    -- 🔑 Anchor: parent_obj(전체 values)에서 index_name 추출
                    CASE 
                        WHEN jsonb_extract_path_text(t.{values_col}, 'index_name') IS NOT NULL
                        THEN ARRAY[jsonb_extract_path_text(t.{values_col}, 'index_name')]
                        ELSE ARRAY[]::text[]
                    END AS dimension_names,
                    ARRAY[kv.key] AS dimension_values,
                    0 AS depth
                FROM {table_name} t
                CROSS JOIN LATERAL jsonb_each(t.{values_col}) AS kv(key, value)
                WHERE {cte_anchor_where_clause}
                
                UNION ALL
                
                -- 재귀: 객체면 한 단계 더 펼치기 + index_name 누적
                SELECT 
                    f.timestamp,
                    f.family_id,
                    f.family_name,
                    {"f.ne," if ne_col else ""}
                    {"f.swname," if swname_col else ""}
                    {"f.rel_ver," if relver_col else ""}
                    kv.key AS path_key,
                    kv.value AS current_val,
                    f.current_val AS parent_obj,  -- 현재 레벨을 다음 단계의 부모로 전달
                    -- 🔑 현재 객체(current_val)에서 형제 index_name 추출
                    -- current_val이 객체면 그 안에서 index_name을 찾음
                    CASE 
                        WHEN jsonb_typeof(f.current_val) = 'object' 
                             AND jsonb_extract_path_text(f.current_val, 'index_name') IS NOT NULL
                        THEN f.dimension_names || jsonb_extract_path_text(f.current_val, 'index_name')
                        ELSE f.dimension_names
                    END AS dimension_names,
                    f.dimension_values || kv.key AS dimension_values,
                    f.depth + 1 AS depth
                FROM flattened f
                CROSS JOIN LATERAL jsonb_each(f.current_val) AS kv(key, value)
                WHERE jsonb_typeof(f.current_val) = 'object'
                  AND kv.key <> 'index_name'  -- index_name은 메타데이터이므로 제외
                  AND f.depth < %(max_recursion_depth)s  -- 설정된 재귀 깊이 제한
            )
            """
            
            # 재귀 깊이 파라미터 추가
            params['max_recursion_depth'] = max_recursion_depth
            
            # 최종 SELECT: 리프 노드(스칼라 값)만 선택
            # dimension_names와 dimension_values를 조합하여 차원 정보 구성
            select_parts: List[str] = [
                "timestamp",
                "family_id",
                "family_name",
            ]
            if ne_col:
                select_parts.append("ne")
            if swname_col:
                select_parts.append("swname")
            if relver_col:
                select_parts.append("rel_ver")
            
            # peg_name: path_key (리프 노드의 키, 즉 실제 PEG 메트릭명)
            select_parts.append("path_key AS peg_name")
            
            # value: 숫자면 숫자로, 문자면 NULL
            # - JSONB number 타입 → 숫자로 변환
            # - JSONB string 타입이고 숫자로 시작 → 숫자 변환 시도
            # - 그 외(null, -, NA, N/D 등) → NULL (text_value에 보존)
            # 
            # 🔑 중요: current_val#>>'{}'는 JSONB 값을 따옴표 없이 텍스트로 추출
            # 예: JSONB "266510.50" → 텍스트 266510.50 (따옴표 제거!)
            select_parts.append(
                "CASE "
                "  WHEN jsonb_typeof(current_val) = 'number' THEN (current_val::text)::double precision "
                "  WHEN jsonb_typeof(current_val) = 'string' AND (current_val#>>'{}') ~ '^\\s*[+-]?\\d' "
                "    THEN (regexp_replace(current_val#>>'{}', '[^0-9\\.\\-eE]', '', 'g'))::double precision "
                "  ELSE NULL "
                "END AS value"
            )
            
            # text_value: 숫자로 파싱 실패한 경우에만 값 보존 (NA, -, N/D, null 등)
            # - 숫자로 파싱 성공 시 → NULL (중복 방지)
            # - 숫자가 아닌 텍스트 → 원본 보존 (디버깅/분석용)
            # 
            # 🎯 목적: value와 text_value가 동시에 값을 갖지 않도록 함
            # 예: value=266510.50, text_value=NULL ✅
            #     value=NULL, text_value='NA' ✅
            select_parts.append(
                "CASE "
                "  WHEN jsonb_typeof(current_val) = 'number' THEN NULL "  # 숫자 타입이면 text_value는 NULL
                "  WHEN jsonb_typeof(current_val) = 'string' THEN "
                "    CASE "
                "      WHEN (current_val#>>'{}') ~ '^\\s*[+-]?\\d' THEN NULL "  # 숫자로 파싱 가능하면 NULL
                "      ELSE current_val#>>'{}' "  # 숫자가 아니면 텍스트 보존 (NA, -, N/D 등)
                "    END "
                "  ELSE NULL "
                "END AS text_value"
            )
            
            # 차원 정보: CTE에서 이미 계산된 dimension_names와 dimension_values를 사용
            # WHERE 절에서 사용할 수 있도록 외부 쿼리에서 dimensions 계산
            select_parts.append("dimension_names")
            select_parts.append("dimension_values")
            
            # 기본 쿼리: flattened CTE에서 리프 노드만 선택
            inner_query = (
                f"{recursive_cte} "
                f"SELECT {', '.join(select_parts)} FROM flattened "
                f"WHERE jsonb_typeof(current_val) <> 'object'"  # 리프 노드만 (스칼라 값)
            )
            logger.debug("fetch_peg_data(): 재귀 CTE 구성 완료 | select_parts=%s", select_parts)



            # 추가 필터 (재귀 CTE 후 적용)
            additional_conditions: List[str] = []
            
            # inner_data에서 선택 가능한 컬럼 목록 정의
            # 이 컬럼들은 outer_select_parts에도 포함되어야 함
            inner_data_columns = {'timestamp', 'family_id', 'family_name', 'peg_name', 'value', 'text_value', 'dimension_names', 'dimension_values'}
            if ne_col:
                inner_data_columns.add('ne')
            if swname_col:
                inner_data_columns.add('swname')
            if relver_col:
                inner_data_columns.add('rel_ver')

            # --- [CSV 필터 로직] ---
            # 2. peg_name 필터링 (family_id는 이미 CTE anchor에서 필터링됨)
            if peg_filter:
                peg_name_filter_clauses = []
                # 각 family_id와 peg_name 목록에 대해 OR 조건 생성
                for i, (family_id, peg_names) in enumerate(peg_filter.items()):
                    if not peg_names:
                        continue
                    
                    family_param_key = f"csv_family_{i}"
                    
                    # 각 PEG 이름에 대해 LIKE 조건 생성
                    # CSV: "AirMacDLThruAvg" → DB: "AirMacDLThruAvg(Kbps)" 매칭
                    peg_like_conditions = []
                    for j, peg_name in enumerate(peg_names):
                        peg_param_key = f"csv_peg_{i}_{j}"
                        # peg_name이 CSV peg_name으로 시작하는 경우 매칭 (LIKE 'AirMacDLThruAvg%')
                        peg_like_conditions.append(f"peg_name LIKE %({peg_param_key})s")
                        params[peg_param_key] = f"{peg_name}%"  # 접두어 매칭
                    
                    # (family_id = %s AND (peg_name LIKE %s OR peg_name LIKE %s ...))
                    # family_id는 DB의 family_id 컬럼 (int)
                    # family_id는 CSV에서 로드한 정수 (예: 5002)
                    peg_conditions_str = " OR ".join(peg_like_conditions)
                    clause = f"(family_id = %({family_param_key})s AND ({peg_conditions_str}))"
                    peg_name_filter_clauses.append(clause)
                    
                    # family_id 파라미터 추가 (정수로 명시적 변환)
                    params[family_param_key] = int(family_id)
                
                if peg_name_filter_clauses:
                    additional_conditions.append(f"({' OR '.join(peg_name_filter_clauses)})")
                    logger.info("CSV 필터 적용: %d개 family_id/peg 조합으로 필터링 (LIKE 패턴 매칭)", len(peg_name_filter_clauses))
            # --- [로직 완료] ---
            
            if filters:
                for key, value in filters.items():
                    if value is None:
                        continue
                    
                    # 차원 필터 (cellid, qci, bpu_id) - dimensions 컬럼에서 검색
                    if key in dimension_alias_map:
                        dimension_key = dimension_alias_map[key]
                        logger.info("🔍 차원 필터 적용: 필터키=%s, 차원키=%s, 값=%s", key, dimension_key, value)
                        
                        # dimensions 문자열에서 "CellIdentity=20" 형태로 검색
                        if isinstance(value, (list, tuple, set)) and value:
                            # 다중 값: dimensions에 포함되는지 OR 조건으로 검사
                            or_conditions = []
                            for i, v in enumerate(value):
                                param_key = f"dim_{key}_{i}"
                                or_conditions.append(f"dimensions LIKE %({param_key})s")
                                params[param_key] = f"%{dimension_key}={v}%"
                            additional_conditions.append(f"({' OR '.join(or_conditions)})")
                            logger.debug("차원 필터: LIKE 조건으로 %d개 값 적용", len(value))
                        else:
                            # 단일 값
                            param_key = f"dim_{key}"
                            additional_conditions.append(f"dimensions LIKE %({param_key})s")
                            params[param_key] = f"%{dimension_key}={value}%"
                            logger.debug("차원 필터: 단일 값 LIKE 조건 적용")
                    else:
                        # 테이블 컬럼 기반 필터 (ne, swname 등)
                        col_name = columns.get(key)
                        if not col_name:
                            continue
                        
                        # inner_data에 실제로 존재하는 컬럼인지 확인
                        if key not in inner_data_columns:
                            logger.warning("필터 키 '%s'는 inner_data에 존재하지 않습니다. 스킵합니다.", key)
                            continue
                        
                        if isinstance(value, (list, tuple, set)) and value:
                            placeholders = ",".join([f"%({key}_{i})s" for i, _ in enumerate(value)])
                            additional_conditions.append(f"{key} IN ({placeholders})")
                            for i, v in enumerate(value):
                                params[f"{key}_{i}"] = v
                        else:
                            additional_conditions.append(f"{key} = %({key})s")
                            params[key] = value

            # 외부 쿼리 구성: inner_query를 서브쿼리로 사용하고 dimensions를 계산
            # - WITH 절로 inner_query를 서브쿼리로 사용
            # - dimensions를 계산하는 중간 단계 추가
            # - WHERE 절에서 dimensions를 사용 가능하도록 함
            outer_select_parts = [
                "timestamp",
                "family_id", 
                "family_name"
            ]
            if ne_col:
                outer_select_parts.append("ne")
            if swname_col:
                outer_select_parts.append("swname")
            if relver_col:
                outer_select_parts.append("rel_ver")
            outer_select_parts.append("peg_name")
            outer_select_parts.append("value")
            outer_select_parts.append("text_value")
            
            # dimensions 계산을 중간 단계에서 수행
            outer_select_parts.append(
                "(SELECT string_agg(dimension_names[i] || '=' || dimension_values[i], ',') "
                "FROM generate_subscripts(dimension_names, 1) AS i) AS dimensions"
            )
            
            # 중간 단계: dimensions를 계산하는 CTE
            query = (
                f"WITH inner_data AS ({inner_query}), "
                f"     data_with_dimensions AS ("
                f"         SELECT {', '.join(outer_select_parts)} FROM inner_data"
                f"     ) "
                f"SELECT * FROM data_with_dimensions"
            )
            
            # 외부 쿼리에 WHERE 조건 추가 (dimensions 사용 가능)
            if additional_conditions:
                query += " WHERE " + " AND ".join(additional_conditions)
            
            query += " ORDER BY timestamp"
            if limit and limit > 0:
                query += f" LIMIT {limit}"

            logger.info(
                "fetch_peg_data(): 재귀 JSONB 확장 쿼리 구성 완료 | sql_len=%d, params_keys=%s",
                len(query), list(params.keys())
            )
            logger.info("fetch_peg_data(): SQL 쿼리=\n%s", query)
            logger.info("fetch_peg_data(): SQL 파라미터=%s", params)
            logger.debug("fetch_peg_data(): SQL preview=%s", query[:5000].replace('\n',' '))
            # 주의: 이미 WHERE/ORDER BY/LIMIT가 포함되어 있으므로 fetch_data에 time_range/limit 전달하지 않음
            
            # 🔍 디버깅: 조회된 데이터의 value 컬럼 통계
            result_data = self.fetch_data(query, params)
            if result_data:
                logger.debug(
                    "fetch_peg_data() 결과: 총=%d행, 샘플 데이터=%s",
                    len(result_data),
                    result_data[:3] if len(result_data) > 0 else []
                )
                
                # value 컬럼 통계 (null, 0 개수)
                value_list = [row.get('value') for row in result_data]
                null_count = sum(1 for v in value_list if v is None)
                zero_count = sum(1 for v in value_list if v == 0 or v == 0.0)
                non_zero_count = sum(1 for v in value_list if v is not None and v != 0 and v != 0.0)
                
                logger.debug(
                    "fetch_peg_data() value 컬럼 통계: null=%d개, 0=%d개, 0이_아닌_값=%d개, 샘플_value=%s",
                    null_count, zero_count, non_zero_count,
                    [v for v in value_list[:10] if v is not None]
                )
            else:
                logger.warning("fetch_peg_data() 결과가 비어있습니다!")
            
            return result_data

        # ========================================================================
        # DEPRECATED: 레거시 모드 (비-JSONB 스키마)
        # ========================================================================
        # TODO: 이 코드는 더 이상 사용되지 않습니다. 향후 제거 예정.
        # 
        # 제거 대상:
        # - Line 864-912: 레거시 스키마 처리 로직 전체
        # - 단순 SELECT 쿼리 방식 (peg_name, value 컬럼 직접 조회)
        # 
        # 현재는 모든 테이블이 JSONB 스키마 (family_id, family_name, values)를 사용하므로
        # 이 레거시 경로는 실행되지 않아야 합니다.
        # 
        # 제거 시점: 모든 테이블이 JSONB 스키마로 마이그레이션된 것을 확인한 후
        # ========================================================================
        
        # [DEPRECATED] 비-JSONB 레거시 스키마: 기존 경로 유지
        logger.warning(
            "fetch_peg_data(): ⚠️ DEPRECATED 레거시 모드 실행됨! "
            "이 경로는 더 이상 사용되지 않아야 합니다. "
            "columns=%s, table=%s", 
            columns, table_name
        )
        
        select_columns = [
            f"{columns['time']} as timestamp",
            f"{columns['peg_name']} as peg_name",
            f"{columns['value']} as value",
        ]

        # 선택적 컬럼들 추가
        optional_columns = ["ne", "cellid", "swname"]
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

        logger.debug("fetch_peg_data(): [DEPRECATED 레거시] SQL preview=%s", query[:5000].replace('\n',' '))
        # 주의: 이미 WHERE/ORDER BY/LIMIT가 포함되어 있으므로 fetch_data에 time_range/limit 전달하지 않음
        return self.fetch_data(query, params)
        
        # ========================================================================
        # END DEPRECATED
        # ========================================================================

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
