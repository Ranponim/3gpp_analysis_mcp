"""
PEG 비교분석 데이터 검증 및 전처리 모듈

이 모듈은 PEG(Performance Engineering Guidelines) 비교분석에 필요한
입력 데이터의 검증, 전처리, 이상치 탐지 및 처리 기능을 제공합니다.

Author: KPI Dashboard Team
Created: 2024-01-15
Version: 1.0.0
"""

import logging
import math
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass
from enum import Enum
import re
from datetime import datetime

# 로컬 모듈 임포트
from ..config.peg_comparison_config import get_config
from ..exceptions.error_handler import ErrorHandler, ErrorType, ErrorSeverity, PEGComparisonError
from ..models.peg_comparison import PEGComparisonRequest, PEGDataPoint, PEGDefinition

# 로거 설정
logger = logging.getLogger(__name__)


class ValidationResult(Enum):
    """검증 결과 열거형"""
    VALID = "valid"
    WARNING = "warning"
    ERROR = "error"


class DataQualityLevel(Enum):
    """데이터 품질 레벨 열거형"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class ValidationReport:
    """검증 보고서 데이터 클래스"""
    is_valid: bool
    quality_level: DataQualityLevel
    warnings: List[str]
    errors: List[str]
    processed_data: Dict[str, Any]
    statistics: Dict[str, Any]
    
    def __post_init__(self):
        """초기화 후 처리"""
        if not self.warnings:
            self.warnings = []
        if not self.errors:
            self.errors = []


@dataclass
class DataQualityMetrics:
    """데이터 품질 메트릭 데이터 클래스"""
    total_records: int
    valid_records: int
    invalid_records: int
    missing_fields: int
    outliers_detected: int
    duplicates_removed: int
    quality_score: float  # 0.0-1.0
    
    def __post_init__(self):
        """초기화 후 처리"""
        if self.total_records > 0:
            self.quality_score = self.valid_records / self.total_records
        else:
            self.quality_score = 0.0


class DataValidator:
    """
    PEG 비교분석 데이터 검증 및 전처리 클래스
    
    입력 데이터의 검증, 전처리, 이상치 탐지 및 처리 기능을 제공합니다.
    """
    
    def __init__(self):
        """검증기 초기화"""
        self.config = get_config()
        self.error_handler = ErrorHandler()
        
        # 검증 규칙 초기화
        self._initialize_validation_rules()
        
        logger.info("PEG 데이터 검증기 초기화 완료")
    
    def _initialize_validation_rules(self):
        """검증 규칙 초기화"""
        self.validation_rules = {
            'kpi_name': {
                'required': True,
                'type': str,
                'min_length': 1,
                'max_length': 100,
                'pattern': r'^[a-zA-Z0-9_\-\.]+$'
            },
            'period': {
                'required': True,
                'type': str,
                'allowed_values': ['N-1', 'N']
            },
            'avg': {
                'required': True,
                'type': (int, float),
                'min_value': self.config.validation.min_avg_value,
                'max_value': self.config.validation.max_avg_value
            },
            'cell_id': {
                'required': True,
                'type': str,
                'min_length': 1,
                'max_length': 50,
                'pattern': r'^[a-zA-Z0-9_\-]+$'
            }
        }
        
        logger.debug(f"검증 규칙 {len(self.validation_rules)}개 초기화 완료")
    
    def validate_and_preprocess(self, raw_data: Dict[str, Any]) -> ValidationReport:
        """
        데이터 검증 및 전처리
        
        Args:
            raw_data: 원시 입력 데이터
        
        Returns:
            ValidationReport: 검증 보고서
        """
        logger.info("데이터 검증 및 전처리 시작")
        
        try:
            # 1. 기본 구조 검증
            self._validate_basic_structure(raw_data)
            
            # 2. 데이터 추출 및 정제
            processed_data = self._extract_and_clean_data(raw_data)
            
            # 3. 개별 레코드 검증
            validation_results = self._validate_individual_records(processed_data)
            
            # 4. 데이터 품질 평가
            quality_metrics = self._assess_data_quality(processed_data, validation_results)
            
            # 5. 이상치 탐지 및 처리
            cleaned_data = self._detect_and_handle_outliers(processed_data)
            
            # 6. 중복 제거
            final_data = self._remove_duplicates(cleaned_data)
            
            # 7. 최종 검증 보고서 생성
            report = self._generate_validation_report(
                final_data, validation_results, quality_metrics
            )
            
            logger.info(f"데이터 검증 및 전처리 완료: 품질={report.quality_level.value}")
            return report
            
        except Exception as e:
            logger.error(f"데이터 검증 및 전처리 중 에러 발생: {e}")
            error_context = self.error_handler.handle_error(
                e,
                context={
                    "function": "validate_and_preprocess",
                    "data_keys": list(raw_data.keys()) if raw_data else []
                }
            )
            raise PEGComparisonError(
                message=f"데이터 검증 및 전처리 실패: {str(e)}",
                error_type=ErrorType.DATA_VALIDATION_ERROR,
                severity=ErrorSeverity.HIGH,
                details=error_context.details
            )
    
    def _validate_basic_structure(self, raw_data: Dict[str, Any]) -> None:
        """기본 데이터 구조 검증"""
        logger.debug("기본 데이터 구조 검증 시작")
        
        # 필수 키 존재 여부 확인
        required_keys = ['stats', 'peg_definitions']
        for key in required_keys:
            if key not in raw_data:
                raise PEGComparisonError(
                    message=f"필수 키 '{key}'가 누락되었습니다",
                    error_type=ErrorType.DATA_VALIDATION_ERROR,
                    severity=ErrorSeverity.HIGH,
                    details={"missing_key": key, "available_keys": list(raw_data.keys())}
                )
        
        # stats 배열 검증
        stats = raw_data.get('stats', [])
        if not isinstance(stats, list):
            raise PEGComparisonError(
                message="'stats'는 배열이어야 합니다",
                error_type=ErrorType.DATA_VALIDATION_ERROR,
                severity=ErrorSeverity.HIGH,
                details={"stats_type": type(stats).__name__}
            )
        
        if not stats:
            raise PEGComparisonError(
                message="'stats' 배열이 비어있습니다",
                error_type=ErrorType.DATA_VALIDATION_ERROR,
                severity=ErrorSeverity.HIGH,
                details={"stats_count": 0}
            )
        
        # peg_definitions 검증
        peg_definitions = raw_data.get('peg_definitions', {})
        if not isinstance(peg_definitions, dict):
            raise PEGComparisonError(
                message="'peg_definitions'는 딕셔너리여야 합니다",
                error_type=ErrorType.DATA_VALIDATION_ERROR,
                severity=ErrorSeverity.HIGH,
                details={"peg_definitions_type": type(peg_definitions).__name__}
            )
        
        if not peg_definitions:
            raise PEGComparisonError(
                message="'peg_definitions'가 비어있습니다",
                error_type=ErrorType.DATA_VALIDATION_ERROR,
                severity=ErrorSeverity.HIGH,
                details={"peg_definitions_count": 0}
            )
        
        logger.debug(f"기본 구조 검증 완료: stats={len(stats)}개, peg_definitions={len(peg_definitions)}개")
    
    def _extract_and_clean_data(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """데이터 추출 및 정제"""
        logger.debug("데이터 추출 및 정제 시작")
        
        try:
            # stats 데이터 정제
            cleaned_stats = []
            for i, stat in enumerate(raw_data.get('stats', [])):
                if not isinstance(stat, dict):
                    logger.warning(f"stats[{i}]가 딕셔너리가 아님: {type(stat).__name__}")
                    continue
                
                cleaned_stat = {}
                for field, value in stat.items():
                    # 문자열 필드 정제
                    if field in ['kpi_name', 'period', 'cell_id'] and isinstance(value, str):
                        cleaned_stat[field] = value.strip()
                    else:
                        cleaned_stat[field] = value
                
                cleaned_stats.append(cleaned_stat)
            
            # peg_definitions 정제
            cleaned_peg_definitions = {}
            for peg_name, definition in raw_data.get('peg_definitions', {}).items():
                if not isinstance(definition, dict):
                    logger.warning(f"PEG 정의 '{peg_name}'가 딕셔너리가 아님")
                    continue
                
                cleaned_definition = {}
                for key, value in definition.items():
                    if key == 'weight' and isinstance(value, (int, float)):
                        cleaned_definition[key] = int(value)
                    elif key == 'thresholds' and isinstance(value, dict):
                        cleaned_definition[key] = value
                    else:
                        cleaned_definition[key] = value
                
                cleaned_peg_definitions[peg_name.strip()] = cleaned_definition
            
            processed_data = {
                'stats': cleaned_stats,
                'peg_definitions': cleaned_peg_definitions,
                'options': raw_data.get('options', {})
            }
            
            logger.debug(f"데이터 추출 및 정제 완료: stats={len(cleaned_stats)}개, peg_definitions={len(cleaned_peg_definitions)}개")
            return processed_data
            
        except Exception as e:
            logger.error(f"데이터 추출 및 정제 중 에러 발생: {e}")
            raise PEGComparisonError(
                message=f"데이터 추출 및 정제 실패: {str(e)}",
                error_type=ErrorType.DATA_PROCESSING_ERROR,
                severity=ErrorSeverity.MEDIUM,
                details={"function": "_extract_and_clean_data"}
            )
    
    def _validate_individual_records(self, processed_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """개별 레코드 검증"""
        logger.debug("개별 레코드 검증 시작")
        
        validation_results = []
        stats = processed_data.get('stats', [])
        
        for i, stat in enumerate(stats):
            record_validation = {
                'index': i,
                'is_valid': True,
                'warnings': [],
                'errors': [],
                'data': stat
            }
            
            # 각 필드별 검증
            for field, rules in self.validation_rules.items():
                field_value = stat.get(field)
                
                # 필수 필드 검증
                if rules.get('required', False) and field_value is None:
                    record_validation['errors'].append(f"필수 필드 '{field}'가 누락되었습니다")
                    record_validation['is_valid'] = False
                    continue
                
                if field_value is None:
                    continue
                
                # 타입 검증
                expected_type = rules.get('type')
                if expected_type and not isinstance(field_value, expected_type):
                    record_validation['errors'].append(f"필드 '{field}'의 타입이 올바르지 않습니다 (예상: {expected_type.__name__}, 실제: {type(field_value).__name__})")
                    record_validation['is_valid'] = False
                    continue
                
                # 문자열 길이 검증
                if isinstance(field_value, str):
                    min_length = rules.get('min_length')
                    max_length = rules.get('max_length')
                    
                    if min_length and len(field_value) < min_length:
                        record_validation['errors'].append(f"필드 '{field}'의 길이가 너무 짧습니다 (최소: {min_length})")
                        record_validation['is_valid'] = False
                    
                    if max_length and len(field_value) > max_length:
                        record_validation['errors'].append(f"필드 '{field}'의 길이가 너무 깁니다 (최대: {max_length})")
                        record_validation['is_valid'] = False
                    
                    # 패턴 검증
                    pattern = rules.get('pattern')
                    if pattern and not re.match(pattern, field_value):
                        record_validation['warnings'].append(f"필드 '{field}'의 형식이 표준과 다릅니다")
                
                # 숫자 범위 검증
                elif isinstance(field_value, (int, float)):
                    min_value = rules.get('min_value')
                    max_value = rules.get('max_value')
                    
                    if min_value is not None and field_value < min_value:
                        record_validation['errors'].append(f"필드 '{field}'의 값이 너무 작습니다 (최소: {min_value})")
                        record_validation['is_valid'] = False
                    
                    if max_value is not None and field_value > max_value:
                        record_validation['errors'].append(f"필드 '{field}'의 값이 너무 큽니다 (최대: {max_value})")
                        record_validation['is_valid'] = False
                
                # 허용된 값 검증
                allowed_values = rules.get('allowed_values')
                if allowed_values and field_value not in allowed_values:
                    record_validation['errors'].append(f"필드 '{field}'의 값이 허용되지 않습니다 (허용값: {allowed_values})")
                    record_validation['is_valid'] = False
            
            validation_results.append(record_validation)
        
        # 검증 결과 통계
        valid_count = sum(1 for r in validation_results if r['is_valid'])
        error_count = sum(1 for r in validation_results if not r['is_valid'])
        warning_count = sum(len(r['warnings']) for r in validation_results)
        
        logger.debug(f"개별 레코드 검증 완료: 유효={valid_count}개, 오류={error_count}개, 경고={warning_count}개")
        return validation_results
    
    def _assess_data_quality(self, processed_data: Dict[str, Any], validation_results: List[Dict[str, Any]]) -> DataQualityMetrics:
        """데이터 품질 평가"""
        logger.debug("데이터 품질 평가 시작")
        
        try:
            stats = processed_data.get('stats', [])
            total_records = len(stats)
            valid_records = sum(1 for r in validation_results if r['is_valid'])
            invalid_records = total_records - valid_records
            
            # 누락된 필드 수 계산
            missing_fields = 0
            for result in validation_results:
                for error in result['errors']:
                    if '누락' in error:
                        missing_fields += 1
            
            # 중복 레코드 탐지
            seen_records = set()
            duplicates = 0
            for stat in stats:
                record_key = (stat.get('kpi_name'), stat.get('period'), stat.get('cell_id'))
                if record_key in seen_records:
                    duplicates += 1
                else:
                    seen_records.add(record_key)
            
            # 이상치 탐지 (간단한 통계적 방법)
            outliers_detected = 0
            if self.config.validation.outlier_detection_enabled:
                # PEG별로 그룹화하여 이상치 탐지
                peg_groups = {}
                for stat in stats:
                    kpi_name = stat.get('kpi_name')
                    if kpi_name not in peg_groups:
                        peg_groups[kpi_name] = []
                    peg_groups[kpi_name].append(stat.get('avg', 0))
                
                for kpi_name, values in peg_groups.items():
                    if len(values) >= self.config.validation.min_data_points_for_outlier:
                        outliers = self._detect_outliers_simple(values)
                        outliers_detected += len(outliers)
            
            metrics = DataQualityMetrics(
                total_records=total_records,
                valid_records=valid_records,
                invalid_records=invalid_records,
                missing_fields=missing_fields,
                outliers_detected=outliers_detected,
                duplicates_removed=duplicates
            )
            
            logger.debug(f"데이터 품질 평가 완료: 품질 점수={metrics.quality_score:.3f}")
            return metrics
            
        except Exception as e:
            logger.error(f"데이터 품질 평가 중 에러 발생: {e}")
            # 기본값 반환
            return DataQualityMetrics(
                total_records=len(processed_data.get('stats', [])),
                valid_records=0,
                invalid_records=0,
                missing_fields=0,
                outliers_detected=0,
                duplicates_removed=0
            )
    
    def _detect_outliers_simple(self, values: List[float]) -> List[int]:
        """간단한 이상치 탐지 (IQR 방법)"""
        try:
            if len(values) < 3:
                return []
            
            sorted_values = sorted(values)
            n = len(sorted_values)
            
            q1_idx = n // 4
            q3_idx = 3 * n // 4
            
            q1 = sorted_values[q1_idx]
            q3 = sorted_values[q3_idx]
            iqr = q3 - q1
            
            if iqr == 0:
                return []
            
            multiplier = self.config.validation.outlier_iqr_multiplier
            lower_bound = q1 - multiplier * iqr
            upper_bound = q3 + multiplier * iqr
            
            outliers = []
            for i, value in enumerate(values):
                if value < lower_bound or value > upper_bound:
                    outliers.append(i)
            
            return outliers
            
        except Exception as e:
            logger.error(f"이상치 탐지 중 에러 발생: {e}")
            return []
    
    def _detect_and_handle_outliers(self, processed_data: Dict[str, Any]) -> Dict[str, Any]:
        """이상치 탐지 및 처리"""
        logger.debug("이상치 탐지 및 처리 시작")
        
        if not self.config.validation.outlier_detection_enabled:
            logger.debug("이상치 탐지가 비활성화되어 있음")
            return processed_data
        
        try:
            stats = processed_data.get('stats', [])
            cleaned_stats = []
            outliers_handled = 0
            
            # PEG별로 그룹화
            peg_groups = {}
            for i, stat in enumerate(stats):
                kpi_name = stat.get('kpi_name')
                if kpi_name not in peg_groups:
                    peg_groups[kpi_name] = []
                peg_groups[kpi_name].append((i, stat))
            
            # 각 PEG 그룹에서 이상치 처리
            for kpi_name, group_data in peg_groups.items():
                if len(group_data) < self.config.validation.min_data_points_for_outlier:
                    # 데이터가 충분하지 않으면 그대로 유지
                    cleaned_stats.extend([data for _, data in group_data])
                    continue
                
                # 값 추출
                values = [data.get('avg', 0) for _, data in group_data]
                outliers = self._detect_outliers_simple(values)
                
                if outliers:
                    logger.info(f"PEG '{kpi_name}'에서 {len(outliers)}개 이상치 발견")
                    
                    # 이상치를 중앙값으로 대체
                    median_value = sorted(values)[len(values) // 2]
                    
                    for i, (original_idx, data) in enumerate(group_data):
                        if i in outliers:
                            data['avg'] = median_value
                            outliers_handled += 1
                            logger.debug(f"이상치 대체: 인덱스 {original_idx}, 값 {values[i]} -> {median_value}")
                
                cleaned_stats.extend([data for _, data in group_data])
            
            processed_data['stats'] = cleaned_stats
            
            if outliers_handled > 0:
                logger.info(f"이상치 처리 완료: {outliers_handled}개 대체")
            
            return processed_data
            
        except Exception as e:
            logger.error(f"이상치 탐지 및 처리 중 에러 발생: {e}")
            return processed_data
    
    def _remove_duplicates(self, processed_data: Dict[str, Any]) -> Dict[str, Any]:
        """중복 레코드 제거"""
        logger.debug("중복 레코드 제거 시작")
        
        try:
            stats = processed_data.get('stats', [])
            seen_records = set()
            unique_stats = []
            duplicates_removed = 0
            
            for stat in stats:
                # 중복 판정 키 생성
                record_key = (
                    stat.get('kpi_name'),
                    stat.get('period'),
                    stat.get('cell_id')
                )
                
                if record_key in seen_records:
                    duplicates_removed += 1
                    logger.debug(f"중복 레코드 제거: {record_key}")
                else:
                    seen_records.add(record_key)
                    unique_stats.append(stat)
            
            processed_data['stats'] = unique_stats
            
            if duplicates_removed > 0:
                logger.info(f"중복 레코드 제거 완료: {duplicates_removed}개 제거")
            
            return processed_data
            
        except Exception as e:
            logger.error(f"중복 레코드 제거 중 에러 발생: {e}")
            return processed_data
    
    def _generate_validation_report(
        self,
        final_data: Dict[str, Any],
        validation_results: List[Dict[str, Any]],
        quality_metrics: DataQualityMetrics
    ) -> ValidationReport:
        """최종 검증 보고서 생성"""
        logger.debug("검증 보고서 생성 시작")
        
        try:
            # 경고 및 에러 수집
            all_warnings = []
            all_errors = []
            
            for result in validation_results:
                all_warnings.extend(result.get('warnings', []))
                all_errors.extend(result.get('errors', []))
            
            # 데이터 품질 레벨 결정
            if quality_metrics.quality_score >= 0.95:
                quality_level = DataQualityLevel.HIGH
            elif quality_metrics.quality_score >= 0.8:
                quality_level = DataQualityLevel.MEDIUM
            else:
                quality_level = DataQualityLevel.LOW
            
            # 검증 성공 여부 결정
            is_valid = len(all_errors) == 0 and quality_metrics.quality_score >= 0.7
            
            # 통계 정보 생성
            statistics = {
                "total_records": quality_metrics.total_records,
                "valid_records": quality_metrics.valid_records,
                "invalid_records": quality_metrics.invalid_records,
                "missing_fields": quality_metrics.missing_fields,
                "outliers_detected": quality_metrics.outliers_detected,
                "duplicates_removed": quality_metrics.duplicates_removed,
                "quality_score": quality_metrics.quality_score,
                "warnings_count": len(all_warnings),
                "errors_count": len(all_errors)
            }
            
            report = ValidationReport(
                is_valid=is_valid,
                quality_level=quality_level,
                warnings=all_warnings,
                errors=all_errors,
                processed_data=final_data,
                statistics=statistics
            )
            
            logger.info(f"검증 보고서 생성 완료: 유효={is_valid}, 품질={quality_level.value}")
            return report
            
        except Exception as e:
            logger.error(f"검증 보고서 생성 중 에러 발생: {e}")
            # 기본 보고서 반환
            return ValidationReport(
                is_valid=False,
                quality_level=DataQualityLevel.LOW,
                warnings=[],
                errors=[f"검증 보고서 생성 실패: {str(e)}"],
                processed_data=final_data,
                statistics={}
            )
    
    def validate_peg_definitions(self, peg_definitions: Dict[str, Any]) -> Dict[str, Any]:
        """PEG 정의 검증"""
        logger.debug(f"PEG 정의 검증 시작: {len(peg_definitions)}개 정의")
        
        try:
            validated_definitions = {}
            validation_errors = []
            
            for peg_name, definition in peg_definitions.items():
                if not isinstance(definition, dict):
                    validation_errors.append(f"PEG '{peg_name}' 정의가 딕셔너리가 아닙니다")
                    continue
                
                # 가중치 검증
                weight = definition.get('weight')
                if not isinstance(weight, (int, float)):
                    validation_errors.append(f"PEG '{peg_name}'의 가중치가 숫자가 아닙니다")
                    continue
                
                weight = int(weight)
                if not (self.config.validation.min_weight <= weight <= self.config.validation.max_weight):
                    validation_errors.append(f"PEG '{peg_name}'의 가중치가 범위를 벗어났습니다 ({self.config.validation.min_weight}-{self.config.validation.max_weight})")
                    continue
                
                # 임계값 검증
                thresholds = definition.get('thresholds', {})
                if not isinstance(thresholds, dict):
                    validation_errors.append(f"PEG '{peg_name}'의 임계값이 딕셔너리가 아닙니다")
                    continue
                
                if not thresholds:
                    validation_errors.append(f"PEG '{peg_name}'의 임계값이 비어있습니다")
                    continue
                
                # 임계값 값 검증
                for threshold_name, threshold_value in thresholds.items():
                    if not isinstance(threshold_value, (int, float)):
                        validation_errors.append(f"PEG '{peg_name}'의 임계값 '{threshold_name}'이 숫자가 아닙니다")
                        continue
                    
                    if threshold_value < 0:
                        validation_errors.append(f"PEG '{peg_name}'의 임계값 '{threshold_name}'이 음수입니다")
                        continue
                
                validated_definitions[peg_name] = {
                    'weight': weight,
                    'thresholds': thresholds
                }
            
            if validation_errors:
                logger.warning(f"PEG 정의 검증에서 {len(validation_errors)}개 오류 발견")
                for error in validation_errors:
                    logger.warning(f"  - {error}")
            
            logger.debug(f"PEG 정의 검증 완료: 유효={len(validated_definitions)}개, 오류={len(validation_errors)}개")
            return validated_definitions
            
        except Exception as e:
            logger.error(f"PEG 정의 검증 중 에러 발생: {e}")
            raise PEGComparisonError(
                message=f"PEG 정의 검증 실패: {str(e)}",
                error_type=ErrorType.DATA_VALIDATION_ERROR,
                severity=ErrorSeverity.MEDIUM,
                details={"function": "validate_peg_definitions"}
            )
    
    def get_validation_summary(self) -> Dict[str, Any]:
        """검증기 설정 및 통계 요약 반환"""
        return {
            "validation_rules": {
                field: {
                    "required": rules.get('required', False),
                    "type": rules.get('type', {}).__name__ if rules.get('type') else None,
                    "min_length": rules.get('min_length'),
                    "max_length": rules.get('max_length'),
                    "min_value": rules.get('min_value'),
                    "max_value": rules.get('max_value'),
                    "allowed_values": rules.get('allowed_values')
                }
                for field, rules in self.validation_rules.items()
            },
            "outlier_detection": {
                "enabled": self.config.validation.outlier_detection_enabled,
                "iqr_multiplier": self.config.validation.outlier_iqr_multiplier,
                "min_data_points": self.config.validation.min_data_points_for_outlier
            },
            "data_quality_thresholds": {
                "min_avg_value": self.config.validation.min_avg_value,
                "max_avg_value": self.config.validation.max_avg_value,
                "min_weight": self.config.validation.min_weight,
                "max_weight": self.config.validation.max_weight
            }
        }


# 전역 검증기 인스턴스
validator = DataValidator()

# 모듈 초기화 로그
logger.info("PEG 비교분석 데이터 검증 모듈이 성공적으로 로드되었습니다")


