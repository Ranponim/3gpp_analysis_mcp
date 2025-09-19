"""
Data Processor for Transformation and Normalization

이 모듈은 N-1과 N 기간 데이터를 병합하고, 변화율을 계산하며,
최종 분석 결과를 정규화하는 DataProcessor 클래스를 제공합니다.

기존 AnalysisService의 데이터 변환 로직을 분리하여
단일 책임 원칙을 강화하고 재사용성을 높입니다.
"""

from __future__ import annotations

import logging
import os

# 임시로 절대 import 사용 (나중에 패키지 구조 정리 시 수정)
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


# 로깅 설정
logger = logging.getLogger(__name__)


@dataclass
class AnalyzedPEGResult:
    """
    분석된 PEG 결과를 나타내는 데이터 모델

    ResponseFormatter(작업 19)를 위한 일관된 데이터 구조를 제공합니다.
    """

    peg_name: str
    n_minus_1_value: Optional[float]
    n_value: Optional[float]
    absolute_change: Optional[float]
    percentage_change: Optional[float]
    llm_analysis_summary: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리 형태로 변환"""
        return {
            "peg_name": self.peg_name,
            "n_minus_1_value": self.n_minus_1_value,
            "n_value": self.n_value,
            "absolute_change": self.absolute_change,
            "percentage_change": self.percentage_change,
            "llm_analysis_summary": self.llm_analysis_summary,
        }

    def has_complete_data(self) -> bool:
        """완전한 데이터 (N-1, N 모두 존재)인지 확인"""
        return self.n_minus_1_value is not None and self.n_value is not None

    def has_change_data(self) -> bool:
        """변화율 데이터가 있는지 확인"""
        return self.absolute_change is not None and self.percentage_change is not None


class DataProcessingError(Exception):
    """
    데이터 처리 관련 오류 예외 클래스

    DataProcessor에서 발생하는 오류를 처리합니다.
    """

    def __init__(
        self,
        message: str,
        details: Optional[Union[str, Dict[str, Any]]] = None,
        processing_step: Optional[str] = None,
        data_context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        DataProcessingError 초기화

        Args:
            message (str): 오류 메시지
            details (Optional[Union[str, Dict[str, Any]]]): 추가 상세 정보
            processing_step (Optional[str]): 실패한 처리 단계
            data_context (Optional[Dict[str, Any]]): 데이터 컨텍스트
        """
        super().__init__(message)
        self.message = message
        self.details = details
        self.processing_step = processing_step
        self.data_context = data_context

        logger.error("DataProcessingError 발생: %s (단계: %s)", message, processing_step)

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리 형태로 변환"""
        return {
            "error_type": "DataProcessingError",
            "message": self.message,
            "details": self.details,
            "processing_step": self.processing_step,
            "data_context": self.data_context,
        }


class DataProcessor:
    """
    데이터 변환 및 정규화 처리 클래스

    N-1과 N 기간 데이터를 병합하고, 변화율을 계산하며,
    LLM 분석 결과와 통합하여 일관된 데이터 구조를 제공합니다.

    기존 AnalysisService의 _assemble_final_result() 로직을 모듈화한 것입니다.

    주요 기능:
    1. N-1과 N 기간 데이터 병합 및 정렬
    2. 변화율 계산 (절대값, 백분율)
    3. 데이터 정규화 및 표준화
    4. LLM 분석 결과와 통합
    5. ResponseFormatter를 위한 일관된 데이터 구조 제공
    """

    def __init__(self):
        """
        DataProcessor 초기화
        """
        self.logger = logging.getLogger(__name__ + ".DataProcessor")

        # 처리 단계 정의
        self.processing_steps = ["data_merging", "change_calculation", "llm_integration", "result_normalization"]

        self.logger.info("DataProcessor 초기화 완료")

    def get_processor_info(self) -> Dict[str, Any]:
        """프로세서 정보 반환"""
        return {
            "processor_name": "DataProcessor",
            "processing_steps": self.processing_steps,
            "supported_formats": ["pandas.DataFrame", "Dict[str, float]"],
            "output_model": "AnalyzedPEGResult",
        }

    def _merge_peg_data(
        self, n_minus_1_data: Dict[str, float], n_data: Dict[str, float]
    ) -> Dict[str, Dict[str, Optional[float]]]:
        """
        N-1과 N 기간 PEG 데이터 병합

        Args:
            n_minus_1_data (Dict[str, float]): N-1 기간 PEG 데이터
            n_data (Dict[str, float]): N 기간 PEG 데이터

        Returns:
            Dict[str, Dict[str, Optional[float]]]: 병합된 데이터
            {peg_name: {'n_minus_1_value': float, 'n_value': float}}

        Raises:
            DataProcessingError: 병합 실패 시
        """
        self.logger.debug("_merge_peg_data() 호출: 데이터 병합 시작")

        try:
            # 모든 고유 PEG 이름 수집
            all_peg_names = set(n_minus_1_data.keys()) | set(n_data.keys())

            merged_data = {}

            for peg_name in all_peg_names:
                merged_data[peg_name] = {
                    "n_minus_1_value": n_minus_1_data.get(peg_name),
                    "n_value": n_data.get(peg_name),
                }

            self.logger.info(
                "데이터 병합 완료: %d개 PEG (N-1: %d개, N: %d개)", len(merged_data), len(n_minus_1_data), len(n_data)
            )

            return merged_data

        except Exception as e:
            raise DataProcessingError(
                f"PEG 데이터 병합 실패: {e}",
                processing_step="data_merging",
                data_context={
                    "n_minus_1_pegs": len(n_minus_1_data),
                    "n_pegs": len(n_data),
                    "total_unique_pegs": len(set(n_minus_1_data.keys()) | set(n_data.keys())),
                },
            ) from e

    def _calculate_change_rates(self, merged_data: Dict[str, Dict[str, Optional[float]]]) -> List[AnalyzedPEGResult]:
        """
        변화율 계산 및 AnalyzedPEGResult 생성

        Args:
            merged_data (Dict): 병합된 PEG 데이터

        Returns:
            List[AnalyzedPEGResult]: 분석된 PEG 결과 리스트

        Raises:
            DataProcessingError: 변화율 계산 실패 시
        """
        self.logger.debug("_calculate_change_rates() 호출: 변화율 계산 시작")

        try:
            results = []

            for peg_name, values in merged_data.items():
                n_minus_1_value = values["n_minus_1_value"]
                n_value = values["n_value"]

                # 절대 변화량 계산
                if n_minus_1_value is not None and n_value is not None:
                    absolute_change = n_value - n_minus_1_value

                    # 백분율 변화율 계산 (0으로 나누기 방지)
                    if n_minus_1_value != 0:
                        percentage_change = (absolute_change / n_minus_1_value) * 100
                    else:
                        percentage_change = None  # 0으로 나누기 불가
                        self.logger.warning("PEG '%s': N-1 값이 0이어서 백분율 계산 불가", peg_name)
                else:
                    absolute_change = None
                    percentage_change = None
                    self.logger.warning(
                        "PEG '%s': 불완전한 데이터 (N-1: %s, N: %s)", peg_name, n_minus_1_value, n_value
                    )

                # AnalyzedPEGResult 생성
                result = AnalyzedPEGResult(
                    peg_name=peg_name,
                    n_minus_1_value=n_minus_1_value,
                    n_value=n_value,
                    absolute_change=absolute_change,
                    percentage_change=percentage_change,
                )

                results.append(result)

            # 결과를 PEG 이름으로 정렬
            results.sort(key=lambda x: x.peg_name)

            self.logger.info("변화율 계산 완료: %d개 PEG 결과", len(results))
            return results

        except Exception as e:
            raise DataProcessingError(
                f"변화율 계산 실패: {e}",
                processing_step="change_calculation",
                data_context={"merged_pegs": len(merged_data)},
            ) from e

    def _integrate_llm_analysis(
        self, peg_results: List[AnalyzedPEGResult], llm_analysis_results: Optional[Dict[str, str]] = None
    ) -> List[AnalyzedPEGResult]:
        """
        LLM 분석 결과를 PEG 결과에 통합

        Args:
            peg_results (List[AnalyzedPEGResult]): PEG 분석 결과
            llm_analysis_results (Optional[Dict[str, str]]): LLM 분석 결과

        Returns:
            List[AnalyzedPEGResult]: LLM 분석이 통합된 결과
        """
        self.logger.debug("_integrate_llm_analysis() 호출: LLM 분석 통합")

        if not llm_analysis_results:
            self.logger.info("LLM 분석 결과가 없어 통합 건너뜀")
            return peg_results

        try:
            # LLM 분석 결과를 PEG별로 매핑
            for peg_result in peg_results:
                peg_name = peg_result.peg_name

                # PEG 이름으로 LLM 분석 찾기 (대소문자 무시)
                llm_summary = None
                for llm_peg_name, summary in llm_analysis_results.items():
                    if llm_peg_name.lower() == peg_name.lower():
                        llm_summary = summary
                        break

                # LLM 분석 결과 설정
                peg_result.llm_analysis_summary = llm_summary

                if llm_summary:
                    self.logger.debug("PEG '%s'에 LLM 분석 통합: %d자", peg_name, len(llm_summary))

            integrated_count = sum(1 for result in peg_results if result.llm_analysis_summary)
            self.logger.info("LLM 분석 통합 완료: %d/%d개 PEG에 분석 결과", integrated_count, len(peg_results))

            return peg_results

        except Exception as e:
            raise DataProcessingError(
                f"LLM 분석 통합 실패: {e}",
                processing_step="llm_integration",
                data_context={"peg_count": len(peg_results), "llm_keys": len(llm_analysis_results)},
            ) from e

    def _dataframe_to_dict(self, df: pd.DataFrame) -> Dict[str, Dict[str, float]]:
        """
        pandas DataFrame을 딕셔너리로 변환

        Args:
            df (pd.DataFrame): 처리된 PEG DataFrame

        Returns:
            Dict[str, Dict[str, float]]: {period: {peg_name: avg_value}}
        """
        self.logger.debug("_dataframe_to_dict() 호출: DataFrame 변환")

        if df.empty:
            return {"N-1": {}, "N": {}}

        try:
            # 기간별로 그룹화
            result = {"N-1": {}, "N": {}}

            for _, row in df.iterrows():
                period = row["period"]
                peg_name = row["peg_name"]
                avg_value = row["avg_value"]

                if period in result:
                    result[period][peg_name] = avg_value

            self.logger.info("DataFrame 변환 완료: N-1=%d개, N=%d개 PEG", len(result["N-1"]), len(result["N"]))

            return result

        except Exception as e:
            raise DataProcessingError(
                f"DataFrame 변환 실패: {e}",
                processing_step="data_merging",
                data_context={"df_shape": df.shape, "df_columns": list(df.columns)},
            ) from e

    def process_data(
        self, processed_df: pd.DataFrame, llm_analysis_results: Optional[Dict[str, Any]] = None
    ) -> List[AnalyzedPEGResult]:
        """
        전체 데이터 처리 워크플로우 실행

        Args:
            processed_df (pd.DataFrame): PEGProcessingService에서 처리된 데이터
            llm_analysis_results (Optional[Dict[str, Any]]): LLM 분석 결과

        Returns:
            List[AnalyzedPEGResult]: 정규화된 분석 결과

        Raises:
            DataProcessingError: 처리 실패 시
        """
        self.logger.info("process_data() 호출: 데이터 처리 워크플로우 시작")

        try:
            # 1단계: DataFrame을 딕셔너리로 변환
            self.logger.info("1단계: DataFrame 변환")
            period_data = self._dataframe_to_dict(processed_df)

            # 2단계: N-1과 N 데이터 병합
            self.logger.info("2단계: 데이터 병합")
            merged_data = self._merge_peg_data(n_minus_1_data=period_data["N-1"], n_data=period_data["N"])

            # 3단계: 변화율 계산
            self.logger.info("3단계: 변화율 계산")
            peg_results = self._calculate_change_rates(merged_data)

            # 4단계: LLM 분석 통합
            self.logger.info("4단계: LLM 분석 통합")

            # LLM 결과에서 PEG별 분석 추출
            llm_peg_analysis = {}
            if llm_analysis_results and isinstance(llm_analysis_results, dict):
                # LLM 결과 구조 분석 (기존 main.py 형식)
                if "summary" in llm_analysis_results:
                    # 전체 요약을 모든 PEG에 적용 (간단한 버전)
                    summary = llm_analysis_results["summary"]
                    for result in peg_results:
                        llm_peg_analysis[result.peg_name] = summary[:200] + "..." if len(summary) > 200 else summary

            final_results = self._integrate_llm_analysis(peg_results, llm_peg_analysis)

            self.logger.info("데이터 처리 워크플로우 완료: %d개 PEG 결과", len(final_results))
            return final_results

        except DataProcessingError:
            # 이미 DataProcessingError인 경우 그대로 전파
            raise

        except Exception as e:
            # 예상치 못한 오류를 DataProcessingError로 변환
            raise DataProcessingError(
                f"데이터 처리 중 예상치 못한 오류: {e}",
                processing_step="unknown",
                data_context={"df_shape": processed_df.shape if not processed_df.empty else None},
            ) from e

    def create_summary_statistics(self, results: List[AnalyzedPEGResult]) -> Dict[str, Any]:
        """
        분석 결과 요약 통계 생성

        Args:
            results (List[AnalyzedPEGResult]): 분석된 PEG 결과

        Returns:
            Dict[str, Any]: 요약 통계
        """
        self.logger.debug("create_summary_statistics() 호출: 요약 통계 생성")

        if not results:
            return {
                "total_pegs": 0,
                "complete_data_pegs": 0,
                "incomplete_data_pegs": 0,
                "positive_changes": 0,
                "negative_changes": 0,
                "no_change": 0,
                "avg_percentage_change": None,
            }

        try:
            complete_data_count = sum(1 for r in results if r.has_complete_data())
            incomplete_data_count = len(results) - complete_data_count

            # 변화율 통계
            valid_changes = [r.percentage_change for r in results if r.percentage_change is not None]

            positive_changes = sum(1 for change in valid_changes if change > 0)
            negative_changes = sum(1 for change in valid_changes if change < 0)
            no_change = sum(1 for change in valid_changes if change == 0)

            avg_percentage_change = sum(valid_changes) / len(valid_changes) if valid_changes else None

            summary = {
                "total_pegs": len(results),
                "complete_data_pegs": complete_data_count,
                "incomplete_data_pegs": incomplete_data_count,
                "positive_changes": positive_changes,
                "negative_changes": negative_changes,
                "no_change": no_change,
                "avg_percentage_change": round(avg_percentage_change, 2) if avg_percentage_change is not None else None,
            }

            self.logger.info(
                "요약 통계 생성 완료: %d개 PEG, 완전 데이터 %d개", summary["total_pegs"], summary["complete_data_pegs"]
            )

            return summary

        except Exception as e:
            raise DataProcessingError(
                f"요약 통계 생성 실패: {e}",
                processing_step="result_normalization",
                data_context={"results_count": len(results)},
            ) from e

    def normalize_for_response_formatter(
        self, results: List[AnalyzedPEGResult], metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        ResponseFormatter를 위한 데이터 정규화

        Args:
            results (List[AnalyzedPEGResult]): 분석된 PEG 결과
            metadata (Optional[Dict[str, Any]]): 추가 메타데이터

        Returns:
            Dict[str, Any]: 정규화된 응답 데이터
        """
        self.logger.debug("normalize_for_response_formatter() 호출: 응답 정규화")

        try:
            # 요약 통계 생성
            summary_stats = self.create_summary_statistics(results)

            # 결과를 딕셔너리 형태로 변환
            peg_results_dict = [result.to_dict() for result in results]

            # 정규화된 응답 구조
            normalized_response = {
                "peg_results": peg_results_dict,
                "summary_statistics": summary_stats,
                "metadata": metadata or {},
                "processing_info": {
                    "processor_name": "DataProcessor",
                    "processing_timestamp": datetime.now().isoformat(),
                    "total_processed": len(results),
                },
            }

            self.logger.info("응답 정규화 완료: %d개 PEG 결과", len(peg_results_dict))
            return normalized_response

        except Exception as e:
            raise DataProcessingError(
                f"응답 정규화 실패: {e}",
                processing_step="result_normalization",
                data_context={"results_count": len(results)},
            ) from e

    def get_processing_status(self) -> Dict[str, Any]:
        """처리 상태 정보 반환"""
        return {"processing_steps": self.processing_steps, "step_count": len(self.processing_steps), "is_ready": True}
