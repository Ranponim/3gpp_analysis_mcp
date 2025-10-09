"""
PEG Processing Service

이 모듈은 PEG 데이터의 조회·검증·집계 및 파생 PEG 계산을 담당하는
`PEGProcessingService` 클래스를 제공합니다. 기존 `AnalysisService`에서
PEG 관련 로직을 분리하여 단일 책임 원칙을 강화하고 재사용성을 높였습니다.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional, Tuple, Union

import pandas as pd

from ..exceptions import ServiceError
from ..repositories import DatabaseRepository
from ..models.request import _DEFAULT_TABLE
from .peg_service import PEGCalculator

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
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        데이터베이스에서 원시 PEG 데이터 조회

        Args:
            time_ranges (Tuple): (n1_start, n1_end, n_start, n_end)
            table_config (Dict[str, Any]): 테이블/컬럼 설정
            filters (Dict[str, Any]): 추가 필터 조건

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

    def _process_with_calculator(
        self, n1_df: pd.DataFrame, n_df: pd.DataFrame, peg_config: Dict[str, Any], filters: Dict[str, Any]
    ) -> pd.DataFrame:
        """
        PEGCalculator를 사용하여 데이터 처리 (식별자 보존)

        Args:
            n1_df (pd.DataFrame): N-1 기간 데이터
            n_df (pd.DataFrame): N 기간 데이터
            peg_config (Dict[str, Any]): PEG 설정 (미사용 시 빈 딕셔너리)
            filters (Dict[str, Any]): 필터 조건 (cell_id 평균화 판단용)

        Returns:
            pd.DataFrame: 처리된 PEG 데이터 (식별자 컬럼 포함)

        Raises:
            PEGProcessingError: PEG 처리 실패 시
        """
        logger.debug("_process_with_calculator() 호출: PEGCalculator 처리 시작")

        try:
            # ✨ 식별자 정보 추출 (집계 전 - DB 조회 값 보존)
            metadata = {}
            source_df = n1_df if not n1_df.empty else n_df
            
            if not source_df.empty:
                first_row = source_df.iloc[0]
                
                # ne_key 추출 (DB가 'ne'로 반환)
                if "ne" in source_df.columns:
                    metadata["ne_key"] = str(first_row["ne"]) if pd.notna(first_row["ne"]) else None
                
                # swname 추출 (DB 컬럼명 그대로)
                if "swname" in source_df.columns:
                    metadata["swname"] = str(first_row["swname"]) if pd.notna(first_row["swname"]) else None
                
                # rel_ver 추출 (DB 컬럼명 그대로)
                if "rel_ver" in source_df.columns:
                    metadata["rel_ver"] = str(first_row["rel_ver"]) if pd.notna(first_row["rel_ver"]) else None
                
                # index_name 추출 (JSONB values 내부에 있을 수 있음)
                if "index_name" in source_df.columns:
                    metadata["index_name"] = str(first_row["index_name"]) if pd.notna(first_row["index_name"]) else None
                
                logger.debug(
                    "식별자 추출 (집계 전): ne_key=%s, swname=%s, rel_ver=%s, index_name=%s",
                    metadata.get("ne_key"),
                    metadata.get("swname"),
                    metadata.get("rel_ver"),
                    metadata.get("index_name")
                )
            
            # ✨ 요구사항 2: cell_id 필터 없으면 여러 cell 평균화
            if 'cellid' not in filters or not filters.get('cellid'):
                logger.info("cell_id 미지정 - 여러 cell 평균화 수행")
                
                for df_name, df in [("N-1", n1_df), ("N", n_df)]:
                    if not df.empty and 'peg_name' in df.columns:
                        # peg_name에서 CellIdentity 차원 제거
                        # 패턴: 'CellIdentity:숫자,' 형식 제거
                        # 예: CellIdentity:0,QCI:20,PEG → QCI:20,PEG
                        original_count = len(df)
                        df['peg_name'] = df['peg_name'].str.replace(
                            r'CellIdentity:\d+,',  # CellIdentity:숫자, 패턴
                            '', 
                            regex=True
                        )
                        logger.debug(
                            "%s 기간: peg_name에서 CellIdentity 차원 제거 (행수: %d)",
                            df_name, original_count
                        )
                
                # 재집계 (cell이 제거된 peg_name 기준)
                if not n1_df.empty:
                    logger.debug("N-1 재집계 전: %d행", len(n1_df))
                    n1_df = n1_df.groupby(['timestamp', 'peg_name']).agg({
                        'value': 'mean',
                        'ne': 'first',
                        'swname': 'first',
                        'family_name': 'first'
                    }).reset_index()
                    logger.info("N-1 cell 평균화 완료: %d행", len(n1_df))
                
                if not n_df.empty:
                    logger.debug("N 재집계 전: %d행", len(n_df))
                    n_df = n_df.groupby(['timestamp', 'peg_name']).agg({
                        'value': 'mean',
                        'ne': 'first',
                        'swname': 'first',
                        'family_name': 'first'
                    }).reset_index()
                    logger.info("N cell 평균화 완료: %d행", len(n_df))
            else:
                logger.debug("cell_id 필터 존재 - cell 평균화 건너뜀")
            
            # 간단한 집계 로직 (PEGCalculator 완전 통합 전 임시)
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
                
                logger.debug(
                    "pivot 결과: shape=%s, columns=%s, N-1_존재=%s, N_존재=%s",
                    pivot_df.shape,
                    list(pivot_df.columns),
                    "N-1" in pivot_df.columns,
                    "N" in pivot_df.columns
                )

                if "N-1" in pivot_df.columns and "N" in pivot_df.columns:
                    # N-1이 0인 경우 체크 (division by zero 방지)
                    zero_n1_count = (pivot_df["N-1"] == 0).sum()
                    if zero_n1_count > 0:
                        logger.warning("N-1 값이 0인 PEG가 %d개 있습니다 (변화율 계산 시 0으로 처리)", zero_n1_count)
                    
                    pivot_df["change_pct"] = ((pivot_df["N"] - pivot_df["N-1"]) / pivot_df["N-1"] * 100).fillna(0)
                    
                    # change_pct 통계 출력 (디버깅)
                    non_zero_changes = (pivot_df["change_pct"] != 0).sum()
                    if len(pivot_df) > 0:
                        sample_pegs = pivot_df.head(5)
                        logger.debug(
                            "change_pct 계산 완료: 총=%d, 0이_아닌_값=%d개, 샘플_PEG=%s",
                            len(pivot_df),
                            non_zero_changes,
                            [(idx, row["N-1"], row["N"], row["change_pct"]) 
                             for idx, row in sample_pegs.iterrows()]
                        )
                else:
                    logger.warning("pivot 결과에 N-1 또는 N 컬럼이 없습니다! change_pct를 0으로 설정")
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
                logger.warning("combined_df가 비어있습니다!")
                processed_df = pd.DataFrame(columns=["peg_name", "period", "avg_value", "change_pct"])
            
            # ✨ 식별자 정보를 모든 행에 추가 (DB 조회 값 보존)
            if metadata:
                for key, value in metadata.items():
                    if value is not None:
                        processed_df[key] = value
                        logger.debug("컬럼 추가: %s=%s", key, value)

            logger.info(
                "PEGCalculator 처리 완료: %d행 (식별자 보존: ne_key=%s, swname=%s, rel_ver=%s, index_name=%s)",
                len(processed_df),
                metadata.get("ne_key"),
                metadata.get("swname"),
                metadata.get("rel_ver"),
                metadata.get("index_name")
            )
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
            table_config (Dict[str, Any]): 테이블/컬럼 설정
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
            logger.debug(
                "시간 범위 요약: N-1=%s~%s, N=%s~%s",
                time_ranges[0],
                time_ranges[1],
                time_ranges[2],
                time_ranges[3],
            )

            # 2단계: 원시 데이터 조회
            logger.info("2단계: 원시 데이터 조회")
            n1_df, n_df = self._retrieve_raw_peg_data(time_ranges, table_config, filters)
            logger.debug(
                "원시 데이터 조회 결과: N-1 rows=%d, N rows=%d", len(n1_df), len(n_df)
            )

            # 3단계: 원시 데이터 검증
            logger.info("3단계: 원시 데이터 검증")
            self._validate_raw_data(n1_df, n_df)

            # 4단계: PEGCalculator 처리
            logger.info("4단계: PEGCalculator 처리")
            processed_df = self._process_with_calculator(n1_df, n_df, peg_config or {}, filters)
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

