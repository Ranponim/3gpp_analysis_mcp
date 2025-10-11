"""
PEG Processing Service

이 모듈은 PEG 데이터의 조회·검증·집계 및 파생 PEG 계산을 담당하는
`PEGProcessingService` 클래스를 제공합니다. 기존 `AnalysisService`에서
PEG 관련 로직을 분리하여 단일 책임 원칙을 강화하고 재사용성을 높였습니다.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional, Tuple, Union
from collections import defaultdict

import pandas as pd

from config import get_settings
from ..exceptions import ServiceError
from ..repositories import DatabaseRepository
from ..models.request import _DEFAULT_TABLE
from .peg_service import PEGCalculator
from ..utils.csv_filter_loader import load_peg_definitions_from_csv

# 로깅 설정
logger = logging.getLogger(__name__)


class PEGProcessingError(ServiceError):
    """
    PEG 처리 관련 오류 예외 클래스

    PEG 데이터 조회 및 처리에서 발생하는 오류를 래핑합니다.
    """

    def __init__(
        self,
        message: str,
        details: Optional[Union[str, Dict[str, Any]]] = None,
        processing_step: Optional[str] = None,
        data_context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        PEGProcessingError 초기화

        Args:
            message (str): 오류 메시지
            details (Optional[Union[str, Dict[str, Any]]]): 추가 상세 정보
            processing_step (Optional[str]): 실패 단계
            data_context (Optional[Dict[str, Any]]): 데이터 컨텍스트
        """
        super().__init__(
            message=message, details=details, service_name="PEGProcessingService", operation="process_peg_data"
        )
        self.processing_step = processing_step
        self.data_context = data_context

        logger.error("PEGProcessingError 발생: %s (단계: %s)", message, processing_step)

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리 형태로 변환"""
        data = super().to_dict()
        data.update({"processing_step": self.processing_step, "data_context": self.data_context})
        return data


class PEGProcessingService:
    """
    PEG 데이터 처리 서비스 클래스

    - 데이터베이스에서 PEG 원시 데이터를 조회
    - 데이터 검증 및 집계 수행
    - `PEGCalculator`를 사용한 파생 PEG 계산
    - 최종 처리 결과를 반환
    """

    def __init__(self, database_repository: DatabaseRepository, peg_calculator: Optional[PEGCalculator] = None):
        """
        PEGProcessingService 초기화

        Args:
            database_repository (DatabaseRepository): 데이터베이스 Repository
            peg_calculator (Optional[PEGCalculator]): PEG 계산기
        """
        self.database_repository = database_repository
        self.peg_calculator = peg_calculator or PEGCalculator()

        # 처리 단계 정의
        self.processing_steps = [
            "data_retrieval",
            "data_validation",
            "aggregation",
            "derived_calculation",
            "result_formatting",
        ]

        logger.info("PEGProcessingService 초기화 완료: calculator=%s", type(self.peg_calculator).__name__)

    def get_service_info(self) -> Dict[str, Any]:
        """서비스 정보 반환"""
        return {
            "service_name": "PEGProcessingService",
            "processing_steps": self.processing_steps,
            "dependencies": {
                "database_repository": type(self.database_repository).__name__,
                "peg_calculator": type(self.peg_calculator).__name__,
            },
        }

    def _validate_time_ranges(self, time_ranges: Tuple[datetime, datetime, datetime, datetime]) -> None:
        """
        시간 범위 유효성 검증

        Args:
            time_ranges (Tuple): (n1_start, n1_end, n_start, n_end)

        Raises:
            PEGProcessingError: 시간 범위가 유효하지 않은 경우
        """
        logger.debug("_validate_time_ranges() 호출: 시간 범위 검증")

        n1_start, n1_end, n_start, n_end = time_ranges

        # 시작 시간이 종료 시간보다 빠른지 검증
        if n1_start >= n1_end:
            raise PEGProcessingError(
                "N-1 기간의 시작 시간이 종료 시간보다 크거나 같습니다",
                processing_step="data_validation",
                data_context={"n1_start": n1_start, "n1_end": n1_end},
            )

        if n_start >= n_end:
            raise PEGProcessingError(
                "N 기간의 시작 시간이 종료 시간보다 크거나 같습니다",
                processing_step="data_validation",
                data_context={"n_start": n_start, "n_end": n_end},
            )

        logger.info("시간 범위 검증 결과: N-1(%s~%s), N(%s~%s)", n1_start, n1_end, n_start, n_end)

    def _retrieve_raw_peg_data(
        self,
        time_ranges: Tuple[datetime, datetime, datetime, datetime],
        table_config: Dict[str, Any],
        filters: Dict[str, Any],
        peg_filter: Dict[int, Set[str]],
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        데이터베이스에서 원시 PEG 데이터 조회

        Args:
            time_ranges (Tuple): (n1_start, n1_end, n_start, n_end)
            table_config (Dict[str, Any]): 테이블/컬럼 설정
            filters (Dict[str, Any]): 추가 필터 조건
            peg_filter (Dict[int, Set[str]]): CSV에서 로드된 PEG 필터

        Returns:
            Tuple[pd.DataFrame, pd.DataFrame]: (n1_df, n_df)

        Raises:
            PEGProcessingError: 데이터 조회 실패 시
        """
        logger.debug("_retrieve_raw_peg_data() 호출: 원시 데이터 조회 시작")

        try:
            n1_start, n1_end, n_start, n_end = time_ranges

            table_name = table_config.get("table", _DEFAULT_TABLE)
            # 새 스키마 기본 매핑 (datetime, family_id, ne_key, rel_ver, swname, values, version)
            # 상위에서 보존된 columns를 우선 사용, 없으면 JSONB 기본 매핑 적용
            columns = table_config.get("columns") or {
                "time": "datetime",
                "family_name": "family_id",
                "values": "values",
                "ne": "ne_key",
                "rel_ver": "rel_ver",
                "swname": "swname",
            }
            data_limit = table_config.get("data_limit")

            # N-1 기간 데이터 조회
            logger.info("N-1 기간 데이터 조회: %s ~ %s", n1_start, n1_end)
            n1_data = self.database_repository.fetch_peg_data(
                table_name=table_name, columns=columns, time_range=(n1_start, n1_end), filters=filters, limit=data_limit, peg_filter=peg_filter
            )

            # N 기간 데이터 조회
            logger.info("N 기간 데이터 조회: %s ~ %s", n_start, n_end)
            n_data = self.database_repository.fetch_peg_data(
                table_name=table_name, columns=columns, time_range=(n_start, n_end), filters=filters, limit=data_limit, peg_filter=peg_filter
            )

            # DataFrame 변환
            n1_df = pd.DataFrame(n1_data)
            n_df = pd.DataFrame(n_data)

            logger.info("원시 데이터 조회 완료: N-1=%d행, N=%d행", len(n1_df), len(n_df))
            return n1_df, n_df

        except Exception as e:
            raise PEGProcessingError(
                f"원시 PEG 데이터 조회 실패: {e}",
                processing_step="data_retrieval",
                data_context={
                    "table_name": table_name,
                    "time_ranges": str(time_ranges)[:100],
                    "filters": str(filters)[:100],
                },
            ) from e

    def _validate_raw_data(self, n1_df: pd.DataFrame, n_df: pd.DataFrame) -> None:
        """
        원시 데이터 유효성 검증

        Args:
            n1_df (pd.DataFrame): N-1 기간 데이터
            n_df (pd.DataFrame): N 기간 데이터

        Raises:
            PEGProcessingError: 데이터가 유효하지 않은 경우
        """
        logger.debug("_validate_raw_data() 호출: 원시 데이터 검증")

        # 빈 데이터 경고
        if len(n1_df) == 0 or len(n_df) == 0:
            logger.warning("한쪽 기간 데이터가 비어있음: N-1=%d행, N=%d행 - 분석 신뢰성에 영향 가능", len(n1_df), len(n_df))

        # 필수 컬럼 확인
        required_columns = ["peg_name", "value"]

        for df_name, df in [("N-1", n1_df), ("N", n_df)]:
            if not df.empty:
                missing_columns = [col for col in required_columns if col not in df.columns]
                if missing_columns:
                    raise PEGProcessingError(
                        f"{df_name} 데이터에 필수 컬럼이 누락되었습니다: {missing_columns}",
                        processing_step="data_validation",
                        data_context={"period": df_name, "columns": list(df.columns)},
                    )

        logger.info("원시 데이터 검증 완료: N-1=%d행, N=%d행", len(n1_df), len(n_df))

    def _resolve_dependency_order(self, derived_pegs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        파생 PEG 간의 의존성을 분석하여 계산 순서를 결정합니다. (위상 정렬)

        Args:
            derived_pegs (List[Dict[str, Any]]): 파생 PEG 정의 리스트

        Returns:
            List[Dict[str, Any]]: 계산 순서대로 정렬된 파생 PEG 리스트

        Raises:
            PEGProcessingError: 순환 참조가 발견된 경우
        """
        if not derived_pegs:
            return []

        logger.debug("파생 PEG 의존성 분석 시작: %d개", len(derived_pegs))
        
        peg_map = {peg['output_peg']: peg for peg in derived_pegs}
        
        # 각 PEG의 의존성 수 계산
        in_degree = {peg['output_peg']: 0 for peg in derived_pegs}
        # 각 PEG이 어떤 다른 PEG들의 계산에 필요한지
        adj = defaultdict(list)

        all_peg_names = set(peg_map.keys())

        for peg in derived_pegs:
            output_peg = peg['output_peg']
            for dep in peg['dependencies']:
                if dep in all_peg_names: # 의존성이 다른 파생 PEG인 경우
                    in_degree[output_peg] += 1
                    adj[dep].append(output_peg)

        # 진입 차수가 0인 PEG들을 큐에 추가
        queue = [peg_name for peg_name, degree in in_degree.items() if degree == 0]
        
        sorted_order = []
        while queue:
            peg_name = queue.pop(0)
            sorted_order.append(peg_map[peg_name])
            
            for dependent_peg in adj[peg_name]:
                in_degree[dependent_peg] -= 1
                if in_degree[dependent_peg] == 0:
                    queue.append(dependent_peg)
        
        if len(sorted_order) != len(derived_pegs):
            circular_deps = {p for p, d in in_degree.items() if d > 0}
            raise PEGProcessingError(
                "파생 PEG 정의에 순환 참조가 있습니다.",
                processing_step="dependency_resolution",
                details={"circular_dependencies": list(circular_deps)}
            )
            
        logger.info("파생 PEG 계산 순서 결정 완료: %s", [p['output_peg'] for p in sorted_order])
        return sorted_order

    def _process_with_calculator(
        self, n1_df: pd.DataFrame, n_df: pd.DataFrame, peg_config: Dict[str, Any], filters: Dict[str, Any], derived_pegs: List[Dict[str, Any]]
    ) -> pd.DataFrame:
        """
        PEGCalculator를 사용하여 데이터 처리 및 파생 PEG 계산

        Args:
            n1_df (pd.DataFrame): N-1 기간 데이터
            n_df (pd.DataFrame): N 기간 데이터
            peg_config (Dict[str, Any]): PEG 설정
            filters (Dict[str, Any]): 필터 조건
            derived_pegs (List[Dict[str, Any]]): 파생 PEG 정의 리스트

        Returns:
            pd.DataFrame: 처리된 PEG 데이터 (파생 PEG 포함)
        """
        logger.debug("_process_with_calculator() 호출: PEGCalculator 처리 시작")

        try:
            # 식별자 정보 추출 (집계 전)
            metadata = {}
            source_df = n1_df if not n1_df.empty else n_df
            if not source_df.empty:
                first_row = source_df.iloc[0]
                if "ne" in source_df.columns: metadata["ne_key"] = str(first_row["ne"]) if pd.notna(first_row["ne"]) else None
                if "swname" in source_df.columns: metadata["swname"] = str(first_row["swname"]) if pd.notna(first_row["swname"]) else None
                if "rel_ver" in source_df.columns: metadata["rel_ver"] = str(first_row["rel_ver"]) if pd.notna(first_row["rel_ver"]) else None
                if "index_name" in source_df.columns: metadata["index_name"] = str(first_row["index_name"]) if pd.notna(first_row["index_name"]) else None

            # cell_id 필터 없으면 여러 cell 평균화
            if 'cellid' not in filters or not filters.get('cellid'):
                logger.info("cell_id 미지정 - 여러 cell 평균화 수행")
                for df_name, df in [("N-1", n1_df), ("N", n_df)]:
                    if not df.empty and 'dimensions' in df.columns:
                        df['dimensions'] = df['dimensions'].str.replace(r'CellIdentity=\d+,?', '', regex=True).str.strip(',')
                agg_cols = ['value']
                first_cols = ['ne', 'swname', 'family_name']
                if not n1_df.empty:
                    group_keys = ['timestamp', 'peg_name', 'dimensions'] if 'dimensions' in n1_df.columns else ['timestamp', 'peg_name']
                    agg_dict = {'value': 'mean'}
                    for col in first_cols: 
                        if col in n1_df.columns: agg_dict[col] = 'first'
                    n1_df = n1_df.groupby(group_keys).agg(agg_dict).reset_index()
                if not n_df.empty:
                    group_keys = ['timestamp', 'peg_name', 'dimensions'] if 'dimensions' in n_df.columns else ['timestamp', 'peg_name']
                    agg_dict = {'value': 'mean'}
                    for col in first_cols:
                        if col in n_df.columns: agg_dict[col] = 'first'
                    n_df = n_df.groupby(group_keys).agg(agg_dict).reset_index()

            # 기본 PEG 집계
            group_keys = ['peg_name', 'dimensions'] if 'dimensions' in n1_df.columns else ['peg_name']
            n1_aggregated = n1_df.groupby(group_keys)["value"].mean().reset_index() if not n1_df.empty else pd.DataFrame(columns=group_keys + ["value"])
            n1_aggregated["period"] = "N-1"
            
            group_keys = ['peg_name', 'dimensions'] if 'dimensions' in n_df.columns else ['peg_name']
            n_aggregated = n_df.groupby(group_keys)["value"].mean().reset_index() if not n_df.empty else pd.DataFrame(columns=group_keys + ["value"])
            n_aggregated["period"] = "N"

            combined_df = pd.concat([n1_aggregated, n_aggregated], ignore_index=True)
            if combined_df.empty:
                return pd.DataFrame(columns=["peg_name", "period", "avg_value", "change_pct"])

            # --- [파생 PEG 계산 로직] ---
            # 파생 PEG 구분을 위한 플래그 추가
            combined_df['is_derived'] = False
            derived_peg_names = []
            
            if derived_pegs:
                logger.info("파생 PEG 계산 시작: %d개", len(derived_pegs))
                # 파생 PEG 계산 시에는 dimensions를 고려하지 않음 (단순화를 위해)
                # peg_name만으로 pivot하여 계산 후, 원래 데이터와 merge
                simple_combined_df = combined_df.groupby(['peg_name', 'period'])['value'].mean().reset_index()
                eval_df = simple_combined_df.pivot(index="period", columns="peg_name", values="value")

                sorted_derived_pegs = self._resolve_dependency_order(derived_pegs)

                for peg_def in sorted_derived_pegs:
                    output_peg = peg_def['output_peg']
                    formula = peg_def['formula']
                    try:
                        eval_df[output_peg] = eval_df.eval(formula, engine='python')
                        logger.debug("파생 PEG 계산 성공: %s", output_peg)
                    except Exception as e:
                        logger.warning("파생 PEG '%s' 계산 실패. 수식: '%s'. 오류: %s", output_peg, formula, e)
                        eval_df[output_peg] = pd.NA

                # 계산된 파생 PEG를 long format으로 변환
                derived_peg_names = [p['output_peg'] for p in derived_pegs if p['output_peg'] in eval_df.columns]
                if derived_peg_names:
                    derived_df_long = eval_df[derived_peg_names].reset_index().melt(
                        id_vars=['period'], var_name='peg_name', value_name='value'
                    )
                    # 파생 PEG 표시
                    derived_df_long['is_derived'] = True
                    # 기존 데이터와 파생 데이터 결합 (파생 PEG가 뒤에 추가됨)
                    combined_df = pd.concat([combined_df, derived_df_long], ignore_index=True)
                    logger.info("파생 PEG 데이터 결합 완료: %d개 (is_derived=True 플래그 추가)", len(derived_peg_names))
            # --- [계산 로직 완료] ---

            # 변화율 계산
            index_keys = ['peg_name', 'dimensions'] if 'dimensions' in combined_df.columns else ['peg_name']
            pivot_df = combined_df.pivot_table(index=index_keys, columns="period", values="value", aggfunc='mean')

            if "N-1" in pivot_df.columns and "N" in pivot_df.columns:
                valid_mask = (pivot_df["N-1"].notna()) & (pivot_df["N"].notna()) & (pivot_df["N-1"] != 0)
                pivot_df["change_pct"] = None
                if valid_mask.sum() > 0:
                    pivot_df.loc[valid_mask, "change_pct"] = ((pivot_df.loc[valid_mask, "N"] - pivot_df.loc[valid_mask, "N-1"]) / pivot_df.loc[valid_mask, "N-1"] * 100)
            else:
                pivot_df["change_pct"] = 0

            # 최종 형태로 변환
            processed_df = pivot_df.reset_index()
            id_vars = [key for key in index_keys] + ["change_pct"]
            value_vars = [col for col in ["N-1", "N"] if col in processed_df.columns]
            processed_df = processed_df.melt(
                id_vars=id_vars,
                value_vars=value_vars,
                var_name="period",
                value_name="avg_value",
            )

            # 식별자 정보를 모든 행에 추가
            if metadata:
                for key, value in metadata.items():
                    if value is not None: processed_df[key] = value

            # --- [파생 PEG를 DataFrame 맨 마지막으로 정렬] ---
            # 파생 PEG 표시 컬럼 추가
            processed_df['is_derived'] = processed_df['peg_name'].isin(derived_peg_names)
            
            # 정렬: 기본 PEG가 먼저, 파생 PEG가 나중에
            # is_derived=False(기본 PEG)가 먼저 오고, is_derived=True(파생 PEG)가 나중에 옴
            processed_df = processed_df.sort_values(by=['is_derived', 'peg_name', 'period']).reset_index(drop=True)
            
            logger.info("PEGCalculator 처리 완료: %d행 (파생 PEG %d개는 DataFrame 맨 마지막에 배치됨)", 
                       len(processed_df), len(derived_peg_names))
            return processed_df

        except Exception as e:
            raise PEGProcessingError(
                f"PEGCalculator 처리 실패: {e}",
                processing_step="aggregation",
                data_context={"n1_rows": len(n1_df), "n_rows": len(n_df)},
            ) from e

    def process_peg_data(
        self,
        time_ranges: Tuple[datetime, datetime, datetime, datetime],
        table_config: Dict[str, Any],
        filters: Dict[str, Any],
        peg_config: Optional[Dict[str, Any]] = None,
        request_context: Optional[Dict[str, Any]] = None,
    ) -> pd.DataFrame:
        """
        전체 PEG 데이터 처리 워크플로우 실행

        Args:
            time_ranges (Tuple): (n1_start, n1_end, n_start, n_end)
            table_config (Dict[str, Any]): 테이블/컬럼 설정
            filters (Dict[str, Any]): 필터 조건
            peg_config (Optional[Dict[str, Any]]): PEG 설정
            request_context (Optional[Dict[str, Any]]): API 요청 컨텍스트 (CSV 경로 재정의용)

        Returns:
            pd.DataFrame: 처리된 PEG 데이터

        Raises:
            PEGProcessingError: 처리 실패 시
        """
        logger.info("process_peg_data() 호출: PEG 데이터 처리 워크플로우 시작")

        # --- [CSV 필터 로직 수정] ---
        settings = get_settings()
        db_filter = {}
        derived_pegs = []
        if settings.peg_filter_enabled:
            request_context = request_context or {}
            filter_file_override = request_context.get("peg_filter_file")
            filename_to_use = filter_file_override if filter_file_override else settings.peg_filter_default_file
            full_csv_path = os.path.join(settings.peg_filter_dir_path, filename_to_use)
            
            # 확장된 로더 호출
            db_filter, derived_pegs = load_peg_definitions_from_csv(full_csv_path)
            logger.info("CSV 로드: DB필터 %d families, 파생PEG %d개", len(db_filter), len(derived_pegs))
        else:
            logger.debug("CSV 필터링 기능이 비활성화되어 있습니다.")
        # --- [수정 완료] ---

        try:
            # 1단계: 시간 범위 검증
            logger.info("1단계: 시간 범위 검증")
            self._validate_time_ranges(time_ranges)
            logger.debug(
                "시간 범위 요약: N-1=%s~%s, N=%s~%s",
                time_ranges[0],
                time_ranges[1],
                time_ranges[2],
                time_ranges[3],
            )

            # 2단계: 원시 데이터 조회
            logger.info("2단계: 원시 데이터 조회")
            n1_df, n_df = self._retrieve_raw_peg_data(time_ranges, table_config, filters, peg_filter=db_filter)
            logger.debug(
                "원시 데이터 조회 결과: N-1 rows=%d, N rows=%d", len(n1_df), len(n_df)
            )

            # 3단계: 원시 데이터 검증
            logger.info("3단계: 원시 데이터 검증")
            self._validate_raw_data(n1_df, n_df)

            # 4단계: PEGCalculator 및 파생 PEG 처리
            logger.info("4단계: PEGCalculator 및 파생 PEG 처리")
            processed_df = self._process_with_calculator(n1_df, n_df, peg_config or {}, filters, derived_pegs=derived_pegs)
            logger.debug(
                "PEGCalculator 처리 결과: 행수=%d, 컬럼=%s",
                len(processed_df),
                list(processed_df.columns),
            )

            logger.info("PEG 데이터 처리 워크플로우 완료: %d행", len(processed_df))
            return processed_df

        except PEGProcessingError:
            # 이미 PEGProcessingError인 경우 그대로 전파
            raise

        except Exception as e:
            # 예상치 못한 오류를 PEGProcessingError로 변환
            raise PEGProcessingError(
                f"PEG 데이터 처리 중 예상치 못한 오류: {e}",
                processing_step="unknown",
                data_context={"time_ranges": str(time_ranges)[:100]},
            ) from e

    def get_processing_status(self) -> Dict[str, Any]:
        """처리 상태 정보 반환"""
        return {
            "processing_steps": self.processing_steps,
            "step_count": len(self.processing_steps),
            "dependencies_ready": {
                "database_repository": self.database_repository is not None,
                "peg_calculator": self.peg_calculator is not None,
            },
        }

    def close(self) -> None:
        """리소스 정리"""
        if hasattr(self.database_repository, "disconnect"):
            self.database_repository.disconnect()

        logger.info("PEGProcessingService 리소스 정리 완료")

    def __enter__(self):
        """컨텍스트 매니저 진입"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """컨텍스트 매니저 종료"""
        self.close()

        # 예외 발생 시 로그 기록
        if exc_type:
            logger.error("PEGProcessingService 컨텍스트에서 예외 발생: %s", exc_val)
        return False  # 예외를 다시 발생시킴

