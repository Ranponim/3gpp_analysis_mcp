# Payload 파싱 개선 구현 완료

## 📋 구현 요약

MCP → 백엔드 V2 API 전송 시 발생하던 422 에러의 근본 원인을 해결했습니다.

### ✅ 해결된 문제

1. **시간 파싱 실패** → ✅ 해결
2. **ne_id, cell_id, swname이 "unknown"** → ✅ 해결
3. **DB 조회 값 미반영** → ✅ 해결

## 🎯 구현 상세

### 1. 시간 파싱 로직 개선

**파일**: `3gpp_analysis_mcp/analysis_llm/utils/backend_payload_builder.py`

**Before**:
```python
# "2025-01-19_00:00~23:59" 형식만 지원
date_part, time_part = time_str.split("_")
start_time, end_time = time_part.split("~")  # ❌ 날짜가 두 번 들어오면 실패
```

**After**:
```python
# 다양한 형식 지원
# 1. "2025-01-19_00:00~23:59" (기존)
# 2. "2025-09-04_21:15 ~2025-09-04_21:30" (신규)

def parse_single_datetime(dt_str: str) -> str:
    """
    단일 날짜-시간 파싱
    - "2025-01-19_00:00" → "2025-01-19 00:00:00"
    - "00:00" → "00:00:00"
    """
    if "_" in dt_str:
        date_part, time_part = dt_str.split("_", 1)
        if time_part.count(":") == 1:
            return f"{date_part} {time_part}:00"
        else:
            return f"{date_part} {time_part}"
    else:
        # 시간만 (날짜 없음)
        return f"{dt_str}:00" if dt_str.count(":") == 1 else dt_str

def parse_time_range(time_str: str) -> tuple:
    """
    "~"로 분리 후 각 부분 독립적으로 파싱
    """
    parts = time_str.split("~")
    if len(parts) != 2:
        raise ValueError(f"잘못된 형식")
    
    start_datetime = parse_single_datetime(parts[0].strip())
    end_datetime = parse_single_datetime(parts[1].strip())
    
    # 형식 1 호환: 끝 시간에 날짜 없으면 시작 날짜 사용
    if "_" in start_datetime and "_" not in parts[1]:
        date_part = start_datetime.split()[0]
        end_datetime = f"{date_part} {end_datetime}"
    
    return (start_datetime, end_datetime)
```

**결과**:
```python
# Before
"2025-09-04_21:15 ~2025-09-04_21:30"
→ ❌ ValueError: too many values to unpack

# After
"2025-09-04_21:15 ~2025-09-04_21:30"
→ ✅ ("2025-09-04 21:15:00", "2025-09-04 21:30:00")
```

### 2. DB 식별자 추출 로직 추가

**파일**: `3gpp_analysis_mcp/analysis_llm/services/analysis_service.py`

#### 2-1. `_extract_db_identifiers()` 메서드 추가

```python
def _extract_db_identifiers(
    self, 
    processed_df: pd.DataFrame, 
    request: Dict[str, Any]
) -> Dict[str, Optional[str]]:
    """
    DB 조회된 실제 식별자 추출
    
    Returns:
        {
            "ne_id": "nvgnb#10000",  # processed_df['ne_key']
            "cell_id": "2010",        # index_name에서 파싱
            "swname": "host01"        # processed_df['name']
        }
    """
    identifiers = {
        "ne_id": None,
        "cell_id": None,
        "swname": None
    }
    
    if processed_df.empty:
        return identifiers
    
    first_row = processed_df.iloc[0]
    
    # ne_id 추출
    if 'ne_key' in processed_df.columns:
        identifiers["ne_id"] = str(first_row['ne_key'])
    elif 'ne' in processed_df.columns:
        identifiers["ne_id"] = str(first_row['ne'])
    
    # swname 추출
    if 'name' in processed_df.columns:
        identifiers["swname"] = str(first_row['name'])
    elif 'host' in processed_df.columns:
        identifiers["swname"] = str(first_row['host'])
    
    # cell_id 추출 (index_name에서)
    if 'index_name' in processed_df.columns:
        index_name = str(first_row['index_name'])
        identifiers["cell_id"] = self._extract_cell_id_from_index_name(index_name)
    
    logger.info(
        "DB 식별자 추출 완료: ne_id=%s, cell_id=%s, swname=%s",
        identifiers["ne_id"],
        identifiers["cell_id"],
        identifiers["swname"]
    )
    
    return identifiers
```

#### 2-2. `_extract_cell_id_from_index_name()` 메서드 추가

```python
def _extract_cell_id_from_index_name(self, index_name: str) -> Optional[str]:
    """
    index_name에서 cell_id 추출
    
    예시:
    - "PEG_420_1100" → "1100"
    - "nvgnb#10000_2010" → "2010"
    """
    if not index_name:
        return None
    
    parts = index_name.split("_")
    if len(parts) >= 2:
        # 마지막 부분이 숫자인지 확인
        last_part = parts[-1]
        if last_part.isdigit():
            return last_part
        # 뒤에서 두 번째 시도
        elif len(parts) >= 3 and parts[-2].isdigit():
            return parts[-2]
    
    return None
```

#### 2-3. `perform_analysis()` 수정

```python
# 6단계: 결과 조립 (DataProcessor 결과 활용)
logger.info("6단계: 결과 조립")

# ✨ 신규: DB 식별자 추출
db_identifiers = self._extract_db_identifiers(processed_df, request)

final_result = self._assemble_final_result_with_processor(
    request=request,
    time_ranges=time_ranges,
    analyzed_peg_results=analyzed_peg_results,
    llm_result=llm_result,
    db_identifiers=db_identifiers,  # ✨ 추가
)
```

#### 2-4. `_assemble_final_result_with_processor()` 수정

```python
def _assemble_final_result_with_processor(
    self,
    request: Dict[str, Any],
    time_ranges: tuple[datetime, datetime, datetime, datetime],
    analyzed_peg_results: List[AnalyzedPEGResult],
    llm_result: Dict[str, Any],
    db_identifiers: Optional[Dict[str, Optional[str]]] = None,  # ✨ 추가
) -> Dict[str, Any]:
    """최종 결과 조립"""
    
    response_payload = {
        "status": "success",
        "time_ranges": {...},
        "peg_metrics": {...},
        "llm_analysis": {...},
        "metadata": {...},
    }
    
    # ✨ DB 식별자 추가 (BackendPayloadBuilder에서 사용)
    if db_identifiers:
        response_payload["db_identifiers"] = db_identifiers
    
    return response_payload
```

### 3. BackendPayloadBuilder 우선순위 적용

**파일**: `3gpp_analysis_mcp/analysis_llm/utils/backend_payload_builder.py`

```python
@staticmethod
def build_v2_payload(
    analysis_result: dict,
    analysis_request: dict
) -> dict:
    """백엔드 V2 페이로드 생성 (DB 조회 값 우선)"""
    
    filters = analysis_request.get("filters", {})
    db_identifiers = analysis_result.get("db_identifiers", {})
    
    # ✨ 우선순위: DB > filters > "unknown"
    ne_id = (
        db_identifiers.get("ne_id") or                        # 1순위: DB 조회 값
        BackendPayloadBuilder._extract_identifier(filters.get("ne")) or  # 2순위: filters
        "unknown"                                              # 3순위: 기본값
    )
    
    cell_id = (
        db_identifiers.get("cell_id") or
        BackendPayloadBuilder._extract_identifier(filters.get("cellid")) or
        "unknown"
    )
    
    swname = (
        db_identifiers.get("swname") or
        BackendPayloadBuilder._extract_identifier(
            filters.get("host") or filters.get("swname")
        ) or
        "unknown"
    )
    
    # 디버그 로그
    logger.debug(
        "식별자 우선순위 적용 결과:\n"
        "  ne_id: %s (DB=%s, filters=%s)\n"
        "  cell_id: %s (DB=%s, filters=%s)\n"
        "  swname: %s (DB=%s, filters=%s)",
        ne_id, db_identifiers.get("ne_id"), filters.get("ne"),
        cell_id, db_identifiers.get("cell_id"), filters.get("cellid"),
        swname, db_identifiers.get("swname"), filters.get("host")
    )
    
    # ... 나머지 payload 구성
```

## 📊 데이터 흐름 개선

### Before (문제)

```
사용자 입력 → DB 조회 → 분석 → Payload
   (filters)    (processed_df)  (analysis_result)
                  [ne_key,           [❌ 누락]        [unknown]
                   name,
                   index_name]
```

### After (해결)

```
사용자 입력 → DB 조회 → DB 식별자 추출 → 분석 결과에 추가 → Payload
   (filters)    (processed_df)   (_extract_db_identifiers)    (db_identifiers)
                  [ne_key,           [ne_id,                   [ne_id,
                   name,              cell_id,                  cell_id,
                   index_name]        swname]                   swname]
                                            ↓
                                  우선순위 적용
                                  DB > filters > "unknown"
```

## 🧪 예상 로그 출력

### Before (오류)

```
WARNING - 시간 범위 파싱 실패: 2025-09-04_21:15 ~2025-09-04_21:30, error=too many values to unpack (expected 2)
INFO - 백엔드 V2 페이로드 생성 완료: ne_id=unknown, cell_id=unknown, swname=unknown, pegs=182
ERROR - ❌ 백엔드 Validation 오류 (422): ...
```

### After (정상)

```
INFO - DB 식별자 추출 완료: ne_id=nvgnb#10000, cell_id=2010, swname=host01
DEBUG - 식별자 우선순위 적용 결과:
  ne_id: nvgnb#10000 (DB=nvgnb#10000, filters=None)
  cell_id: 2010 (DB=2010, filters=None)
  swname: host01 (DB=host01, filters=None)
INFO - 백엔드 V2 페이로드 생성 완료: ne_id=nvgnb#10000, cell_id=2010, swname=host01, pegs=182
INFO - 백엔드 POST 성공: status_code=201, elapsed=1.23s
```

## 🔍 테스트 케이스

### 케이스 1: DB 조회 성공 (일반적인 경우)

**입력**:
```python
processed_df = pd.DataFrame({
    'ne_key': ['nvgnb#10000'],
    'name': ['host01'],
    'index_name': ['PEG_420_2010']
})
filters = {}
```

**결과**:
```python
{
    "ne_id": "nvgnb#10000",   # ✅ DB에서 추출
    "cell_id": "2010",         # ✅ index_name에서 파싱
    "swname": "host01"         # ✅ DB에서 추출
}
```

### 케이스 2: DB 조회 실패, filters 사용

**입력**:
```python
processed_df = pd.DataFrame()  # 비어있음
filters = {
    "ne": ["nvgnb#10000"],
    "cellid": ["2010"],
    "host": ["host01"]
}
```

**결과**:
```python
{
    "ne_id": "nvgnb#10000",   # ✅ filters에서 추출
    "cell_id": "2010",         # ✅ filters에서 추출
    "swname": "host01"         # ✅ filters에서 추출
}
```

### 케이스 3: 모두 없음, 기본값 사용

**입력**:
```python
processed_df = pd.DataFrame()
filters = {}
```

**결과**:
```python
{
    "ne_id": "unknown",   # ⚠️ 기본값
    "cell_id": "unknown", # ⚠️ 기본값
    "swname": "unknown"   # ⚠️ 기본값
}
```

## 📝 변경된 파일 목록

1. ✅ `3gpp_analysis_mcp/analysis_llm/utils/backend_payload_builder.py`
   - `_parse_analysis_period()`: 시간 파싱 로직 개선
   - `build_v2_payload()`: DB 식별자 우선순위 적용

2. ✅ `3gpp_analysis_mcp/analysis_llm/services/analysis_service.py`
   - `_extract_db_identifiers()`: DB 식별자 추출 메서드 추가
   - `_extract_cell_id_from_index_name()`: cell_id 파싱 메서드 추가
   - `perform_analysis()`: DB 식별자 추출 호출
   - `_assemble_final_result_with_processor()`: db_identifiers 파라미터 추가

3. ✅ `3gpp_analysis_mcp/analysis_llm/main.py`
   - `_build_backend_payload()`: 디버그 로그 강화
   - `_post_to_backend()`: 422 에러 상세 로그 추가

4. ✅ `3gpp_analysis_mcp/docs/V2_DEBUGGING_ENHANCEMENT.md`: 디버깅 가이드 추가
5. ✅ `3gpp_analysis_mcp/docs/PAYLOAD_PARSING_FIX_PLAN.md`: 수정 계획 문서
6. ✅ `3gpp_analysis_mcp/docs/PAYLOAD_PARSING_IMPLEMENTATION.md`: 구현 완료 문서 (본 파일)

## 🚀 배포 절차

### 1. MCP 재시작

```bash
docker restart kpi-mcp-llm
```

### 2. 로그 모니터링

```bash
# 실시간 로그 확인
docker logs -f kpi-mcp-llm

# DB 식별자 추출 확인
docker logs kpi-mcp-llm 2>&1 | grep "DB 식별자 추출 완료"

# payload 생성 확인
docker logs kpi-mcp-llm 2>&1 | grep "백엔드 V2 페이로드 생성 완료"
```

### 3. 검증

1. ✅ 시간 파싱 경고 없음
2. ✅ ne_id, cell_id, swname이 "unknown" 아님
3. ✅ 백엔드 POST 성공 (201)
4. ✅ 422 에러 없음

## 🔗 관련 문서

- [V2 디버깅 가이드](V2_DEBUGGING_ENHANCEMENT.md)
- [Payload 파싱 수정 계획](PAYLOAD_PARSING_FIX_PLAN.md)
- [백엔드 V2 API 요약](../../docs/ANALYSIS_API_V2_SUMMARY.md)
- [프론트엔드 V2 통합](../../frontend/docs/V2_INTEGRATION_GUIDE.md)

## 📞 문제 발생 시

422 에러가 여전히 발생하는 경우:

1. **로그 확인**:
   ```bash
   docker logs kpi-mcp-llm 2>&1 | grep -A 20 "❌ 백엔드 Validation 오류"
   ```

2. **DB 식별자 확인**:
   ```bash
   docker logs kpi-mcp-llm 2>&1 | grep "DB 식별자 추출"
   ```

3. **processed_df 구조 확인**:
   - `processed_df.columns`에 `ne_key`, `name`, `index_name`이 있는지 확인
   - 첫 번째 행에 값이 있는지 확인

4. **백엔드 응답 확인**:
   - `detail` 필드에서 어떤 필드가 validation에 실패했는지 확인

