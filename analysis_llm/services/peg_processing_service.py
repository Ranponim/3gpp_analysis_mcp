"""
PEG Processing Service

??모듈?� PEG ?�이?�의 조회, ?�터�? 처리�??�당?�는
PEGProcessingService ?�래?��? ?�공?�니??

기존 AnalysisService?�서 PEG 관??로직??분리?�여
?�일 책임 ?�칙??강화?�고 ?�사?�성???�입?�다.
"""

from __future__ import annotations

import logging
import os

# ?�시�??��? import ?�용 (?�중???�키지 구조 ?�리 ???�정)
import sys
from datetime import datetime
from typing import Any, Dict, Optional, Tuple, Union

import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from exceptions import ServiceError
from repositories import DatabaseRepository
from .peg_service import PEGCalculator

# 로깅 ?�정
logger = logging.getLogger(__name__)


class PEGProcessingError(ServiceError):
    """
    PEG 처리 ?�비??관???�류 ?�외 ?�래??

    PEG ?�이??조회, ?�터�? 처리?�서 발생?�는 ?�류�?처리?�니??
    """

    def __init__(
        self,
        message: str,
        details: Optional[Union[str, Dict[str, Any]]] = None,
        processing_step: Optional[str] = None,
        data_context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        PEGProcessingError 초기??

        Args:
            message (str): ?�류 메시지
            details (Optional[Union[str, Dict[str, Any]]]): 추�? ?�세 ?�보
            processing_step (Optional[str]): ?�패??처리 ?�계
            data_context (Optional[Dict[str, Any]]): ?�이??컨텍?�트
        """
        super().__init__(
            message=message, details=details, service_name="PEGProcessingService", operation="process_peg_data"
        )
        self.processing_step = processing_step
        self.data_context = data_context

        logger.error("PEGProcessingError 발생: %s (?�계: %s)", message, processing_step)

    def to_dict(self) -> Dict[str, Any]:
        """?�셔?�리 ?�태�?변??""
        data = super().to_dict()
        data.update({"processing_step": self.processing_step, "data_context": self.data_context})
        return data


class PEGProcessingService:
    """
    PEG ?�이??처리 ?�비???�래??

    ?�이?�베?�스?�서 PEG ?�이?��? 조회?�고, ?�터�??�용?�며,
    PEGCalculator�??�용?�여 집계 �??�생 PEG�?계산?�니??

    AnalysisService?�서 PEG 관??로직??분리?�여 ?�일 책임 ?�칙??강화?�고
    ?�사?�성???�이??것이 목표?�니??

    주요 기능:
    1. DatabaseRepository�??�한 ?�시 PEG ?�이??조회
    2. ?�간 범위 �??�터 조건 ?�용
    3. PEGCalculator�??�한 집계 �??�생 PEG 계산
    4. ProcessedPEGData ?�태�?결과 반환
    """

    def __init__(self, database_repository: DatabaseRepository, peg_calculator: Optional[PEGCalculator] = None):
        """
        PEGProcessingService 초기??

        Args:
            database_repository (DatabaseRepository): ?�이?�베?�스 Repository
            peg_calculator (Optional[PEGCalculator]): PEG 계산�?
        """
        self.database_repository = database_repository
        self.peg_calculator = peg_calculator or PEGCalculator()

        # 처리 ?�계 ?�의
        self.processing_steps = [
            "data_retrieval",
            "data_validation",
            "aggregation",
            "derived_calculation",
            "result_formatting",
        ]

        logger.info("PEGProcessingService 초기???�료: calculator=%s", type(self.peg_calculator).__name__)

    def get_service_info(self) -> Dict[str, Any]:
        """?�비???�보 반환"""
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
        ?�간 범위 ?�효??검�?

        Args:
            time_ranges (Tuple): (n1_start, n1_end, n_start, n_end)

        Raises:
            PEGProcessingError: ?�간 범위가 ?�효?��? ?��? 경우
        """
        logger.debug("_validate_time_ranges() ?�출: ?�간 범위 검�?)

        n1_start, n1_end, n_start, n_end = time_ranges

        # �?기간 ?�에???�작 < ??검�?
        if n1_start >= n1_end:
            raise PEGProcessingError(
                "N-1 기간???�작 ?�간?????�간보다 ??��??같습?�다",
                processing_step="data_validation",
                data_context={"n1_start": n1_start, "n1_end": n1_end},
            )

        if n_start >= n_end:
            raise PEGProcessingError(
                "N 기간???�작 ?�간?????�간보다 ??��??같습?�다",
                processing_step="data_validation",
                data_context={"n_start": n_start, "n_end": n_end},
            )

        logger.info("?�간 범위 검�??�과: N-1(%s~%s), N(%s~%s)", n1_start, n1_end, n_start, n_end)

    def _retrieve_raw_peg_data(
        self,
        time_ranges: Tuple[datetime, datetime, datetime, datetime],
        table_config: Dict[str, Any],
        filters: Dict[str, Any],
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        ?�이?�베?�스?�서 ?�시 PEG ?�이??조회

        Args:
            time_ranges (Tuple): (n1_start, n1_end, n_start, n_end)
            table_config (Dict[str, Any]): ?�이�?�?컬럼 ?�정
            filters (Dict[str, Any]): ?�터 조건

        Returns:
            Tuple[pd.DataFrame, pd.DataFrame]: (n1_df, n_df)

        Raises:
            PEGProcessingError: ?�이??조회 ?�패 ??
        """
        logger.debug("_retrieve_raw_peg_data() ?�출: ?�시 ?�이??조회 ?�작")

        try:
            n1_start, n1_end, n_start, n_end = time_ranges

            table_name = table_config.get("table", "summary")
            columns = table_config.get(
                "columns",
                {
                    "time": "datetime",
                    "peg_name": "peg_name",
                    "value": "value",
                    "ne": "ne",
                    "cellid": "cellid",
                    "host": "host",
                },
            )
            data_limit = table_config.get("data_limit")

            # N-1 기간 ?�이??조회
            logger.info("N-1 기간 ?�이??조회: %s ~ %s", n1_start, n1_end)
            n1_data = self.database_repository.fetch_peg_data(
                table_name=table_name, columns=columns, time_range=(n1_start, n1_end), filters=filters, limit=data_limit
            )

            # N 기간 ?�이??조회
            logger.info("N 기간 ?�이??조회: %s ~ %s", n_start, n_end)
            n_data = self.database_repository.fetch_peg_data(
                table_name=table_name, columns=columns, time_range=(n_start, n_end), filters=filters, limit=data_limit
            )

            # DataFrame 변??
            n1_df = pd.DataFrame(n1_data)
            n_df = pd.DataFrame(n_data)

            logger.info("?�시 ?�이??조회 ?�료: N-1=%d?? N=%d??, len(n1_df), len(n_df))
            return n1_df, n_df

        except Exception as e:
            raise PEGProcessingError(
                f"?�시 PEG ?�이??조회 ?�패: {e}",
                processing_step="data_retrieval",
                data_context={
                    "table_name": table_name,
                    "time_ranges": str(time_ranges)[:100],
                    "filters": str(filters)[:100],
                },
            ) from e

    def _validate_raw_data(self, n1_df: pd.DataFrame, n_df: pd.DataFrame) -> None:
        """
        ?�시 ?�이???�효??검�?

        Args:
            n1_df (pd.DataFrame): N-1 기간 ?�이??
            n_df (pd.DataFrame): N 기간 ?�이??

        Raises:
            PEGProcessingError: ?�이?��? ?�효?��? ?��? 경우
        """
        logger.debug("_validate_raw_data() ?�출: ?�시 ?�이??검�?)

        # �??�이??경고
        if len(n1_df) == 0 or len(n_df) == 0:
            logger.warning(
                "?�쪽 기간 ?�이?��? 비어?�음: N-1=%d?? N=%d??- 분석 ?�뢰?��? ??���????�음", len(n1_df), len(n_df)
            )

        # ?�수 컬럼 ?�인
        required_columns = ["peg_name", "value"]

        for df_name, df in [("N-1", n1_df), ("N", n_df)]:
            if not df.empty:
                missing_columns = [col for col in required_columns if col not in df.columns]
                if missing_columns:
                    raise PEGProcessingError(
                        f"{df_name} ?�이?�에 ?�수 컬럼???�락?�었?�니?? {missing_columns}",
                        processing_step="data_validation",
                        data_context={"period": df_name, "columns": list(df.columns)},
                    )

        logger.info("?�시 ?�이??검�??�료: N-1=%d?? N=%d??, len(n1_df), len(n_df))

    def _process_with_calculator(
        self, n1_df: pd.DataFrame, n_df: pd.DataFrame, peg_config: Dict[str, Any]
    ) -> pd.DataFrame:
        """
        PEGCalculator�??�용???�이??처리

        Args:
            n1_df (pd.DataFrame): N-1 기간 ?�이??
            n_df (pd.DataFrame): N 기간 ?�이??
            peg_config (Dict[str, Any]): PEG ?�정

        Returns:
            pd.DataFrame: 처리??PEG ?�이??

        Raises:
            PEGProcessingError: PEG 처리 ?�패 ??
        """
        logger.debug("_process_with_calculator() ?�출: PEGCalculator 처리 ?�작")

        try:
            # ?�재??간단??집계 로직 (PEGCalculator ?�전 ?�합?� 추후)
            # N-1 기간 집계
            if not n1_df.empty:
                n1_aggregated = n1_df.groupby("peg_name")["value"].mean().reset_index()
                n1_aggregated["period"] = "N-1"
            else:
                n1_aggregated = pd.DataFrame(columns=["peg_name", "value", "period"])

            # N 기간 집계
            if not n_df.empty:
                n_aggregated = n_df.groupby("peg_name")["value"].mean().reset_index()
                n_aggregated["period"] = "N"
            else:
                n_aggregated = pd.DataFrame(columns=["peg_name", "value", "period"])

            # 결합 �?변?�율 계산
            combined_df = pd.concat([n1_aggregated, n_aggregated], ignore_index=True)

            # 변?�율 계산 로직
            if not combined_df.empty:
                # pivot?�로 N-1, N 기간??컬럼?�로 변??
                pivot_df = combined_df.pivot(index="peg_name", columns="period", values="value").fillna(0)

                if "N-1" in pivot_df.columns and "N" in pivot_df.columns:
                    pivot_df["change_pct"] = ((pivot_df["N"] - pivot_df["N-1"]) / pivot_df["N-1"] * 100).fillna(0)
                else:
                    pivot_df["change_pct"] = 0

                # 최종 ?�태�?변??
                processed_df = pivot_df.reset_index()
                processed_df = processed_df.melt(
                    id_vars=["peg_name", "change_pct"],
                    value_vars=["N-1", "N"],
                    var_name="period",
                    value_name="avg_value",
                )
            else:
                processed_df = pd.DataFrame(columns=["peg_name", "period", "avg_value", "change_pct"])

            logger.info("PEGCalculator 처리 ?�료: %d??, len(processed_df))
            return processed_df

        except Exception as e:
            raise PEGProcessingError(
                f"PEGCalculator 처리 ?�패: {e}",
                processing_step="aggregation",
                data_context={"n1_rows": len(n1_df), "n_rows": len(n_df)},
            ) from e

    def process_peg_data(
        self,
        time_ranges: Tuple[datetime, datetime, datetime, datetime],
        table_config: Dict[str, Any],
        filters: Dict[str, Any],
        peg_config: Optional[Dict[str, Any]] = None,
    ) -> pd.DataFrame:
        """
        ?�체 PEG ?�이??처리 ?�크?�로???�행

        Args:
            time_ranges (Tuple): (n1_start, n1_end, n_start, n_end)
            table_config (Dict[str, Any]): ?�이�?�?컬럼 ?�정
            filters (Dict[str, Any]): ?�터 조건
            peg_config (Optional[Dict[str, Any]]): PEG ?�정

        Returns:
            pd.DataFrame: 처리??PEG ?�이??

        Raises:
            PEGProcessingError: 처리 ?�패 ??
        """
        logger.info("process_peg_data() ?�출: PEG ?�이??처리 ?�크?�로???�작")

        try:
            # 1?�계: ?�간 범위 검�?
            logger.info("1?�계: ?�간 범위 검�?)
            self._validate_time_ranges(time_ranges)

            # 2?�계: ?�시 ?�이??조회
            logger.info("2?�계: ?�시 ?�이??조회")
            n1_df, n_df = self._retrieve_raw_peg_data(time_ranges, table_config, filters)

            # 3?�계: ?�시 ?�이??검�?
            logger.info("3?�계: ?�시 ?�이??검�?)
            self._validate_raw_data(n1_df, n_df)

            # 4?�계: PEGCalculator 처리
            logger.info("4?�계: PEGCalculator 처리")
            processed_df = self._process_with_calculator(n1_df, n_df, peg_config or {})

            logger.info("PEG ?�이??처리 ?�크?�로???�료: %d??, len(processed_df))
            return processed_df

        except PEGProcessingError:
            # ?��? PEGProcessingError??경우 그�?�??�파
            raise

        except Exception as e:
            # ?�상�?못한 ?�류�?PEGProcessingError�?변??
            raise PEGProcessingError(
                f"PEG ?�이??처리 �??�상�?못한 ?�류: {e}",
                processing_step="unknown",
                data_context={"time_ranges": str(time_ranges)[:100]},
            ) from e

    def get_processing_status(self) -> Dict[str, Any]:
        """처리 ?�태 ?�보 반환"""
        return {
            "processing_steps": self.processing_steps,
            "step_count": len(self.processing_steps),
            "dependencies_ready": {
                "database_repository": self.database_repository is not None,
                "peg_calculator": self.peg_calculator is not None,
            },
        }

    def close(self) -> None:
        """리소???�리"""
        if hasattr(self.database_repository, "disconnect"):
            self.database_repository.disconnect()

        logger.info("PEGProcessingService 리소???�리 ?�료")

    def __enter__(self):
        """컨텍?�트 매니?� 진입"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """컨텍?�트 매니?� 종료"""
        self.close()

        # ?�외 발생 ??로그 기록
        if exc_type:
            logger.error("PEGProcessingService 컨텍?�트?�서 ?�외 발생: %s", exc_val)

        return False  # ?�외�??�시 발생?�킴
