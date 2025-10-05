"""
PEG (Performance Event Group) 처리 서비스

이 모듈은 PEG 데이터의 집계, 파생 PEG 계산, 수식 평가 등을 담당하는
PEGCalculator 클래스를 제공합니다.

기존 main.py의 _safe_eval_expr() 및 compute_derived_pegs_for_period()
로직을 모듈화한 것입니다.
"""

from __future__ import annotations

import ast
import logging
import math
import os

# 임시로 절대 import 사용 (나중에 패키지 구조 정리 시 수정)
import sys
from typing import Any, Dict, List, Optional, Union

from ..exceptions import ServiceError
from ..models import AggregatedPEGData, PEGConfig, PEGData, TimeRange

# 로깅 설정
logger = logging.getLogger(__name__)


class PEGCalculationError(ServiceError):
    """
    PEG 계산 관련 오류 예외 클래스

    PEG 집계, 파생 PEG 계산, 수식 평가 중 발생하는 오류를 처리합니다.
    """

    def __init__(
        self,
        message: str,
        details: Optional[Union[str, Dict[str, Any]]] = None,
        peg_name: Optional[str] = None,
        formula: Optional[str] = None,
        variables: Optional[Dict[str, float]] = None,
    ) -> None:
        """
        PEGCalculationError 초기화

        Args:
            message (str): 오류 메시지
            details (Optional[Union[str, Dict[str, Any]]]): 추가 상세 정보
            peg_name (Optional[str]): 계산 실패한 PEG 이름
            formula (Optional[str]): 실패한 수식
            variables (Optional[Dict[str, float]]): 수식 평가 시 사용된 변수들
        """
        super().__init__(message=message, details=details, service_name="PEGCalculator", operation="calculate_peg")
        self.peg_name = peg_name
        self.formula = formula
        self.variables = variables or {}

        logger.error("PEGCalculationError 발생: %s (PEG: %s, 수식: %s)", message, peg_name, formula)

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리 형태로 변환"""
        data = super().to_dict()
        data.update({"peg_name": self.peg_name, "formula": self.formula, "variables": self.variables})
        return data


class PEGCalculator:
    """
    PEG (Performance Event Group) 계산기 클래스

    기존 main.py의 PEG 계산 로직을 모듈화하여 재사용 가능하고
    테스트 가능한 형태로 제공합니다.

    주요 기능:
    1. 원시 PEG 데이터 집계 (합계, 평균 등)
    2. 파생 PEG 계산 (사용자 정의 수식)
    3. 안전한 수식 평가 (AST 기반)
    4. 오류 처리 (0으로 나누기, 누락 변수 등)
    """

    def __init__(self, peg_config: Optional[PEGConfig] = None):
        """
        PEGCalculator 초기화

        Args:
            peg_config (Optional[PEGConfig]): PEG 설정 (파생 PEG 정의 포함)
        """
        self.peg_config = peg_config or PEGConfig()

        # 지원하는 집계 방법들
        self.supported_aggregations = {
            "sum": sum,
            "average": lambda values: sum(values) / len(values) if values else 0.0,
            "mean": lambda values: sum(values) / len(values) if values else 0.0,
            "min": min,
            "max": max,
            "count": len,
        }

        logger.info("PEGCalculator 초기화 완료: 파생 PEG %d개", len(self.peg_config.peg_definitions))

    def get_supported_aggregations(self) -> List[str]:
        """지원하는 집계 방법 목록 반환"""
        return list(self.supported_aggregations.keys())

    def has_derived_pegs(self) -> bool:
        """파생 PEG가 정의되어 있는지 확인"""
        return self.peg_config.has_derived_pegs()

    def get_derived_peg_names(self) -> List[str]:
        """파생 PEG 이름 목록 반환"""
        return list(self.peg_config.peg_definitions.keys())

    def validate_formula_syntax(self, formula: str) -> bool:
        """수식 구문이 유효한지 검증"""
        try:
            ast.parse(formula, mode="eval")
            return True
        except SyntaxError:
            return False

    def aggregate_peg_data(
        self, peg_data_list: List[PEGData], time_range: TimeRange, aggregation_method: str = "average"
    ) -> Dict[str, AggregatedPEGData]:
        """
        원시 PEG 데이터를 집계하여 AggregatedPEGData 객체들을 생성

        Args:
            peg_data_list (List[PEGData]): 원시 PEG 데이터 목록
            time_range (TimeRange): 집계 대상 시간 범위
            aggregation_method (str): 집계 방법 ('average', 'sum', 'min', 'max', 'count')

        Returns:
            Dict[str, AggregatedPEGData]: PEG 이름별 집계된 데이터

        Raises:
            PEGCalculationError: 집계 처리 중 오류 발생 시
        """
        logger.info("aggregate_peg_data() 호출: 데이터 %d개, 집계방법=%s", len(peg_data_list), aggregation_method)

        if aggregation_method not in self.supported_aggregations:
            raise PEGCalculationError(
                f"지원되지 않는 집계 방법: {aggregation_method}",
                details={"supported": self.get_supported_aggregations()},
            )

        # PEG 이름별로 데이터 그룹화
        peg_groups: Dict[str, List[float]] = {}

        for peg_data in peg_data_list:
            # 시간 범위 내 데이터만 처리
            if not time_range.contains(peg_data.timestamp):
                logger.debug("시간 범위 밖 데이터 제외: %s at %s", peg_data.peg_name, peg_data.timestamp)
                continue

            if not peg_data.is_valid_value():
                logger.warning("유효하지 않은 PEG 값 건너뜀: %s = %s", peg_data.peg_name, peg_data.value)
                continue

            if peg_data.peg_name not in peg_groups:
                peg_groups[peg_data.peg_name] = []

            peg_groups[peg_data.peg_name].append(peg_data.value)

        # 집계 함수 선택
        aggregation_func = self.supported_aggregations[aggregation_method]

        # 집계 실행
        aggregated_results = {}

        for peg_name, values in peg_groups.items():
            try:
                if not values:
                    logger.warning("PEG %s의 유효한 데이터가 없음", peg_name)
                    continue

                # 집계 계산
                if aggregation_method in ["min", "max"] and len(values) == 0:
                    avg_value = min_value = max_value = 0.0
                else:
                    avg_value = aggregation_func(values)
                    min_value = min(values) if values else 0.0
                    max_value = max(values) if values else 0.0

                # AggregatedPEGData 객체 생성
                aggregated_data = AggregatedPEGData(
                    peg_name=peg_name,
                    avg_value=avg_value,
                    min_value=min_value,
                    max_value=max_value,
                    count=len(values),
                    time_range=time_range,
                    is_derived=False,
                )

                aggregated_results[peg_name] = aggregated_data
                logger.debug("PEG 집계 완료: %s = %.2f (개수: %d)", peg_name, avg_value, len(values))

            except Exception as e:
                raise PEGCalculationError(
                    f"PEG 집계 중 오류 발생: {peg_name}",
                    details={"values_count": len(values), "aggregation": aggregation_method},
                    peg_name=peg_name,
                ) from e

        logger.info("aggregate_peg_data() 완료: %d개 PEG 집계", len(aggregated_results))
        return aggregated_results

    def safe_eval_formula(self, formula: str, variables: Dict[str, float]) -> float:
        """
        안전한 수식 평가 (기존 _safe_eval_expr 로직)

        허용 연산: 숫자, 변수명(peg_name), +, -, *, /, (, ), 단항 +/-
        변수값은 variables 딕셔너리에서 가져옵니다.

        Args:
            formula (str): 평가할 수식
            variables (Dict[str, float]): 변수명과 값의 매핑

        Returns:
            float: 계산 결과 (오류 시 NaN)
        """
        logger.debug("safe_eval_formula() 호출: formula=%s, variables=%s", formula, list(variables.keys()))

        try:
            node = ast.parse(formula, mode="eval")

            def _eval(node):
                """내부 AST 노드 평가 함수"""
                if isinstance(node, ast.Expression):
                    return _eval(node.body)

                if isinstance(node, ast.BinOp):
                    left = _eval(node.left)
                    right = _eval(node.right)

                    if isinstance(node.op, ast.Add):
                        return float(left) + float(right)
                    if isinstance(node.op, ast.Sub):
                        return float(left) - float(right)
                    if isinstance(node.op, ast.Mult):
                        return float(left) * float(right)
                    if isinstance(node.op, ast.Div):
                        return float(left) / float(right)

                    raise ValueError("허용되지 않은 연산자")

                if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
                    operand = _eval(node.operand)
                    return +float(operand) if isinstance(node.op, ast.UAdd) else -float(operand)

                # ast.Num은 Python 3.8에서 deprecated되어 ast.Constant로 대체됨

                if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                    return float(node.value)

                if isinstance(node, ast.Name):
                    name = node.id
                    if name not in variables:
                        raise KeyError(f"정의되지 않은 변수: {name}")
                    return float(variables[name])

                # 보안: 허용되지 않은 AST 노드들
                if isinstance(node, ast.Call):
                    raise ValueError("함수 호출은 허용되지 않습니다")
                if isinstance(node, (ast.Attribute, ast.Subscript, ast.List, ast.Dict, ast.Tuple)):
                    raise ValueError("허용되지 않은 표현식 형식")

                raise ValueError("지원되지 않는 AST 노드")

            result = float(_eval(node))
            logger.debug("수식 평가 성공: %s = %s", formula, result)
            return result

        except ZeroDivisionError:
            logger.warning("수식 평가 중 0으로 나눔 발생: %s", formula)
            return float("nan")
        except KeyError as e:
            logger.error("수식 평가 실패 (누락 변수): %s (formula=%s)", e, formula)
            return float("nan")
        except Exception as e:
            logger.error("수식 평가 실패: %s (formula=%s)", e, formula)
            return float("nan")

    def calculate_derived_pegs(
        self, aggregated_pegs: Dict[str, AggregatedPEGData], time_range: TimeRange, period_label: str = ""
    ) -> Dict[str, AggregatedPEGData]:
        """
        파생 PEG 계산 (기존 compute_derived_pegs_for_period 로직)

        Args:
            aggregated_pegs (Dict[str, AggregatedPEGData]): 기본 PEG 집계 결과
            time_range (TimeRange): 시간 범위
            period_label (str): 기간 라벨 (N-1, N 등)

        Returns:
            Dict[str, AggregatedPEGData]: 파생 PEG 계산 결과

        Raises:
            PEGCalculationError: 파생 PEG 계산 중 오류 발생 시
        """
        logger.info(
            "calculate_derived_pegs() 호출: period=%s, 기본PEG=%d개, 파생정의=%d개",
            period_label,
            len(aggregated_pegs),
            len(self.peg_config.peg_definitions),
        )

        if not self.has_derived_pegs():
            logger.debug("파생 PEG 정의가 없음, 빈 결과 반환")
            return {}

        # 변수 맵 구성 (PEG 이름 → 평균값)
        variables = {}
        for peg_name, agg_data in aggregated_pegs.items():
            variables[peg_name] = agg_data.avg_value

        logger.debug("수식 평가용 변수 맵: %s", list(variables.keys()))

        # 파생 PEG 계산 결과
        derived_results = {}

        for derived_name, formula in self.peg_config.peg_definitions.items():
            try:
                logger.debug("파생 PEG 계산 시작: %s = %s", derived_name, formula)

                # 수식 평가
                calculated_value = self.safe_eval_formula(formula, variables)

                # NaN 체크
                if math.isnan(calculated_value):
                    logger.warning("파생 PEG 계산 결과가 NaN: %s (수식: %s)", derived_name, formula)
                    continue

                # AggregatedPEGData 객체 생성
                derived_data = AggregatedPEGData(
                    peg_name=derived_name,
                    avg_value=calculated_value,
                    min_value=calculated_value,  # 파생 PEG는 단일 값
                    max_value=calculated_value,
                    count=1,  # 파생 PEG는 계산된 단일 값
                    time_range=time_range,
                    is_derived=True,
                    formula=formula,
                )

                derived_results[derived_name] = derived_data

                # 계산된 파생 PEG를 변수 맵에 추가 (연쇄 계산 지원)
                variables[derived_name] = calculated_value

                logger.info("파생 PEG 계산 완료: %s = %.2f (수식: %s)", derived_name, calculated_value, formula)

            except Exception as e:
                logger.error("파생 PEG 계산 실패: %s (수식: %s, 오류: %s)", derived_name, formula, e)
                # 개별 파생 PEG 실패는 전체 처리를 중단하지 않음
                continue

        logger.info("calculate_derived_pegs() 완료: %d개 파생 PEG 계산", len(derived_results))
        return derived_results

    def calculate_all_pegs(
        self,
        peg_data_list: List[PEGData],
        time_range: TimeRange,
        aggregation_method: str = "average",
        period_label: str = "",
    ) -> Dict[str, AggregatedPEGData]:
        """
        원시 PEG 집계 + 파생 PEG 계산을 한 번에 수행

        Args:
            peg_data_list (List[PEGData]): 원시 PEG 데이터 목록
            time_range (TimeRange): 집계 대상 시간 범위
            aggregation_method (str): 집계 방법
            period_label (str): 기간 라벨

        Returns:
            Dict[str, AggregatedPEGData]: 기본 PEG + 파생 PEG 전체 결과
        """
        logger.info(
            "calculate_all_pegs() 호출: 데이터=%d개, 방법=%s, 기간=%s",
            len(peg_data_list),
            aggregation_method,
            period_label,
        )

        # 1단계: 원시 PEG 데이터 집계
        aggregated_pegs = self.aggregate_peg_data(peg_data_list, time_range, aggregation_method)

        # 2단계: 파생 PEG 계산
        if self.has_derived_pegs():
            derived_pegs = self.calculate_derived_pegs(aggregated_pegs, time_range, period_label)

            # 결과 병합
            aggregated_pegs.update(derived_pegs)

            logger.info(
                "전체 PEG 계산 완료: 기본=%d개, 파생=%d개", len(aggregated_pegs) - len(derived_pegs), len(derived_pegs)
            )
        else:
            logger.info("전체 PEG 계산 완료: 기본=%d개 (파생 PEG 없음)", len(aggregated_pegs))

        return aggregated_pegs

    def validate_required_variables(self, formula: str, available_variables: Dict[str, float]) -> List[str]:
        """
        수식에 필요한 변수들이 모두 사용 가능한지 확인

        Args:
            formula (str): 검증할 수식
            available_variables (Dict[str, float]): 사용 가능한 변수들

        Returns:
            List[str]: 누락된 변수 이름 목록 (빈 리스트면 모든 변수 사용 가능)
        """
        try:
            node = ast.parse(formula, mode="eval")
            required_vars = set()

            def _collect_names(node):
                """AST에서 변수명 수집"""
                if isinstance(node, ast.Name):
                    required_vars.add(node.id)
                elif hasattr(node, "_fields"):
                    for field in node._fields:
                        value = getattr(node, field, None)
                        if isinstance(value, list):
                            for item in value:
                                if isinstance(item, ast.AST):
                                    _collect_names(item)
                        elif isinstance(value, ast.AST):
                            _collect_names(value)

            _collect_names(node)

            # 누락된 변수 확인
            missing_vars = [var for var in required_vars if var not in available_variables]

            if missing_vars:
                logger.warning("수식 %s에 필요한 변수 누락: %s", formula, missing_vars)

            return missing_vars

        except Exception as e:
            logger.error("수식 변수 분석 실패: %s (formula=%s)", e, formula)
            return [f"분석_실패_{e}"]

    def get_calculation_statistics(self) -> Dict[str, Any]:
        """계산 통계 정보 반환"""
        return {
            "derived_peg_count": len(self.peg_config.peg_definitions),
            "supported_aggregations": self.get_supported_aggregations(),
            "has_derived_pegs": self.has_derived_pegs(),
            "derived_peg_names": self.get_derived_peg_names(),
        }
