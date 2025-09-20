"""
Utility functions package

이 패키지는 시간 파싱, 데이터 변환, 검증 등의 유틸리티를 제공합니다.
패키지 import 시 불필요한 의존성 로딩을 피하기 위해 지연 로딩을 사용합니다.
"""

from __future__ import annotations

import importlib
from typing import Any

__all__ = [
    # 노출할 심볼명(문자열). 실제 import는 속성 접근 시 수행됩니다.
    "TimeRangeParser",
    "TimeParsingError",
    "DataProcessor",
    "AnalyzedPEGResult",
    "DataProcessingError",
    "ResponseFormatter",
    "ResponseFormattingError",
    "RequestValidator",
    "RequestValidationError",
]


def __getattr__(name: str) -> Any:  # PEP 562
    if name in ("TimeRangeParser",):
        mod = importlib.import_module("analysis_llm.utils.time_parser")
        return getattr(mod, name)
    if name in ("TimeParsingError",):
        mod = importlib.import_module("analysis_llm.utils.exceptions")
        return getattr(mod, name)
    if name in ("DataProcessor", "AnalyzedPEGResult", "DataProcessingError"):
        mod = importlib.import_module("analysis_llm.utils.data_processor")
        return getattr(mod, name)
    if name in ("ResponseFormatter", "ResponseFormattingError"):
        mod = importlib.import_module("analysis_llm.utils.formatters")
        return getattr(mod, name)
    if name in ("RequestValidator", "RequestValidationError"):
        mod = importlib.import_module("analysis_llm.utils.validators")
        return getattr(mod, name)
    raise AttributeError(name)
