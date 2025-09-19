"""
Custom exceptions module

이 모듈은 애플리케이션 전반에서 사용되는 커스텀 예외 클래스를 정의합니다.

모든 예외는 AnalysisError 기본 클래스에서 상속되며,
계층적 구조를 통해 구체적인 오류 유형을 제공합니다.
"""

from .custom_exceptions import AnalysisError, DatabaseError, LLMError, RepositoryError, ServiceError, ValidationError

# 편의를 위한 __all__ 정의
__all__ = ["AnalysisError", "DatabaseError", "LLMError", "ValidationError", "ServiceError", "RepositoryError"]
