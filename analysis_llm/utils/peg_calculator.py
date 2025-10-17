"""
PEG 비교분석 통계 계산 유틸리티 모듈

이 모듈은 PEG(Performance Engineering Guidelines) 비교분석에 필요한
모든 통계 계산 기능을 제공합니다. 평균, RSD, 변화율, 트렌드 판정,
유의성 판정 등의 계산을 수행합니다.

Author: KPI Dashboard Team
Created: 2024-01-15
Version: 1.0.0
"""

import numpy as np
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import math
from statistics import median, stdev, mean

# 로컬 모듈 임포트
from ..config.peg_comparison_config import get_config
from ..exceptions.error_handler import ErrorHandler, ErrorType, ErrorSeverity, PEGComparisonError

# 로거 설정
logger = logging.getLogger(__name__)


class TrendDirection(Enum):
    """트렌드 방향 열거형"""
    UP = "up"
    DOWN = "down"
    STABLE = "stable"


class SignificanceLevel(Enum):
    """유의성 레벨 열거형"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class StatisticalResult:
    """통계 계산 결과 데이터 클래스"""
    mean: float
    std: float
    rsd: float
    median: float
    count: int
    min_value: float
    max_value: float
    values: List[float]
    
    def __post_init__(self):
        """초기화 후 검증"""
        if self.count != len(self.values):
            raise ValueError("데이터 개수와 값 배열 길이가 일치하지 않습니다")
        if self.count <= 0:
            raise ValueError("데이터 개수는 0보다 커야 합니다")


@dataclass
class ComparisonResult:
    """비교 분석 결과 데이터 클래스"""
    change_percent: float
    change_absolute: float
    trend: TrendDirection
    significance: SignificanceLevel
    confidence: float
    is_significant: bool


class PEGCalculator:
    """
    PEG 비교분석 통계 계산 클래스
    
    다양한 통계 계산 및 분석 기능을 제공합니다.
    """
    
    def __init__(self):
        """계산기 초기화"""
        self.config = get_config()
        self.error_handler = ErrorHandler()
        
        logger.info("PEG 통계 계산기 초기화 완료")
    
    def calculate_statistics(self, values: List[float]) -> StatisticalResult:
        """
        기본 통계 계산
        
        Args:
            values: 계산할 값들의 리스트
        
        Returns:
            StatisticalResult: 통계 계산 결과
        
        Raises:
            PEGComparisonError: 계산 중 에러 발생 시
        """
        logger.debug(f"통계 계산 시작: {len(values)}개 값")
        
        try:
            # 입력 데이터 검증
            if not values:
                raise PEGComparisonError(
                    message="계산할 값이 없습니다",
                    error_type=ErrorType.DATA_PROCESSING_ERROR,
                    severity=ErrorSeverity.MEDIUM,
                    details={"values_count": 0}
                )
            
            # 유효한 값만 필터링 (NaN, None 제거)
            valid_values = [v for v in values if v is not None and not math.isnan(v)]
            
            if not valid_values:
                raise PEGComparisonError(
                    message="유효한 값이 없습니다",
                    error_type=ErrorType.DATA_PROCESSING_ERROR,
                    severity=ErrorSeverity.MEDIUM,
                    details={"original_count": len(values), "valid_count": 0}
                )
            
            # 기본 통계 계산
            mean_value = self._sanitize_float_value(mean(valid_values))
            std_value = self._sanitize_float_value(stdev(valid_values) if len(valid_values) > 1 else 0.0)
            median_value = self._sanitize_float_value(median(valid_values))
            min_value = self._sanitize_float_value(min(valid_values))
            max_value = self._sanitize_float_value(max(valid_values))
            
            # RSD 계산
            rsd_value = self._sanitize_float_value(self._calculate_rsd(valid_values, mean_value))
            
            result = StatisticalResult(
                mean=mean_value,
                std=std_value,
                rsd=rsd_value,
                median=median_value,
                count=len(valid_values),
                min_value=min_value,
                max_value=max_value,
                values=valid_values
            )
            
            logger.debug(f"통계 계산 완료: 평균={mean_value:.2f}, RSD={rsd_value:.2f}%")
            return result
            
        except Exception as e:
            logger.error(f"통계 계산 중 에러 발생: {e}")
            error_context = self.error_handler.handle_error(
                e,
                context={
                    "values_count": len(values) if values else 0,
                    "function": "calculate_statistics"
                }
            )
            raise PEGComparisonError(
                message=f"통계 계산 실패: {str(e)}",
                error_type=ErrorType.CALCULATION_ERROR,
                severity=ErrorSeverity.MEDIUM,
                details=error_context.details
            )
    
    def _calculate_rsd(self, values: List[float], mean_value: float) -> float:
        """
        상대표준편차(RSD) 계산
        
        Args:
            values: 값들의 리스트
            mean_value: 평균값
        
        Returns:
            float: RSD 값 (%)
        """
        try:
            if mean_value == 0:
                logger.warning("평균값이 0이므로 RSD를 0으로 설정")
                return 0.0
            
            if len(values) <= 1:
                logger.warning("데이터가 1개 이하이므로 RSD를 0으로 설정")
                return 0.0
            
            # 표준편차 계산
            if self.config.analysis.use_sample_std:
                # 표본 표준편차 (N-1로 나누기)
                std_value = stdev(values)
            else:
                # 모집단 표준편차 (N으로 나누기)
                std_value = math.sqrt(sum((x - mean_value) ** 2 for x in values) / len(values))
            
            # RSD 계산 (%)
            rsd = (std_value / mean_value) * 100
            
            # 결과 정규화
            rsd = self._sanitize_float_value(rsd)
            
            logger.debug(f"RSD 계산: 표준편차={std_value:.4f}, 평균={mean_value:.4f}, RSD={rsd:.2f}%")
            return rsd
            
        except Exception as e:
            logger.error(f"RSD 계산 중 에러 발생: {e}")
            return 0.0
    
    def _sanitize_float_value(self, value: float) -> float:
        """
        float 값을 JSON 호환 가능한 값으로 정규화
        
        inf, -inf, nan 값을 안전한 값으로 변환합니다.
        
        Args:
            value: 정규화할 float 값
            
        Returns:
            JSON 호환 가능한 float 값
        """
        if math.isnan(value):
            logger.warning("NaN 값을 0.0으로 변환")
            return 0.0
        elif math.isinf(value):
            if value > 0:
                logger.warning("양의 무한대 값을 999999.0으로 변환")
                return 999999.0
            else:
                logger.warning("음의 무한대 값을 -999999.0으로 변환")
                return -999999.0
        else:
            return value
    
    def calculate_change_percent(self, n1_avg: float, n_avg: float) -> float:
        """
        변화율 계산 (%)
        
        Args:
            n1_avg: N-1 기간 평균값
            n_avg: N 기간 평균값
        
        Returns:
            float: 변화율 (%)
        """
        logger.debug(f"변화율 계산: N-1={n1_avg:.2f}, N={n_avg:.2f}")
        
        try:
            # 입력 값 정규화 (inf, nan 체크)
            n1_avg = self._sanitize_float_value(n1_avg)
            n_avg = self._sanitize_float_value(n_avg)
            
            if n1_avg == 0:
                if n_avg == 0:
                    logger.warning("N-1과 N 기간 모두 0이므로 변화율을 0으로 설정")
                    return 0.0
                else:
                    logger.warning("N-1 기간이 0이므로 변화율을 100%로 설정")
                    return 100.0
            
            change_percent = ((n_avg - n1_avg) / n1_avg) * 100
            
            # 결과 값 정규화
            change_percent = self._sanitize_float_value(change_percent)
            
            logger.debug(f"변화율 계산 완료: {change_percent:.2f}%")
            return change_percent
            
        except Exception as e:
            logger.error(f"변화율 계산 중 에러 발생: {e}")
            return 0.0
    
    def calculate_change_absolute(self, n1_avg: float, n_avg: float) -> float:
        """
        절대 변화량 계산
        
        Args:
            n1_avg: N-1 기간 평균값
            n_avg: N 기간 평균값
        
        Returns:
            float: 절대 변화량
        """
        logger.debug(f"절대 변화량 계산: N-1={n1_avg:.2f}, N={n_avg:.2f}")
        
        try:
            # 입력 값 정규화
            n1_avg = self._sanitize_float_value(n1_avg)
            n_avg = self._sanitize_float_value(n_avg)
            
            change_absolute = n_avg - n1_avg
            
            # 결과 값 정규화
            change_absolute = self._sanitize_float_value(change_absolute)
            
            logger.debug(f"절대 변화량 계산 완료: {change_absolute:.2f}")
            return change_absolute
            
        except Exception as e:
            logger.error(f"절대 변화량 계산 중 에러 발생: {e}")
            return 0.0
    
    def determine_trend(self, change_percent: float) -> TrendDirection:
        """
        트렌드 방향 판정
        
        Args:
            change_percent: 변화율 (%)
        
        Returns:
            TrendDirection: 트렌드 방향
        """
        logger.debug(f"트렌드 판정: 변화율={change_percent:.2f}%")
        
        try:
            threshold = self.config.analysis.trend_threshold_percent
            
            if abs(change_percent) < threshold:
                trend = TrendDirection.STABLE
            elif change_percent > 0:
                trend = TrendDirection.UP
            else:
                trend = TrendDirection.DOWN
            
            logger.debug(f"트렌드 판정 완료: {trend.value} (임계값: {threshold}%)")
            return trend
            
        except Exception as e:
            logger.error(f"트렌드 판정 중 에러 발생: {e}")
            return TrendDirection.STABLE
    
    def determine_significance(self, change_percent: float) -> SignificanceLevel:
        """
        유의성 레벨 판정
        
        Args:
            change_percent: 변화율 (%)
        
        Returns:
            SignificanceLevel: 유의성 레벨
        """
        logger.debug(f"유의성 판정: 변화율={change_percent:.2f}%")
        
        try:
            abs_change = abs(change_percent)
            
            if abs_change >= self.config.analysis.highly_significant_threshold_percent:
                significance = SignificanceLevel.HIGH
            elif abs_change >= self.config.analysis.significant_threshold_percent:
                significance = SignificanceLevel.MEDIUM
            else:
                significance = SignificanceLevel.LOW
            
            logger.debug(f"유의성 판정 완료: {significance.value} (절대 변화율: {abs_change:.2f}%)")
            return significance
            
        except Exception as e:
            logger.error(f"유의성 판정 중 에러 발생: {e}")
            return SignificanceLevel.LOW
    
    def calculate_confidence(
        self,
        n1_values: List[float],
        n_values: List[float],
        change_percent: float
    ) -> float:
        """
        분석 신뢰도 계산
        
        Args:
            n1_values: N-1 기간 값들
            n_values: N 기간 값들
            change_percent: 변화율 (%)
        
        Returns:
            float: 신뢰도 (0.0-1.0)
        """
        logger.debug(f"신뢰도 계산: N-1={len(n1_values)}개, N={len(n_values)}개")
        
        try:
            # 기본 신뢰도
            base_confidence = self.config.analysis.default_confidence
            
            # 데이터 개수에 따른 신뢰도 조정
            min_count = min(len(n1_values), len(n_values))
            if min_count >= 10:
                count_factor = 1.0
            elif min_count >= 5:
                count_factor = 0.9
            elif min_count >= 3:
                count_factor = 0.8
            else:
                count_factor = 0.6
            
            # 데이터 품질에 따른 신뢰도 조정
            n1_rsd = self._calculate_rsd(n1_values, mean(n1_values)) if n1_values else 0
            n_rsd = self._calculate_rsd(n_values, mean(n_values)) if n_values else 0
            avg_rsd = (n1_rsd + n_rsd) / 2
            
            if avg_rsd <= self.config.analysis.high_quality_rsd_threshold:
                quality_factor = 1.0
            elif avg_rsd <= self.config.analysis.medium_quality_rsd_threshold:
                quality_factor = 0.9
            else:
                quality_factor = 0.7
            
            # 변화율 크기에 따른 신뢰도 조정
            abs_change = abs(change_percent)
            if abs_change >= 50:
                change_factor = 0.8  # 극단적 변화는 신뢰도 감소
            elif abs_change >= 20:
                change_factor = 0.9
            else:
                change_factor = 1.0
            
            # 최종 신뢰도 계산
            confidence = base_confidence * count_factor * quality_factor * change_factor
            confidence = max(0.0, min(1.0, confidence))  # 0.0-1.0 범위로 제한
            
            # 결과 정규화
            confidence = self._sanitize_float_value(confidence)
            
            logger.debug(f"신뢰도 계산 완료: {confidence:.3f} (기본:{base_confidence}, 개수:{count_factor}, 품질:{quality_factor}, 변화:{change_factor})")
            return confidence
            
        except Exception as e:
            logger.error(f"신뢰도 계산 중 에러 발생: {e}")
            return self.config.analysis.default_confidence
    
    def compare_periods(
        self,
        n1_values: List[float],
        n_values: List[float]
    ) -> ComparisonResult:
        """
        두 기간 비교 분석
        
        Args:
            n1_values: N-1 기간 값들
            n_values: N 기간 값들
        
        Returns:
            ComparisonResult: 비교 분석 결과
        """
        logger.debug(f"기간 비교 분석 시작: N-1={len(n1_values)}개, N={len(n_values)}개")
        
        try:
            # 각 기간의 통계 계산
            n1_stats = self.calculate_statistics(n1_values)
            n_stats = self.calculate_statistics(n_values)
            
            # 변화율 및 절대 변화량 계산
            change_percent = self.calculate_change_percent(n1_stats.mean, n_stats.mean)
            change_absolute = self.calculate_change_absolute(n1_stats.mean, n_stats.mean)
            
            # 트렌드 및 유의성 판정
            trend = self.determine_trend(change_percent)
            significance = self.determine_significance(change_percent)
            
            # 신뢰도 계산
            confidence = self.calculate_confidence(n1_values, n_values, change_percent)
            
            # 유의성 여부 판정
            is_significant = significance in [SignificanceLevel.MEDIUM, SignificanceLevel.HIGH]
            
            result = ComparisonResult(
                change_percent=change_percent,
                change_absolute=change_absolute,
                trend=trend,
                significance=significance,
                confidence=confidence,
                is_significant=is_significant
            )
            
            logger.info(f"기간 비교 분석 완료: 변화율={change_percent:.2f}%, 트렌드={trend.value}, 유의성={significance.value}")
            return result
            
        except Exception as e:
            logger.error(f"기간 비교 분석 중 에러 발생: {e}")
            error_context = self.error_handler.handle_error(
                e,
                context={
                    "n1_count": len(n1_values) if n1_values else 0,
                    "n_count": len(n_values) if n_values else 0,
                    "function": "compare_periods"
                }
            )
            raise PEGComparisonError(
                message=f"기간 비교 분석 실패: {str(e)}",
                error_type=ErrorType.CALCULATION_ERROR,
                severity=ErrorSeverity.MEDIUM,
                details=error_context.details
            )
    
    def calculate_weighted_average_change(
        self,
        peg_results: List[Dict[str, Any]]
    ) -> float:
        """
        가중 평균 변화율 계산
        
        Args:
            peg_results: PEG 결과 리스트 (weight, change_percent 포함)
        
        Returns:
            float: 가중 평균 변화율 (%)
        """
        logger.debug(f"가중 평균 변화율 계산: {len(peg_results)}개 PEG")
        
        try:
            if not peg_results:
                logger.warning("PEG 결과가 없어 가중 평균 변화율을 0으로 설정")
                return 0.0
            
            total_weighted_change = 0.0
            total_weight = 0.0
            
            for peg in peg_results:
                weight = peg.get('weight', 1)
                change_percent = peg.get('change_percent', 0.0)
                
                total_weighted_change += change_percent * weight
                total_weight += weight
            
            if total_weight == 0:
                logger.warning("총 가중치가 0이어 가중 평균 변화율을 0으로 설정")
                return 0.0
            
            weighted_avg_change = total_weighted_change / total_weight
            
            # 결과 정규화
            weighted_avg_change = self._sanitize_float_value(weighted_avg_change)
            
            logger.debug(f"가중 평균 변화율 계산 완료: {weighted_avg_change:.2f}%")
            return weighted_avg_change
            
        except Exception as e:
            logger.error(f"가중 평균 변화율 계산 중 에러 발생: {e}")
            return 0.0
    
    def determine_overall_trend(self, weighted_avg_change: float) -> TrendDirection:
        """
        전체 트렌드 판정
        
        Args:
            weighted_avg_change: 가중 평균 변화율 (%)
        
        Returns:
            TrendDirection: 전체 트렌드 방향
        """
        logger.debug(f"전체 트렌드 판정: 가중 평균 변화율={weighted_avg_change:.2f}%")
        
        try:
            threshold = self.config.analysis.trend_threshold_percent
            
            if abs(weighted_avg_change) < threshold:
                overall_trend = TrendDirection.STABLE
            elif weighted_avg_change > 0:
                overall_trend = TrendDirection.UP
            else:
                overall_trend = TrendDirection.DOWN
            
            logger.debug(f"전체 트렌드 판정 완료: {overall_trend.value}")
            return overall_trend
            
        except Exception as e:
            logger.error(f"전체 트렌드 판정 중 에러 발생: {e}")
            return TrendDirection.STABLE
    
    def detect_outliers(self, values: List[float], method: str = "iqr") -> List[int]:
        """
        이상치 탐지
        
        Args:
            values: 탐지할 값들
            method: 탐지 방법 ("iqr", "zscore", "modified_zscore")
        
        Returns:
            List[int]: 이상치 인덱스 리스트
        """
        logger.debug(f"이상치 탐지 시작: {len(values)}개 값, 방법={method}")
        
        try:
            if len(values) < 3:
                logger.warning("데이터가 3개 미만이어 이상치 탐지를 건너뜀")
                return []
            
            outliers = []
            
            if method == "iqr":
                outliers = self._detect_outliers_iqr(values)
            elif method == "zscore":
                outliers = self._detect_outliers_zscore(values)
            elif method == "modified_zscore":
                outliers = self._detect_outliers_modified_zscore(values)
            else:
                logger.warning(f"알 수 없는 이상치 탐지 방법: {method}")
                return []
            
            logger.debug(f"이상치 탐지 완료: {len(outliers)}개 발견")
            return outliers
            
        except Exception as e:
            logger.error(f"이상치 탐지 중 에러 발생: {e}")
            return []
    
    def _detect_outliers_iqr(self, values: List[float]) -> List[int]:
        """IQR 방법으로 이상치 탐지"""
        try:
            q1 = np.percentile(values, 25)
            q3 = np.percentile(values, 75)
            iqr = q3 - q1
            
            multiplier = self.config.validation.outlier_iqr_multiplier
            lower_bound = q1 - multiplier * iqr
            upper_bound = q3 + multiplier * iqr
            
            outliers = []
            for i, value in enumerate(values):
                if value < lower_bound or value > upper_bound:
                    outliers.append(i)
            
            return outliers
            
        except Exception as e:
            logger.error(f"IQR 이상치 탐지 중 에러 발생: {e}")
            return []
    
    def _detect_outliers_zscore(self, values: List[float], threshold: float = 3.0) -> List[int]:
        """Z-score 방법으로 이상치 탐지"""
        try:
            mean_value = mean(values)
            std_value = stdev(values) if len(values) > 1 else 0.0
            
            if std_value == 0:
                return []
            
            outliers = []
            for i, value in enumerate(values):
                z_score = abs((value - mean_value) / std_value)
                if z_score > threshold:
                    outliers.append(i)
            
            return outliers
            
        except Exception as e:
            logger.error(f"Z-score 이상치 탐지 중 에러 발생: {e}")
            return []
    
    def _detect_outliers_modified_zscore(self, values: List[float], threshold: float = 3.5) -> List[int]:
        """Modified Z-score 방법으로 이상치 탐지"""
        try:
            median_value = median(values)
            mad = median([abs(x - median_value) for x in values])
            
            if mad == 0:
                return []
            
            outliers = []
            for i, value in enumerate(values):
                modified_z_score = 0.6745 * (value - median_value) / mad
                if abs(modified_z_score) > threshold:
                    outliers.append(i)
            
            return outliers
            
        except Exception as e:
            logger.error(f"Modified Z-score 이상치 탐지 중 에러 발생: {e}")
            return []
    
    def get_calculation_summary(self) -> Dict[str, Any]:
        """계산기 설정 및 통계 요약 반환"""
        return {
            "algorithm_version": self.config.algorithm_version,
            "trend_threshold": self.config.analysis.trend_threshold_percent,
            "significant_threshold": self.config.analysis.significant_threshold_percent,
            "highly_significant_threshold": self.config.analysis.highly_significant_threshold_percent,
            "use_sample_std": self.config.analysis.use_sample_std,
            "rsd_calculation_method": self.config.analysis.rsd_calculation_method,
            "default_confidence": self.config.analysis.default_confidence,
            "outlier_detection_enabled": self.config.validation.outlier_detection_enabled,
            "outlier_iqr_multiplier": self.config.validation.outlier_iqr_multiplier
        }


# 전역 계산기 인스턴스
calculator = PEGCalculator()

# 편의 함수들
def calculate_statistics(values: List[float]) -> StatisticalResult:
    """전역 계산기를 사용한 통계 계산"""
    return calculator.calculate_statistics(values)

def compare_periods(n1_values: List[float], n_values: List[float]) -> ComparisonResult:
    """전역 계산기를 사용한 기간 비교"""
    return calculator.compare_periods(n1_values, n_values)

def calculate_weighted_average_change(peg_results: List[Dict[str, Any]]) -> float:
    """전역 계산기를 사용한 가중 평균 변화율 계산"""
    return calculator.calculate_weighted_average_change(peg_results)

def get_calculation_summary() -> Dict[str, Any]:
    """계산기 요약 정보 반환"""
    return calculator.get_calculation_summary()

# 모듈 초기화 로그
logger.info("PEG 비교분석 통계 계산 모듈이 성공적으로 로드되었습니다")




