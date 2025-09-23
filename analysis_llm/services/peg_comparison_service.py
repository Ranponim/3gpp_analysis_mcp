"""
PEG 비교분석 메인 서비스 모듈

이 모듈은 PEG(Performance Engineering Guidelines) 비교분석의 핵심 비즈니스 로직을
담당합니다. 데이터 검증, 통계 계산, 트렌드 분석, 요약 통계 생성 등의 전체 플로우를
조율하고 관리합니다.

Author: KPI Dashboard Team
Created: 2024-01-15
Version: 1.0.0
"""

import time
import logging
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from datetime import datetime
import asyncio

# 로컬 모듈 임포트
from ..config.peg_comparison_config import get_config
from ..exceptions.error_handler import ErrorHandler, ErrorType, ErrorSeverity, PEGComparisonError
from ..models.peg_comparison import (
    PEGComparisonRequest, PEGComparisonResponse, PEGResult, PEGSummary,
    PEGPeriodData, PEGComparison, create_success_response, create_error_response
)
from ..utils.data_validator import DataValidator, ValidationReport
from ..utils.peg_calculator import PEGCalculator, StatisticalResult, ComparisonResult

# 로거 설정
logger = logging.getLogger(__name__)


@dataclass
class AnalysisContext:
    """분석 컨텍스트 정보"""
    analysis_id: str
    start_time: datetime
    data_quality: str
    total_pegs: int
    processed_pegs: int
    failed_pegs: int
    processing_time: float = 0.0
    
    def __post_init__(self):
        """초기화 후 처리"""
        if self.start_time is None:
            self.start_time = datetime.utcnow()


class PEGComparisonAnalyzer:
    """
    PEG 비교분석 메인 서비스 클래스
    
    PEG 비교분석의 전체 플로우를 관리하고 조율합니다.
    """
    
    def __init__(self):
        """분석기 초기화"""
        self.config = get_config()
        self.error_handler = ErrorHandler()
        self.validator = DataValidator()
        self.calculator = PEGCalculator()
        
        logger.info("PEG 비교분석 서비스 초기화 완료")
    
    async def analysis_peg_comparison(
        self,
        raw_data: Dict[str, Any],
        options: Optional[Dict[str, Any]] = None
    ) -> PEGComparisonResponse:
        """
        PEG 비교분석 수행 (메인 메서드)
        
        Args:
            raw_data: 원시 KPI 데이터 및 PEG 정의
            options: 분석 옵션 (메타데이터 포함 여부 등)
        
        Returns:
            PEGComparisonResponse: PEG 비교분석 결과
        """
        analysis_id = raw_data.get('analysis_id', f"analysis_{int(time.time())}")
        start_time = time.time()
        
        logger.info(f"PEG 비교분석 시작: ID={analysis_id}")
        
        try:
            # 분석 컨텍스트 생성
            context = AnalysisContext(
                analysis_id=analysis_id,
                start_time=datetime.utcnow(),
                data_quality="unknown",
                total_pegs=0,
                processed_pegs=0,
                failed_pegs=0
            )
            
            # 1. 데이터 검증 및 전처리
            logger.debug("1단계: 데이터 검증 및 전처리")
            validation_report = await self._validate_and_preprocess_data(raw_data, context)
            
            if not validation_report.is_valid:
                return create_error_response(
                    error_message="데이터 검증 실패",
                    error_type="DATA_VALIDATION_ERROR",
                    details={
                        "validation_errors": validation_report.errors,
                        "quality_score": validation_report.statistics.get('quality_score', 0)
                    }
                )
            
            # 2. PEG별 데이터 그룹화
            logger.debug("2단계: PEG별 데이터 그룹화")
            grouped_data = await self._group_by_peg_and_period(validation_report.processed_data, context)
            
            # 3. 통계 계산 및 트렌드 분석
            logger.debug("3단계: 통계 계산 및 트렌드 분석")
            peg_results = await self._calculate_statistics_and_analyze_trends(grouped_data, context)
            
            # 4. 요약 통계 생성
            logger.debug("4단계: 요약 통계 생성")
            summary = await self._generate_summary(peg_results, context)
            
            # 5. 분석 메타데이터 생성
            logger.debug("5단계: 분석 메타데이터 생성")
            analysis_metadata = await self._generate_analysis_metadata(context, options)
            
            # 처리 시간 계산
            processing_time = time.time() - start_time
            context.processing_time = processing_time
            
            # 최종 결과 구성
            result_data = {
                "analysis_id": analysis_id,
                "peg_comparison_results": peg_results,
                "summary": summary,
                "analysis_metadata": analysis_metadata
            }
            
            logger.info(f"PEG 비교분석 완료: ID={analysis_id}, 처리시간={processing_time:.3f}초, PEG={context.processed_pegs}개")
            return create_success_response(result_data, processing_time, self.config.algorithm_version)
            
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"PEG 비교분석 실패: ID={analysis_id}, 처리시간={processing_time:.3f}초, 에러={str(e)}")
            
            error_context = self.error_handler.handle_error(
                e,
                context={
                    "analysis_id": analysis_id,
                    "processing_time": processing_time,
                    "function": "analysis_peg_comparison"
                }
            )
            
            return create_error_response(
                error_message=f"PEG 비교분석 실패: {str(e)}",
                error_type="ANALYSIS_ERROR",
                details=error_context.details
            )
    
    async def _validate_and_preprocess_data(
        self,
        raw_data: Dict[str, Any],
        context: AnalysisContext
    ) -> ValidationReport:
        """데이터 검증 및 전처리"""
        logger.debug("데이터 검증 및 전처리 시작")
        
        try:
            # 데이터 검증 수행
            validation_report = self.validator.validate_and_preprocess(raw_data)
            
            # 컨텍스트 업데이트
            context.data_quality = validation_report.quality_level.value
            context.total_pegs = len(set(stat.get('kpi_name') for stat in validation_report.processed_data.get('stats', [])))
            
            # 검증 결과 로깅
            if validation_report.is_valid:
                logger.info(f"데이터 검증 성공: 품질={context.data_quality}, PEG={context.total_pegs}개")
            else:
                logger.warning(f"데이터 검증 경고: 품질={context.data_quality}, 오류={len(validation_report.errors)}개")
            
            return validation_report
            
        except Exception as e:
            logger.error(f"데이터 검증 및 전처리 중 에러 발생: {e}")
            raise PEGComparisonError(
                message=f"데이터 검증 및 전처리 실패: {str(e)}",
                error_type=ErrorType.DATA_VALIDATION_ERROR,
                severity=ErrorSeverity.HIGH,
                details={"function": "_validate_and_preprocess_data"}
            )
    
    async def _group_by_peg_and_period(
        self,
        processed_data: Dict[str, Any],
        context: AnalysisContext
    ) -> Dict[str, Dict[str, List[float]]]:
        """PEG별, 기간별 데이터 그룹화"""
        logger.debug("PEG별, 기간별 데이터 그룹화 시작")
        
        try:
            stats = processed_data.get('stats', [])
            grouped_data = {}
            
            for stat in stats:
                kpi_name = stat.get('kpi_name')
                period = stat.get('period')
                avg_value = stat.get('avg')
                
                if not all([kpi_name, period, avg_value is not None]):
                    logger.warning(f"불완전한 데이터 건너뜀: {stat}")
                    continue
                
                if kpi_name not in grouped_data:
                    grouped_data[kpi_name] = {'N-1': [], 'N': []}
                
                if period in grouped_data[kpi_name]:
                    grouped_data[kpi_name][period].append(avg_value)
                else:
                    logger.warning(f"알 수 없는 기간: {period}")
            
            # 그룹화 결과 검증
            valid_groups = 0
            for peg_name, periods in grouped_data.items():
                if len(periods.get('N-1', [])) > 0 and len(periods.get('N', [])) > 0:
                    valid_groups += 1
                else:
                    logger.warning(f"PEG '{peg_name}'에 N-1 또는 N 기간 데이터가 부족함")
            
            logger.info(f"데이터 그룹화 완료: 총 PEG={len(grouped_data)}개, 유효 그룹={valid_groups}개")
            return grouped_data
            
        except Exception as e:
            logger.error(f"데이터 그룹화 중 에러 발생: {e}")
            raise PEGComparisonError(
                message=f"데이터 그룹화 실패: {str(e)}",
                error_type=ErrorType.DATA_PROCESSING_ERROR,
                severity=ErrorSeverity.MEDIUM,
                details={"function": "_group_by_peg_and_period"}
            )
    
    async def _calculate_statistics_and_analyze_trends(
        self,
        grouped_data: Dict[str, Dict[str, List[float]]],
        context: AnalysisContext
    ) -> List[Dict[str, Any]]:
        """통계 계산 및 트렌드 분석"""
        logger.debug("통계 계산 및 트렌드 분석 시작")
        
        try:
            peg_results = []
            processed_count = 0
            failed_count = 0
            
            for peg_name, periods in grouped_data.items():
                try:
                    logger.debug(f"PEG '{peg_name}' 분석 시작")
                    
                    # N-1과 N 기간 데이터 추출
                    n1_values = periods.get('N-1', [])
                    n_values = periods.get('N', [])
                    
                    if not n1_values or not n_values:
                        logger.warning(f"PEG '{peg_name}'에 충분한 데이터가 없음: N-1={len(n1_values)}개, N={len(n_values)}개")
                        failed_count += 1
                        continue
                    
                    # 통계 계산
                    n1_stats = self.calculator.calculate_statistics(n1_values)
                    n_stats = self.calculator.calculate_statistics(n_values)
                    
                    # 기간 비교 분석
                    comparison = self.calculator.compare_periods(n1_values, n_values)
                    
                    # PEG 정의에서 가중치 가져오기
                    weight = self._get_peg_weight(peg_name, context)
                    
                    # PEG 결과 생성
                    peg_result = {
                        "peg_name": peg_name,
                        "weight": weight,
                        "n1_period": {
                            "avg": n1_stats.mean,
                            "rsd": n1_stats.rsd,
                            "values": n1_stats.values,
                            "count": n1_stats.count
                        },
                        "n_period": {
                            "avg": n_stats.mean,
                            "rsd": n_stats.rsd,
                            "values": n_stats.values,
                            "count": n_stats.count
                        },
                        "comparison": {
                            "change_percent": comparison.change_percent,
                            "change_absolute": comparison.change_absolute,
                            "trend": comparison.trend.value,
                            "significance": comparison.significance.value,
                            "confidence": comparison.confidence
                        },
                        "metadata": {
                            "cell_id": self._extract_cell_id(peg_name, context),
                            "calculated_at": datetime.utcnow().isoformat(),
                            "data_quality": self._assess_peg_data_quality(n1_stats, n_stats)
                        }
                    }
                    
                    peg_results.append(peg_result)
                    processed_count += 1
                    
                    logger.debug(f"PEG '{peg_name}' 분석 완료: 변화율={comparison.change_percent:.2f}%, 트렌드={comparison.trend.value}")
                    
                except Exception as e:
                    logger.error(f"PEG '{peg_name}' 분석 중 에러 발생: {e}")
                    failed_count += 1
                    continue
            
            # 컨텍스트 업데이트
            context.processed_pegs = processed_count
            context.failed_pegs = failed_count
            
            logger.info(f"통계 계산 및 트렌드 분석 완료: 성공={processed_count}개, 실패={failed_count}개")
            return peg_results
            
        except Exception as e:
            logger.error(f"통계 계산 및 트렌드 분석 중 에러 발생: {e}")
            raise PEGComparisonError(
                message=f"통계 계산 및 트렌드 분석 실패: {str(e)}",
                error_type=ErrorType.CALCULATION_ERROR,
                severity=ErrorSeverity.MEDIUM,
                details={"function": "_calculate_statistics_and_analyze_trends"}
            )
    
    async def _generate_summary(
        self,
        peg_results: List[Dict[str, Any]],
        context: AnalysisContext
    ) -> Dict[str, Any]:
        """요약 통계 생성"""
        logger.debug("요약 통계 생성 시작")
        
        try:
            if not peg_results:
                logger.warning("PEG 결과가 없어 기본 요약 통계 생성")
                return {
                    "total_pegs": 0,
                    "improved": 0,
                    "declined": 0,
                    "stable": 0,
                    "weighted_avg_change": 0.0,
                    "overall_trend": "stable"
                }
            
            # 트렌드별 분류
            improved = len([p for p in peg_results if p['comparison']['trend'] == 'up'])
            declined = len([p for p in peg_results if p['comparison']['trend'] == 'down'])
            stable = len([p for p in peg_results if p['comparison']['trend'] == 'stable'])
            
            # 가중 평균 변화율 계산
            weighted_avg_change = self.calculator.calculate_weighted_average_change(peg_results)
            
            # 전체 트렌드 판정
            overall_trend = self.calculator.determine_overall_trend(weighted_avg_change)
            
            summary = {
                "total_pegs": len(peg_results),
                "improved": improved,
                "declined": declined,
                "stable": stable,
                "weighted_avg_change": weighted_avg_change,
                "overall_trend": overall_trend.value
            }
            
            logger.info(f"요약 통계 생성 완료: 총 PEG={len(peg_results)}개, 개선={improved}개, 하락={declined}개, 안정={stable}개")
            return summary
            
        except Exception as e:
            logger.error(f"요약 통계 생성 중 에러 발생: {e}")
            raise PEGComparisonError(
                message=f"요약 통계 생성 실패: {str(e)}",
                error_type=ErrorType.CALCULATION_ERROR,
                severity=ErrorSeverity.MEDIUM,
                details={"function": "_generate_summary"}
            )
    
    async def _generate_analysis_metadata(
        self,
        context: AnalysisContext,
        options: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """분석 메타데이터 생성"""
        logger.debug("분석 메타데이터 생성 시작")
        
        try:
            metadata = {
                "calculated_at": context.start_time.isoformat(),
                "algorithm_version": self.config.algorithm_version,
                "data_source": "kpi_timeseries",
                "processing_time": context.processing_time,
                "data_quality": context.data_quality,
                "total_pegs": context.total_pegs,
                "processed_pegs": context.processed_pegs,
                "failed_pegs": context.failed_pegs,
                "success_rate": context.processed_pegs / context.total_pegs if context.total_pegs > 0 else 0
            }
            
            # 옵션에서 추가 메타데이터 포함
            if options and options.get('include_metadata', True):
                metadata.update({
                    "period_definition": {
                        "n1_start": options.get('n1_start'),
                        "n1_end": options.get('n1_end'),
                        "n_start": options.get('n_start'),
                        "n_end": options.get('n_end')
                    },
                    "analysis_options": options
                })
            
            logger.debug("분석 메타데이터 생성 완료")
            return metadata
            
        except Exception as e:
            logger.error(f"분석 메타데이터 생성 중 에러 발생: {e}")
            return {
                "calculated_at": context.start_time.isoformat(),
                "algorithm_version": self.config.algorithm_version,
                "data_source": "kpi_timeseries",
                "error": f"메타데이터 생성 실패: {str(e)}"
            }
    
    def _get_peg_weight(self, peg_name: str, context: AnalysisContext) -> int:
        """PEG 가중치 가져오기"""
        try:
            # 실제 구현에서는 PEG 정의에서 가중치를 가져와야 함
            # 현재는 기본값 반환
            default_weight = 5
            logger.debug(f"PEG '{peg_name}' 가중치: {default_weight} (기본값)")
            return default_weight
            
        except Exception as e:
            logger.warning(f"PEG '{peg_name}' 가중치 가져오기 실패: {e}")
            return 5  # 기본값
    
    def _extract_cell_id(self, peg_name: str, context: AnalysisContext) -> str:
        """셀 ID 추출"""
        try:
            # 실제 구현에서는 데이터에서 셀 ID를 추출해야 함
            # 현재는 기본값 반환
            default_cell_id = "CELL_001"
            logger.debug(f"PEG '{peg_name}' 셀 ID: {default_cell_id} (기본값)")
            return default_cell_id
            
        except Exception as e:
            logger.warning(f"PEG '{peg_name}' 셀 ID 추출 실패: {e}")
            return "UNKNOWN"
    
    def _assess_peg_data_quality(
        self,
        n1_stats: StatisticalResult,
        n_stats: StatisticalResult
    ) -> str:
        """PEG 데이터 품질 평가"""
        try:
            # RSD 기반 품질 평가
            avg_rsd = (n1_stats.rsd + n_stats.rsd) / 2
            
            if avg_rsd <= self.config.analysis.high_quality_rsd_threshold:
                quality = "high"
            elif avg_rsd <= self.config.analysis.medium_quality_rsd_threshold:
                quality = "medium"
            else:
                quality = "low"
            
            logger.debug(f"데이터 품질 평가: 평균 RSD={avg_rsd:.2f}%, 품질={quality}")
            return quality
            
        except Exception as e:
            logger.warning(f"데이터 품질 평가 실패: {e}")
            return "unknown"
    
    def get_service_summary(self) -> Dict[str, Any]:
        """서비스 요약 정보 반환"""
        return {
            "service_name": "PEGComparisonAnalyzer",
            "version": "1.0.0",
            "algorithm_version": self.config.algorithm_version,
            "capabilities": [
                "데이터 검증 및 전처리",
                "통계 계산",
                "트렌드 분석",
                "요약 통계 생성",
                "에러 처리 및 복구"
            ],
            "configuration": {
                "trend_threshold": self.config.analysis.trend_threshold_percent,
                "significant_threshold": self.config.analysis.significant_threshold_percent,
                "highly_significant_threshold": self.config.analysis.highly_significant_threshold_percent,
                "outlier_detection_enabled": self.config.validation.outlier_detection_enabled,
                "max_processing_time": self.config.performance.max_processing_time_seconds
            }
        }


# 전역 분석기 인스턴스
analyzer = PEGComparisonAnalyzer()

# 편의 함수들
async def analysis_peg_comparison(
    raw_data: Dict[str, Any],
    options: Optional[Dict[str, Any]] = None
) -> PEGComparisonResponse:
    """전역 분석기를 사용한 PEG 비교분석"""
    return await analyzer.analysis_peg_comparison(raw_data, options)

def get_service_summary() -> Dict[str, Any]:
    """서비스 요약 정보 반환"""
    return analyzer.get_service_summary()

# 모듈 초기화 로그
logger.info("PEG 비교분석 메인 서비스 모듈이 성공적으로 로드되었습니다")




