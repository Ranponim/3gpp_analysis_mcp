"""
Analysis Service Orchestration

이 모듈은 전체 셀 성능 분석 워크플로우를 오케스트레이션하는
AnalysisService 클래스를 제공합니다.

기존 main.py의 _analyze_cell_performance_logic() 함수를 모듈화한 것입니다.
"""

from __future__ import annotations

import logging
import os

# 임시로 절대 import 사용 (나중에 패키지 구조 정리 시 수정)
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import pandas as pd

from ..exceptions import ServiceError
from ..repositories import DatabaseRepository
from ..utils import AnalyzedPEGResult, DataProcessingError, DataProcessor, TimeParsingError, TimeRangeParser

from .llm_service import LLMAnalysisService
from .peg_processing_service import PEGProcessingError, PEGProcessingService

# 로깅 설정
logger = logging.getLogger(__name__)


class AnalysisServiceError(ServiceError):
    """
    분석 서비스 관련 오류 예외 클래스

    전체 분석 워크플로우에서 발생하는 오류를 처리합니다.
    """

    def __init__(
        self,
        message: str,
        details: Optional[Union[str, Dict[str, Any]]] = None,
        workflow_step: Optional[str] = None,
        request_context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        AnalysisServiceError 초기화

        Args:
            message (str): 오류 메시지
            details (Optional[Union[str, Dict[str, Any]]]): 추가 상세 정보
            workflow_step (Optional[str]): 실패한 워크플로우 단계
            request_context (Optional[Dict[str, Any]]): 요청 컨텍스트
        """
        super().__init__(message=message, details=details, service_name="AnalysisService", operation="perform_analysis")
        self.workflow_step = workflow_step
        self.request_context = request_context

        logger.error("AnalysisServiceError 발생: %s (단계: %s)", message, workflow_step)

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리 형태로 변환"""
        data = super().to_dict()
        data.update({"workflow_step": self.workflow_step, "request_context": self.request_context})
        return data


class AnalysisService:
    """
    분석 서비스 오케스트레이션 클래스

    전체 셀 성능 분석 워크플로우를 관리하고 조정합니다.
    각 단계별 서비스들을 조합하여 완전한 분석 파이프라인을 제공합니다.

    기존 main.py의 _analyze_cell_performance_logic() 함수를 모듈화한 것입니다.

    워크플로우:
    1. 요청 검증 및 시간 범위 파싱
    2. 데이터베이스에서 PEG 데이터 조회
    3. PEG 데이터 집계 및 파생 PEG 계산
    4. LLM 분석 실행
    5. 백엔드 전송 및 결과 반환
    """

    def __init__(
        self,
        database_repository: Optional[DatabaseRepository] = None,
        peg_processing_service: Optional[PEGProcessingService] = None,
        llm_analysis_service: Optional[LLMAnalysisService] = None,
        time_parser: Optional[TimeRangeParser] = None,
        data_processor: Optional[DataProcessor] = None,
    ):
        """
        AnalysisService 초기화

        Args:
            database_repository (Optional[DatabaseRepository]): 데이터베이스 Repository (레거시)
            peg_processing_service (Optional[PEGProcessingService]): PEG 처리 서비스
            llm_analysis_service (Optional[LLMAnalysisService]): LLM 분석 서비스
            time_parser (Optional[TimeRangeParser]): 시간 범위 파서
            data_processor (Optional[DataProcessor]): 데이터 변환 프로세서
        """
        # 의존성 주입 (기본값으로 구체 구현체 생성)
        self.database_repository = database_repository  # 레거시 지원
        self.peg_processing_service = peg_processing_service
        self.llm_analysis_service = llm_analysis_service or LLMAnalysisService()
        self.time_parser = time_parser or TimeRangeParser()
        self.data_processor = data_processor or DataProcessor()

        # PEGProcessingService가 없으면 레거시 모드로 생성
        if not self.peg_processing_service and self.database_repository:
            self.peg_processing_service = PEGProcessingService(database_repository=self.database_repository)

        # 워크플로우 단계 정의 (DataProcessor 통합)
        self.workflow_steps = [
            "request_validation",
            "time_parsing",
            "peg_processing",  # 데이터 조회 + 처리 통합
            "llm_analysis",
            "data_transformation",  # DataProcessor 단계 추가
            "result_assembly",
        ]

        logger.info(
            "AnalysisService 초기화 완료: peg_service=%s, llm_service=%s, data_processor=%s",
            type(self.peg_processing_service).__name__ if self.peg_processing_service else "None",
            type(self.llm_analysis_service).__name__,
            type(self.data_processor).__name__,
        )

    def get_service_info(self) -> Dict[str, Any]:
        """서비스 정보 반환"""
        return {
            "service_name": "AnalysisService",
            "workflow_steps": self.workflow_steps,
            "dependencies": {
                "peg_processing_service": (
                    type(self.peg_processing_service).__name__ if self.peg_processing_service else None
                ),
                "llm_analysis_service": type(self.llm_analysis_service).__name__,
                "time_parser": type(self.time_parser).__name__,
                "data_processor": type(self.data_processor).__name__,
                "database_repository": (
                    type(self.database_repository).__name__ if self.database_repository else None
                ),  # 레거시
            },
        }

    def validate_request(self, request: Dict[str, Any]) -> None:
        """
        요청 데이터 검증 (기존 main.py 로직)

        Args:
            request (Dict[str, Any]): 분석 요청 데이터

        Raises:
            AnalysisServiceError: 요청 검증 실패 시
        """
        logger.debug("validate_request() 호출: 요청 검증 시작")

        # 필수 필드 확인
        required_fields = ["n_minus_1", "n"]
        missing_fields = [field for field in required_fields if not request.get(field)]

        if missing_fields:
            raise AnalysisServiceError(
                f"필수 필드가 누락되었습니다: {missing_fields}",
                workflow_step="request_validation",
                request_context={"missing_fields": missing_fields},
            )

        # 시간 범위 형식 기본 검증
        n1_text = request.get("n_minus_1", "").strip()
        n_text = request.get("n", "").strip()

        if not n1_text or not n_text:
            raise AnalysisServiceError(
                "'n_minus_1'와 'n' 시간 범위를 모두 제공해야 합니다",
                workflow_step="request_validation",
                request_context={"n_minus_1": n1_text, "n": n_text},
            )

        logger.info("요청 검증 완료: n_minus_1=%s, n=%s", n1_text, n_text)

    def parse_time_ranges(self, request: Dict[str, Any]) -> tuple[datetime, datetime, datetime, datetime]:
        """
        시간 범위 파싱 (TimeRangeParser 사용)

        Args:
            request (Dict[str, Any]): 분석 요청 데이터

        Returns:
            tuple: (n1_start, n1_end, n_start, n_end)

        Raises:
            AnalysisServiceError: 시간 파싱 실패 시
        """
        logger.debug("parse_time_ranges() 호출: 시간 범위 파싱 시작")

        try:
            n1_text = request["n_minus_1"]
            n_text = request["n"]

            # TimeRangeParser 사용 (작업 7에서 구현됨)
            n1_start, n1_end = self.time_parser.parse(n1_text)
            n_start, n_end = self.time_parser.parse(n_text)

            logger.info("시간 범위 파싱 완료: N-1=%s~%s, N=%s~%s", n1_start, n1_end, n_start, n_end)

            return n1_start, n1_end, n_start, n_end

        except TimeParsingError as e:
            raise AnalysisServiceError(
                f"시간 범위 파싱 실패: {e.message}",
                workflow_step="time_parsing",
                request_context={"n_minus_1": request.get("n_minus_1"), "n": request.get("n")},
                details=e.to_dict(),
            ) from e

        except Exception as e:
            raise AnalysisServiceError(
                f"시간 범위 파싱 중 예상치 못한 오류: {e}",
                workflow_step="time_parsing",
                request_context={"n_minus_1": request.get("n_minus_1"), "n": request.get("n")},
            ) from e

    def retrieve_peg_data(
        self, request: Dict[str, Any], time_ranges: tuple[datetime, datetime, datetime, datetime]
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        데이터베이스에서 PEG 데이터 조회

        Args:
            request (Dict[str, Any]): 분석 요청 데이터
            time_ranges (tuple): (n1_start, n1_end, n_start, n_end)

        Returns:
            tuple[pd.DataFrame, pd.DataFrame]: (n1_df, n_df)

        Raises:
            AnalysisServiceError: 데이터 조회 실패 시
        """
        logger.debug("retrieve_peg_data() 호출: 데이터 조회 시작")

        if not self.database_repository:
            raise AnalysisServiceError("DatabaseRepository가 설정되지 않았습니다", workflow_step="data_retrieval")

        try:
            n1_start, n1_end, n_start, n_end = time_ranges

            # 데이터베이스 설정 (기존 main.py 로직)
            request.get("db", {})
            table = request.get("table", "summary")
            columns = request.get(
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

            # N-1 기간 데이터 조회
            logger.info("N-1 기간 데이터 조회: %s ~ %s", n1_start, n1_end)
            n1_data = self.database_repository.fetch_peg_data(
                table_name=table,
                columns=columns,
                time_range=(n1_start, n1_end),
                filters=request.get("filters", {}),
                limit=request.get("data_limit"),
            )

            # N 기간 데이터 조회
            logger.info("N 기간 데이터 조회: %s ~ %s", n_start, n_end)
            n_data = self.database_repository.fetch_peg_data(
                table_name=table,
                columns=columns,
                time_range=(n_start, n_end),
                filters=request.get("filters", {}),
                limit=request.get("data_limit"),
            )

            # DataFrame 변환
            n1_df = pd.DataFrame(n1_data)
            n_df = pd.DataFrame(n_data)

            logger.info("데이터 조회 완료: N-1=%d행, N=%d행", len(n1_df), len(n_df))
            return n1_df, n_df

        except Exception as e:
            raise AnalysisServiceError(
                f"데이터 조회 실패: {e}",
                workflow_step="data_retrieval",
                request_context={"table": table, "time_ranges": str(time_ranges)[:100]},
            ) from e

    def process_peg_data(self, n1_df: pd.DataFrame, n_df: pd.DataFrame, request: Dict[str, Any]) -> pd.DataFrame:
        """
        PEG 데이터 처리 및 집계 (PEGCalculator 사용)

        Args:
            n1_df (pd.DataFrame): N-1 기간 데이터
            n_df (pd.DataFrame): N 기간 데이터
            request (Dict[str, Any]): 분석 요청 데이터

        Returns:
            pd.DataFrame: 처리된 PEG 데이터

        Raises:
            AnalysisServiceError: PEG 처리 실패 시
        """
        logger.debug("process_peg_data() 호출: PEG 데이터 처리 시작")

        try:
            # 기존 main.py의 process_and_analyze() 로직을 여기서 구현
            # 현재는 간단한 집계로 시작 (추후 작업 10에서 상세 구현)

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

            # 변화율 계산 로직 (간단한 버전)
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

            logger.info("PEG 데이터 처리 완료: %d행", len(processed_df))
            return processed_df

        except Exception as e:
            raise AnalysisServiceError(
                f"PEG 데이터 처리 실패: {e}",
                workflow_step="peg_processing",
                request_context={"n1_rows": len(n1_df), "n_rows": len(n_df)},
            ) from e

    def perform_analysis(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        전체 분석 워크플로우 실행

        Args:
            request (Dict[str, Any]): 분석 요청 데이터

        Returns:
            Dict[str, Any]: 분석 결과

        Raises:
            AnalysisServiceError: 분석 실패 시
        """
        logger.info("perform_analysis() 호출: 전체 분석 워크플로우 시작")

        try:
            # 1단계: 요청 검증
            logger.info("1단계: 요청 검증")
            self.validate_request(request)
            logger.debug(
                "요청 필드 요약: keys=%s, backend_url=%s",
                list(request.keys()),
                bool(request.get("backend_url")),
            )

            # 2단계: 시간 범위 파싱
            logger.info("2단계: 시간 범위 파싱")
            time_ranges = self.parse_time_ranges(request)
            logger.debug(
                "시간 범위 파싱 결과: N-1=%s~%s, N=%s~%s",
                time_ranges[0],
                time_ranges[1],
                time_ranges[2],
                time_ranges[3],
            )

            # 3단계: PEG 데이터 처리 (PEGProcessingService 사용)
            if self.peg_processing_service:
                logger.info("3단계: PEG 데이터 처리 (PEGProcessingService 위임)")

                # 테이블 설정 준비
                table_config = {
                    "table": request.get("table", "summary"),
                    "columns": request.get(
                        "columns",
                        {
                            "time": "datetime",
                            "peg_name": "peg_name",
                            "value": "value",
                            "ne": "ne",
                            "cellid": "cellid",
                            "host": "host",
                        },
                    ),
                    "data_limit": request.get("data_limit"),
                }
                logger.debug(
                    "PEGProcessingService 입력: table_config=%s, filters=%s",
                    {
                        "table": table_config["table"],
                        "columns": list(table_config["columns"].keys()),
                        "data_limit": table_config["data_limit"],
                    },
                    request.get("filters", {}),
                )

                # PEG 설정 준비
                peg_config = {"aggregation_method": "mean", "derived_pegs": request.get("peg_definitions", {})}

                try:
                    processed_df = self.peg_processing_service.process_peg_data(
                        time_ranges=time_ranges,
                        table_config=table_config,
                        filters=request.get("filters", {}),
                        peg_config=peg_config,
                    )
                except PEGProcessingError as e:
                    raise AnalysisServiceError(
                        f"PEG 처리 서비스 실패: {e.message}", workflow_step="peg_processing", details=e.to_dict()
                    ) from e
            else:
                logger.warning("PEGProcessingService가 없어 레거시 모드 사용")
                # 레거시 모드: 직접 처리
                if self.database_repository:
                    n1_df, n_df = self.retrieve_peg_data(request, time_ranges)
                    processed_df = self.process_peg_data(n1_df, n_df, request)
                else:
                    # 모킹 데이터
                    logger.warning("DatabaseRepository도 없어 모킹 데이터 사용")
                    n1_df = pd.DataFrame(
                        {
                            "peg_name": ["preamble_count", "response_count"],
                            "value": [1000.0, 950.0],
                            "timestamp": [time_ranges[0], time_ranges[0]],
                        }
                    )
                    n_df = pd.DataFrame(
                        {
                            "peg_name": ["preamble_count", "response_count"],
                            "value": [1100.0, 1000.0],
                            "timestamp": [time_ranges[2], time_ranges[2]],
                        }
                    )
                    processed_df = self.process_peg_data(n1_df, n_df, request)

            # 4단계: LLM 분석
            logger.info("4단계: LLM 분석")
            analysis_type = request.get("analysis_type", "enhanced")
            selected_pegs = request.get("selected_pegs")
            enable_mock = request.get("enable_mock", False)
            logger.debug(
                "LLM 분석 호출 준비: analysis_type=%s, selected_pegs=%s, enable_mock=%s", 
                analysis_type,
                selected_pegs,
                enable_mock,
            )

            llm_result = self.llm_analysis_service.analyze_peg_data(
                processed_df=processed_df,
                n1_range=request["n_minus_1"],
                n_range=request["n"],
                analysis_type=analysis_type,
                selected_pegs=selected_pegs,
                enable_mock=enable_mock,
            )

            # 4.5단계: Choi Deterministic 판정 (옵션)
            # 요청 파라미터 > 환경변수 > 기본값 순으로 우선순위 적용
            from config.settings import get_settings
            settings = get_settings()
            use_choi = bool(request.get("use_choi", settings.peg_use_choi))
            choi_result_normalized = None
            if use_choi:
                logger.info("4.5단계: Choi Deterministic 판정 실행")
                try:
                    from .deterministic_judgement_service import run_choi_judgement
                    # MCP 표준 요청 바디 생성(백엔드 요구 형태와 동일 구조 사용)
                    choi_request = {
                        "input_data": request.get("input_data", {}),
                        "cell_ids": request.get("cell_ids", []),
                        "time_range": request.get("time_range", {}),
                        "compare_mode": request.get("compare_mode", True),
                    }
                    choi_result_normalized = run_choi_judgement(choi_request)
                except Exception as e:  # pragma: no cover
                    logger.error("Choi 판정 실행 실패(계속 진행): %s", e, exc_info=True)
                    choi_result_normalized = {
                        "overall": None,
                        "reasons": ["Choi judgement failed"],
                        "by_kpi": {},
                        "warnings": [str(e)],
                    }

            # 5단계: 데이터 변환 (DataProcessor 사용)
            logger.info("5단계: 데이터 변환 (DataProcessor 위임)")
            try:
                analyzed_peg_results = self.data_processor.process_data(
                    processed_df=processed_df, llm_analysis_results=llm_result
                )
                logger.debug(
                    "DataProcessor 결과: analyzed_pegs=%d", len(analyzed_peg_results)
                )
            except DataProcessingError as e:
                raise AnalysisServiceError(
                    f"데이터 변환 실패: {e.message}", workflow_step="data_transformation", details=e.to_dict()
                ) from e

            # 6단계: 결과 조립 (DataProcessor 결과 활용)
            logger.info("6단계: 결과 조립")
            final_result = self._assemble_final_result_with_processor(
                request=request,
                time_ranges=time_ranges,
                analyzed_peg_results=analyzed_peg_results,
                llm_result=llm_result,
            )
            logger.debug("최종 결과 조립 완료: keys=%s", list(final_result.keys()))

            # 6.5단계: peg_analysis에 choi_judgement 병합(옵션)
            if choi_result_normalized is not None:
                logger.info("6.5단계: peg_analysis.choi_judgement 병합")
                peg_analysis = final_result.setdefault("peg_analysis", {})
                peg_analysis["choi_judgement"] = choi_result_normalized

            logger.info("전체 분석 워크플로우 완료: 결과키=%d개", len(final_result))
            return final_result

        except AnalysisServiceError:
            # 이미 AnalysisServiceError인 경우 그대로 전파
            raise

        except Exception as e:
            # 예상치 못한 오류를 AnalysisServiceError로 변환
            raise AnalysisServiceError(
                f"분석 워크플로우 실행 중 예상치 못한 오류: {e}",
                workflow_step="unknown",
                request_context={"request_keys": list(request.keys())},
            ) from e

    def _assemble_final_result(
        self,
        request: Dict[str, Any],
        time_ranges: tuple[datetime, datetime, datetime, datetime],
        processed_df: pd.DataFrame,
        llm_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        최종 결과 조립 (기존 main.py 로직)

        Args:
            request (Dict[str, Any]): 원본 요청
            time_ranges (tuple): 파싱된 시간 범위
            processed_df (pd.DataFrame): 처리된 PEG 데이터
            llm_result (Dict[str, Any]): LLM 분석 결과

        Returns:
            Dict[str, Any]: 최종 분석 결과
        """
        logger.debug("_assemble_final_result() 호출: 최종 결과 조립")

        n1_start, n1_end, n_start, n_end = time_ranges

        # 기본 결과 구조
        result = {
            "status": "success",
            "analysis_type": request.get("analysis_type", "enhanced"),
            "time_ranges": {
                "n_minus_1": {
                    "start": n1_start.isoformat(),
                    "end": n1_end.isoformat(),
                    "range_text": request["n_minus_1"],
                },
                "n": {"start": n_start.isoformat(), "end": n_end.isoformat(), "range_text": request["n"]},
            },
            "data_summary": {
                "total_pegs": len(processed_df["peg_name"].unique()) if not processed_df.empty else 0,
                "total_rows": len(processed_df),
                "has_data": not processed_df.empty,
            },
            "llm_analysis": llm_result,
            "metadata": {
                "workflow_version": "2.0",
                "processing_timestamp": datetime.now().isoformat(),
                "request_id": request.get("request_id", "unknown"),
                "enable_mock": request.get("enable_mock", False),
            },
        }

        # 선택적 필드들 추가
        if "selected_pegs" in request and request["selected_pegs"]:
            result["selected_pegs"] = request["selected_pegs"]

        if "output_dir" in request:
            result["output_dir"] = request["output_dir"]

        logger.info("최종 결과 조립 완료: %d개 최상위 키", len(result))
        return result

    def _assemble_final_result_with_processor(
        self,
        request: Dict[str, Any],
        time_ranges: tuple[datetime, datetime, datetime, datetime],
        analyzed_peg_results: List[AnalyzedPEGResult],
        llm_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        DataProcessor 결과를 활용한 최종 결과 조립

        Args:
            request (Dict[str, Any]): 원본 요청
            time_ranges (tuple): 파싱된 시간 범위
            analyzed_peg_results (List[AnalyzedPEGResult]): DataProcessor 결과
            llm_result (Dict[str, Any]): LLM 분석 결과

        Returns:
            Dict[str, Any]: 최종 분석 결과
        """
        logger.debug("_assemble_final_result_with_processor() 호출: DataProcessor 결과 조립")

        n1_start, n1_end, n_start, n_end = time_ranges

        # DataProcessor 요약 통계 생성
        summary_stats = self.data_processor.create_summary_statistics(analyzed_peg_results)

        # 기본 결과 구조 (DataProcessor 결과 통합)
        result = {
            "status": "success",
            "analysis_type": request.get("analysis_type", "enhanced"),
            "time_ranges": {
                "n_minus_1": {
                    "start": n1_start.isoformat(),
                    "end": n1_end.isoformat(),
                    "range_text": request["n_minus_1"],
                },
                "n": {"start": n_start.isoformat(), "end": n_end.isoformat(), "range_text": request["n"]},
            },
            "data_summary": {
                "total_pegs": summary_stats["total_pegs"],
                "complete_data_pegs": summary_stats["complete_data_pegs"],
                "incomplete_data_pegs": summary_stats["incomplete_data_pegs"],
                "has_data": summary_stats["total_pegs"] > 0,
            },
            "peg_analysis": {
                "results": [result.to_dict() for result in analyzed_peg_results],
                "statistics": summary_stats,
            },
            "llm_analysis": llm_result,
            "metadata": {
                "workflow_version": "3.0",  # DataProcessor 통합 버전
                "processing_timestamp": datetime.now().isoformat(),
                "request_id": request.get("request_id", "unknown"),
                "enable_mock": request.get("enable_mock", False),
                "data_processor": True,
            },
        }

        # 선택적 필드들 추가
        if "selected_pegs" in request and request["selected_pegs"]:
            result["selected_pegs"] = request["selected_pegs"]

        if "output_dir" in request:
            result["output_dir"] = request["output_dir"]

        logger.info(
            "DataProcessor 결과 조립 완료: %d개 최상위 키, %d개 PEG 분석", len(result), len(analyzed_peg_results)
        )
        return result

    def get_workflow_status(self) -> Dict[str, Any]:
        """워크플로우 상태 정보 반환"""
        return {
            "workflow_steps": self.workflow_steps,
            "step_count": len(self.workflow_steps),
            "dependencies_ready": {
                "peg_processing_service": self.peg_processing_service is not None,
                "llm_analysis_service": self.llm_analysis_service is not None,
                "time_parser": self.time_parser is not None,
                "data_processor": self.data_processor is not None,
                "database_repository": self.database_repository is not None,  # 레거시
            },
        }

    def close(self) -> None:
        """리소스 정리"""
        if hasattr(self.llm_analysis_service, "close"):
            self.llm_analysis_service.close()

        if hasattr(self.peg_processing_service, "close"):
            self.peg_processing_service.close()

        if hasattr(self.database_repository, "disconnect"):
            self.database_repository.disconnect()

        logger.info("AnalysisService 리소스 정리 완료")

    def __enter__(self):
        """컨텍스트 매니저 진입"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """컨텍스트 매니저 종료"""
        self.close()

        # 예외 발생 시 로그 기록
        if exc_type:
            logger.error("AnalysisService 컨텍스트에서 예외 발생: %s", exc_val)

        return False  # 예외를 다시 발생시킴
