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
    
    필드명 규칙:
    - n_minus_1_avg, n_avg: 평균값 (avg는 통계 용어로 명확함)
    - dimensions: 차원 정보 (예: "cNum=52,mcID=0,EstabCause=MO_DATA,QCI=9")
    - 향후 확장: n_minus_1_pct_95, n_minus_1_min, n_minus_1_max 등
    """

    peg_name: str
    n_minus_1_avg: Optional[float]  # 수정: _value → _avg (평균값이므로)
    n_avg: Optional[float]           # 수정: _value → _avg (평균값이므로)
    absolute_change: Optional[float]
    percentage_change: Optional[float]
    dimensions: Optional[str] = None  # 추가: 차원 정보 (cNum, mcID, QCI 등)
    llm_analysis_summary: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리 형태로 변환"""
        return {
            "peg_name": self.peg_name,
            "n_minus_1_avg": self.n_minus_1_avg,  # 수정
            "n_avg": self.n_avg,                   # 수정
            "absolute_change": self.absolute_change,
            "percentage_change": self.percentage_change,
            "dimensions": self.dimensions,  # 추가
            "llm_analysis_summary": self.llm_analysis_summary,
        }

    def has_complete_data(self) -> bool:
        """완전한 데이터 (N-1, N 모두 존재)인지 확인"""
        return self.n_minus_1_avg is not None and self.n_avg is not None  # 수정

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

            # dimensions 컬럼 존재 여부 확인
            has_dimensions = 'dimensions' in processed_df.columns
            
            # QCI 필터링 (QCI 1, 5, 9만 유지)
            if has_dimensions:
                initial_count = len(processed_df)
                
                # QCI가 포함된 dimensions를 가진 행 식별
                qci_mask = processed_df['dimensions'].notna() & processed_df['dimensions'].str.contains('QCI=', na=False)
                
                if qci_mask.sum() > 0:
                    self.logger.info("🔍 QCI 필터링 시작: %d개 행에서 QCI 검출", qci_mask.sum())
                    
                    # QCI 1, 5, 9만 유지하는 마스크
                    allowed_qci_pattern = r'QCI=(1|5|9)(?:,|$)'
                    keep_mask = ~qci_mask | processed_df['dimensions'].str.contains(allowed_qci_pattern, regex=True, na=False)
                    
                    # 필터링 전후 통계
                    filtered_out = (~keep_mask).sum()
                    if filtered_out > 0:
                        self.logger.info("🗑️ QCI 필터링: %d개 행 제거 (QCI ≠ 1,5,9)", filtered_out)
                        
                        # 제거된 QCI 값 샘플 출력 (디버깅용)
                        removed_dims = processed_df[~keep_mask]['dimensions'].unique()[:5]
                        self.logger.debug("   제거된 dimensions 샘플: %s", removed_dims.tolist())
                    
                    # 필터링 적용
                    processed_df = processed_df[keep_mask].reset_index(drop=True)
                    self.logger.info("✅ QCI 필터링 완료: %d → %d개 행", initial_count, len(processed_df))
                else:
                    self.logger.debug("QCI 차원이 포함된 데이터 없음 - 필터링 스킵")
            
            # 필터링 후 데이터 검증
            if processed_df.empty:
                self.logger.warning("⚠️ QCI 필터링 후 데이터가 비어있습니다!")
                return []

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

            # change_map 생성 후 타입 검증 및 정제
            # dimensions가 있으면 (peg_name, dimensions) 튜플로 그룹화
            if has_dimensions:
                self.logger.info("✅ dimensions 컬럼 감지 - 차원별 PEG 유지")
                change_map_raw = processed_df.groupby(["peg_name", "dimensions"])["change_pct"].first().to_dict()
            else:
                self.logger.warning("⚠️ dimensions 컬럼 없음 - peg_name만으로 그룹화")
                change_map_raw = processed_df.groupby("peg_name")["change_pct"].first().to_dict()
            
            # change_map 타입 검증: 문자열을 숫자로 변환
            change_map = {}
            invalid_count = 0
            for key, value in change_map_raw.items():
                # key는 has_dimensions에 따라 str 또는 (str, str) 튜플
                peg_display = f"{key[0]} (dims: {key[1]})" if has_dimensions else str(key)
                
                if value is None or pd.isna(value):
                    change_map[key] = None
                elif isinstance(value, (int, float)):
                    change_map[key] = value
                elif isinstance(value, str):
                    try:
                        change_map[key] = float(value)
                        self.logger.warning(
                            "PEG '%s'의 change_pct가 문자열('%s')입니다. float로 변환했습니다.",
                            peg_display, value
                        )
                    except (ValueError, TypeError):
                        self.logger.error(
                            "PEG '%s'의 change_pct('%s')를 숫자로 변환할 수 없습니다. None으로 처리합니다.",
                            peg_display, value
                        )
                        change_map[key] = None
                        invalid_count += 1
                else:
                    self.logger.error(
                        "PEG '%s'의 change_pct가 예상치 못한 타입(%s)입니다. None으로 처리합니다.",
                        peg_display, type(value).__name__
                    )
                    change_map[key] = None
                    invalid_count += 1
            
            if invalid_count > 0:
                self.logger.warning(
                    "⚠️ change_map 생성 중 %d개의 잘못된 타입 발견 (None으로 처리됨)",
                    invalid_count
                )
            
            # change_map 통계 확인 (디버깅) - 타입 안전하게 비교
            if change_map:
                # 숫자 타입이고 0이 아닌 값만 카운트
                non_zero_in_map = sum(
                    1 for v in change_map.values() 
                    if v is not None and isinstance(v, (int, float)) and v != 0
                )
                sample_items = list(change_map.items())[:5]
                self.logger.debug(
                    "change_map 생성: 총=%d개, 0이_아닌_값=%d개, 샘플=%s",
                    len(change_map),
                    non_zero_in_map,
                    sample_items
                )
                
                # 큰 폭의 음수 변화율 검출 - 타입 안전하게 비교
                large_negative_changes = {
                    k: v for k, v in change_map.items() 
                    if v is not None and isinstance(v, (int, float)) and v < -20
                }
                if large_negative_changes:
                    self.logger.warning(
                        "⚠️ change_map에서 큰 폭의 감소 감지: %d개 PEG (변화율 < -20%%)",
                        len(large_negative_changes)
                    )
                    for key, change_pct in large_negative_changes.items():
                        # key는 has_dimensions에 따라 str 또는 (str, str) 튜플
                        peg_display = f"{key[0]} (dims: {key[1]})" if has_dimensions else str(key)
                        self.logger.warning(f"   {peg_display}: {change_pct:.2f}%")
            else:
                self.logger.warning("change_map이 비어있습니다!")

            # 중복 데이터 감지 및 로깅 (pivot 실패 방지)
            self.logger.debug("pivot 실행 전 중복 데이터 검사 시작")
            subset_cols = ['peg_name', 'dimensions', 'period', 'avg_value'] if has_dimensions else ['peg_name', 'period', 'avg_value']
            duplicates = processed_df[processed_df.duplicated(subset=subset_cols, keep=False)]
            
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
                        dims = row.get('dimensions', 'N/A') if has_dimensions else 'N/A'
                        self.logger.error(f"       period={period}, avg_value={avg_value}, dimensions={dims}")
                
                if unique_peg_count > 5:
                    self.logger.error(f"   ... 외 {unique_peg_count - 5}개 PEG 더 있음")
            else:
                self.logger.debug("✓ 중복 데이터 없음 (pivot 안전)")

            # pivot_table 사용 (dimensions 포함 여부에 따라 분기)
            index_cols = ["peg_name", "dimensions"] if has_dimensions else "peg_name"
            self.logger.info(f"pivot_table 실행: index={index_cols}, columns=period, aggfunc=first")
            try:
                pivot_df = (
                    processed_df.pivot_table(
                        index=index_cols,
                        columns="period",
                        values="avg_value",
                        aggfunc='first',  # 중복 시 첫 번째 값 사용
                        observed=True  # 성능 최적화
                    )
                    .rename(columns={"N-1": "n_minus_1", "N": "n"})
                )
                self.logger.info("✅ pivot_table 완료: %d개 행 (차원 포함 시 PEG×dimensions 조합)", len(pivot_df))
            except Exception as pivot_error:
                self.logger.error("pivot_table 실행 중 오류 발생: %s", pivot_error)
                self.logger.error("processed_df 정보: shape=%s, columns=%s", 
                                 processed_df.shape, processed_df.columns.tolist())
                raise

            pivot_df = pivot_df.where(pivot_df.notna(), None)

            results: List[AnalyzedPEGResult] = []

            for index_key, row in pivot_df.iterrows():
                # index_key는 dimensions 포함 시 (peg_name, dimensions) 튜플, 아니면 peg_name 문자열
                if has_dimensions:
                    peg_name, dimensions = index_key
                    peg_display = f"{peg_name} (dims: {dimensions})"
                    change_key = (peg_name, dimensions)
                else:
                    peg_name = index_key
                    dimensions = None
                    peg_display = peg_name
                    change_key = peg_name
                
                n_minus_1_avg = row.get("n_minus_1")  # 수정: _value → _avg
                n_avg = row.get("n")                   # 수정: _value → _avg

                absolute_change: Optional[float] = None
                percentage_change: Optional[float] = None

                if n_minus_1_avg is not None and n_avg is not None:
                    absolute_change = n_avg - n_minus_1_avg  # 수정
                    
                    # change_map에서 percentage_change 가져오기 (타입 검증 포함)
                    percentage_change_raw = change_map.get(change_key)
                    
                    # 타입 검증: None, NaN, 숫자가 아닌 경우 None으로 처리
                    if percentage_change_raw is None or pd.isna(percentage_change_raw):
                        percentage_change = None
                    elif isinstance(percentage_change_raw, (int, float)):
                        # 숫자 타입이면 그대로 사용
                        percentage_change = percentage_change_raw
                    elif isinstance(percentage_change_raw, str):
                        # 문자열이면 숫자로 변환 시도
                        try:
                            percentage_change = float(percentage_change_raw)
                            self.logger.warning(
                                "PEG '%s'의 percentage_change가 문자열('%s')입니다. float로 변환했습니다.",
                                peg_display, percentage_change_raw
                            )
                        except (ValueError, TypeError):
                            self.logger.error(
                                "PEG '%s'의 percentage_change('%s')를 숫자로 변환할 수 없습니다. None으로 처리합니다.",
                                peg_display, percentage_change_raw
                            )
                            percentage_change = None
                    else:
                        # 예상치 못한 타입
                        self.logger.error(
                            "PEG '%s'의 percentage_change가 예상치 못한 타입(%s)입니다. None으로 처리합니다.",
                            peg_display, type(percentage_change_raw).__name__
                        )
                        percentage_change = None
                else:
                    self.logger.warning(
                        "PEG '%s' 데이터 불완전 (N-1=%s, N=%s)", peg_display, n_minus_1_avg, n_avg  # 수정
                    )

                results.append(
                    AnalyzedPEGResult(
                        peg_name=peg_name,
                        n_minus_1_avg=n_minus_1_avg,  # 수정
                        n_avg=n_avg,                   # 수정
                        absolute_change=absolute_change,
                        percentage_change=percentage_change,
                        dimensions=dimensions,  # 추가
                    )
                )

            # 정렬: peg_name 기준, dimensions가 있으면 그것도 2차 정렬
            results.sort(key=lambda x: (x.peg_name, x.dimensions or ""))

            self.logger.info("2단계: LLM 분석 통합")
            llm_peg_analysis: Dict[str, str] = {}
            if llm_analysis_results and isinstance(llm_analysis_results, dict):
                peg_insights = llm_analysis_results.get("peg_insights")
                if isinstance(peg_insights, dict):
                    for peg_name, summary in peg_insights.items():
                        if isinstance(summary, str) and summary.strip():
                            llm_peg_analysis[peg_name] = summary

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

            # 변화율 통계 (타입 검증 포함)
            # percentage_change가 None이 아니고, 숫자 타입(int 또는 float)인 경우만 포함
            valid_changes = [
                r.percentage_change 
                for r in results 
                if r.percentage_change is not None and isinstance(r.percentage_change, (int, float))
            ]
            
            # 문자열 타입의 percentage_change가 있는지 확인 (디버깅용)
            invalid_changes = [
                (r.peg_name, r.percentage_change, type(r.percentage_change).__name__)
                for r in results 
                if r.percentage_change is not None and not isinstance(r.percentage_change, (int, float))
            ]
            if invalid_changes:
                self.logger.warning(
                    "⚠️ 숫자가 아닌 percentage_change 발견: %d개 (통계에서 제외됨)",
                    len(invalid_changes)
                )
                for peg_name, value, value_type in invalid_changes[:5]:  # 최대 5개만 출력
                    self.logger.warning(
                        "   PEG '%s': value='%s', type='%s'",
                        peg_name, value, value_type
                    )

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
