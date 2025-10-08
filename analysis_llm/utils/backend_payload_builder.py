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
        
        # ne_id: DB > filters > "unknown"
        ne_id = (
            db_identifiers.get("ne_id") or
            BackendPayloadBuilder._extract_identifier(filters.get("ne")) or
            "unknown"
        )
        
        # cell_id: DB > filters > "unknown"
        cell_id = (
            db_identifiers.get("cell_id") or
            BackendPayloadBuilder._extract_identifier(filters.get("cellid")) or
            "unknown"
        )
        
        # swname: DB > filters(swname) > "unknown"
        swname = (
            db_identifiers.get("swname") or
            BackendPayloadBuilder._extract_identifier(
                filters.get("swname")
            ) or
            "unknown"
        )
        
        # rel_ver: filters만 사용 (DB에 저장되지 않음)
        rel_ver = BackendPayloadBuilder._extract_identifier(
            filters.get("rel_ver"),
            default=None
        )
        
        logger.debug(
            "식별자 우선순위 적용 결과:\n"
            "  ne_id: %s (DB=%s, filters=%s)\n"
            "  cell_id: %s (DB=%s, filters=%s)\n"
            "  swname: %s (DB=%s, filters=%s)",
            ne_id,
            db_identifiers.get("ne_id"),
            BackendPayloadBuilder._extract_identifier(filters.get("ne")),
            cell_id,
            db_identifiers.get("cell_id"),
            BackendPayloadBuilder._extract_identifier(filters.get("cellid")),
            swname,
            db_identifiers.get("swname"),
            BackendPayloadBuilder._extract_identifier(filters.get("swname"))
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
            
            # 추적용 ID
            "analysis_id": analysis_result.get("analysis_id")
        }
        
        logger.info(
            "백엔드 V2 페이로드 생성 완료: ne_id=%s, cell_id=%s, swname=%s, pegs=%d",
            ne_id,
            cell_id,
            swname,
            len(peg_comparisons)
        )
        
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
        LLM 분석 결과 추출
        
        Args:
            analysis_result: AnalysisService 결과
            
        Returns:
            LLM 분석 결과
        """
        llm_data = analysis_result.get("llm_analysis", {})
        
        return {
            "summary": llm_data.get("summary"),
            "issues": llm_data.get("issues", []),
            "recommendations": llm_data.get("recommended_actions", []),
            "confidence": llm_data.get("confidence"),
            "model_name": llm_data.get("model")
        }
    
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


