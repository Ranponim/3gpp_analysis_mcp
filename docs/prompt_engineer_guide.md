# 프롬프트 엔지니어 가이드 (3GPP 분석 MCP)

본 문서는 프롬프트 엔지니어가 코드 수정 없이 YAML 설정으로 프롬프트를 관리·배포하는 방법을 설명합니다. 현재 시스템은 YAML + Python 기본 포매팅(.format) 기반이며, 추후 Jinja2로 전환 가능하도록 설계되었습니다.

## 1. 파일 위치와 구조

- 기본 경로: `config/prompts/v1.yaml`
- 환경 변수로 경로 변경: `PROMPT_CONFIG_PATH=/path/to/custom.yaml`
- 파일 구조 개요:

```yaml
metadata:
  version: "1.0"
  description: "3GPP PEG 분석 프롬프트"
  format_type: "python_basic"
  created_date: "YYYY-MM-DD"
  variables:
    - name: n1_range
      type: string
    - name: n_range
      type: string
    - name: data_preview
      type: string
prompts:
  enhanced: |
    [컨텍스트]
    - 기간 n-1: {n1_range}
    - 기간 n: {n_range}
    {data_preview}
  specific_pegs: |
    - 대상 PEG: {selected_pegs_str}
    - 기간 n-1: {n1_range}
    - 기간 n: {n_range}
    {data_preview}
```

## 2. 변수(Placeholder) 사용 규칙

- Python `.format()` 규칙을 따릅니다: `{변수명}` 형태.
- 사용 가능한 변수는 `metadata.variables`에 기입해 합의합니다.
- 현재 주요 변수:
  - `n1_range`: 기간 n-1 텍스트
  - `n_range`: 기간 n 텍스트
  - `data_preview`: 표 형태의 데이터 미리보기 문자열
  - `selected_pegs_str`: 특정 PEG 목록(쉼표 구분)

주의: 템플릿에 정의한 모든 변수는 런타임에 제공되어야 하며, 누락 시 오류가 발생합니다.

## 3. 유효성 검증(Validation)

- YAML 로드 시 Pydantic 스키마로 검증합니다:
  - `prompts` 키가 존재하고 문자열 템플릿이어야 함
  - 비어있는 템플릿 금지
- 잘못된 파일/빈 파일/파싱 오류는 즉시 명확한 오류로 표시됩니다.

## 4. 프롬프트 타입 관리

- 사용 가능한 타입 확인:
  - 코드: `PromptLoader.get_available_prompt_types()`
  - 기본 제공: `enhanced`, `specific_pegs` (필요 시 `overall` 등 추가 가능)
- 새 타입 추가 방법:
  1. `metadata.variables`에 필요한 변수 추가 (협의 필수)
  2. `prompts.<새이름>` 키에 템플릿 작성
  3. 단위 테스트로 변수 누락/포맷 검증 추가 권장

## 5. 런타임 동작

- 코드에서는 `PromptLoader('config/prompts/v1.yaml').format_prompt('enhanced', n1_range='...', n_range='...', data_preview='...')` 형태로 사용합니다.
- 통합 경로에서는 실패 시 최소 문자열 폴백을 사용하도록 보호되어 있습니다(안전장치).

## 6. 베스트 프랙티스

- 문서화: 변경 시 `metadata.description`, `version` 갱신
- 간결성: 모델 토큰 효율을 위해 불필요한 장문/중복 제거
- 가이드 레일: 출력 JSON 스키마를 템플릿에 명시해 일관성 확보
- 국제화: 현재 한국어 중심, 다국어가 필요하면 별도 템플릿 분기 권장
- 변수 검증: 새 변수 도입 시 유닛 테스트에 누락 케이스 추가

## 7. 변경 테스트(로컬)

- 단일 테스트 실행 예시:

```powershell
python -m pytest -q analysis_llm/tests/config/test_prompt_loader_schema.py
```

- 실패 시 확인 포인트:
  - 환경변수 `PROMPT_CONFIG_PATH`가 올바른지
  - YAML 구문 오류(들여쓰기/콜론/따옴표)
  - 템플릿에 있는 모든 변수가 런타임에 전달되는지

## 8. FAQ

- Q. 템플릿 변수 하나만 추가하고 싶어요.
  - A. `metadata.variables`에 목록 추가 후 템플릿에 `{변수}` 삽입. 사용처 코드에서 해당 변수를 제공해야 합니다.
- Q. 기본 파일이 아닌 다른 템플릿을 쓰고 싶어요.
  - A. `PROMPT_CONFIG_PATH` 환경 변수를 설정하거나, 코드에서 `PromptLoader(custom_path)`를 사용하세요.
- Q. Jinja2로 바꾸고 싶어요.
  - A. `metadata.format_type` 전환 및 로더 확장이 필요합니다. 기존 YAML/변수 목록은 재사용 가능합니다.

## 9. 문의/기여

- 템플릿 정책/스키마 변경 제안은 PR 또는 이슈로 등록해 주세요.
- 리뷰 체크리스트에 토큰/가독성/출력 스키마 준수 항목을 포함해 주세요.
