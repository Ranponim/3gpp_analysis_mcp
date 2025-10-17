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

        # 데이터 포맷팅
        preview_cols = [c for c in processed_df.columns if c in ("peg_name", "avg_value", "period", "change_pct")]
        if not preview_cols:
            preview_cols = list(processed_df.columns)[:6]

        preview_rows = int(os.getenv("PROMPT_PREVIEW_ROWS", "200"))
        preview_df = processed_df[preview_cols].head(preview_rows)
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
            
            # 폴백: 하드코딩된 프롬프트 사용
            prompt = f"""
3GPP Cell 성능 고도화 분석 요청 (연쇄적 사고 진단)

**분석 기간:**
- N-1 기간: {n1_range}
- N 기간: {n_range}

**PEG 집계 데이터:**
{data_preview}

**분석 워크플로우:**

1️⃣ **데이터 품질 검증**
- 데이터 완성도 및 이상치 확인
- 측정 신뢰성 평가

2️⃣ **성능 트렌드 분석**
- N-1 → N 기간 변화율 분석
- 성능 개선/악화 패턴 식별

3️⃣ **임계값 및 이상 상황 탐지**
- KPI 임계값 위반 확인
- 급격한 성능 변화 감지

4️⃣ **근본 원인 분석**
- 성능 변화의 잠재적 원인 추론
- Cell간 상관관계 분석

5️⃣ **실행 가능한 권고사항**
- 구체적이고 측정 가능한 개선 방안
- 우선순위별 액션 플랜

**요구 출력 형식 (JSON):**
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
  ],
  "summary": "전문가 수준의 종합 요약",
  "key_findings": [
    "데이터 기반 핵심 발견사항들"
  ],
  "recommendations": [
    "실행 가능한 구체적 권고사항들"
  ],
  "technical_analysis": {{
    "overall_status": "GOOD/WARNING/CRITICAL",
    "critical_issues": ["발견된 중요 이슈들"],
    "performance_trends": "상세 트렌드 분석",
    "data_quality_score": "HIGH/MEDIUM/LOW",
    "confidence_level": "HIGH/MEDIUM/LOW"
  }},
  "cells_with_significant_change": {{
    "CELL_ID": "변화 원인 및 영향 분석"
  }},
  "action_plan": [
    {{
      "priority": "HIGH/MEDIUM/LOW",
      "action": "구체적 액션",
      "expected_impact": "예상 효과",
      "timeframe": "실행 기간"
    }}
  ]
}}
"""

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
            # 프롬프트 생성
            prompt = strategy.build_prompt(processed_df, n1_range, n_range, **kwargs)

            # 프롬프트 검증
            if not self.llm_repository.validate_prompt(prompt):
                logger.warning("프롬프트 검증 실패, 자르기 적용")
                # 프롬프트가 너무 긴 경우 처리 로직이 LLMClient에 있음

            # LLM 분석 실행
            logger.info("LLM 분석 시작: 전략=%s, 프롬프트=%d자", strategy.get_strategy_name(), len(prompt))

            analysis_result = self.llm_repository.analyze_data(prompt, enable_mock=enable_mock)

            # 응답 후처리
            processed_result = self._post_process_analysis_result(analysis_result, analysis_type, processed_df)

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

        # 기본 필드 보장
        default_fields = {
            "summary": "분석 요약이 제공되지 않았습니다",
            "key_findings": [],
            "recommendations": [],
            "technical_analysis": {
                "overall_status": "UNKNOWN",
                "critical_issues": [],
                "performance_trends": "분석되지 않음",
            },
        }

        for field, default_value in default_fields.items():
            if field not in enhanced_result:
                enhanced_result[field] = default_value
                logger.debug("기본 필드 추가: %s", field)

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
