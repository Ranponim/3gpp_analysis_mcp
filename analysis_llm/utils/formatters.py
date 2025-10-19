"""
Response Formatter

이 모듈은 분석 결과를 표준화된 응답 형식으로 변환하는
ResponseFormatter 클래스를 제공합니다.

AnalysisService의 복잡한 응답 구조를 AnalysisResponse 모델로 변환하고
다양한 출력 형식을 지원합니다.
"""

from __future__ import annotations

import json
import logging
import os

from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from ..models import AnalysisResponse, AnalysisStats, LLMAnalysisResult, PEGStatistics

# 로깅 설정
logger = logging.getLogger(__name__)


class ResponseFormattingError(Exception):
    """
    응답 포맷팅 관련 오류 예외 클래스

    ResponseFormatter에서 발생하는 오류를 처리합니다.
    """

    def __init__(
        self,
        message: str,
        details: Optional[Union[str, Dict[str, Any]]] = None,
        formatting_step: Optional[str] = None,
        input_context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        ResponseFormattingError 초기화

        Args:
            message (str): 오류 메시지
            details (Optional[Union[str, Dict[str, Any]]]): 추가 상세 정보
            formatting_step (Optional[str]): 실패한 포맷팅 단계
            input_context (Optional[Dict[str, Any]]): 입력 컨텍스트
        """
        super().__init__(message)
        self.message = message
        self.details = details
        self.formatting_step = formatting_step
        self.input_context = input_context

        logger.error("ResponseFormattingError 발생: %s (단계: %s)", message, formatting_step)

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리 형태로 변환"""
        return {
            "error_type": "ResponseFormattingError",
            "message": self.message,
            "details": self.details,
            "formatting_step": self.formatting_step,
            "input_context": self.input_context,
        }


class ResponseFormatter:
    """
    응답 포맷팅 클래스

    AnalysisService의 복잡한 응답 구조를 표준화된 AnalysisResponse 모델로 변환하고
    다양한 출력 형식을 지원합니다.

    주요 기능:
    1. AnalysisService 결과 → AnalysisResponse 변환
    2. 다양한 출력 형식 지원 (JSON, CSV, Excel 등)
    3. 오류 응답 표준화
    4. 백엔드 전송을 위한 형식 최적화
    """

    def __init__(self):
        """
        ResponseFormatter 초기화
        """
        self.logger = logging.getLogger(__name__ + ".ResponseFormatter")

        # 포맷팅 단계 정의
        self.formatting_steps = ["data_extraction", "model_conversion", "error_handling", "serialization"]

        # 지원하는 출력 형식
        self.supported_formats = ["json", "dict", "analysis_response"]

        self.logger.info("ResponseFormatter 초기화 완료")

    def get_formatter_info(self) -> Dict[str, Any]:
        """포맷터 정보 반환"""
        return {
            "formatter_name": "ResponseFormatter",
            "formatting_steps": self.formatting_steps,
            "supported_formats": self.supported_formats,
            "target_model": "AnalysisResponse",
        }

    def _extract_peg_statistics(self, peg_analysis: Dict[str, Any]) -> List[PEGStatistics]:
        """
        PEG 분석 결과에서 PEGStatistics 리스트 추출

        Args:
            peg_analysis (Dict[str, Any]): AnalysisService의 peg_analysis 섹션

        Returns:
            List[PEGStatistics]: 변환된 PEG 통계 리스트

        Raises:
            ResponseFormattingError: 추출 실패 시
        """
        self.logger.debug("_extract_peg_statistics() 호출: PEG 통계 추출")

        try:
            peg_statistics = []

            # AnalyzedPEGResult 리스트에서 PEGStatistics로 변환
            peg_results = peg_analysis.get("results", [])

            for result_dict in peg_results:
                # AnalyzedPEGResult 형식에서 PEGStatistics 형식으로 변환
                peg_name = result_dict.get("peg_name", "unknown")
                n_minus_1_value = result_dict.get("n_minus_1_value", 0.0) or 0.0
                n_value = result_dict.get("n_value", 0.0) or 0.0
                absolute_change = result_dict.get("absolute_change", 0.0) or 0.0
                percentage_change = result_dict.get("percentage_change", 0.0) or 0.0

                peg_stat = PEGStatistics(
                    peg_name=peg_name,
                    avg_n_minus_1=n_minus_1_value,
                    avg_n=n_value,
                    diff=absolute_change,
                    pct_change=percentage_change,
                    is_derived=False,  # 추후 파생 PEG 구분 로직 추가 가능
                )

                peg_statistics.append(peg_stat)

            self.logger.info("PEG 통계 추출 완료: %d개", len(peg_statistics))
            return peg_statistics

        except Exception as e:
            raise ResponseFormattingError(
                f"PEG 통계 추출 실패: {e}",
                formatting_step="data_extraction",
                input_context={"peg_analysis_keys": list(peg_analysis.keys())},
            ) from e

    def _extract_analysis_stats(self, data_summary: Dict[str, Any], metadata: Dict[str, Any]) -> AnalysisStats:
        """
        데이터 요약과 메타데이터에서 AnalysisStats 추출

        Args:
            data_summary (Dict[str, Any]): AnalysisService의 data_summary 섹션
            metadata (Dict[str, Any]): AnalysisService의 metadata 섹션

        Returns:
            AnalysisStats: 분석 통계

        Raises:
            ResponseFormattingError: 추출 실패 시
        """
        self.logger.debug("_extract_analysis_stats() 호출: 분석 통계 추출")

        try:
            # 기본값으로 AnalysisStats 생성
            total_pegs = data_summary.get("total_pegs", 0)
            processed_pegs = data_summary.get("complete_data_pegs", 0)
            derived_pegs = 0  # 추후 파생 PEG 카운트 로직 추가

            # 분석 소요 시간 (추정)
            analysis_duration = 0.0
            if "processing_timestamp" in metadata:
                # 간단한 추정 (실제로는 시작/종료 시간 필요)
                analysis_duration = 1.0  # 기본값

            # LLM 토큰 사용량 (추정)
            llm_tokens_used = 0
            # 추후 LLM 서비스에서 토큰 사용량 추출 가능

            analysis_stats = AnalysisStats(
                total_pegs=total_pegs,
                processed_pegs=processed_pegs,
                derived_pegs=derived_pegs,
                analysis_duration_seconds=analysis_duration,
                llm_tokens_used=llm_tokens_used,
            )

            self.logger.info("분석 통계 추출 완료: total=%d, processed=%d", total_pegs, processed_pegs)

            return analysis_stats

        except Exception as e:
            raise ResponseFormattingError(
                f"분석 통계 추출 실패: {e}",
                formatting_step="data_extraction",
                input_context={"data_summary_keys": list(data_summary.keys()), "metadata_keys": list(metadata.keys())},
            ) from e

    def _extract_llm_analysis_result(self, llm_analysis: Dict[str, Any]) -> Optional[LLMAnalysisResult]:
        """
        LLM 분석 결과에서 LLMAnalysisResult 추출

        Args:
            llm_analysis (Dict[str, Any]): AnalysisService의 llm_analysis 섹션

        Returns:
            Optional[LLMAnalysisResult]: LLM 분석 결과
        """
        self.logger.debug("_extract_llm_analysis_result() 호출: LLM 결과 추출")

        if not llm_analysis:
            self.logger.info("LLM 분석 결과가 없어 None 반환")
            return None

        try:
            # LLMAnalysisResult 형식으로 변환 (Enhanced 구조)
            executive_summary = llm_analysis.get("executive_summary", "")
            diagnostic_findings = llm_analysis.get("diagnostic_findings", [])
            recommended_actions = llm_analysis.get("recommended_actions", [])

            # 문자열로 변환 (LLMAnalysisResult 모델에 맞춤)
            if isinstance(diagnostic_findings, list):
                diagnostic_findings_str = "; ".join([str(finding) for finding in diagnostic_findings])
            else:
                diagnostic_findings_str = str(diagnostic_findings)

            if isinstance(recommended_actions, list):
                recommended_actions_str = "; ".join([str(action) for action in recommended_actions])
            else:
                recommended_actions_str = str(recommended_actions)

            llm_result = LLMAnalysisResult(
                integrated_analysis=executive_summary,
                specific_peg_analysis=diagnostic_findings_str,
                recommendations=recommended_actions_str,
                confidence_score=llm_analysis.get("confidence_score", 0.8),  # 기본값
                model_used=llm_analysis.get("model_used", "unknown"),
                tokens_used=llm_analysis.get("tokens_used", 0),
                analysis_timestamp=datetime.now(),
            )

            self.logger.info("LLM 결과 추출 완료: summary=%d자", len(summary))
            return llm_result

        except Exception as e:
            raise ResponseFormattingError(
                f"LLM 결과 추출 실패: {e}",
                formatting_step="data_extraction",
                input_context={"llm_analysis_keys": list(llm_analysis.keys())},
            ) from e

    def format_analysis_response(self, raw_analysis_output: Dict[str, Any]) -> AnalysisResponse:
        """
        AnalysisService 결과를 AnalysisResponse로 변환

        Args:
            raw_analysis_output (Dict[str, Any]): AnalysisService 원시 출력

        Returns:
            AnalysisResponse: 표준화된 응답

        Raises:
            ResponseFormattingError: 포맷팅 실패 시
        """
        self.logger.info("format_analysis_response() 호출: 응답 포맷팅 시작")

        try:
            # 1단계: 기본 정보 추출
            self.logger.info("1단계: 기본 정보 추출")

            status = raw_analysis_output.get("status", "unknown")
            message = raw_analysis_output.get("message", "분석이 완료되었습니다.")

            # 오류 상태 확인
            if status == "error":
                return self._format_error_response(raw_analysis_output)

            # 2단계: PEG 통계 추출
            self.logger.info("2단계: PEG 통계 추출")
            peg_analysis = raw_analysis_output.get("peg_analysis", {})
            peg_statistics = self._extract_peg_statistics(peg_analysis)

            # 3단계: 분석 통계 추출
            self.logger.info("3단계: 분석 통계 추출")
            data_summary = raw_analysis_output.get("data_summary", {})
            metadata = raw_analysis_output.get("metadata", {})
            analysis_stats = self._extract_analysis_stats(data_summary, metadata)

            # 4단계: LLM 분석 결과 추출
            self.logger.info("4단계: LLM 분석 결과 추출")
            llm_analysis = raw_analysis_output.get("llm_analysis", {})
            llm_result = self._extract_llm_analysis_result(llm_analysis)

            # 5단계: AnalysisResponse 생성
            self.logger.info("5단계: AnalysisResponse 생성")

            # 타임스탬프 추출
            request_timestamp = None
            completion_timestamp = datetime.now()

            if "processing_timestamp" in metadata:
                try:
                    completion_timestamp = datetime.fromisoformat(metadata["processing_timestamp"])
                except Exception:
                    pass

            response = AnalysisResponse(
                status="completed" if status == "success" else status,
                message=message,
                analysis_id=metadata.get("request_id"),
                request_timestamp=request_timestamp,
                completion_timestamp=completion_timestamp,
                peg_statistics=peg_statistics,
                llm_analysis=llm_result,
                analysis_stats=analysis_stats,
                output_files=[],  # 추후 파일 출력 지원 시 추가
                backend_response=None,  # 추후 백엔드 응답 처리 시 추가
                error_details=None,
            )

            self.logger.info("응답 포맷팅 완료: %d개 PEG, status=%s", len(peg_statistics), response.status)

            return response

        except ResponseFormattingError:
            # 이미 ResponseFormattingError인 경우 그대로 전파
            raise

        except Exception as e:
            # 예상치 못한 오류를 ResponseFormattingError로 변환
            raise ResponseFormattingError(
                f"응답 포맷팅 중 예상치 못한 오류: {e}",
                formatting_step="unknown",
                input_context={"raw_output_keys": list(raw_analysis_output.keys())},
            ) from e

    def _format_error_response(self, raw_error_output: Dict[str, Any]) -> AnalysisResponse:
        """
        오류 응답 포맷팅

        Args:
            raw_error_output (Dict[str, Any]): AnalysisService 오류 출력

        Returns:
            AnalysisResponse: 표준화된 오류 응답
        """
        self.logger.debug("_format_error_response() 호출: 오류 응답 포맷팅")

        try:
            error_message = raw_error_output.get("message", "분석 중 오류가 발생했습니다.")
            error_type = raw_error_output.get("error_type", "unknown_error")

            # 오류 상세 정보 수집
            error_details = {
                "error_type": error_type,
                "details": raw_error_output.get("details"),
                "workflow_step": raw_error_output.get("workflow_step"),
                "timestamp": datetime.now().isoformat(),
            }

            # 기본 AnalysisStats (오류 상황)
            error_stats = AnalysisStats(
                total_pegs=0, processed_pegs=0, derived_pegs=0, analysis_duration_seconds=0.0, llm_tokens_used=0
            )

            error_response = AnalysisResponse(
                status="error",
                message=error_message,
                analysis_id=None,
                request_timestamp=None,
                completion_timestamp=datetime.now(),
                peg_statistics=[],
                llm_analysis=None,
                analysis_stats=error_stats,
                output_files=[],
                backend_response=None,
                error_details=error_details,
            )

            self.logger.info("오류 응답 포맷팅 완료: type=%s", error_type)
            return error_response

        except Exception as e:
            # 오류 포맷팅 중 오류 발생 시 최소한의 응답 생성
            self.logger.error("오류 응답 포맷팅 실패: %s", e)

            return AnalysisResponse(
                status="error",
                message="응답 포맷팅 중 오류가 발생했습니다.",
                analysis_id=None,
                request_timestamp=None,
                completion_timestamp=datetime.now(),
                peg_statistics=[],
                llm_analysis=None,
                analysis_stats=AnalysisStats(),
                output_files=[],
                backend_response=None,
                error_details={"error": str(e)},
            )

    def to_dict(self, response: AnalysisResponse) -> Dict[str, Any]:
        """
        AnalysisResponse를 딕셔너리로 변환 (JSON 직렬화 지원)

        Args:
            response (AnalysisResponse): 응답 객체

        Returns:
            Dict[str, Any]: 직렬화 가능한 딕셔너리

        Raises:
            ResponseFormattingError: 직렬화 실패 시
        """
        self.logger.debug("to_dict() 호출: AnalysisResponse 직렬화")

        try:
            # dataclass를 딕셔너리로 변환
            response_dict = asdict(response)

            # datetime 객체를 ISO 문자열로 변환
            if response_dict.get("request_timestamp"):
                response_dict["request_timestamp"] = response.request_timestamp.isoformat()

            if response_dict.get("completion_timestamp"):
                response_dict["completion_timestamp"] = response.completion_timestamp.isoformat()

            # LLM 분석 결과의 timestamp 처리
            if response_dict.get("llm_analysis") and response_dict["llm_analysis"].get("analysis_timestamp"):
                if hasattr(response.llm_analysis, "analysis_timestamp"):
                    response_dict["llm_analysis"][
                        "analysis_timestamp"
                    ] = response.llm_analysis.analysis_timestamp.isoformat()

            self.logger.info("AnalysisResponse 직렬화 완료: %d개 키", len(response_dict))
            return response_dict

        except Exception as e:
            raise ResponseFormattingError(
                f"AnalysisResponse 직렬화 실패: {e}",
                formatting_step="serialization",
                input_context={"response_status": response.status},
            ) from e

    def to_json(self, response: AnalysisResponse, indent: int = 2) -> str:
        """
        AnalysisResponse를 JSON 문자열로 변환

        Args:
            response (AnalysisResponse): 응답 객체
            indent (int): JSON 들여쓰기

        Returns:
            str: JSON 문자열

        Raises:
            ResponseFormattingError: JSON 변환 실패 시
        """
        self.logger.debug("to_json() 호출: JSON 변환")

        try:
            response_dict = self.to_dict(response)
            json_str = json.dumps(response_dict, ensure_ascii=False, indent=indent)

            self.logger.info("JSON 변환 완료: %d자", len(json_str))
            return json_str

        except Exception as e:
            raise ResponseFormattingError(f"JSON 변환 실패: {e}", formatting_step="serialization") from e

    def format_for_backend(self, response: AnalysisResponse) -> Dict[str, Any]:
        """
        백엔드 전송을 위한 최적화된 형식으로 변환

        Args:
            response (AnalysisResponse): 응답 객체

        Returns:
            Dict[str, Any]: 백엔드 최적화 형식
        """
        self.logger.debug("format_for_backend() 호출: 백엔드 형식 변환")

        try:
            # 백엔드 전송용 간소화된 구조
            backend_format = {
                "analysis_id": response.analysis_id,
                "status": response.status,
                "completion_timestamp": (
                    response.completion_timestamp.isoformat() if response.completion_timestamp else None
                ),
                "summary": {
                    "total_pegs": response.analysis_stats.total_pegs if response.analysis_stats else 0,
                    "processed_pegs": response.analysis_stats.processed_pegs if response.analysis_stats else 0,
                    "llm_summary": response.llm_analysis.integrated_analysis if response.llm_analysis else None,
                },
                "peg_data": [],
            }

            # PEG 데이터 간소화
            for peg_stat in response.peg_statistics:
                peg_data = {
                    "peg_name": peg_stat.peg_name,
                    "n_minus_1": peg_stat.avg_n_minus_1,
                    "n": peg_stat.avg_n,
                    "change_pct": peg_stat.pct_change,
                }
                backend_format["peg_data"].append(peg_data)

            # 오류 정보 (있는 경우)
            if response.error_details:
                backend_format["error"] = response.error_details

            self.logger.info("백엔드 형식 변환 완료: %d개 PEG", len(backend_format["peg_data"]))
            return backend_format

        except Exception as e:
            raise ResponseFormattingError(f"백엔드 형식 변환 실패: {e}", formatting_step="serialization") from e

    def get_formatting_status(self) -> Dict[str, Any]:
        """포맷팅 상태 정보 반환"""
        return {
            "formatting_steps": self.formatting_steps,
            "step_count": len(self.formatting_steps),
            "supported_formats": self.supported_formats,
            "is_ready": True,
        }
