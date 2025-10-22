"""
백엔드 Payload 생성 유틸리티

목적: MCP 분석 결과를 백엔드 V2 API 스키마에 맞게 변환
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


class BackendPayloadBuilder:
    """
    백엔드 V2 API용 Payload 생성기
    
    변환 규칙:
    - host → swname 명칭 변경
    - 중첩 구조 제거 및 평탄화
    - 필수 필드 보장
    """
    
    @staticmethod
    def build_v2_payload(
        analysis_result: dict,
        analysis_request: dict
    ) -> dict:
        """
        백엔드 V2 API용 페이로드 생성 (DB 조회 값 우선)
        
        Args:
            analysis_result: AnalysisService 결과 (db_identifiers 포함 가능)
            analysis_request: 원본 MCP 요청 (filters 포함)
            
        Returns:
            백엔드 V2 스키마 호환 페이로드
        """
        logger.info("백엔드 V2 페이로드 생성 시작")
        
        # DB 조회 값 우선, filters 폴백, 기본값 순
        filters = analysis_request.get("filters", {})
        columns = analysis_request.get("columns", {})
        db_identifiers = analysis_result.get("db_identifiers", {})
        
        # ne_id: DB > filters > "All NEs" (기본값)
        ne_id = (
            db_identifiers.get("ne_id") or
            BackendPayloadBuilder._extract_identifier(filters.get("ne")) or
            "All NEs"
        )
        
        # cell_id: DB > filters > "All cells" (기본값)
        cell_id = (
            db_identifiers.get("cell_id") or
            BackendPayloadBuilder._extract_identifier(filters.get("cellid")) or
            "All cells"
        )
        
        # swname: DB > filters(swname) > "All hosts"
        swname = (
            db_identifiers.get("swname") or
            BackendPayloadBuilder._extract_identifier(
                filters.get("swname")
            ) or
            "All hosts"
        )
        
        # rel_ver: DB > filters > None (기본값)
        rel_ver = (
            db_identifiers.get("rel_ver") or
            BackendPayloadBuilder._extract_identifier(filters.get("rel_ver")) or
            None
        )
        
        logger.debug(
            "식별자 우선순위 적용 결과:\n"
            "  ne_id: %s (DB=%s, filters=%s)\n"
            "  cell_id: %s (DB=%s, filters=%s)\n"
            "  swname: %s (DB=%s, filters=%s)\n"
            "  rel_ver: %s (DB=%s, filters=%s)",
            ne_id,
            db_identifiers.get("ne_id"),
            BackendPayloadBuilder._extract_identifier(filters.get("ne")),
            cell_id,
            db_identifiers.get("cell_id"),
            BackendPayloadBuilder._extract_identifier(filters.get("cellid")),
            swname,
            db_identifiers.get("swname"),
            BackendPayloadBuilder._extract_identifier(filters.get("swname")),
            rel_ver,
            db_identifiers.get("rel_ver"),
            BackendPayloadBuilder._extract_identifier(filters.get("rel_ver"))
        )
        
        # 분석 기간 파싱
        analysis_period = BackendPayloadBuilder._parse_analysis_period(
            analysis_request.get("n_minus_1"),
            analysis_request.get("n")
        )
        
        # Choi 알고리즘 결과 추출
        choi_result = BackendPayloadBuilder._extract_choi_result(
            analysis_result
        )
        
        # LLM 분석 결과 추출
        llm_analysis = BackendPayloadBuilder._extract_llm_analysis(
            analysis_result
        )
        
        # LLM 분석 키 디버깅
        llm_data_raw = analysis_result.get("llm_analysis", {})
        logger.debug(
            "LLM 분석 원본 키: %s",
            list(llm_data_raw.keys()) if isinstance(llm_data_raw, dict) else type(llm_data_raw).__name__
        )
        
        # llm_analysis가 None일 수 있으므로 안전하게 처리
        if llm_analysis and isinstance(llm_analysis, dict):
            logger.debug(
                "추출된 llm_analysis (Enhanced): executive_summary=%s, diagnostic_findings=%d개, recommended_actions=%d개, model=%s",
                "있음" if llm_analysis.get("executive_summary") else "없음",
                len(llm_analysis.get("diagnostic_findings", [])),
                len(llm_analysis.get("recommended_actions", [])),
                llm_analysis.get("model_name")
            )
        else:
            logger.warning("llm_analysis가 None이거나 dict가 아닙니다: type=%s", type(llm_analysis).__name__)
        
        # PEG 비교 결과 추출
        peg_comparisons = BackendPayloadBuilder._extract_peg_comparisons(
            analysis_result
        )
        
        # 페이로드 구성
        payload = {
            # 식별자
            "ne_id": ne_id,
            "cell_id": cell_id,
            "swname": swname,
            "rel_ver": rel_ver,
            
            # 분석 기간
            "analysis_period": analysis_period,
            
            # Choi 알고리즘 (선택)
            "choi_result": choi_result,
            
            # LLM 분석
            "llm_analysis": llm_analysis,
            
            # PEG 비교
            "peg_comparisons": peg_comparisons,
            
            # 추적용 ID (백엔드 _id를 analysis_id로 매핑)
            "analysis_id": analysis_result.get("analysis_id")
        }
        
        # 백엔드 응답에서 _id가 있으면 제거 (중복 방지)
        if "_id" in payload:
            del payload["_id"]
            logger.debug("페이로드에서 _id 필드 제거 (analysis_id 사용)")
        
        logger.info(
            "백엔드 V2 페이로드 생성 완료: ne_id=%s, cell_id=%s, swname=%s, pegs=%d",
            ne_id,
            cell_id,
            swname,
            len(peg_comparisons)
        )
        
        # 🔍 422 에러 디버깅: 전체 페이로드 구조 로깅
        logger.debug("🔍 [422 디버깅] 생성된 페이로드 구조:")
        logger.debug("  - ne_id: %s (type: %s)", payload.get("ne_id"), type(payload.get("ne_id")).__name__)
        logger.debug("  - cell_id: %s (type: %s)", payload.get("cell_id"), type(payload.get("cell_id")).__name__)
        logger.debug("  - swname: %s (type: %s)", payload.get("swname"), type(payload.get("swname")).__name__)
        logger.debug("  - rel_ver: %s (type: %s)", payload.get("rel_ver"), type(payload.get("rel_ver")).__name__)
        logger.debug("  - analysis_period: %s", payload.get("analysis_period"))
        logger.debug("  - choi_result: %s", payload.get("choi_result"))
        logger.debug("  - analysis_id: %s (type: %s)", payload.get("analysis_id"), type(payload.get("analysis_id")).__name__)
        
        # LLM 분석 상세 구조 로깅
        llm_analysis_data = payload.get("llm_analysis", {})
        logger.debug("  - llm_analysis keys: %s", list(llm_analysis_data.keys()) if isinstance(llm_analysis_data, dict) else "Not a dict")
        logger.debug("  - llm_analysis type: %s", type(llm_analysis_data).__name__)
        
        if isinstance(llm_analysis_data, dict):
            # diagnostic_findings 구조 확인
            diagnostic_findings = llm_analysis_data.get("diagnostic_findings", [])
            logger.debug("  - diagnostic_findings: %d개", len(diagnostic_findings) if isinstance(diagnostic_findings, list) else 0)
            if isinstance(diagnostic_findings, list) and len(diagnostic_findings) > 0:
                first_finding = diagnostic_findings[0]
                logger.debug("  - 첫 번째 diagnostic_finding: %s", first_finding)
                logger.debug("  - 첫 번째 finding keys: %s", list(first_finding.keys()) if isinstance(first_finding, dict) else "Not a dict")
            
            # recommended_actions 구조 확인
            recommended_actions = llm_analysis_data.get("recommended_actions", [])
            logger.debug("  - recommended_actions: %d개", len(recommended_actions) if isinstance(recommended_actions, list) else 0)
            if isinstance(recommended_actions, list) and len(recommended_actions) > 0:
                first_action = recommended_actions[0]
                logger.debug("  - 첫 번째 recommended_action: %s", first_action)
                logger.debug("  - 첫 번째 action keys: %s", list(first_action.keys()) if isinstance(first_action, dict) else "Not a dict")
        
        # PEG 비교 구조 확인
        logger.debug("  - peg_comparisons: %d개", len(peg_comparisons))
        if len(peg_comparisons) > 0:
            first_peg = peg_comparisons[0]
            logger.debug("  - 첫 번째 PEG: %s", first_peg)
            logger.debug("  - 첫 번째 PEG keys: %s", list(first_peg.keys()) if isinstance(first_peg, dict) else "Not a dict")
        
        return payload
    
    @staticmethod
    def _extract_identifier(value: Any, default: Optional[str] = None) -> Optional[str]:
        """
        식별자 추출 (리스트면 첫 번째 값)
        
        Args:
            value: 추출할 값 (str, list, None)
            default: 기본값
            
        Returns:
            추출된 문자열 또는 기본값
        """
        if isinstance(value, list):
            return str(value[0]) if value else default
        return str(value) if value else default
    
    @staticmethod
    def _parse_analysis_period(n_minus_1: str, n: str) -> Dict[str, str]:
        """
        분석 기간 파싱 (다양한 형식 지원)
        
        지원 형식:
        - "2025-01-19_00:00~23:59" (기존 - 같은 날짜)
        - "2025-09-04_21:15 ~2025-09-04_21:30" (신규 - 날짜_시간 ~날짜_시간)
        
        Args:
            n_minus_1: N-1 기간
            n: N 기간
            
        Returns:
            {
                "n_minus_1_start": "2025-01-19 00:00:00",
                "n_minus_1_end": "2025-01-19 23:59:59",
                "n_start": "2025-01-20 00:00:00",
                "n_end": "2025-01-20 23:59:59"
            }
        """
        def parse_single_datetime(dt_str: str) -> str:
            """
            단일 날짜-시간 파싱
            
            지원:
            - "2025-01-19_00:00" → "2025-01-19 00:00:00"
            - "00:00" → "00:00:00" (날짜 없음)
            """
            dt_str = dt_str.strip()
            
            if "_" in dt_str:
                # "날짜_시간" 형식
                date_part, time_part = dt_str.split("_", 1)
                # 초가 없으면 추가
                if time_part.count(":") == 1:
                    return f"{date_part} {time_part}:00"
                else:
                    return f"{date_part} {time_part}"
            else:
                # 시간만 (날짜 없음)
                if dt_str.count(":") == 1:
                    return f"{dt_str}:00"
                else:
                    return dt_str
        
        def parse_time_range(time_str: str) -> tuple:
            """
            시간 범위 파싱
            
            형식 1: "2025-01-19_00:00~23:59"
            형식 2: "2025-09-04_21:15 ~2025-09-04_21:30"
            """
            if not time_str or "~" not in time_str:
                return ("unknown", "unknown")
            
            try:
                # 공백 제거 및 정규화
                time_str = time_str.strip()
                
                # "~"로 분리
                parts = time_str.split("~")
                if len(parts) != 2:
                    raise ValueError(f"잘못된 형식: 2개 부분 예상, {len(parts)}개 발견")
                
                start_str = parts[0].strip()
                end_str = parts[1].strip()
                
                # 각 부분 파싱
                start_datetime = parse_single_datetime(start_str)
                end_datetime = parse_single_datetime(end_str)
                
                # 형식 1 호환: 끝 시간에 날짜가 없으면 시작 날짜 사용
                if "_" in start_datetime and "_" not in end_str and ":" in end_str:
                    # "2025-01-19_00:00" ~ "23:59" 형식
                    date_part = start_datetime.split()[0]  # "2025-01-19"
                    end_datetime = f"{date_part} {end_datetime}"
                    # 초 처리
                    if end_datetime.count(":") == 1:
                        end_datetime = f"{end_datetime}:59"
                
                return (start_datetime, end_datetime)
                
            except Exception as e:
                logger.warning(f"시간 범위 파싱 실패: {time_str}, error={e}")
                return ("unknown", "unknown")
        
        n_minus_1_start, n_minus_1_end = parse_time_range(n_minus_1)
        n_start, n_end = parse_time_range(n)
        
        return {
            "n_minus_1_start": n_minus_1_start,
            "n_minus_1_end": n_minus_1_end,
            "n_start": n_start,
            "n_end": n_end
        }
    
    @staticmethod
    def _extract_choi_result(analysis_result: dict) -> Optional[Dict[str, Any]]:
        """
        Choi 알고리즘 결과 추출
        
        Args:
            analysis_result: AnalysisService 결과
            
        Returns:
            Choi 결과 또는 None
        """
        # TODO: Choi 알고리즘이 구현되면 실제 추출 로직 추가
        choi_data = analysis_result.get("choi_algorithm", {})
        
        if not choi_data or not choi_data.get("enabled"):
            return None
        
        return {
            "enabled": True,
            "status": choi_data.get("status", "normal"),
            "score": choi_data.get("score"),
            "details": choi_data.get("details", {})
        }
    
    @staticmethod
    def _extract_llm_analysis(analysis_result: dict) -> Dict[str, Any]:
        """
        LLM 분석 결과 추출 (Enhanced 프롬프트 구조 그대로 전송)
        
        전송 구조:
        - executive_summary: 전체 요약 (str)
        - diagnostic_findings: 진단 결과 리스트 (list of dict)
          - primary_hypothesis
          - supporting_evidence
          - confounding_factors_assessment
        - recommended_actions: 권장 조치 리스트 (list of dict)
          - priority
          - action
          - details
        
        Args:
            analysis_result: AnalysisService 결과
            
        Returns:
            Enhanced 프롬프트 원본 구조
        """
        llm_data = analysis_result.get("llm_analysis", {})
        
        # 디버그 로깅: 원본 LLM 데이터 구조 확인
        logger.debug(
            "🔍 LLM 분석 원본 데이터 구조 분석 (Enhanced 프롬프트):\n"
            "  전체 키: %s\n"
            "  executive_summary: %s\n"
            "  diagnostic_findings: %s\n"
            "  recommended_actions: %s",
            list(llm_data.keys()) if isinstance(llm_data, dict) else type(llm_data).__name__,
            "있음" if llm_data.get("executive_summary") else "없음",
            "있음" if llm_data.get("diagnostic_findings") else "없음",
            "있음" if llm_data.get("recommended_actions") else "없음"
        )
        
        # Enhanced 프롬프트 구조 그대로 추출
        executive_summary = llm_data.get("executive_summary")
        diagnostic_findings = llm_data.get("diagnostic_findings", [])
        recommended_actions = llm_data.get("recommended_actions", [])
        
        # 추가 분석 필드 추출 (심도 있는 분석용) - 타입 정규화
        technical_analysis = llm_data.get("technical_analysis")
        # 빈 객체 {}인 경우 None으로 변환
        if isinstance(technical_analysis, dict) and not technical_analysis:
            technical_analysis = None
        
        cells_with_significant_change = llm_data.get("cells_with_significant_change", [])
        # 빈 객체 {}인 경우 빈 배열로 변환
        if isinstance(cells_with_significant_change, dict):
            cells_with_significant_change = []
        
        action_plan = llm_data.get("action_plan")
        # 빈 배열 []인 경우 None으로 변환
        if isinstance(action_plan, list):
            action_plan = None
        
        key_findings = llm_data.get("key_findings", [])
        # 빈 객체 {}인 경우 빈 배열로 변환
        if isinstance(key_findings, dict):
            key_findings = []
        
        # 메타데이터 추출
        confidence = llm_data.get("confidence")
        model_name = (
            llm_data.get("model_name") or
            llm_data.get("model") or
            llm_data.get("model_used")
        )
        
        # Enhanced 프롬프트 구조 + 추가 분석 필드
        result = {
            # Enhanced 프롬프트 필수 필드
            "executive_summary": executive_summary,
            "diagnostic_findings": diagnostic_findings,
            "recommended_actions": recommended_actions,
            
            # 추가 분석 필드 (Optional)
            "technical_analysis": technical_analysis,
            "cells_with_significant_change": cells_with_significant_change,
            "action_plan": action_plan,
            "key_findings": key_findings,
            
            # 메타데이터
            "confidence": confidence,
            "model_name": model_name
        }
        
        # 디버그 로깅: 추출된 결과 확인 (타입 정규화 후)
        logger.debug(
            "✅ LLM 분석 추출 완료 (Enhanced 프롬프트 구조 + 추가 필드 - 타입 정규화):\n"
            "  executive_summary: %s (type: %s)\n"
            "  diagnostic_findings: %d개 (type: %s)\n"
            "  recommended_actions: %d개 (type: %s)\n"
            "  technical_analysis: %s (type: %s)\n"
            "  cells_with_significant_change: %s (type: %s)\n"
            "  action_plan: %s (type: %s)\n"
            "  key_findings: %s (type: %s)\n"
            "  confidence: %s (type: %s)\n"
            "  model_name: %s (type: %s)",
            "있음" if result["executive_summary"] else "없음",
            type(result["executive_summary"]).__name__,
            len(result["diagnostic_findings"]) if isinstance(result["diagnostic_findings"], list) else 0,
            type(result["diagnostic_findings"]).__name__,
            len(result["recommended_actions"]) if isinstance(result["recommended_actions"], list) else 0,
            type(result["recommended_actions"]).__name__,
            "있음" if result["technical_analysis"] else "없음",
            type(result["technical_analysis"]).__name__,
            f"{len(result['cells_with_significant_change'])}개" if result["cells_with_significant_change"] else "없음",
            type(result["cells_with_significant_change"]).__name__,
            "있음" if result["action_plan"] else "없음",
            type(result["action_plan"]).__name__,
            f"{len(result['key_findings'])}개" if result["key_findings"] else "없음",
            type(result["key_findings"]).__name__,
            result["confidence"],
            type(result["confidence"]).__name__,
            result["model_name"],
            type(result["model_name"]).__name__
        )
        
        return result
    
    @staticmethod
    def _extract_peg_comparisons(analysis_result: dict) -> List[Dict[str, Any]]:
        """
        PEG 비교 결과 추출
        
        Args:
            analysis_result: AnalysisService 결과
            
        Returns:
            PEG 비교 결과 리스트
        """
        peg_metrics = analysis_result.get("peg_metrics", {})
        peg_items = peg_metrics.get("items", [])
        
        # LLM의 PEG별 인사이트
        llm_insights = analysis_result.get("llm_analysis", {}).get("peg_insights", {})
        
        comparisons = []
        
        for item in peg_items:
            peg_name = item.get("peg_name")
            if not peg_name:
                continue
            
            # N-1 통계
            n_minus_1_stats = {
                "avg": item.get("n_minus_1_avg"),
                "pct_95": item.get("n_minus_1_pct_95"),
                "pct_99": item.get("n_minus_1_pct_99"),
                "min": item.get("n_minus_1_min"),
                "max": item.get("n_minus_1_max"),
                "count": item.get("n_minus_1_count"),
                "std": item.get("n_minus_1_std")
            }
            
            # N 통계
            n_stats = {
                "avg": item.get("n_avg") or item.get("n_value"),
                "pct_95": item.get("n_pct_95"),
                "pct_99": item.get("n_pct_99"),
                "min": item.get("n_min"),
                "max": item.get("n_max"),
                "count": item.get("n_count"),
                "std": item.get("n_std")
            }
            
            comparison = {
                "peg_name": peg_name,
                "n_minus_1": n_minus_1_stats,
                "n": n_stats,
                "change_absolute": item.get("absolute_change"),
                "change_percentage": item.get("percentage_change"),
                "llm_insight": llm_insights.get(peg_name) or item.get("llm_analysis_summary")
            }
            
            comparisons.append(comparison)
        
        return comparisons


__all__ = ["BackendPayloadBuilder"]


