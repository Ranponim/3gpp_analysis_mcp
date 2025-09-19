"""
PEG Processing Service

이 모듈은 PEG 데이터의 조회, 필터링, 처리를 담당하는
PEGProcessingService 클래스를 제공합니다.

기존 AnalysisService에서 PEG 관련 로직을 분리하여
단일 책임 원칙을 강화하고 재사용성을 높입니다.
"""

from __future__ import annotations

import logging
import os

# 임시로 절대 import 사용 (나중에 패키지 구조 정리 시 수정)
import sys
from datetime import datetime
from typing import Any, Dict, Optional, Tuple, Union

import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from exceptions import ServiceError
from repositories import DatabaseRepository
from services import PEGCalculator

# 로깅 설정
logger = logging.getLogger(__name__)


class PEGProcessingError(ServiceError):
    """
    PEG 처리 서비스 관련 오류 예외 클래스

    PEG 데이터 조회, 필터링, 처리에서 발생하는 오류를 처리합니다.
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
            processing_step (Optional[str]): 실패한 처리 단계
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

    데이터베이스에서 PEG 데이터를 조회하고, 필터를 적용하며,
    PEGCalculator를 사용하여 집계 및 파생 PEG를 계산합니다.

    AnalysisService에서 PEG 관련 로직을 분리하여 단일 책임 원칙을 강화하고
    재사용성을 높이는 것이 목표입니다.

    주요 기능:
    1. DatabaseRepository를 통한 원시 PEG 데이터 조회
    2. 시간 범위 및 필터 조건 적용
    3. PEGCalculator를 통한 집계 및 파생 PEG 계산
    4. ProcessedPEGData 형태로 결과 반환
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

        # 각 기간 내에서 시작 < 끝 검증
        if n1_start >= n1_end:
            raise PEGProcessingError(
                "N-1 기간의 시작 시간이 끝 시간보다 늦거나 같습니다",
                processing_step="data_validation",
                data_context={"n1_start": n1_start, "n1_end": n1_end},
            )

        if n_start >= n_end:
            raise PEGProcessingError(
                "N 기간의 시작 시간이 끝 시간보다 늦거나 같습니다",
                processing_step="data_validation",
                data_context={"n_start": n_start, "n_end": n_end},
            )

        logger.info("시간 범위 검증 통과: N-1(%s~%s), N(%s~%s)", n1_start, n1_end, n_start, n_end)

    def _retrieve_raw_peg_data(
        self,
        time_ranges: Tuple[datetime, datetime, datetime, datetime],
        table_config: Dict[str, Any],
        filters: Dict[str, Any],
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        데이터베이스에서 원시 PEG 데이터 조회

        Args:
            time_ranges (Tuple): (n1_start, n1_end, n_start, n_end)
            table_config (Dict[str, Any]): 테이블 및 컬럼 설정
            filters (Dict[str, Any]): 필터 조건

        Returns:
            Tuple[pd.DataFrame, pd.DataFrame]: (n1_df, n_df)

        Raises:
            PEGProcessingError: 데이터 조회 실패 시
        """
        logger.debug("_retrieve_raw_peg_data() 호출: 원시 데이터 조회 시작")

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

            # N-1 기간 데이터 조회
            logger.info("N-1 기간 데이터 조회: %s ~ %s", n1_start, n1_end)
            n1_data = self.database_repository.fetch_peg_data(
                table_name=table_name, columns=columns, time_range=(n1_start, n1_end), filters=filters, limit=data_limit
            )

            # N 기간 데이터 조회
            logger.info("N 기간 데이터 조회: %s ~ %s", n_start, n_end)
            n_data = self.database_repository.fetch_peg_data(
                table_name=table_name, columns=columns, time_range=(n_start, n_end), filters=filters, limit=data_limit
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
            logger.warning(
                "한쪽 기간 데이터가 비어있음: N-1=%d행, N=%d행 - 분석 신뢰도가 낮아질 수 있음", len(n1_df), len(n_df)
            )

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

    def _process_with_calculator(
        self, n1_df: pd.DataFrame, n_df: pd.DataFrame, peg_config: Dict[str, Any]
    ) -> pd.DataFrame:
        """
        PEGCalculator를 사용한 데이터 처리

        Args:
            n1_df (pd.DataFrame): N-1 기간 데이터
            n_df (pd.DataFrame): N 기간 데이터
            peg_config (Dict[str, Any]): PEG 설정

        Returns:
            pd.DataFrame: 처리된 PEG 데이터

        Raises:
            PEGProcessingError: PEG 처리 실패 시
        """
        logger.debug("_process_with_calculator() 호출: PEGCalculator 처리 시작")

        try:
            # 현재는 간단한 집계 로직 (PEGCalculator 완전 통합은 추후)
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

            # 결합 및 변화율 계산
            combined_df = pd.concat([n1_aggregated, n_aggregated], ignore_index=True)

            # 변화율 계산 로직
            if not combined_df.empty:
                # pivot으로 N-1, N 기간을 컬럼으로 변환
                pivot_df = combined_df.pivot(index="peg_name", columns="period", values="value").fillna(0)

                if "N-1" in pivot_df.columns and "N" in pivot_df.columns:
                    pivot_df["change_pct"] = ((pivot_df["N"] - pivot_df["N-1"]) / pivot_df["N-1"] * 100).fillna(0)
                else:
                    pivot_df["change_pct"] = 0

                # 최종 형태로 변환
                processed_df = pivot_df.reset_index()
                processed_df = processed_df.melt(
                    id_vars=["peg_name", "change_pct"],
                    value_vars=["N-1", "N"],
                    var_name="period",
                    value_name="avg_value",
                )
            else:
                processed_df = pd.DataFrame(columns=["peg_name", "period", "avg_value", "change_pct"])

            logger.info("PEGCalculator 처리 완료: %d행", len(processed_df))
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
    ) -> pd.DataFrame:
        """
        전체 PEG 데이터 처리 워크플로우 실행

        Args:
            time_ranges (Tuple): (n1_start, n1_end, n_start, n_end)
            table_config (Dict[str, Any]): 테이블 및 컬럼 설정
            filters (Dict[str, Any]): 필터 조건
            peg_config (Optional[Dict[str, Any]]): PEG 설정

        Returns:
            pd.DataFrame: 처리된 PEG 데이터

        Raises:
            PEGProcessingError: 처리 실패 시
        """
        logger.info("process_peg_data() 호출: PEG 데이터 처리 워크플로우 시작")

        try:
            # 1단계: 시간 범위 검증
            logger.info("1단계: 시간 범위 검증")
            self._validate_time_ranges(time_ranges)

            # 2단계: 원시 데이터 조회
            logger.info("2단계: 원시 데이터 조회")
            n1_df, n_df = self._retrieve_raw_peg_data(time_ranges, table_config, filters)

            # 3단계: 원시 데이터 검증
            logger.info("3단계: 원시 데이터 검증")
            self._validate_raw_data(n1_df, n_df)

            # 4단계: PEGCalculator 처리
            logger.info("4단계: PEGCalculator 처리")
            processed_df = self._process_with_calculator(n1_df, n_df, peg_config or {})

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
