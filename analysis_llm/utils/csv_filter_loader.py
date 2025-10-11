"""
CSV-based PEG Filter and Definition Loader

이 모듈은 CSV 파일에서 family_id, peg_name, define(파생 PEG 수식) 목록을 읽어,
필터링 및 파생 PEG 계산에 사용할 수 있는 데이터 구조로 변환하는 유틸리티를 제공합니다.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Any, Dict, List, Set, Tuple

import pandas as pd

# 로깅 설정
logger = logging.getLogger(__name__)


def load_peg_definitions_from_csv(
    file_path: str,
) -> Tuple[Dict[int, Set[str]], List[Dict[str, Any]]]:
    """
    CSV 파일에서 PEG 필터 목록과 파생 PEG 정의를 로드합니다.

    CSV 파일은 'family_id', 'peg_name', 'define' 컬럼을 포함할 수 있습니다.
    - define이 없는 행: DB 조회를 위한 필터로 사용됩니다.
    - define이 있는 행: 파생 PEG를 정의하는 데 사용됩니다.

    Args:
        file_path (str): 읽어올 CSV 파일의 전체 경로

    Returns:
        Tuple[Dict[int, Set[str]], List[Dict[str, Any]]]:
        1. DB 필터용 딕셔너리: {family_id: {peg_name_1, peg_name_2, ...}}
           (family_id는 정수로 유지되어 DB의 int 컬럼과 매칭됨)
        2. 파생 PEG 정의 리스트: [{'output_peg': str, 'formula': str, 'dependencies': Set[str]}, ...]
    """
    db_filter: Dict[int, Set[str]] = defaultdict(set)
    derived_pegs: List[Dict[str, Any]] = []

    try:
        logger.info("CSV 파일 로드 시도: %s", file_path)
        # 모든 컬럼을 먼저 문자열로 읽은 후 처리
        df = pd.read_csv(
            file_path,
            dtype=str,  # 모든 컬럼을 문자열로 읽음
            keep_default_na=False  # 빈 문자열을 NaN으로 변환하지 않음
        )
        
        # 빈 문자열을 NaN으로 변환 후 다시 빈 문자열로
        df.replace('', pd.NA, inplace=True)
        df.fillna('', inplace=True)

        for _, row in df.iterrows():
            define_formula = row.get("define", "").strip()

            if define_formula:
                # define 컬럼에 수식이 있는 경우 (파생 PEG)
                try:
                    if "=" not in define_formula:
                        logger.warning("잘못된 define 형식 (무시): '='가 없습니다 - '%s'", define_formula)
                        continue

                    output_peg, formula = define_formula.split("=", 1)
                    output_peg = output_peg.strip()
                    formula = formula.strip()

                    if not output_peg or not formula:
                        logger.warning("잘못된 define 형식 (무시): PEG 이름 또는 수식이 비어있습니다 - '%s'", define_formula)
                        continue
                    
                    # 수식에서 의존성(다른 PEG 이름) 추출
                    dependencies = set(re.findall(r'[a-zA-Z_][a-zA-Z0-9_.]*', formula))
                    
                    derived_pegs.append({
                        "output_peg": output_peg,
                        "formula": formula,
                        "dependencies": dependencies,
                    })
                except Exception as e:
                    logger.error("Define 수식 파싱 중 오류: '%s'. 오류: %s", define_formula, e)
            else:
                # define 컬럼이 없는 경우 (DB 조회 대상 PEG)
                # family_id 컬럼만 지원 (DB의 family_id int 컬럼과 매칭)
                family_val = row.get("family_id", "").strip()
                peg_name = row.get("peg_name", "").strip()

                # family_id와 peg_name이 모두 유효한 경우만 처리
                if family_val and peg_name:
                    try:
                        # family_id를 정수로 변환 (DB의 int 컬럼과 매칭)
                        # CSV에 5002라고 적혀있으면 → 5002 (정수)로 변환
                        family_key = int(family_val)
                        db_filter[family_key].add(peg_name)
                        logger.debug("CSV 필터 추가: family_id=%d, peg_name='%s'", family_key, peg_name)
                    except (ValueError, TypeError) as e:
                        logger.warning(
                            "Family ID를 정수로 변환 실패 (무시): family_id='%s', peg_name='%s'. 오류: %s",
                            family_val, peg_name, e
                        )

        logger.info(
            "CSV 파일 로드 완료: DB필터 %d families, 파생PEG %d개",
            len(db_filter),
            len(derived_pegs),
        )
        return dict(db_filter), derived_pegs

    except FileNotFoundError:
        logger.warning("CSV 파일을 찾을 수 없습니다: %s. 빈 설정으로 진행합니다.", file_path)
        return {}, []
    except Exception as e:
        logger.error(
            "CSV 파일 처리 중 오류 발생: %s. 빈 설정으로 진행합니다. 오류: %s",
            file_path, e, exc_info=True
        )
        return {}, []