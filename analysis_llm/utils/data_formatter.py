"""
데이터 포매팅 유틸리티 모듈

프롬프트 생성을 위한 데이터 전처리 및 포매팅 기능을 제공합니다.
이 모듈은 기존 프롬프트 생성 함수들에서 중복되던 데이터 처리 로직을 
단일 책임 원칙(SRP)에 따라 분리한 것입니다.
"""

import os
import logging
import pandas as pd
from typing import List, Optional


def format_dataframe_for_prompt(
    df: pd.DataFrame, 
    preferred_columns: Optional[List[str]] = None,
    max_rows: Optional[int] = None,
    fallback_column_count: int = 5
) -> str:
    """
    DataFrame을 프롬프트에 포함할 수 있는 문자열 형태로 포매팅합니다.
    
    이 함수는 기존 프롬프트 생성 함수들에서 중복되던 데이터 전처리 로직을
    추출하여 재사용 가능한 형태로 만든 것입니다.
    
    Args:
        df (pd.DataFrame): 포매팅할 DataFrame
        preferred_columns (Optional[List[str]]): 우선적으로 포함할 컬럼 목록
            기본값은 ["peg_name", "avg_value", "period"]
        max_rows (Optional[int]): 포함할 최대 행 수
            None이면 환경변수 PROMPT_PREVIEW_ROWS 또는 기본값 200 사용
        fallback_column_count (int): preferred_columns가 없을 때 사용할 컬럼 수
    
    Returns:
        str: 포매팅된 데이터 문자열 (인덱스 제외)
        
    Raises:
        ValueError: DataFrame이 비어있거나 None인 경우
        
    Example:
        >>> df = pd.DataFrame({
        ...     'peg_name': ['PEG_A', 'PEG_B'],
        ...     'avg_value': [10.5, 20.3],
        ...     'period': ['2023-01', '2023-01']
        ... })
        >>> formatted = format_dataframe_for_prompt(df)
        >>> print(formatted)
        peg_name  avg_value    period
           PEG_A       10.5  2023-01
           PEG_B       20.3  2023-01
    """
    # 입력 검증
    if df is None:
        logging.warning("format_dataframe_for_prompt(): None DataFrame 입력")
        raise ValueError("DataFrame이 비어있거나 None입니다")
    
    if df.empty:
        logging.warning("format_dataframe_for_prompt(): 빈 DataFrame 입력")
        raise ValueError("DataFrame이 비어있거나 None입니다")
    
    logging.info(f"format_dataframe_for_prompt() 호출: DataFrame 크기={df.shape}")
    
    # 기본 우선 컬럼 설정
    # PEG 분석에 필요한 실제 컬럼명들
    if preferred_columns is None:
        preferred_columns = ["peg_name", "avg_n_minus_1", "avg_n", "diff", "pct_change"]
    
    # 우선 컬럼 선택 (존재하는 컬럼만)
    available_preferred_cols = [col for col in preferred_columns if col in df.columns]
    
    if available_preferred_cols:
        selected_columns = available_preferred_cols
        logging.info(f"우선 컬럼 사용: {selected_columns}")
    else:
        # 우선 컬럼이 없으면 모든 컬럼 사용
        selected_columns = list(df.columns)
        logging.info(f"대체 컬럼 사용 (전체 컬럼): {selected_columns}")
    
    # 컬럼 필터링된 DataFrame 생성
    filtered_df = df[selected_columns]
    
    # 행 수 제한 적용
    if max_rows is None:
        # 환경변수에서 미리보기 행 수 설정 (기본값: 200행)
        max_rows = int(os.getenv('PROMPT_PREVIEW_ROWS', '200'))
        logging.info(f"환경변수 PROMPT_PREVIEW_ROWS에서 행 수 제한: {max_rows}")
    
    # 행 수 제한 적용
    preview_df = filtered_df.head(max_rows)
    
    # 문자열로 변환 (인덱스 제외)
    formatted_string = preview_df.to_string(index=False)
    
    logging.info(f"format_dataframe_for_prompt() 완료: {len(preview_df)}행, {len(selected_columns)}컬럼 포매팅")
    
    return formatted_string


def extract_column_info(df: pd.DataFrame) -> dict:
    """
    DataFrame의 컬럼 정보를 추출합니다.
    
    프롬프트에서 데이터 구조를 설명할 때 사용할 수 있는 
    컬럼 이름, 데이터 타입, 샘플 값 등의 정보를 제공합니다.
    
    Args:
        df (pd.DataFrame): 분석할 DataFrame
        
    Returns:
        dict: 컬럼 정보 딕셔너리
            - columns: 컬럼 이름 목록
            - dtypes: 컬럼별 데이터 타입
            - shape: DataFrame 크기 (행, 열)
            - sample_values: 각 컬럼의 첫 번째 값 (샘플)
    """
    logging.info(f"extract_column_info() 호출: DataFrame 크기={df.shape}")
    
    if df is None or df.empty:
        logging.warning("extract_column_info(): 빈 DataFrame 입력")
        return {
            "columns": [],
            "dtypes": {},
            "shape": (0, 0),
            "sample_values": {}
        }
    
    # 컬럼 정보 추출
    column_info = {
        "columns": list(df.columns),
        "dtypes": {col: str(df[col].dtype) for col in df.columns},
        "shape": df.shape,
        "sample_values": {}
    }
    
    # 각 컬럼의 첫 번째 비어있지 않은 값을 샘플로 추출
    for col in df.columns:
        non_null_values = df[col].dropna()
        if len(non_null_values) > 0:
            column_info["sample_values"][col] = str(non_null_values.iloc[0])
        else:
            column_info["sample_values"][col] = "N/A"
    
    logging.info(f"extract_column_info() 완료: {len(column_info['columns'])}개 컬럼 정보 추출")
    
    return column_info


def validate_dataframe_for_prompt(df: pd.DataFrame, required_columns: Optional[List[str]] = None) -> bool:
    """
    DataFrame이 프롬프트 생성에 적합한지 검증합니다.
    
    Args:
        df (pd.DataFrame): 검증할 DataFrame
        required_columns (Optional[List[str]]): 필수 컬럼 목록
        
    Returns:
        bool: 검증 통과 여부
        
    Raises:
        ValueError: 필수 컬럼이 누락된 경우
    """
    # 기본 검증
    if df is None:
        logging.error("DataFrame이 None입니다")
        return False
        
    if df.empty:
        logging.error("DataFrame이 비어있습니다")
        return False
    
    logging.info(f"validate_dataframe_for_prompt() 호출: DataFrame 크기={df.shape}")
    
    # 필수 컬럼 검증
    if required_columns:
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            error_msg = f"필수 컬럼 누락: {missing_columns}"
            logging.error(error_msg)
            raise ValueError(error_msg)
    
    logging.info("validate_dataframe_for_prompt() 완료: 검증 통과")
    return True
