# Payload 파싱 개선 계획

## 📋 문제 요약

MCP가 백엔드 V2 API로 POST 요청 시 다음 문제 발생:

1. ✅ 시간 파싱 실패: `"2025-09-04_21:15 ~2025-09-04_21:30"` 형식 처리 불가
2. ✅ ne_id, cell_id, swname이 "unknown"으로 설정됨
3. ✅ DB 조회된 실제 값이 payload에 반영되지 않음

## 🔍 원인 분석

### 1. 시간 파싱 로직 문제

**현재 로직** (`BackendPayloadBuilder._parse_analysis_period`):

```python
# 기대 형식: "2025-01-19_00:00~23:59" (같은 날짜)
date_part, time_part = time_str.split("_")  # "2025-01-19", "00:00~23:59"
start_time, end_time = time_part.split("~")  # "00:00", "23:59"
```

**실제 입력**:

```
"2025-09-04_21:15 ~2025-09-04_21:30"
      ↓
date_part = "2025-09-04"
time_part = "21:15 ~2025-09-04_21:30"
      ↓
time_part.split("~") → TOO MANY VALUES! ❌
```

### 2. 식별자 추출 문제

**현재 로직** (`BackendPayloadBuilder.build_v2_payload`):

```python
# filters에서만 추출 (사용자 입력값)
filters = analysis_request.get("filters", {})
ne_id = self._extract_identifier(filters.get("ne"), default="unknown")
cell_id = self._extract_identifier(filters.get("cellid"), default="unknown")
swname = self._extract_identifier(filters.get("host"), default="unknown")
```

**문제점**:

- `filters`에 값이 없으면 "unknown"으로 설정
- DB 조회된 실제 값(`processed_df`의 ne_key, name, index_name)을 사용하지 않음

### 3. 데이터 전달 누락

**AnalysisService 결과 구조**:

```python
{
    "status": "success",
    "peg_metrics": {
        "items": [...],  # ✅ PEG 데이터는 있음
        "statistics": {...}
    },
    "llm_analysis": {...},
    "metadata": {
        "filters": {...}  # ⚠️ 사용자 입력값만
    }
    # ❌ 실제 ne_id, cell_id, swname 없음!
}
```

## 🎯 해결 방안

### 방안 1: AnalysisService에서 실제 값 추출 및 전달 (권장)

**장점**:

- ✅ DB 조회된 **실제 값** 사용
- ✅ 데이터 일관성 보장
- ✅ filters가 비어있어도 동작

**구현**:

#### 1-1. `AnalysisService._assemble_final_result_with_processor()` 수정

```python
def _assemble_final_result_with_processor(
    self,
    request: Dict[str, Any],
    time_ranges: tuple[datetime, datetime, datetime, datetime],
    analyzed_peg_results: List[AnalyzedPEGResult],
    llm_result: Dict[str, Any],
) -> Dict[str, Any]:
    """최종 결과 조립 (DB 조회 값 추가)"""

    # 기존 로직
    response_payload = {
        "status": "success",
        "time_ranges": self._build_time_ranges_payload(request, time_ranges),
        "peg_metrics": {...},
        "llm_analysis": {...},
        "metadata": {...},
    }

    # ✨ 신규: DB 조회된 실제 식별자 추가
    if analyzed_peg_results:
        # analyzed_peg_results[0]에 ne_key, swname, cell_id 정보가 있음
        first_result = analyzed_peg_results[0]
        response_payload["db_identifiers"] = {
            "ne_id": getattr(first_result, "ne_key", None),
            "swname": getattr(first_result, "swname", None) or getattr(first_result, "host", None),
            "cell_id": self._extract_cell_id_from_index_name(
                getattr(first_result, "index_name", "")
            ),
        }

    return response_payload

def _extract_cell_id_from_index_name(self, index_name: str) -> Optional[str]:
    """index_name에서 cell_id 추출"""
    # 예: "PEG_420_1100" → "1100"
    if not index_name:
        return None
    parts = index_name.split("_")
    return parts[-1] if len(parts) >= 2 else None
```

#### 1-2. `BackendPayloadBuilder.build_v2_payload()` 수정

```python
@staticmethod
def build_v2_payload(
    analysis_result: dict,
    analysis_request: dict
) -> dict:
    """백엔드 V2 페이로드 생성 (DB 조회 값 우선)"""

    filters = analysis_request.get("filters", {})

    # ✨ 우선순위: DB 조회 값 > filters > "unknown"
    db_identifiers = analysis_result.get("db_identifiers", {})

    ne_id = (
        db_identifiers.get("ne_id") or
        BackendPayloadBuilder._extract_identifier(filters.get("ne")) or
        "unknown"
    )

    cell_id = (
        db_identifiers.get("cell_id") or
        BackendPayloadBuilder._extract_identifier(filters.get("cellid")) or
        "unknown"
    )

    swname = (
        db_identifiers.get("swname") or
        BackendPayloadBuilder._extract_identifier(filters.get("host") or filters.get("swname")) or
        "unknown"
    )

    # ... 나머지 로직
```

#### 1-3. 시간 파싱 로직 수정

```python
@staticmethod
def _parse_analysis_period(n_minus_1: str, n: str) -> Dict[str, str]:
    """
    분석 기간 파싱 (다양한 형식 지원)

    지원 형식:
    - "2025-01-19_00:00~23:59" (기존)
    - "2025-09-04_21:15 ~2025-09-04_21:30" (신규)
    """
    def parse_time_range(time_str: str) -> tuple:
        """
        시간 범위 파싱

        지원 형식:
        1. "2025-01-19_00:00~23:59" → ("2025-01-19 00:00:00", "2025-01-19 23:59:59")
        2. "2025-09-04_21:15 ~2025-09-04_21:30" → ("2025-09-04 21:15:00", "2025-09-04 21:30:00")
        """
        if not time_str or "~" not in time_str:
            return ("unknown", "unknown")

        try:
            # 공백 제거 및 정규화
            time_str = time_str.strip()

            # "~"로 분리
            parts = time_str.split("~")
            if len(parts) != 2:
                raise ValueError(f"Invalid format: expected 2 parts, got {len(parts)}")

            start_str, end_str = parts[0].strip(), parts[1].strip()

            # 각 부분 파싱
            start_datetime = parse_single_datetime(start_str)
            end_datetime = parse_single_datetime(end_str)

            return (start_datetime, end_datetime)

        except Exception as e:
            logger.warning(f"시간 범위 파싱 실패: {time_str}, error={e}")
            return ("unknown", "unknown")

    def parse_single_datetime(dt_str: str) -> str:
        """
        단일 날짜-시간 파싱

        지원 형식:
        - "2025-01-19_00:00" → "2025-01-19 00:00:00"
        - "2025-09-04_21:15" → "2025-09-04 21:15:00"
        - "23:59" (시간만) → "23:59:00" (날짜는 부모 컨텍스트에서)
        """
        if "_" in dt_str:
            # "날짜_시간" 형식
            date_part, time_part = dt_str.split("_", 1)
            return f"{date_part} {time_part}:00"
        else:
            # 시간만 (기존 형식 호환)
            return f"{time_part}:00"

    n_minus_1_start, n_minus_1_end = parse_time_range(n_minus_1)
    n_start, n_end = parse_time_range(n)

    return {
        "n_minus_1_start": n_minus_1_start,
        "n_minus_1_end": n_minus_1_end,
        "n_start": n_start,
        "n_end": n_end
    }
```

### 방안 2: processed_df를 analysis_result에 포함 (비권장)

**단점**:

- DataFrame 직렬화 필요
- Payload 크기 증가
- 데이터 중복

## 📝 구현 순서

### Phase 1: 시간 파싱 수정 (우선)

1. ✅ `BackendPayloadBuilder._parse_analysis_period()` 수정
2. ✅ 단위 테스트 추가
3. ✅ 기존 형식 호환성 확인

### Phase 2: 식별자 추출 개선

1. ✅ `AnalysisService._extract_db_identifiers()` 메서드 추가
2. ✅ `_assemble_final_result_with_processor()`에서 호출
3. ✅ `BackendPayloadBuilder`에서 우선순위 적용

### Phase 3: 테스트 및 검증

1. ✅ MCP 재시작
2. ✅ 로그 확인
3. ✅ 백엔드 POST 성공 여부 확인

## 🧪 테스트 케이스

### 시간 파싱

```python
# 케이스 1: 기존 형식 (호환성)
input = "2025-01-19_00:00~23:59"
expected = {
    "start": "2025-01-19 00:00:00",
    "end": "2025-01-19 23:59:59"
}

# 케이스 2: 신규 형식
input = "2025-09-04_21:15 ~2025-09-04_21:30"
expected = {
    "start": "2025-09-04 21:15:00",
    "end": "2025-09-04 21:30:00"
}

# 케이스 3: 공백 포함
input = "2025-09-04_21:15  ~  2025-09-04_21:30"
expected = {
    "start": "2025-09-04 21:15:00",
    "end": "2025-09-04 21:30:00"
}
```

### 식별자 추출

```python
# 케이스 1: DB 조회 값 우선
analysis_result = {
    "db_identifiers": {
        "ne_id": "nvgnb#10000",
        "cell_id": "2010",
        "swname": "host01"
    }
}
filters = {}
expected = {
    "ne_id": "nvgnb#10000",  # DB 값 사용
    "cell_id": "2010",
    "swname": "host01"
}

# 케이스 2: filters 폴백
analysis_result = {}
filters = {
    "ne": ["nvgnb#10000"],
    "cellid": ["2010"],
    "host": ["host01"]
}
expected = {
    "ne_id": "nvgnb#10000",  # filters 사용
    "cell_id": "2010",
    "swname": "host01"
}

# 케이스 3: 기본값
analysis_result = {}
filters = {}
expected = {
    "ne_id": "unknown",
    "cell_id": "unknown",
    "swname": "unknown"
}
```

## 📊 예상 로그 출력

### Before (현재)

```
WARNING - 시간 범위 파싱 실패: 2025-09-04_21:15 ~2025-09-04_21:30, error=too many values to unpack (expected 2)
INFO - 백엔드 V2 페이로드 생성 완료: ne_id=unknown, cell_id=unknown, swname=unknown, pegs=182
```

### After (수정 후)

```
INFO - 시간 범위 파싱 성공: N-1=2025-09-04 21:15:00 ~ 2025-09-04 21:30:00
INFO - DB 식별자 추출: ne_id=nvgnb#10000, cell_id=2010, swname=host01
INFO - 백엔드 V2 페이로드 생성 완료: ne_id=nvgnb#10000, cell_id=2010, swname=host01, pegs=182
```

## 🔗 관련 파일

- `3gpp_analysis_mcp/analysis_llm/services/analysis_service.py`
- `3gpp_analysis_mcp/analysis_llm/utils/backend_payload_builder.py`
- `3gpp_analysis_mcp/analysis_llm/main.py`
