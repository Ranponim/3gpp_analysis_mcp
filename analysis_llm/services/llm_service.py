"""
LLM Analysis Service

이 모듈은 LLM을 활용한 데이터 분석 비즈니스 로직을 담당하는
LLMAnalysisService 클래스를 제공합니다.

기존 main.py의 LLM 관련 분석 로직을 모듈화한 것입니다.
"""

from __future__ import annotations

import logging
import os

# 임시로 절대 import 사용 (나중에 패키지 구조 정리 시 수정)
import sys
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import pandas as pd

from ..exceptions import LLMError, ServiceError
from ..repositories import LLMClient, LLMRepository

# 로깅 설정
logger = logging.getLogger(__name__)


class LLMAnalysisError(ServiceError):
    """
    LLM 분석 관련 오류 예외 클래스

    LLM 분석 과정에서 발생하는 오류를 처리합니다.
    """

    def __init__(
        self,
        message: str,
        details: Optional[Union[str, Dict[str, Any]]] = None,
        analysis_type: Optional[str] = None,
        prompt_preview: Optional[str] = None,
    ) -> None:
        """
        LLMAnalysisError 초기화

        Args:
            message (str): 오류 메시지
            details (Optional[Union[str, Dict[str, Any]]]): 추가 상세 정보
            analysis_type (Optional[str]): 분석 유형
            prompt_preview (Optional[str]): 프롬프트 미리보기
        """
        super().__init__(message=message, details=details, service_name="LLMAnalysisService", operation="analyze_data")
        self.analysis_type = analysis_type
        self.prompt_preview = prompt_preview

        logger.error("LLMAnalysisError 발생: %s (분석유형: %s)", message, analysis_type)

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리 형태로 변환"""
        data = super().to_dict()
        data.update({"analysis_type": self.analysis_type, "prompt_preview": self.prompt_preview})
        return data


class BasePromptStrategy(ABC):
    """
    프롬프트 생성 전략 추상 기본 클래스

    다양한 분석 유형에 따른 프롬프트 생성 전략을 정의합니다.
    Strategy Pattern을 구현합니다.
    """

    @abstractmethod
    def build_prompt(self, processed_df: pd.DataFrame, n1_range: str, n_range: str, **kwargs) -> str:
        """
        프롬프트 생성

        Args:
            processed_df (pd.DataFrame): 처리된 PEG 데이터
            n1_range (str): N-1 기간 문자열
            n_range (str): N 기간 문자열
            **kwargs: 추가 매개변수

        Returns:
            str: 생성된 프롬프트
        """

    @abstractmethod
    def get_strategy_name(self) -> str:
        """전략 이름 반환"""

    def validate_input_data(self, processed_df: pd.DataFrame) -> bool:
        """입력 데이터 유효성 검증"""
        if processed_df is None or processed_df.empty:
            return False

        required_columns = ["peg_name", "avg_value", "period"]
        missing_columns = [col for col in required_columns if col not in processed_df.columns]

        if missing_columns:
            logger.warning("필수 컬럼 누락: %s", missing_columns)
            return False

        return True

    def format_dataframe_for_prompt(self, df: pd.DataFrame, max_rows: Optional[int] = None) -> str:
        """DataFrame을 프롬프트용 문자열로 포맷팅"""
        if df.empty:
            return "데이터가 없습니다."

        # 행 수 제한
        if max_rows and len(df) > max_rows:
            df = df.head(max_rows)
            logger.debug("DataFrame 행 수 제한 적용: %d행으로 단축", max_rows)

        # 테이블 형태로 변환
        formatted = df.to_string(index=False, max_cols=10)
        logger.debug("DataFrame 포맷팅 완료: %d행, %d컬럼", len(df), len(df.columns))

        return formatted


class EnhancedAnalysisPromptStrategy(BasePromptStrategy):
    """
    고도화된 종합 분석 프롬프트 전략
    (기존 main.py의 create_llm_analysis_prompt_enhanced 로직)
    """

    def get_strategy_name(self) -> str:
        return "enhanced_analysis"

    def build_prompt(self, processed_df: pd.DataFrame, n1_range: str, n_range: str, **kwargs) -> str:
        """고도화된 종합 분석 프롬프트 생성 (YAML 템플릿 사용)"""
        logger.info("EnhancedAnalysisPromptStrategy.build_prompt() 호출")

        if not self.validate_input_data(processed_df):
            raise LLMAnalysisError("입력 데이터가 유효하지 않습니다", analysis_type=self.get_strategy_name())

        # 🔍 토큰 최적화: change_pct가 NULL인 PEG들을 프롬프트에서 제외
        original_peg_count = len(processed_df["peg_name"].unique())
        
        if "change_pct" in processed_df.columns:
            # change_pct가 NULL이 아닌 행들만 필터링
            filtered_df = processed_df[pd.notna(processed_df["change_pct"])].copy()
            filtered_peg_count = len(filtered_df["peg_name"].unique())
            excluded_peg_count = original_peg_count - filtered_peg_count
            
            if excluded_peg_count > 0:
                logger.info(
                    f"🔍 토큰 최적화: change_pct=NULL인 PEG {excluded_peg_count}개 제외 "
                    f"(전체 {original_peg_count}개 → 프롬프트 {filtered_peg_count}개)"
                )
                
                # 제외된 PEG 이름들 상세 로깅 (DEBUG2 레벨)
                from config.logging_config import log_at_debug2
                excluded_pegs = set(processed_df["peg_name"].unique()) - set(filtered_df["peg_name"].unique())
                log_at_debug2(
                    logger,
                    f"🔍 프롬프트에서 제외된 PEG 목록 ({len(excluded_pegs)}개): {sorted(list(excluded_pegs))}"
                )
                
                # 필터링된 데이터 사용
                processed_df = filtered_df
            else:
                logger.info("🔍 토큰 최적화: 제외할 PEG 없음 (모든 PEG의 change_pct가 유효함)")
        else:
            logger.warning("🔍 토큰 최적화: change_pct 컬럼이 없어 필터링을 수행할 수 없습니다")

        # 필터링 후 데이터가 비어있는지 확인
        if processed_df.empty:
            raise LLMAnalysisError(
                "필터링 후 분석할 PEG 데이터가 없습니다. 모든 PEG의 change_pct가 NULL일 수 있습니다.",
                analysis_type=self.get_strategy_name()
            )

        # 데이터 포맷팅 - 모든 PEG 포함 (데이터 유실 방지)
        preview_cols = [c for c in processed_df.columns if c in ("peg_name", "avg_value", "period", "change_pct")]
        if not preview_cols:
            preview_cols = list(processed_df.columns)[:6]

        # 모든 PEG를 포함하도록 수정 (행 수 제한 제거)
        # 기존: preview_rows = int(os.getenv("PROMPT_PREVIEW_ROWS", "200"))
        # 기존: preview_df = processed_df[preview_cols].head(preview_rows)
        preview_df = processed_df[preview_cols]  # 모든 데이터 포함
        logger.info("프롬프트 데이터 준비: 전체 %d행 포함 (모든 PEG 포함)", len(preview_df))
        data_preview = self.format_dataframe_for_prompt(preview_df)

        # YAML 프롬프트 템플릿 사용
        try:
            from analysis_llm.config.prompt_loader import PromptLoader
            prompt_loader = PromptLoader()
            prompt_template = prompt_loader.get_prompt_template("enhanced")
            
            # 변수 치환
            prompt = prompt_template.format(
                n1_range=n1_range,
                n_range=n_range,
                data_preview=data_preview,
                selected_pegs_str="All PEGs"  # enhanced 프롬프트에서는 사용하지 않음
            )
            
            logger.info("YAML 템플릿 기반 enhanced 프롬프트 생성 완료: %d자", len(prompt))
            return prompt
            
        except Exception as e:
            logger.warning("YAML 프롬프트 로드 실패, 하드코딩된 프롬프트 사용: %s", e)
            
            # 폴백: 하드코딩된 프롬프트 사용 (YAML과 동일한 구조)
            prompt = f"""[페르소나 및 임무]
당신은 Tier-1 이동통신사에서 20년 경력을 가진 수석 네트워크 진단 및 최적화 전략가입니다. 당신의 임무는 신속한 근본 원인 분석(RCA)을 수행하고, 고객 영향도에 따라 문제의 우선순위를 정하며, 현장 엔지니어링 팀을 위한 명확하고 실행 가능한 계획을 제공하는 것입니다. 당신의 분석은 3GPP 표준(TS 36/38.xxx 시리즈)과 운영 모범 사례에 부합해야 하며, 엄격하고 증거에 기반해야 합니다.

[컨텍스트 및 가정]
- 분석 대상은 두 기간 동안의 PEG(Performance Event Group) 카운터 변화입니다.
- 기간 n-1: {n1_range}
- 기간 n: {n_range}
- 핵심 가정: 두 기간은 동일한 시험환경(동일 하드웨어, 기본 파라미터, 트래픽 모델)에서 수행되었습니다.
- 입력 데이터는 PEG 단위로 집계된 평균값이며, 개별 셀(cell) 데이터는 포함되어 있지 않습니다. 따라서 셀 단위의 특정 문제 식별은 불가능하며, 집계 데이터 기반의 거시적 분석을 수행해야 합니다.

[입력 데이터]
- 컬럼 설명: peg_name(PEG 이름), avg_n_minus_1(기간 n-1 평균), avg_n(기간 n 평균), diff(변화량), pct_change(변화율)
- 데이터 테이블:
{data_preview}

[분석 워크플로우 지침]
아래의 4단계 연쇄적 사고(Chain-of-Thought) 진단 워크플로우를 엄격히 따라서 분석을 수행하십시오.

# [LLM-1] 문제 분류 및 중요도 평가 (Triage and Significance Assessment)
먼저, 입력 테이블의 모든 PEG를 검토하여 가장 심각한 '부정적' 변화를 보인 상위 3~5개의 PEG를 식별하십시오. '중요도'는 'pct_change'의 절대값 크기와 해당 PEG의 운영상 '고객 영향도'를 종합하여 판단합니다. 각 PEG가 영향을 미치는 3GPP 서비스 범주(Accessibility, Retainability, Mobility, Integrity, Latency)에 따라 영향도를 분류하고, 가장 시급하게 다루어야 할 문제를 선정하십시오.

# [LLM-2] 주제별 그룹화 및 핵심 가설 생성 (Thematic Grouping and Primary Hypothesis Generation)
[LLM-1]에서 식별된 우선순위가 높은 문제들에 대해, 연관된 PEG들을 논리적으로 그룹화하여 '진단 주제(Diagnostic Theme)'를 정의하십시오. (예: 다수의 접속 관련 PEG 악화 -> 'Accessibility Degradation' 주제). 각 주제에 대해, 3GPP 호 처리 절차(Call Flow) 및 운영 경험에 기반하여 가장 개연성 높은 단일 '핵심 가설(Primary Hypothesis)'을 수립하십시오. 이 가설은 구체적이고 검증 가능해야 합니다.

# [LLM-3] 시스템적 요인 분석 및 교란 변수 고려 (Systemic Factor Analysis & Confounding Variable Assessment)
수립한 핵심 가설을 검증하기 위해, 전체 데이터 테이블에서 가설을 뒷받침하거나(supporting evidence) 반박하는(contradictory evidence) 다른 PEG 변화를 분석하십시오. 또한, '동일 환경' 가정이 깨질 수 있는 잠재적 교란 요인(예: 라우팅 정책 변경, 소프트웨어 마이너 패치, 특정 파라미터 롤백, 단말기 믹스 변화)을 명시적으로 고려하고, 이러한 요인들이 현재 문제의 원인일 가능성이 높은지 낮은지, 그리고 그 판단의 근거는 무엇인지 논리적으로 기술하십시오.

# [LLM-4] 증거 기반의 검증 계획 수립 (Formulation of an Evidence-Based Verification Plan)
각 핵심 가설에 대해, 현장 엔지니어가 즉시 수행할 수 있는 구체적이고 우선순위가 부여된 '검증 계획'을 수립하십시오. 조치는 반드시 구체적이어야 합니다. (예: '로그 확인' 대신 '특정 카운터(pmRachAtt) 추이 분석'). 조치별로 P1(즉시 조치), P2(심층 조사), P3(정기 감사)와 같은 우선순위를 부여하고, 필요한 데이터(카운터, 파라미터 등)나 도구를 명시하십시오.

[출력 형식 제약]
- 분석 결과는 반드시 아래의 JSON 스키마를 정확히 준수하여 생성해야 합니다.
- 모든 문자열 값은 한국어로 작성하십시오.
- 각 필드에 대한 설명과 열거형(Enum) 값을 반드시 따르십시오.

{{
  "executive_summary": "네트워크 상태 변화와 식별된 가장 치명적인 문제에 대한 1-2 문장의 최상위 요약",
  "diagnostic_findings": [
    {{
      "primary_hypothesis": "가장 가능성 높은 단일 근본 원인 가설",
      "supporting_evidence": "데이터 테이블 내에서 가설을 뒷받침하는 다른 PEG 변화나 논리적 근거",
      "confounding_factors_assessment": "교란 변수들의 가능성에 대한 평가 및 그 근거"
    }}
  ],
  "recommended_actions": [
    {{
      "priority": "P1|P2|P3",
      "action": "구체적 실행 항목",
      "details": "필요 데이터/도구 및 수행 방법"
    }}
  ]
}}"""

            logger.info("하드코딩된 enhanced 프롬프트 생성 완료: %d자", len(prompt))
            return prompt


# class SpecificPEGsAnalysisPromptStrategy(BasePromptStrategy):
#     """
#     특정 PEG 전용 분석 프롬프트 전략
#     (기존 main.py의 create_llm_analysis_prompt_specific_pegs 로직)
#     """

#     def get_strategy_name(self) -> str:
#         return "specific_pegs_analysis"

#     def build_prompt(
#         self,
#         processed_df: pd.DataFrame,
#         n1_range: str,
#         n_range: str,
#         **kwargs,
#     ) -> str:
#         """특정 PEG 전용 분석 프롬프트 생성"""
#         logger.info("SpecificPEGsAnalysisPromptStrategy.build_prompt() 호출")

#         if not self.validate_input_data(processed_df):
#             raise LLMAnalysisError("입력 데이터가 유효하지 않습니다", analysis_type=self.get_strategy_name())

#         if processed_df.empty:
#             raise LLMAnalysisError(
#                 f"분석할 PEG 데이터가 없습니다.",
#                 analysis_type=self.get_strategy_name(),
#             )

#         # 데이터 포맷팅
#         preview_rows = int(os.getenv("PROMPT_PREVIEW_ROWS", "200"))
#         preview_df = processed_df.head(preview_rows)
#         data_preview = self.format_dataframe_for_prompt(preview_df)

#         # 선택된 PEG 목록 (DataFrame에서 직접 추출)
#         pegs_list = ", ".join(processed_df["peg_name"].unique())

#         # 프롬프트 구성
#         prompt = f"""
# 3GPP Cell 성능 특정 PEG 집중 분석

# **분석 대상 PEG:** {pegs_list}

# **분석 기간:**
# - N-1 기간: {n1_range}
# - N 기간: {n_range}

# **선택된 PEG 데이터:**
# {data_preview}

# **집중 분석 요구사항:**
# 선택된 PEG들에 대해 다음 형식의 JSON 응답을 생성해주세요:

# {{
#   "summary": "선택된 PEG들의 성능 요약",
#   "peg_analysis": {{
#     "PEG_NAME": {{
#       "status": "GOOD/WARNING/CRITICAL",
#       "n1_value": "N-1 기간 값",
#       "n_value": "N 기간 값",
#       "change_analysis": "변화 분석",
#       "recommendations": ["PEG별 권고사항"]
#     }}
#   }},
#   "cross_peg_insights": [
#     "PEG간 상관관계 및 패턴 분석"
#   ],
#   "focused_recommendations": [
#     "선택된 PEG들에 특화된 권고사항"
#   ],
#   "technical_details": {{
#     "measurement_quality": "측정 품질 평가",
#     "data_completeness": "데이터 완성도",
#     "analysis_confidence": "분석 신뢰도"
#   }}
# }}

# **분석 지침:**
# 1. 선택된 PEG들에만 집중하여 심층 분석
# 2. PEG간 상호작용 및 의존성 분석
# 3. 각 PEG별 개별 성능 평가
# 4. 특화된 최적화 방안 제시
# """

#         logger.info("특정 PEG 분석 프롬프트 생성 완료: %d자 (PEG: %d개)", len(prompt), len(processed_df["peg_name"].unique()))
#         return prompt


class LLMAnalysisService:
    """
    LLM 분석 서비스 클래스

    LLM을 활용한 데이터 분석의 전체 비즈니스 로직을 담당합니다.
    프롬프트 생성, LLM 호출, 응답 처리를 통합 관리합니다.

    기존 main.py의 LLM 분석 로직을 모듈화한 것입니다.
    """

    def __init__(self, llm_repository: Optional[LLMRepository] = None):
        """
        LLMAnalysisService 초기화

        Args:
            llm_repository (Optional[LLMRepository]): LLM Repository 인스턴스
        """
        # LLM Repository 설정 (의존성 주입)
        if llm_repository:
            self.llm_repository = llm_repository
        else:
            # 기본값: LLMClient 인스턴스 생성
            self.llm_repository = LLMClient()

        # 프롬프트 전략들 초기화
        self.prompt_strategies = {
            "enhanced": EnhancedAnalysisPromptStrategy(),
            # "specific": SpecificPEGsAnalysisPromptStrategy(),  # 주석처리: 사용되지 않음
        }

        logger.info(
            "LLMAnalysisService 초기화 완료: repository=%s, strategies=%d개",
            type(self.llm_repository).__name__,
            len(self.prompt_strategies),
        )

    def get_available_strategies(self) -> List[str]:
        """사용 가능한 분석 전략 목록 반환"""
        return list(self.prompt_strategies.keys())

    def analyze_peg_data(
        self,
        processed_df: pd.DataFrame,
        n1_range: str,
        n_range: str,
        analysis_type: str = "enhanced",
        enable_mock: bool = False,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        PEG 데이터 분석 실행

        Args:
            processed_df (pd.DataFrame): 처리된 PEG 데이터
            n1_range (str): N-1 기간 문자열
            n_range (str): N 기간 문자열
            analysis_type (str): 분석 유형 ('enhanced')  # 'specific' 주석처리: 사용되지 않음
            enable_mock (bool): 모킹 모드 활성화
            **kwargs: 추가 매개변수

        Returns:
            Dict[str, Any]: LLM 분석 결과

        Raises:
            LLMAnalysisError: 분석 실패 시
        """
        logger.info(
            "analyze_peg_data() 호출: 분석유형=%s, 데이터=%d행, 모킹=%s", analysis_type, len(processed_df), enable_mock
        )

        # 분석 전략 선택
        if analysis_type not in self.prompt_strategies:
            raise LLMAnalysisError(
                f"지원되지 않는 분석 유형: {analysis_type}",
                analysis_type=analysis_type,
                details={"available_types": list(self.prompt_strategies.keys())},
            )

        strategy = self.prompt_strategies[analysis_type]

        try:
            # DEBUG2 로깅 유틸리티 import
            from config.logging_config import log_step, log_data_flow
            
            # 프롬프트 생성
            log_step(logger, "[LLM 단계 1] 프롬프트 생성 시작", f"전략={strategy.get_strategy_name()}")
            prompt = strategy.build_prompt(processed_df, n1_range, n_range, **kwargs)
            log_data_flow(logger, "생성된 프롬프트", {"prompt": prompt, "length": len(prompt)})

            # 프롬프트 검증
            if not self.llm_repository.validate_prompt(prompt):
                logger.warning("프롬프트 검증 실패, 자르기 적용")
                # 프롬프트가 너무 긴 경우 처리 로직이 LLMClient에 있음

            # LLM 분석 실행
            logger.info("LLM 분석 시작: 전략=%s, 프롬프트=%d자", strategy.get_strategy_name(), len(prompt))
            log_step(logger, "[LLM 단계 2] LLM API 호출 시작", f"모킹={enable_mock}")

            analysis_result = self.llm_repository.analyze_data(prompt, enable_mock=enable_mock)
            log_data_flow(logger, "LLM 원본 응답", analysis_result)

            # 응답 후처리
            log_step(logger, "[LLM 단계 3] 응답 후처리 시작")
            processed_result = self._post_process_analysis_result(analysis_result, analysis_type, processed_df)
            log_data_flow(logger, "후처리된 LLM 결과", processed_result)

            logger.info("LLM 분석 완료: 전략=%s, 결과키=%d개", strategy.get_strategy_name(), len(processed_result))

            return processed_result

        except LLMError as e:
            raise LLMAnalysisError(
                f"LLM 호출 실패: {e.message}",
                analysis_type=analysis_type,
                prompt_preview=prompt[:200] if "prompt" in locals() else None,
                details=e.to_dict(),
            ) from e

        except Exception as e:
            raise LLMAnalysisError(
                f"분석 실행 중 예상치 못한 오류: {e}",
                analysis_type=analysis_type,
                prompt_preview=prompt[:200] if "prompt" in locals() else None,
            ) from e

    def _post_process_analysis_result(
        self, raw_result: Dict[str, Any], analysis_type: str, original_df: pd.DataFrame
    ) -> Dict[str, Any]:
        """
        LLM 분석 결과 후처리
        (기존 main.py의 build_results_overview 로직 개선)
        """
        logger.debug("_post_process_analysis_result() 호출: 분석유형=%s", analysis_type)

        # 기본 결과 구조 확인
        if not isinstance(raw_result, dict):
            logger.warning("LLM 결과가 딕셔너리가 아님, 문자열로 처리")
            raw_result = {"summary": str(raw_result)}

        # 결과 강화
        enhanced_result = raw_result.copy()

        # 메타데이터 추가
        enhanced_result.update(
            {
                "_analysis_metadata": {
                    "analysis_type": analysis_type,
                    "data_rows": len(original_df),
                    "data_columns": len(original_df.columns),
                    "unique_pegs": len(original_df["peg_name"].unique()) if "peg_name" in original_df.columns else 0,
                    "timestamp": datetime.now().isoformat(),
                    "strategy_used": analysis_type,
                },
                "model_name": getattr(self.llm_repository, 'config', {}).get('model', 'unknown'),
                "model_used": getattr(self.llm_repository, 'config', {}).get('model', 'unknown')
            }
        )

        # Enhanced 프롬프트 구조 필드만 보장
        enhanced_default_fields = {
            "executive_summary": "분석 요약이 제공되지 않았습니다",
            "diagnostic_findings": [],
            "recommended_actions": [],
        }

        for field, default_value in enhanced_default_fields.items():
            if field not in enhanced_result:
                enhanced_result[field] = default_value
                logger.debug("Enhanced 기본 필드 추가: %s", field)

        logger.debug("분석 결과 후처리 완료: %d개 필드", len(enhanced_result))
        return enhanced_result

    def get_service_info(self) -> Dict[str, Any]:
        """서비스 정보 반환"""
        return {
            "service_name": "LLMAnalysisService",
            "available_strategies": self.get_available_strategies(),
            "llm_repository_type": type(self.llm_repository).__name__,
            "strategies_count": len(self.prompt_strategies),
        }

    def close(self) -> None:
        """리소스 정리"""
        if hasattr(self.llm_repository, "close"):
            self.llm_repository.close()
            logger.info("LLMAnalysisService 리소스 정리 완료")

    def __enter__(self):
        """컨텍스트 매니저 진입"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """컨텍스트 매니저 종료"""
        self.close()

        # 예외 발생 시 로그 기록
        if exc_type:
            logger.error("LLMAnalysisService 컨텍스트에서 예외 발생: %s", exc_val)

        return False  # 예외를 다시 발생시킴
