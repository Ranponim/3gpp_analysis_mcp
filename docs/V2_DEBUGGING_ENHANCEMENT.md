# MCP → 백엔드 V2 API 디버깅 개선

## 📋 개요

MCP에서 백엔드 V2 API(`/api/analysis/results-v2/`)로 POST 요청 시 422 Unprocessable Entity 에러 발생 시 상세 디버깅을 위한 로그 개선

## 🎯 개선 사항

### 1. Payload 생성 단계 디버깅 강화

**파일**: `3gpp_analysis_mcp/analysis_llm/main.py` → `_build_backend_payload()`

**추가된 로그**:

```python
self.logger.debug(
    "✅ 페이로드 생성 완료:\n"
    "  최상위 키: %s\n"
    "  ne_id: %s\n"
    "  cell_id: %s\n"
    "  swname: %s\n"
    "  rel_ver: %s\n"
    "  analysis_period: %s\n"
    "  choi_result: %s\n"
    "  llm_analysis 키: %s\n"
    "  peg_comparisons 개수: %d\n"
    "  analysis_id: %s",
    list(payload.keys()),
    payload.get("ne_id"),
    payload.get("cell_id"),
    payload.get("swname"),
    payload.get("rel_ver"),
    payload.get("analysis_period"),
    "있음" if payload.get("choi_result") else "없음",
    list(payload.get("llm_analysis", {}).keys()),
    len(payload.get("peg_comparisons", [])),
    payload.get("analysis_id")
)
```

**목적**:

- Payload 구조 확인
- 필수 필드 누락 여부 확인
- JSON 직렬화 가능 여부 테스트

### 2. 422 에러 상세 로깅

**파일**: `3gpp_analysis_mcp/analysis_llm/main.py` → `_post_to_backend()`

**추가된 로그**:

```python
if e.response and e.response.status_code == 422:
    try:
        error_detail = e.response.json()
        self.logger.error(
            "❌ 백엔드 Validation 오류 (422):\n"
            "  응답 상세: %s\n"
            "  전송한 payload 키: %s\n"
            "  ne_id: %s, cell_id: %s, swname: %s\n"
            "  analysis_period: %s\n"
            "  llm_analysis 키: %s\n"
            "  peg_comparisons 개수: %d",
            error_detail,
            list(payload.keys()),
            payload.get("ne_id"),
            payload.get("cell_id"),
            payload.get("swname"),
            payload.get("analysis_period"),
            list(payload.get("llm_analysis", {}).keys()),
            len(payload.get("peg_comparisons", []))
        )
    except:
        self.logger.error("422 응답 파싱 실패: %s", e.response.text[:500])
```

**목적**:

- 백엔드 Pydantic Validation 에러 상세 확인
- 어떤 필드가 문제인지 즉시 파악
- 전송한 payload와 비교

## 🔍 디버깅 절차

### 1단계: MCP 로그 확인

MCP 컨테이너 로그를 확인하여 payload 생성 로그를 찾습니다:

```bash
docker logs kpi-mcp-llm 2>&1 | grep "페이로드 생성 완료"
```

**확인 사항**:

- ✅ `ne_id`, `cell_id`, `swname`가 "unknown"이 아닌지
- ✅ `analysis_period`가 올바른 Dict 형식인지
- ✅ `llm_analysis`가 최소한 빈 Dict가 아닌 키를 포함하는지
- ✅ `peg_comparisons` 개수가 0보다 큰지

### 2단계: 422 에러 상세 확인

422 에러 발생 시 상세 로그를 확인합니다:

```bash
docker logs kpi-mcp-llm 2>&1 | grep -A 20 "백엔드 Validation 오류"
```

**확인 사항**:

- ❌ FastAPI/Pydantic의 `detail` 필드에서 어떤 필드가 문제인지 확인
- ❌ `loc` (location)과 `msg` (message) 확인

**예시 응답**:

```json
{
  "detail": [
    {
      "loc": ["body", "analysis_period"],
      "msg": "field required",
      "type": "value_error.missing"
    },
    {
      "loc": ["body", "llm_analysis", "summary"],
      "msg": "none is not an allowed value",
      "type": "type_error.none.not_allowed"
    }
  ]
}
```

### 3단계: 백엔드 스키마와 비교

**백엔드 V2 스키마** (`backend/app/models/analysis_simplified.py`):

필수 필드:

- `ne_id: str` (필수)
- `cell_id: str` (필수)
- `swname: str` (필수)
- `analysis_period: Dict[str, str]` (필수)
- `llm_analysis: LLMAnalysis` (기본값 제공)
- `peg_comparisons: List[PegComparison]` (기본값 제공)

선택 필드:

- `rel_ver: Optional[str]`
- `choi_result: Optional[ChoiAlgorithmResult]`
- `analysis_id: Optional[str]`

### 4단계: Payload Builder 검증

**파일**: `3gpp_analysis_mcp/analysis_llm/utils/backend_payload_builder.py`

**검증 사항**:

1. **식별자 추출 로직**:

   ```python
   ne_id = BackendPayloadBuilder._extract_identifier(
       filters.get("ne"),
       default="unknown"
   )
   ```

   → 리스트면 첫 번째 값, 아니면 그대로 반환

2. **분석 기간 파싱**:

   ```python
   analysis_period = BackendPayloadBuilder._parse_analysis_period(
       analysis_request.get("n_minus_1"),
       analysis_request.get("n")
   )
   ```

   → "2025-01-19_00:00~23:59" 형식을 Dict로 변환

3. **LLM 분석 추출**:

   ```python
   llm_analysis = BackendPayloadBuilder._extract_llm_analysis(
       analysis_result
   )
   ```

   → 최소한 빈 Dict가 아닌 구조 반환

4. **PEG 비교 추출**:
   ```python
   peg_comparisons = BackendPayloadBuilder._extract_peg_comparisons(
       analysis_result
   )
   ```
   → 빈 리스트 또는 PegComparison 리스트 반환

## ⚠️ 자주 발생하는 문제

### 문제 1: `analysis_period`가 None

**원인**: `n_minus_1` 또는 `n` 값이 요청에 없음

**해결**:

```python
# analysis_request에 다음 필드가 있는지 확인
{
  "n_minus_1": "2025-01-19_00:00~23:59",
  "n": "2025-01-20_00:00~23:59"
}
```

### 문제 2: `llm_analysis.summary`가 None

**원인**: LLM 분석이 실패했거나 비어있음

**해결**:

```python
# BackendPayloadBuilder._extract_llm_analysis()에서
# 최소한 빈 문자열 반환하도록 수정
return {
    "summary": llm_data.get("summary") or "",  # None 대신 빈 문자열
    "issues": llm_data.get("issues", []),
    "recommendations": llm_data.get("recommended_actions", []),
    "confidence": llm_data.get("confidence"),
    "model_name": llm_data.get("model")
}
```

### 문제 3: `peg_comparisons`가 빈 리스트

**원인**: PEG 데이터가 없거나 추출 실패

**해결**: 백엔드 V2 스키마는 빈 리스트를 허용하므로 문제 없음

## 📊 로그 출력 예시

### 정상 케이스

```
INFO - 백엔드 V2 페이로드 생성 시작
DEBUG - ✅ 페이로드 생성 완료:
  최상위 키: ['ne_id', 'cell_id', 'swname', 'rel_ver', 'analysis_period', 'choi_result', 'llm_analysis', 'peg_comparisons', 'analysis_id']
  ne_id: nvgnb#10000
  cell_id: 2010
  swname: host01
  rel_ver: R23A
  analysis_period: {'n_minus_1_start': '2025-01-19 00:00:00', 'n_minus_1_end': '2025-01-19 23:59:59', 'n_start': '2025-01-20 00:00:00', 'n_end': '2025-01-20 23:59:59'}
  choi_result: 있음
  llm_analysis 키: ['summary', 'issues', 'recommendations', 'confidence', 'model_name']
  peg_comparisons 개수: 5
  analysis_id: analysis-abc123
DEBUG - JSON 직렬화 테스트 성공
INFO - 백엔드 POST 성공: status_code=201, elapsed=1.23s
```

### 422 에러 케이스

```
ERROR - ❌ 백엔드 Validation 오류 (422):
  응답 상세: {'detail': [{'loc': ['body', 'analysis_period'], 'msg': 'field required', 'type': 'value_error.missing'}]}
  전송한 payload 키: ['ne_id', 'cell_id', 'swname', 'llm_analysis', 'peg_comparisons']
  ne_id: nvgnb#10000, cell_id: 2010, swname: host01
  analysis_period: None
  llm_analysis 키: ['summary', 'issues', 'recommendations']
  peg_comparisons 개수: 5
```

**분석**: `analysis_period` 필드가 누락됨 → `n_minus_1`과 `n` 값 확인 필요

## 🔗 관련 파일

- **MCP Payload Builder**: `3gpp_analysis_mcp/analysis_llm/utils/backend_payload_builder.py`
- **MCP Main**: `3gpp_analysis_mcp/analysis_llm/main.py`
- **백엔드 V2 스키마**: `backend/app/models/analysis_simplified.py`
- **백엔드 V2 라우터**: `backend/app/routers/analysis_v2.py`
- **백엔드 V2 API 요약**: `docs/ANALYSIS_API_V2_SUMMARY.md`

## 🚀 다음 단계

1. MCP 재시작 후 로그 확인
2. 422 에러 발생 시 상세 로그 분석
3. Payload Builder 로직 수정 (필요 시)
4. 백엔드 스키마 검증 (필요 시)




