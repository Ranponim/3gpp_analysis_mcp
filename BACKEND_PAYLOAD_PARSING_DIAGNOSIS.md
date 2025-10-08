# ne_id, cell_id, swname 파싱 실패 원인 및 해결 방안

## 🔴 문제 현황

### 로그 분석

```log
info - 백엔드 V2 페이로드 생성 시작
Debug - 식별자 우선순위 적용 결과:
  ne_id: unknown (DB=None, filters=None)
  cell_id: unknown (DB=None, filters=None)
  swname: unknown (DB=None, filters=None)
info - 백엔드 V2 페이로드 생성 완료: ne_id=unknown, cell_id=unknown, swname=unknown, pegs=182
```

### 증상

- ✅ **PEG 데이터**: 182개 정상 파싱
- ❌ **ne_id**: "unknown" (DB=None, filters=None)
- ❌ **cell_id**: "unknown" (DB=None, filters=None)
- ❌ **swname**: "unknown" (DB=None, filters=None)

### 문제 요약

1. DB에서 182개의 PEG를 조회했다면, **당연히 ne_key, name, index_name도 함께 조회됨**
2. 하지만 `BackendPayloadBuilder`에는 **DB=None**으로 전달됨
3. **데이터 흐름 중간에 식별자 정보가 소실**됨

## 🔍 근본 원인 분석

### 데이터 흐름 추적

```
1️⃣ DB 조회 (DatabaseRepository.fetch_peg_data)
   ↓
   결과: [
     {
       "datetime": "2025-09-04 21:15:00",
       "ne_key": "nvgnb#10000",          ← ✅ 있음
       "name": "host01",                  ← ✅ 있음
       "index_name": "PEG_420_2010",      ← ✅ 있음
       "peg_name": "RRC Setup SR",
       "value": 99.5
     },
     ...
   ]

2️⃣ DataFrame 변환 (PEGProcessingService._retrieve_raw_peg_data)
   ↓
   n1_df = pd.DataFrame(n1_data)
   컬럼: [datetime, ne_key, name, index_name, peg_name, value]  ← ✅ 있음

3️⃣ 집계 작업 (PEGProcessingService._process_with_calculator)
   ↓
   n1_aggregated = n1_df.groupby("peg_name")["value"].mean()
                                              ^^^^^^^^^^^
                                              ❌ 여기서 ne_key, name, index_name 소실!
   ↓
   processed_df 컬럼: [peg_name, period, avg_value, change_pct]  ← ❌ 식별자 없음!

4️⃣ 식별자 추출 시도 (AnalysisService._extract_db_identifiers)
   ↓
   if 'ne_key' in processed_df.columns:  # ← ❌ False!
       identifiers["ne_id"] = ...
   ↓
   결과: {"ne_id": None, "cell_id": None, "swname": None}  ← ❌ 모두 None

5️⃣ Payload 생성 (BackendPayloadBuilder.build_v2_payload)
   ↓
   ne_id = (
       db_identifiers.get("ne_id") or      # ← None
       filters.get("ne") or                # ← None
       "unknown"                           # ← ✅ 기본값 사용
   )
   ↓
   결과: ne_id="unknown", cell_id="unknown", swname="unknown"
```

### 핵심 문제

**`groupby("peg_name")["value"].mean()`는 오직 `peg_name`과 `value` 컬럼만 사용**합니다.

```python
# Before 집계
n1_df.columns = [datetime, ne_key, name, index_name, peg_name, value]
                            ↓
# After 집계
n1_aggregated.columns = [peg_name, value]
                        ↑
                        ne_key, name, index_name 소실!
```

이것은 **pandas groupby의 기본 동작**입니다:

- `groupby("peg_name")["value"]`는 `peg_name`과 `value` 컬럼만 선택
- 다른 컬럼들은 자동으로 제외됨

## 🎯 해결 방안

### ✅ 해결 완료: 방안 1 - 식별자 보존

**수정 파일**: `3gpp_analysis_mcp/analysis_llm/services/peg_processing_service.py`

**수정 내용**:

```python
def _process_with_calculator(
    self, n1_df: pd.DataFrame, n_df: pd.DataFrame, peg_config: Dict[str, Any]
) -> pd.DataFrame:
    """PEGCalculator를 사용하여 데이터 처리 (식별자 보존)"""

    # ✨ 1단계: 집계 전 식별자 추출 (DB 조회 값 보존)
    metadata = {}
    source_df = n1_df if not n1_df.empty else n_df

    if not source_df.empty:
        first_row = source_df.iloc[0]

        if "ne_key" in source_df.columns:
            metadata["ne_key"] = str(first_row["ne_key"]) if pd.notna(first_row["ne_key"]) else None

        if "name" in source_df.columns:
            metadata["name"] = str(first_row["name"]) if pd.notna(first_row["name"]) else None

        if "index_name" in source_df.columns:
            metadata["index_name"] = str(first_row["index_name"]) if pd.notna(first_row["index_name"]) else None

        logger.debug(
            "식별자 추출 (집계 전): ne_key=%s, name=%s, index_name=%s",
            metadata.get("ne_key"),
            metadata.get("name"),
            metadata.get("index_name")
        )

    # 2단계: 집계 작업 (기존 로직)
    n1_aggregated = n1_df.groupby("peg_name")["value"].mean().reset_index()
    n_aggregated = n_df.groupby("peg_name")["value"].mean().reset_index()
    # ... (중략)

    # 3단계: 식별자 정보를 모든 행에 추가 (복원)
    if metadata:
        for key, value in metadata.items():
            if value is not None:
                processed_df[key] = value  # ← 모든 행에 동일 값 추가
                logger.debug("컬럼 추가: %s=%s", key, value)

    logger.info(
        "PEGCalculator 처리 완료: %d행 (식별자 보존: ne_key=%s, name=%s, index_name=%s)",
        len(processed_df),
        metadata.get("ne_key"),
        metadata.get("name"),
        metadata.get("index_name")
    )

    return processed_df
```

### 작동 원리

#### Before (문제)

```python
# DB 조회
n1_df = pd.DataFrame({
    'ne_key': ['nvgnb#10000', 'nvgnb#10000', ...],  # 182개
    'name': ['host01', 'host01', ...],
    'index_name': ['PEG_420_2010', 'PEG_420_2010', ...],
    'peg_name': ['RRC Setup SR', 'ERAB Setup SR', ...],
    'value': [99.5, 98.2, ...]
})

# 집계 (groupby)
n1_aggregated = n1_df.groupby("peg_name")["value"].mean()
# ↓
# 결과: peg_name, value만 남음
# ❌ ne_key, name, index_name 소실!

processed_df.columns = ['peg_name', 'period', 'avg_value', 'change_pct']
```

#### After (해결)

```python
# DB 조회
n1_df = pd.DataFrame({
    'ne_key': ['nvgnb#10000', 'nvgnb#10000', ...],
    'name': ['host01', 'host01', ...],
    'index_name': ['PEG_420_2010', 'PEG_420_2010', ...],
    'peg_name': ['RRC Setup SR', 'ERAB Setup SR', ...],
    'value': [99.5, 98.2, ...]
})

# ✨ 1단계: 집계 전 식별자 저장
metadata = {
    'ne_key': 'nvgnb#10000',    # ← first_row에서 추출
    'name': 'host01',
    'index_name': 'PEG_420_2010'
}

# 2단계: 집계 (groupby)
n1_aggregated = n1_df.groupby("peg_name")["value"].mean()
# ↓
# 결과: peg_name, value만 남음

# 3단계: 식별자 복원
processed_df['ne_key'] = metadata['ne_key']          # ← 모든 행에 추가
processed_df['name'] = metadata['name']
processed_df['index_name'] = metadata['index_name']

processed_df.columns = ['peg_name', 'period', 'avg_value', 'change_pct',
                        'ne_key', 'name', 'index_name']  # ← ✅ 식별자 포함!
```

## 📊 예상 결과

### Before (오류)

```
DEBUG - 식별자 우선순위 적용 결과:
  ne_id: unknown (DB=None, filters=None)
  cell_id: unknown (DB=None, filters=None)
  swname: unknown (DB=None, filters=None)
```

### After (정상)

```
DEBUG - 식별자 추출 (집계 전): ne_key=nvgnb#10000, name=host01, index_name=PEG_420_2010
DEBUG - 컬럼 추가: ne_key=nvgnb#10000
DEBUG - 컬럼 추가: name=host01
DEBUG - 컬럼 추가: index_name=PEG_420_2010
INFO - PEGCalculator 처리 완료: 364행 (식별자 보존: ne_key=nvgnb#10000, name=host01, index_name=PEG_420_2010)
INFO - DB 식별자 추출 완료: ne_id=nvgnb#10000, cell_id=2010, swname=host01
DEBUG - 식별자 우선순위 적용 결과:
  ne_id: nvgnb#10000 (DB=nvgnb#10000, filters=None)
  cell_id: 2010 (DB=2010, filters=None)
  swname: host01 (DB=host01, filters=None)
INFO - 백엔드 V2 페이로드 생성 완료: ne_id=nvgnb#10000, cell_id=2010, swname=host01, pegs=182
```

## 🧪 검증 방법

### 1. MCP 재시작

```bash
docker restart kpi-mcp-llm
```

### 2. 로그 확인

```bash
# 식별자 추출 확인
docker logs -f kpi-mcp-llm | grep -E "(식별자 추출|컬럼 추가|ne_key|name|index_name)"
```

### 3. 기대 로그 순서

1. ✅ `식별자 추출 (집계 전): ne_key=..., name=..., index_name=...`
2. ✅ `컬럼 추가: ne_key=...`
3. ✅ `컬럼 추가: name=...`
4. ✅ `컬럼 추가: index_name=...`
5. ✅ `PEGCalculator 처리 완료: 364행 (식별자 보존: ne_key=..., name=..., index_name=...)`
6. ✅ `DB 식별자 추출 완료: ne_id=..., cell_id=..., swname=...`
7. ✅ `식별자 우선순위 적용 결과: ne_id=... (DB=..., filters=...)`
8. ✅ `백엔드 V2 페이로드 생성 완료: ne_id=..., cell_id=..., swname=..., pegs=182`

## 📝 변경 파일 목록

### ✅ 완료된 수정

1. **`3gpp_analysis_mcp/analysis_llm/utils/backend_payload_builder.py`**

   - `_parse_analysis_period()`: 시간 파싱 로직 개선
   - `build_v2_payload()`: DB 식별자 우선순위 적용

2. **`3gpp_analysis_mcp/analysis_llm/services/analysis_service.py`**

   - `_extract_db_identifiers()`: DB 식별자 추출 메서드 추가
   - `_extract_cell_id_from_index_name()`: cell_id 파싱 메서드 추가
   - `perform_analysis()`: DB 식별자 추출 호출
   - `_assemble_final_result_with_processor()`: db_identifiers 파라미터 추가

3. **`3gpp_analysis_mcp/analysis_llm/services/peg_processing_service.py`** ⭐ 핵심
   - `_process_with_calculator()`: 집계 전 식별자 추출 및 복원 로직 추가

### 📁 문서

4. **`3gpp_analysis_mcp/PAYLOAD_PARSING_FIX_PLAN.md`**: 수정 계획
5. **`3gpp_analysis_mcp/PAYLOAD_PARSING_IMPLEMENTATION.md`**: 구현 완료
6. **`3gpp_analysis_mcp/BACKEND_PAYLOAD_PARSING_DIAGNOSIS.md`**: 근본 원인 분석 (본 파일)

## 🎯 핵심 인사이트

### pandas groupby의 특성

```python
# groupby는 지정된 컬럼만 유지
df.groupby("peg_name")["value"].mean()
           ^^^^^^^^^^^  ^^^^^^^
           그룹 기준     집계 대상

# 결과: peg_name, value만 남음
# 다른 컬럼(ne_key, name, index_name)은 자동 제외됨
```

### 식별자 보존 전략

**문제**: 집계 작업 중 식별자 소실  
**해결**: 집계 전 추출 → 집계 후 복원

```python
# 1. 집계 전: 첫 번째 행에서 식별자 추출
metadata = {
    'ne_key': first_row['ne_key'],
    'name': first_row['name'],
    'index_name': first_row['index_name']
}

# 2. 집계 작업 (기존 로직)
aggregated_df = df.groupby("peg_name")["value"].mean()

# 3. 집계 후: 식별자를 모든 행에 추가
for key, value in metadata.items():
    aggregated_df[key] = value  # 브로드캐스팅
```

**가정**: 한 번의 분석은 **단일 ne_id, cell_id, swname**에 대해 수행됨  
→ 첫 번째 행의 식별자 = 모든 행의 식별자

## 🚨 왜 이 문제가 발견되지 않았는가?

### 1. PEG 데이터는 정상 동작

- `groupby("peg_name")["value"].mean()`는 PEG 집계를 정상 수행
- 182개의 PEG가 정상 파싱됨
- **기능적으로는 문제 없음**

### 2. 식별자는 백엔드 전송 시에만 필요

- 분석 자체는 식별자가 없어도 동작
- **백엔드 V2 API 연동 시에만 문제 발생**
- V2 API가 추가되기 전에는 발견되지 않음

### 3. filters 폴백 메커니즘이 없음

- 기존에는 `filters`에서 추출했을 것으로 추정
- 하지만 현재 로그에서 `filters=None`
- **이중 안전장치가 작동하지 않음**

## 🔗 관련 문서

- [Payload 파싱 수정 계획](PAYLOAD_PARSING_FIX_PLAN.md)
- [Payload 파싱 구현 완료](PAYLOAD_PARSING_IMPLEMENTATION.md)
- [백엔드 V2 API 스키마](../docs/ANALYSIS_API_V2_SUMMARY.md)

## 📞 문제 재발 방지

### 향후 개선 사항

1. **DataFrame 구조 검증 로직 추가**

   ```python
   def _validate_processed_df_structure(processed_df: pd.DataFrame) -> None:
       """processed_df에 필수 식별자 컬럼이 있는지 검증"""
       required_columns = ['ne_key', 'name', 'index_name']
       missing_columns = [col for col in required_columns if col not in processed_df.columns]

       if missing_columns:
           logger.warning(
               "processed_df에 식별자 컬럼이 누락됨: %s (현재 컬럼: %s)",
               missing_columns,
               list(processed_df.columns)
           )
   ```

2. **단위 테스트 추가**

   ```python
   def test_peg_processing_preserves_identifiers():
       """PEG 처리 시 식별자가 보존되는지 확인"""
       n1_df = pd.DataFrame({
           'ne_key': ['nvgnb#10000'],
           'name': ['host01'],
           'index_name': ['PEG_420_2010'],
           'peg_name': ['RRC Setup SR'],
           'value': [99.5]
       })

       service = PEGProcessingService(...)
       processed_df = service._process_with_calculator(n1_df, n1_df, {})

       assert 'ne_key' in processed_df.columns
       assert 'name' in processed_df.columns
       assert 'index_name' in processed_df.columns
       assert processed_df['ne_key'].iloc[0] == 'nvgnb#10000'
   ```

3. **로깅 강화**
   - 각 단계에서 DataFrame 컬럼 구조 로그 출력
   - 식별자 추출 성공/실패 명시적 로그

---

**결론**: `backend_payload_builder.py` 자체는 정상이었고, **상위 데이터 파이프라인(PEGProcessingService)에서 식별자가 소실**되는 것이 근본 원인이었습니다. 🎯
