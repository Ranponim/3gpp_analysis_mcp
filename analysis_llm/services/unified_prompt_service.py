"""
통합 프롬프트 생성 서비스

기존의 중복된 프롬프트 생성 함수들을 대체하는 단일 통합 함수를 제공합니다.
외부 YAML 설정과 데이터 포매팅 유틸리티를 활용하여 재사용 가능하고 
유지보수가 쉬운 프롬프트 생성 기능을 제공합니다.
"""

import logging
import pandas as pd
from typing import List, Optional, Dict, Any, Union
from enum import Enum

from analysis_llm.config.prompt_loader import PromptLoader, PromptConfigurationError
from analysis_llm.utils.data_formatter import format_dataframe_for_prompt, validate_dataframe_for_prompt


class PromptType(Enum):
    """지원되는 프롬프트 타입"""
    OVERALL = "overall"
    ENHANCED = "enhanced"  
    SPECIFIC_PEGS = "specific_pegs"


class UnifiedPromptGenerationError(Exception):
    """통합 프롬프트 생성 관련 오류"""
    pass


class UnifiedPromptService:
    """
    통합 프롬프트 생성 서비스 클래스
    
    기존의 create_llm_analysis_prompt_overall, create_llm_analysis_prompt_enhanced,
    create_llm_analysis_prompt_specific_pegs 함수들을 대체하는 단일 서비스입니다.
    
    주요 기능:
    - 외부 YAML 설정을 통한 프롬프트 템플릿 관리
    - 데이터 포매팅 유틸리티 활용
    - 타입 안전성 및 검증
    - 포괄적인 오류 처리
    """
    
    def __init__(self, prompt_loader: Optional[PromptLoader] = None):
        """
        UnifiedPromptService 초기화
        
        Args:
            prompt_loader (Optional[PromptLoader]): 프롬프트 로더 인스턴스.
                None이면 기본 로더 사용
        """
        self.prompt_loader = prompt_loader or PromptLoader()
        logging.info("UnifiedPromptService 초기화 완료")
    
    def create_unified_llm_analysis_prompt(
        self,
        prompt_type: Union[PromptType, str],
        processed_df: pd.DataFrame,
        n1_range: str,
        n_range: str,
        selected_pegs: Optional[List[str]] = None,
        **additional_variables: Any
    ) -> str:
        """
        통합 LLM 분석 프롬프트를 생성합니다.
        
        이 함수는 기존의 3개 프롬프트 생성 함수를 대체하는 단일 진입점입니다:
        - create_llm_analysis_prompt_overall -> prompt_type="overall"
        - create_llm_analysis_prompt_enhanced -> prompt_type="enhanced"  
        - create_llm_analysis_prompt_specific_pegs -> prompt_type="specific_pegs"
        
        Args:
            prompt_type (Union[PromptType, str]): 프롬프트 타입
            processed_df (pd.DataFrame): 처리된 PEG 데이터
            n1_range (str): 기간 n-1의 날짜 범위
            n_range (str): 기간 n의 날짜 범위  
            selected_pegs (Optional[List[str]]): 선택된 PEG 목록 (specific_pegs 타입에서만 필요)
            **additional_variables: 추가 템플릿 변수들
            
        Returns:
            str: 생성된 LLM 분석 프롬프트
            
        Raises:
            UnifiedPromptGenerationError: 프롬프트 생성 실패 시
            
        Example:
            >>> service = UnifiedPromptService()
            >>> prompt = service.create_unified_llm_analysis_prompt(
            ...     prompt_type="overall",
            ...     processed_df=df,
            ...     n1_range="2023-01-01 to 2023-01-15",
            ...     n_range="2023-01-16 to 2023-01-31"
            ... )
        """
        try:
            # 프롬프트 타입 정규화
            if isinstance(prompt_type, str):
                prompt_type_str = prompt_type.lower()
            else:
                prompt_type_str = prompt_type.value
                
            logging.info(f"create_unified_llm_analysis_prompt() 호출: 타입={prompt_type_str}, "
                        f"DataFrame 크기={processed_df.shape}")
            
            # DataFrame 검증
            self._validate_input_dataframe(processed_df)
            
            # 입력 파라미터 검증
            self._validate_input_parameters(prompt_type_str, n1_range, n_range, selected_pegs)
            
            # 데이터 포매팅
            data_preview = self._format_data_for_prompt(processed_df)
            
            # 템플릿 변수 준비
            template_variables = self._prepare_template_variables(
                prompt_type_str, n1_range, n_range, data_preview, selected_pegs, additional_variables
            )
            
            # 프롬프트 생성
            final_prompt = self._generate_prompt(prompt_type_str, template_variables)
            
            logging.info(f"create_unified_llm_analysis_prompt() 완료: {len(final_prompt)} 문자 생성")
            
            return final_prompt
            
        except Exception as e:
            error_msg = f"통합 프롬프트 생성 실패 (타입: {prompt_type}): {e}"
            logging.error(error_msg)
            raise UnifiedPromptGenerationError(error_msg) from e
    
    def _validate_input_dataframe(self, df: pd.DataFrame) -> None:
        """DataFrame 입력 검증"""
        try:
            # 기본 검증 (빈 DataFrame, None 체크)
            validate_dataframe_for_prompt(df)
            
            # PEG 분석에 필요한 기본 컬럼들이 있는지 확인 (선택사항)
            recommended_columns = ['peg_name']
            missing_recommended = [col for col in recommended_columns if col not in df.columns]
            
            if missing_recommended:
                logging.warning(f"권장 컬럼 누락: {missing_recommended}. 프롬프트 품질에 영향을 줄 수 있습니다.")
                
        except Exception as e:
            raise UnifiedPromptGenerationError(f"DataFrame 검증 실패: {e}")
    
    def _validate_input_parameters(
        self, 
        prompt_type: str, 
        n1_range: str, 
        n_range: str, 
        selected_pegs: Optional[List[str]]
    ) -> None:
        """입력 파라미터 검증"""
        # 프롬프트 타입 검증
        valid_types = [pt.value for pt in PromptType]
        if prompt_type not in valid_types:
            raise UnifiedPromptGenerationError(
                f"지원되지 않는 프롬프트 타입: {prompt_type}. "
                f"지원되는 타입: {valid_types}"
            )
        
        # 날짜 범위 검증
        if not n1_range or not n1_range.strip():
            raise UnifiedPromptGenerationError("n1_range가 비어있습니다")
        if not n_range or not n_range.strip():
            raise UnifiedPromptGenerationError("n_range가 비어있습니다")
        
        # specific_pegs 타입에서 selected_pegs 필수 검증
        if prompt_type == PromptType.SPECIFIC_PEGS.value:
            if not selected_pegs:
                raise UnifiedPromptGenerationError(
                    "specific_pegs 타입에서는 selected_pegs 파라미터가 필수입니다"
                )
            if not isinstance(selected_pegs, list) or len(selected_pegs) == 0:
                raise UnifiedPromptGenerationError(
                    "selected_pegs는 비어있지 않은 리스트여야 합니다"
                )
    
    def _format_data_for_prompt(self, df: pd.DataFrame) -> str:
        """데이터를 프롬프트용으로 포매팅"""
        try:
            return format_dataframe_for_prompt(df)
        except Exception as e:
            raise UnifiedPromptGenerationError(f"데이터 포매팅 실패: {e}")
    
    def _prepare_template_variables(
        self,
        prompt_type: str,
        n1_range: str,
        n_range: str,
        data_preview: str,
        selected_pegs: Optional[List[str]],
        additional_variables: Dict[str, Any]
    ) -> Dict[str, Any]:
        """템플릿 변수 준비"""
        # 기본 변수들
        variables = {
            'n1_range': n1_range,
            'n_range': n_range,
            'data_preview': data_preview
        }
        
        # specific_pegs 타입에서 추가 변수
        if prompt_type == PromptType.SPECIFIC_PEGS.value and selected_pegs:
            variables['selected_pegs_str'] = ', '.join(selected_pegs)
        
        # 추가 변수들 병합
        variables.update(additional_variables)
        
        logging.debug(f"템플릿 변수 준비 완료: {len(variables)}개 변수")
        
        return variables
    
    def _generate_prompt(self, prompt_type: str, variables: Dict[str, Any]) -> str:
        """프롬프트 생성"""
        try:
            return self.prompt_loader.format_prompt(prompt_type, **variables)
        except PromptConfigurationError as e:
            raise UnifiedPromptGenerationError(f"프롬프트 템플릿 처리 실패: {e}")
    
    def get_available_prompt_types(self) -> List[str]:
        """사용 가능한 프롬프트 타입 목록 반환"""
        try:
            return self.prompt_loader.get_available_prompt_types()
        except Exception as e:
            logging.error(f"프롬프트 타입 목록 조회 실패: {e}")
            return [pt.value for pt in PromptType]  # 기본값 반환
    
    def validate_prompt_variables(self, prompt_type: str, variables: Dict[str, Any]) -> bool:
        """프롬프트 변수 검증"""
        try:
            return self.prompt_loader.validate_variables(prompt_type, variables)
        except Exception as e:
            raise UnifiedPromptGenerationError(f"변수 검증 실패: {e}")
    
    def reload_prompt_templates(self) -> None:
        """프롬프트 템플릿 재로드 (개발/테스트 시 유용)"""
        try:
            self.prompt_loader.reload_config()
            logging.info("프롬프트 템플릿 재로드 완료")
        except Exception as e:
            logging.error(f"프롬프트 템플릿 재로드 실패: {e}")
            raise UnifiedPromptGenerationError(f"템플릿 재로드 실패: {e}")


# 전역 인스턴스 (선택적 사용)
_default_service: Optional[UnifiedPromptService] = None


def get_default_service() -> UnifiedPromptService:
    """
    기본 통합 프롬프트 서비스 인스턴스를 반환합니다.
    
    Returns:
        UnifiedPromptService: 기본 서비스 인스턴스
    """
    global _default_service
    if _default_service is None:
        _default_service = UnifiedPromptService()
    return _default_service


def create_unified_llm_analysis_prompt(
    prompt_type: Union[PromptType, str],
    processed_df: pd.DataFrame,
    n1_range: str,
    n_range: str,
    selected_pegs: Optional[List[str]] = None,
    **additional_variables: Any
) -> str:
    """
    기본 서비스를 사용한 편의 함수
    
    기존 함수들과의 호환성을 위한 전역 함수입니다.
    
    Args:
        prompt_type: 프롬프트 타입
        processed_df: 처리된 데이터
        n1_range: 기간 n-1
        n_range: 기간 n
        selected_pegs: 선택된 PEG 목록
        **additional_variables: 추가 변수들
        
    Returns:
        str: 생성된 프롬프트
    """
    service = get_default_service()
    return service.create_unified_llm_analysis_prompt(
        prompt_type=prompt_type,
        processed_df=processed_df,
        n1_range=n1_range,
        n_range=n_range,
        selected_pegs=selected_pegs,
        **additional_variables
    )
