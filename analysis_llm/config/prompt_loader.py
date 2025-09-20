"""
프롬프트 설정 로더 서비스

YAML 파일에서 프롬프트 템플릿을 로드하고 Python 기본 포매팅을 사용하여
동적 변수를 치환하는 기능을 제공합니다.

이 모듈은 프롬프트 엔지니어가 코드 수정 없이 외부 YAML 파일을 통해
프롬프트를 관리할 수 있도록 설계되었습니다.
"""

import os
import yaml
import logging
from typing import Dict, Any, Optional
from functools import lru_cache
from pathlib import Path


class PromptConfigurationError(Exception):
    """프롬프트 설정 관련 오류"""
    pass


class PromptLoader:
    """
    프롬프트 템플릿 로더 클래스
    
    YAML 파일에서 프롬프트 템플릿을 로드하고 변수 치환을 수행합니다.
    캐싱을 통해 성능을 최적화하며, 환경변수를 통한 설정 파일 경로 오버라이드를 지원합니다.
    """
    
    DEFAULT_CONFIG_PATH = "config/prompts/v1.yaml"
    
    def __init__(self, config_path: Optional[str] = None):
        """
        PromptLoader 초기화
        
        Args:
            config_path (Optional[str]): 설정 파일 경로. None이면 환경변수 또는 기본값 사용
        """
        self.config_path = self._resolve_config_path(config_path)
        self._config_cache: Optional[Dict[str, Any]] = None
        logging.info(f"PromptLoader 초기화: 설정 파일 경로={self.config_path}")
        
    def _resolve_config_path(self, config_path: Optional[str]) -> str:
        """
        설정 파일 경로를 결정합니다.
        
        우선순위: 
        1. 생성자 파라미터
        2. PROMPT_CONFIG_PATH 환경변수
        3. 기본값
        
        Args:
            config_path (Optional[str]): 생성자에서 전달된 경로
            
        Returns:
            str: 최종 설정 파일 경로
        """
        if config_path:
            return config_path
            
        env_path = os.getenv('PROMPT_CONFIG_PATH')
        if env_path:
            logging.info(f"환경변수 PROMPT_CONFIG_PATH 사용: {env_path}")
            return env_path
            
        return self.DEFAULT_CONFIG_PATH
    
    def _load_config(self) -> Dict[str, Any]:
        """
        YAML 설정 파일을 로드합니다.
        
        Returns:
            Dict[str, Any]: 파싱된 YAML 설정
            
        Raises:
            PromptConfigurationError: 파일 로드 또는 파싱 실패 시
        """
        try:
            config_file_path = Path(self.config_path)
            
            if not config_file_path.exists():
                raise PromptConfigurationError(
                    f"프롬프트 설정 파일을 찾을 수 없습니다: {self.config_path}"
                )
            
            logging.info(f"YAML 설정 파일 로드 시작: {self.config_path}")
            
            with open(config_file_path, 'r', encoding='utf-8') as file:
                config = yaml.safe_load(file)
                
            if not config:
                raise PromptConfigurationError(
                    f"빈 설정 파일입니다: {self.config_path}"
                )
                
            # 스키마 검증 (Pydantic)
            try:
                from analysis_llm.config.prompt_schema import PromptConfig
                validated = PromptConfig.model_validate(config)
                # dict로 반환하여 기존 사용처와 호환 유지
                validated_dict = validated.model_dump()
                logging.info(
                    f"YAML 설정 파일 로드 완료(검증됨): {len(validated_dict.get('prompts', {}))}개 프롬프트 템플릿"
                )
                return validated_dict
            except Exception as ve:
                raise PromptConfigurationError(f"스키마 검증 실패: {ve}")
            
        except yaml.YAMLError as e:
            error_msg = f"YAML 파싱 오류: {e}"
            logging.error(error_msg)
            raise PromptConfigurationError(error_msg)
        except Exception as e:
            error_msg = f"설정 파일 로드 실패: {e}"
            logging.error(error_msg)
            raise PromptConfigurationError(error_msg)
    
    @lru_cache(maxsize=1)
    def get_config(self) -> Dict[str, Any]:
        """
        설정을 로드하고 캐시합니다.
        
        Returns:
            Dict[str, Any]: 캐시된 설정 데이터
        """
        if self._config_cache is None:
            self._config_cache = self._load_config()
        return self._config_cache
    
    def reload_config(self) -> None:
        """
        설정 캐시를 초기화하고 다시 로드합니다.
        
        프롬프트 파일이 변경된 후 호출하여 변경사항을 반영할 수 있습니다.
        """
        logging.info("프롬프트 설정 캐시 초기화 및 재로드")
        self._config_cache = None
        self.get_config.cache_clear()
        self.get_config()  # 즉시 재로드
    
    def get_prompt_template(self, prompt_type: str) -> str:
        """
        지정된 타입의 프롬프트 템플릿을 가져옵니다.
        
        Args:
            prompt_type (str): 프롬프트 타입 ('overall', 'enhanced', 'specific_pegs')
            
        Returns:
            str: 프롬프트 템플릿 문자열
            
        Raises:
            PromptConfigurationError: 프롬프트 타입을 찾을 수 없는 경우
        """
        config = self.get_config()
        prompts = config.get('prompts', {})
        
        if prompt_type not in prompts:
            available_types = list(prompts.keys())
            raise PromptConfigurationError(
                f"프롬프트 타입 '{prompt_type}'을 찾을 수 없습니다. "
                f"사용 가능한 타입: {available_types}"
            )
        
        template = prompts[prompt_type]
        if not template or not isinstance(template, str):
            raise PromptConfigurationError(
                f"프롬프트 타입 '{prompt_type}'의 템플릿이 비어있거나 잘못된 형식입니다."
            )
        
        logging.debug(f"프롬프트 템플릿 반환: {prompt_type} ({len(template)} 문자)")
        return template
    
    def format_prompt(self, prompt_type: str, **variables) -> str:
        """
        프롬프트 템플릿에 변수를 치환하여 최종 프롬프트를 생성합니다.
        
        Args:
            prompt_type (str): 프롬프트 타입
            **variables: 템플릿에 치환할 변수들
            
        Returns:
            str: 변수가 치환된 최종 프롬프트
            
        Raises:
            PromptConfigurationError: 템플릿 포매팅 실패 시
        """
        try:
            template = self.get_prompt_template(prompt_type)
            
            # Python 기본 포매팅 사용 (.format() 메서드)
            formatted_prompt = template.format(**variables)
            
            logging.info(f"프롬프트 포매팅 완료: {prompt_type}, 변수 {len(variables)}개, "
                        f"결과 길이 {len(formatted_prompt)} 문자")
            
            return formatted_prompt
            
        except KeyError as e:
            missing_var = str(e).strip("'")
            error_msg = f"프롬프트 템플릿 '{prompt_type}'에 필요한 변수 '{missing_var}'가 제공되지 않았습니다."
            logging.error(error_msg)
            raise PromptConfigurationError(error_msg)
        except Exception as e:
            error_msg = f"프롬프트 포매팅 실패 ({prompt_type}): {e}"
            logging.error(error_msg)
            raise PromptConfigurationError(error_msg)
    
    def get_metadata(self) -> Dict[str, Any]:
        """
        설정 파일의 메타데이터를 반환합니다.
        
        Returns:
            Dict[str, Any]: 메타데이터 정보
        """
        config = self.get_config()
        return config.get('metadata', {})
    
    def get_available_prompt_types(self) -> list[str]:
        """
        사용 가능한 프롬프트 타입 목록을 반환합니다.
        
        Returns:
            list[str]: 프롬프트 타입 목록
        """
        config = self.get_config()
        prompts = config.get('prompts', {})
        return list(prompts.keys())
    
    def validate_variables(self, prompt_type: str, variables: Dict[str, Any]) -> bool:
        """
        주어진 변수들이 프롬프트 템플릿에 필요한 모든 변수를 포함하는지 검증합니다.
        
        Args:
            prompt_type (str): 프롬프트 타입
            variables (Dict[str, Any]): 검증할 변수들
            
        Returns:
            bool: 모든 필요한 변수가 포함되어 있으면 True
            
        Raises:
            PromptConfigurationError: 누락된 변수가 있는 경우
        """
        try:
            template = self.get_prompt_template(prompt_type)
            # 테스트 포매팅으로 누락된 변수 확인
            template.format(**variables)
            return True
        except KeyError as e:
            missing_var = str(e).strip("'")
            raise PromptConfigurationError(
                f"프롬프트 '{prompt_type}'에 필요한 변수 '{missing_var}'가 누락되었습니다."
            )


# 전역 인스턴스 (선택적 사용)
_default_loader: Optional[PromptLoader] = None


def get_default_loader() -> PromptLoader:
    """
    기본 프롬프트 로더 인스턴스를 반환합니다.
    
    Returns:
        PromptLoader: 기본 로더 인스턴스
    """
    global _default_loader
    if _default_loader is None:
        _default_loader = PromptLoader()
    return _default_loader


def format_prompt(prompt_type: str, **variables) -> str:
    """
    기본 로더를 사용한 편의 함수
    
    Args:
        prompt_type (str): 프롬프트 타입
        **variables: 템플릿 변수들
        
    Returns:
        str: 포매팅된 프롬프트
    """
    loader = get_default_loader()
    return loader.format_prompt(prompt_type, **variables)
