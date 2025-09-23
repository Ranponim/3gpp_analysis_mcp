"""
PEG 비교분석 관련 데이터 모델 정의

이 모듈은 PEG(Performance Engineering Guidelines) 비교분석에 사용되는
모든 데이터 모델을 정의합니다. Pydantic을 사용하여 데이터 검증과
직렬화를 자동화합니다.

Author: KPI Dashboard Team
Created: 2024-01-15
Version: 1.0.0
"""

from datetime import datetime
from typing import List, Dict, Optional, Any, Literal
from pydantic import BaseModel, Field, validator
import logging

# 로거 설정
logger = logging.getLogger(__name__)


class PEGDataPoint(BaseModel):
    """
    개별 PEG 데이터 포인트 모델
    
    각 PEG의 특정 기간(N-1 또는 N)에 대한 통계 데이터를 나타냅니다.
    """
    kpi_name: str = Field(
        ..., 
        description="PEG 이름 (예: UL_throughput_avg)",
        min_length=1,
        max_length=100
    )
    period: Literal["N-1", "N"] = Field(
        ..., 
        description="기간 구분 (N-1: 이전 기간, N: 현재 기간)"
    )
    avg: float = Field(
        ..., 
        description="평균값",
        ge=0.0,
        le=1000000.0
    )
    cell_id: str = Field(
        ..., 
        description="셀 식별자",
        min_length=1,
        max_length=50
    )

    @validator('kpi_name')
    def validate_kpi_name(cls, v):
        """KPI 이름 검증"""
        if not v or not v.strip():
            raise ValueError("KPI 이름은 비어있을 수 없습니다")
        logger.debug(f"KPI 이름 검증 완료: {v}")
        return v.strip()

    @validator('avg')
    def validate_avg(cls, v):
        """평균값 검증"""
        if v < 0:
            raise ValueError("평균값은 0 이상이어야 합니다")
        if v > 1000000:
            raise ValueError("평균값은 1,000,000 이하여야 합니다")
        logger.debug(f"평균값 검증 완료: {v}")
        return v

    class Config:
        """Pydantic 설정"""
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        schema_extra = {
            "example": {
                "kpi_name": "UL_throughput_avg",
                "period": "N-1",
                "avg": 45.8,
                "cell_id": "CELL_001"
            }
        }


class PEGDefinition(BaseModel):
    """
    PEG 정의 모델
    
    각 PEG의 가중치와 임계값 설정을 포함합니다.
    """
    weight: int = Field(
        ..., 
        description="PEG 가중치 (1-10)",
        ge=1,
        le=10
    )
    thresholds: Dict[str, float] = Field(
        ..., 
        description="임계값 설정",
        min_items=1
    )

    @validator('weight')
    def validate_weight(cls, v):
        """가중치 검증"""
        if not (1 <= v <= 10):
            raise ValueError("가중치는 1-10 사이의 값이어야 합니다")
        logger.debug(f"가중치 검증 완료: {v}")
        return v

    @validator('thresholds')
    def validate_thresholds(cls, v):
        """임계값 검증"""
        if not v:
            raise ValueError("임계값은 최소 1개 이상 설정되어야 합니다")
        
        for key, value in v.items():
            if not isinstance(value, (int, float)):
                raise ValueError(f"임계값 '{key}'는 숫자여야 합니다")
            if value < 0:
                raise ValueError(f"임계값 '{key}'는 0 이상이어야 합니다")
        
        logger.debug(f"임계값 검증 완료: {v}")
        return v

    class Config:
        """Pydantic 설정"""
        schema_extra = {
            "example": {
                "weight": 8,
                "thresholds": {
                    "high": 80.0,
                    "medium": 60.0,
                    "low": 40.0
                }
            }
        }


class PEGPeriodData(BaseModel):
    """
    PEG 기간별 데이터 모델
    
    특정 기간(N-1 또는 N)에 대한 상세 통계 정보를 포함합니다.
    """
    avg: float = Field(
        ..., 
        description="평균값",
        ge=0.0
    )
    rsd: float = Field(
        ..., 
        description="상대표준편차 (%)",
        ge=0.0
    )
    values: List[float] = Field(
        ..., 
        description="원시 데이터 배열",
        min_items=1
    )
    count: int = Field(
        ..., 
        description="데이터 개수",
        ge=1
    )

    @validator('values')
    def validate_values(cls, v):
        """원시 데이터 검증"""
        if not v:
            raise ValueError("원시 데이터는 최소 1개 이상이어야 합니다")
        
        for value in v:
            if not isinstance(value, (int, float)):
                raise ValueError("원시 데이터는 숫자여야 합니다")
            if value < 0:
                raise ValueError("원시 데이터는 0 이상이어야 합니다")
        
        logger.debug(f"원시 데이터 검증 완료: {len(v)}개 항목")
        return v

    @validator('count')
    def validate_count(cls, v, values):
        """데이터 개수 검증"""
        if 'values' in values and v != len(values['values']):
            raise ValueError("데이터 개수는 원시 데이터 배열의 길이와 일치해야 합니다")
        logger.debug(f"데이터 개수 검증 완료: {v}")
        return v

    class Config:
        """Pydantic 설정"""
        schema_extra = {
            "example": {
                "avg": 45.83,
                "rsd": 2.1,
                "values": [45.8, 46.2, 45.5],
                "count": 3
            }
        }


class PEGComparison(BaseModel):
    """
    PEG 비교 분석 결과 모델
    
    N-1 기간과 N 기간 간의 비교 분석 결과를 포함합니다.
    """
    change_percent: float = Field(
        ..., 
        description="변화율 (%)",
        ge=-1000.0,
        le=1000.0
    )
    change_absolute: float = Field(
        ..., 
        description="절대 변화량"
    )
    trend: Literal["up", "down", "stable"] = Field(
        ..., 
        description="트렌드 방향"
    )
    significance: Literal["high", "medium", "low"] = Field(
        ..., 
        description="변화의 유의성"
    )
    confidence: float = Field(
        ..., 
        description="분석 신뢰도 (0.0-1.0)",
        ge=0.0,
        le=1.0
    )

    @validator('confidence')
    def validate_confidence(cls, v):
        """신뢰도 검증"""
        if not (0.0 <= v <= 1.0):
            raise ValueError("신뢰도는 0.0-1.0 사이의 값이어야 합니다")
        logger.debug(f"신뢰도 검증 완료: {v}")
        return v

    class Config:
        """Pydantic 설정"""
        schema_extra = {
            "example": {
                "change_percent": 2.1,
                "change_absolute": 0.97,
                "trend": "up",
                "significance": "low",
                "confidence": 0.85
            }
        }


class PEGResult(BaseModel):
    """
    개별 PEG 분석 결과 모델
    
    하나의 PEG에 대한 완전한 분석 결과를 포함합니다.
    """
    peg_name: str = Field(
        ..., 
        description="PEG 이름",
        min_length=1
    )
    weight: int = Field(
        ..., 
        description="PEG 가중치",
        ge=1,
        le=10
    )
    n1_period: PEGPeriodData = Field(
        ..., 
        description="N-1 기간 데이터"
    )
    n_period: PEGPeriodData = Field(
        ..., 
        description="N 기간 데이터"
    )
    comparison: PEGComparison = Field(
        ..., 
        description="비교 분석 결과"
    )
    metadata: Dict[str, Any] = Field(
        ..., 
        description="메타데이터",
        min_items=1
    )

    @validator('metadata')
    def validate_metadata(cls, v):
        """메타데이터 검증"""
        required_fields = ['cell_id', 'calculated_at', 'data_quality']
        for field in required_fields:
            if field not in v:
                raise ValueError(f"메타데이터에 필수 필드 '{field}'가 누락되었습니다")
        
        # 데이터 품질 검증
        if v['data_quality'] not in ['high', 'medium', 'low']:
            raise ValueError("데이터 품질은 'high', 'medium', 'low' 중 하나여야 합니다")
        
        logger.debug(f"메타데이터 검증 완료: {len(v)}개 필드")
        return v

    class Config:
        """Pydantic 설정"""
        schema_extra = {
            "example": {
                "peg_name": "UL_throughput_avg",
                "weight": 8,
                "n1_period": {
                    "avg": 45.83,
                    "rsd": 2.1,
                    "values": [45.8, 46.2, 45.5],
                    "count": 3
                },
                "n_period": {
                    "avg": 46.8,
                    "rsd": 1.8,
                    "values": [46.8, 47.1, 46.5],
                    "count": 3
                },
                "comparison": {
                    "change_percent": 2.1,
                    "change_absolute": 0.97,
                    "trend": "up",
                    "significance": "low",
                    "confidence": 0.85
                },
                "metadata": {
                    "cell_id": "CELL_001",
                    "calculated_at": "2024-01-15T10:30:00Z",
                    "data_quality": "high"
                }
            }
        }


class PEGSummary(BaseModel):
    """
    PEG 비교분석 요약 통계 모델
    
    전체 PEG 비교분석의 요약 정보를 포함합니다.
    """
    total_pegs: int = Field(
        ..., 
        description="총 PEG 개수",
        ge=0
    )
    improved: int = Field(
        ..., 
        description="개선된 PEG 개수",
        ge=0
    )
    declined: int = Field(
        ..., 
        description="하락한 PEG 개수",
        ge=0
    )
    stable: int = Field(
        ..., 
        description="안정된 PEG 개수",
        ge=0
    )
    weighted_avg_change: float = Field(
        ..., 
        description="가중 평균 변화율 (%)"
    )
    overall_trend: Literal["improving", "declining", "stable"] = Field(
        ..., 
        description="전체 트렌드"
    )

    @validator('improved', 'declined', 'stable')
    def validate_counts(cls, v, values):
        """개수 검증"""
        if 'total_pegs' in values:
            total = values['total_pegs']
            if v > total:
                raise ValueError("개별 카운트는 총 개수를 초과할 수 없습니다")
        logger.debug(f"카운트 검증 완료: {v}")
        return v

    @validator('total_pegs')
    def validate_total_pegs(cls, v, values):
        """총 PEG 개수 검증"""
        if v < 0:
            raise ValueError("총 PEG 개수는 0 이상이어야 합니다")
        
        # 다른 카운트들과의 일관성 검증
        if 'improved' in values and 'declined' in values and 'stable' in values:
            sum_counts = values['improved'] + values['declined'] + values['stable']
            if sum_counts != v:
                raise ValueError("개선+하락+안정 개수의 합은 총 개수와 일치해야 합니다")
        
        logger.debug(f"총 PEG 개수 검증 완료: {v}")
        return v

    class Config:
        """Pydantic 설정"""
        schema_extra = {
            "example": {
                "total_pegs": 15,
                "improved": 5,
                "declined": 3,
                "stable": 7,
                "weighted_avg_change": 1.2,
                "overall_trend": "improving"
            }
        }


class PEGComparisonRequest(BaseModel):
    """
    PEG 비교분석 요청 모델
    
    MCP 도구로 전달되는 입력 데이터를 정의합니다.
    """
    analysis_id: str = Field(
        ..., 
        description="분석 ID",
        min_length=1,
        max_length=100
    )
    raw_data: Dict[str, List[PEGDataPoint]] = Field(
        ..., 
        description="원시 KPI 데이터",
        min_items=1
    )
    peg_definitions: Dict[str, PEGDefinition] = Field(
        ..., 
        description="PEG 정의 정보",
        min_items=1
    )
    options: Optional[Dict[str, Any]] = Field(
        default=None,
        description="분석 옵션"
    )

    @validator('analysis_id')
    def validate_analysis_id(cls, v):
        """분석 ID 검증"""
        if not v or not v.strip():
            raise ValueError("분석 ID는 비어있을 수 없습니다")
        logger.debug(f"분석 ID 검증 완료: {v}")
        return v.strip()

    @validator('raw_data')
    def validate_raw_data(cls, v):
        """원시 데이터 검증"""
        if not v:
            raise ValueError("원시 데이터는 최소 1개 이상이어야 합니다")
        
        # stats 키가 있는지 확인
        if 'stats' not in v:
            raise ValueError("원시 데이터에 'stats' 키가 필요합니다")
        
        if not v['stats']:
            raise ValueError("stats 배열은 비어있을 수 없습니다")
        
        logger.debug(f"원시 데이터 검증 완료: {len(v['stats'])}개 항목")
        return v

    @validator('peg_definitions')
    def validate_peg_definitions(cls, v):
        """PEG 정의 검증"""
        if not v:
            raise ValueError("PEG 정의는 최소 1개 이상이어야 합니다")
        
        logger.debug(f"PEG 정의 검증 완료: {len(v)}개 정의")
        return v

    class Config:
        """Pydantic 설정"""
        schema_extra = {
            "example": {
                "analysis_id": "result_123",
                "raw_data": {
                    "stats": [
                        {
                            "kpi_name": "UL_throughput_avg",
                            "period": "N-1",
                            "avg": 45.8,
                            "cell_id": "CELL_001"
                        }
                    ]
                },
                "peg_definitions": {
                    "UL_throughput_avg": {
                        "weight": 8,
                        "thresholds": {
                            "high": 80.0,
                            "medium": 60.0,
                            "low": 40.0
                        }
                    }
                },
                "options": {
                    "include_metadata": True,
                    "algorithm_version": "v2.1.0"
                }
            }
        }


class PEGComparisonResponse(BaseModel):
    """
    PEG 비교분석 응답 모델
    
    MCP 도구에서 반환되는 결과 데이터를 정의합니다.
    """
    success: bool = Field(
        ..., 
        description="분석 성공 여부"
    )
    data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="분석 결과 데이터"
    )
    processing_time: float = Field(
        ..., 
        description="처리 시간 (초)",
        ge=0.0
    )
    algorithm_version: str = Field(
        ..., 
        description="알고리즘 버전",
        min_length=1
    )
    error: Optional[Dict[str, Any]] = Field(
        default=None,
        description="에러 정보 (실패 시)"
    )

    @validator('processing_time')
    def validate_processing_time(cls, v):
        """처리 시간 검증"""
        if v < 0:
            raise ValueError("처리 시간은 0 이상이어야 합니다")
        logger.debug(f"처리 시간 검증 완료: {v}초")
        return v

    @validator('algorithm_version')
    def validate_algorithm_version(cls, v):
        """알고리즘 버전 검증"""
        if not v or not v.strip():
            raise ValueError("알고리즘 버전은 비어있을 수 없습니다")
        logger.debug(f"알고리즘 버전 검증 완료: {v}")
        return v.strip()

    class Config:
        """Pydantic 설정"""
        schema_extra = {
            "example": {
                "success": True,
                "data": {
                    "peg_comparison_results": [],
                    "summary": {},
                    "analysis_metadata": {}
                },
                "processing_time": 0.123,
                "algorithm_version": "v2.1.0"
            }
        }


# 유틸리티 함수들
def create_error_response(
    error_message: str, 
    error_type: str = "PROCESSING_ERROR",
    details: Optional[Dict[str, Any]] = None
) -> PEGComparisonResponse:
    """
    에러 응답 생성 유틸리티 함수
    
    Args:
        error_message: 에러 메시지
        error_type: 에러 타입
        details: 추가 에러 세부사항
    
    Returns:
        PEGComparisonResponse: 에러 응답 객체
    """
    logger.error(f"에러 응답 생성: {error_type} - {error_message}")
    
    return PEGComparisonResponse(
        success=False,
        processing_time=0.0,
        algorithm_version="v2.1.0",
        error={
            "message": error_message,
            "type": error_type,
            "details": details or {},
            "timestamp": datetime.utcnow().isoformat()
        }
    )


def create_success_response(
    data: Dict[str, Any],
    processing_time: float,
    algorithm_version: str = "v2.1.0"
) -> PEGComparisonResponse:
    """
    성공 응답 생성 유틸리티 함수
    
    Args:
        data: 분석 결과 데이터
        processing_time: 처리 시간
        algorithm_version: 알고리즘 버전
    
    Returns:
        PEGComparisonResponse: 성공 응답 객체
    """
    logger.info(f"성공 응답 생성: 처리시간 {processing_time}초, 버전 {algorithm_version}")
    
    return PEGComparisonResponse(
        success=True,
        data=data,
        processing_time=processing_time,
        algorithm_version=algorithm_version
    )


# 모듈 초기화 로그
logger.info("PEG 비교분석 데이터 모델 모듈이 성공적으로 로드되었습니다")




