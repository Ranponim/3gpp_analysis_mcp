"""
프롬프트 설정 스키마 (Pydantic v2)

YAML 구성 파일의 구조와 자료형을 검증하기 위한 모델 정의입니다.
프롬프트 엔지니어가 템플릿을 추가/수정할 때 사전 검증으로 안정성을 높입니다.
"""

from __future__ import annotations

from typing import Dict, List, Optional
from pydantic import BaseModel, Field, ValidationError, field_validator


class PromptVariable(BaseModel):
    """템플릿에서 사용 가능한 변수 정의"""

    name: str = Field(..., min_length=1, description="변수 이름")
    type: Optional[str] = Field(default="string", description="변수 타입 (설명용)")
    description: Optional[str] = Field(default=None, description="변수 설명")


class Metadata(BaseModel):
    """프롬프트 설정 메타데이터"""

    version: str = Field(..., description="스키마/템플릿 버전")
    description: Optional[str] = Field(default=None, description="설명")
    format_type: str = Field(..., description="템플릿 포맷 유형: python_basic 등")
    created_date: Optional[str] = Field(default=None, description="생성 날짜")
    variables: List[PromptVariable] = Field(default_factory=list, description="사용 가능한 변수 목록")


class PromptConfig(BaseModel):
    """프롬프트 설정 루트 모델"""

    metadata: Metadata
    prompts: Dict[str, str] = Field(..., description="프롬프트 템플릿 맵")

    @field_validator("prompts")
    @classmethod
    def validate_prompts_non_empty(cls, value: Dict[str, str]) -> Dict[str, str]:
        # 최소 1개 이상의 템플릿이 존재해야 하며, 모든 값은 비어있지 않은 문자열이어야 함
        if not isinstance(value, dict) or not value:
            raise ValueError("prompts 섹션이 비어있습니다")
        bad_keys = [k for k, v in value.items() if not isinstance(v, str) or not v.strip()]
        if bad_keys:
            raise ValueError(f"빈(또는 잘못된) 템플릿이 있습니다: {bad_keys}")
        return value


__all__ = [
    "PromptVariable",
    "Metadata",
    "PromptConfig",
    "ValidationError",
]


