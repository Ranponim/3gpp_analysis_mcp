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
        self.processing_steps = ["change_calculation", "llm_integration", "result_normalization"]

        self.logger.info("DataProcessor 초기화 완료")

    def get_processor_info(self) -> Dict[str, Any]:
        """프로세서 정보 반환"""
        return {
            "processor_name": "DataProcessor",
            "processing_steps": self.processing_steps,
            "supported_formats": ["pandas.DataFrame", "Dict[str, float]"],
            "output_model": "AnalyzedPEGResult",
        }

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
            if processed_df.empty:
                self.logger.info("처리된 DataFrame이 비어 있습니다 - 분석 결과가 없습니다")
                return []

            self.logger.info("1단계: 변화율 계산 및 구조화")

            # processed_df의 change_pct 컬럼 확인 (디버깅)
            if "change_pct" in processed_df.columns:
                unique_change_values = processed_df["change_pct"].unique()
                non_zero_changes = processed_df[processed_df["change_pct"] != 0]["change_pct"].count()
                self.logger.debug(
                    "processed_df change_pct 분석: 고유값_개수=%d, 0이_아닌_값=%d, 샘플_값=%s",
                    len(unique_change_values),
                    non_zero_changes,
                    unique_change_values[:10].tolist() if len(unique_change_values) > 0 else []
                )
            else:
                self.logger.warning("processed_df에 change_pct 컬럼이 없습니다!")

            change_map = processed_df.groupby("peg_name")["change_pct"].first().to_dict()
            
            # change_map 통계 확인 (디버깅)
            if change_map:
                non_zero_in_map = sum(1 for v in change_map.values() if v != 0 and v is not None)
                sample_items = list(change_map.items())[:5]
                self.logger.debug(
                    "change_map 생성: 총=%d개, 0이_아닌_값=%d개, 샘플=%s",
                    len(change_map),
                    non_zero_in_map,
                    sample_items
                )
                
                # 큰 폭의 음수 변화율 검출
                large_negative_changes = {k: v for k, v in change_map.items() if v is not None and v < -20}
                if large_negative_changes:
                    self.logger.warning(
                        "⚠️ change_map에서 큰 폭의 감소 감지: %d개 PEG (변화율 < -20%%)",
                        len(large_negative_changes)
                    )
                    for peg_name, change_pct in large_negative_changes.items():
                        self.logger.warning(f"   {peg_name}: {change_pct:.2f}%")
            else:
                self.logger.warning("change_map이 비어있습니다!")

            # 중복 데이터 감지 및 로깅 (pivot 실패 방지)
            self.logger.debug("pivot 실행 전 중복 데이터 검사 시작")
            
            # dimensions 컬럼이 있으면 포함하여 중복 검사 (cellid 등 고려)
            if 'dimensions' in processed_df.columns:
                duplicate_subset = ['peg_name', 'dimensions', 'period', 'avg_value']
                self.logger.debug("dimensions 컬럼 포함하여 중복 검사: %s", duplicate_subset)
            else:
                duplicate_subset = ['peg_name', 'period', 'avg_value']
                self.logger.debug("dimensions 컬럼 없음, 기본 중복 검사: %s", duplicate_subset)
            
            duplicates = processed_df[processed_df.duplicated(subset=duplicate_subset, keep=False)]
            
            if not duplicates.empty:
                unique_peg_count = duplicates['peg_name'].nunique()
                self.logger.error("❌ 중복 데이터 발견! (pivot 실패 위험)")
                self.logger.error("   중복 건수: %d행, %d개 PEG", len(duplicates), unique_peg_count)
                
                # 중복된 peg_name별로 상세 출력 (최대 5개만)
                for idx, peg_name in enumerate(duplicates['peg_name'].unique()[:5]):
                    dup_rows = duplicates[duplicates['peg_name'] == peg_name]
                    self.logger.error(f"   [{idx+1}] PEG: {peg_name} (중복 {len(dup_rows)}건)")
                    for _, row in dup_rows.iterrows():
                        period = row.get('period', 'N/A')
                        avg_value = row.get('avg_value', 'N/A')
                        dimensions = row.get('dimensions', 'N/A')
                        self.logger.error(f"       period={period}, avg_value={avg_value}, dimensions={dimensions}")
                
                if unique_peg_count > 5:
                    self.logger.error(f"   ... 외 {unique_peg_count - 5}개 PEG 더 있음")
            else:
                self.logger.debug("✓ 중복 데이터 없음 (pivot 안전)")

            # pivot_table 사용 (중복 시에도 안전하게 처리)
            self.logger.debug("pivot_table 실행: index=peg_name, columns=period, aggfunc=first")
            try:
                pivot_df = (
                    processed_df.pivot_table(
                        index="peg_name",
                        columns="period",
                        values="avg_value",
                        aggfunc='first',  # 중복 시 첫 번째 값 사용
                        observed=True  # 성능 최적화
                    )
                    .rename(columns={"N-1": "n_minus_1", "N": "n"})
                )
                self.logger.debug("pivot_table 완료: %d개 PEG", len(pivot_df))
            except Exception as pivot_error:
                self.logger.error("pivot_table 실행 중 오류 발생: %s", pivot_error)
                self.logger.error("processed_df 정보: shape=%s, columns=%s", 
                                 processed_df.shape, processed_df.columns.tolist())
                raise

            pivot_df = pivot_df.where(pivot_df.notna(), None)

            results: List[AnalyzedPEGResult] = []

            for peg_name, row in pivot_df.iterrows():
                n_minus_1_value = row.get("n_minus_1")
                n_value = row.get("n")

                absolute_change: Optional[float] = None
                percentage_change: Optional[float] = None

                if n_minus_1_value is not None and n_value is not None:
                    absolute_change = n_value - n_minus_1_value
                    percentage_change = change_map.get(peg_name)
                    if percentage_change is not None and pd.isna(percentage_change):
                        percentage_change = None
                else:
                    self.logger.warning(
                        "PEG '%s' 데이터 불완전 (N-1=%s, N=%s)", peg_name, n_minus_1_value, n_value
                    )

                results.append(
                    AnalyzedPEGResult(
                        peg_name=peg_name,
                        n_minus_1_value=n_minus_1_value,
                        n_value=n_value,
                        absolute_change=absolute_change,
                        percentage_change=percentage_change,
                    )
                )

            results.sort(key=lambda x: x.peg_name)

            self.logger.info("2단계: LLM 분석 통합")
            llm_peg_analysis: Dict[str, str] = {}
            if llm_analysis_results and isinstance(llm_analysis_results, dict):
                peg_insights = llm_analysis_results.get("peg_insights")
                if isinstance(peg_insights, dict):
                    for peg_name, summary in peg_insights.items():
                        if isinstance(summary, str) and summary.strip():
                            llm_peg_analysis[peg_name] = summary
                elif isinstance(llm_analysis_results.get("summary"), str):
                    summary = llm_analysis_results["summary"]
                    trimmed = summary[:200] + "..." if len(summary) > 200 else summary
                    for result in results:
                        llm_peg_analysis[result.peg_name] = trimmed

            final_results = self._integrate_llm_analysis(results, llm_peg_analysis)

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
