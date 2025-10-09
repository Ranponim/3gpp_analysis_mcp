# 환경변수 설정 가이드

이 문서는 Cell 성능 LLM 분석기의 환경변수 설정 방법을 설명합니다.

## 환경변수 설정 방법

### 1. .env 파일 생성 (권장)

프로젝트 루트에 `.env` 파일을 생성하고 아래 설정을 추가하세요:

```bash
# .env 파일 예시
# ===========================================
# Cell 성능 LLM 분석기 환경 설정 파일
# ===========================================

# --- LLM API 설정 ---
LLM_ENDPOINTS=http://10.251.204.93:10000,http://100.105.188.117:8888
LLM_MODEL=Gemma-3-27B
LLM_TIMEOUT=180
LLM_RETRY_TOTAL=3
LLM_RETRY_BACKOFF=1.0
LLM_TEMPERATURE=0.2
LLM_MAX_TOKENS=4096

# --- 프롬프트 설정 ---
DEFAULT_MAX_PROMPT_TOKENS=24000
DEFAULT_MAX_PROMPT_CHARS=80000
DEFAULT_SPECIFIC_MAX_ROWS=500
DEFAULT_MAX_RAW_STR=4000
DEFAULT_MAX_RAW_ARRAY=100

# --- 토큰 추정 설정 ---
CHARS_PER_TOKEN_RATIO=3.5
FALLBACK_CHARS_PER_TOKEN_RATIO=4.0
PROMPT_TRUNCATE_BUFFER=200
STRING_SUMMARY_LIMIT=2000
PROMPT_PREVIEW_ROWS=200

# --- HTTP 설정 ---
HTTP_USER_AGENT=Cell-Performance-LLM-Analyzer/1.0
MAX_PAYLOAD_SIZE_MB=1

# --- 백엔드 API 설정 ---
DEFAULT_BACKEND_URL=http://165.213.69.30:8000/api/analysis/results/

# --- 데이터베이스 설정 ---
DEFAULT_DB_HOST=127.0.0.1
DEFAULT_DB_PORT=5432
DEFAULT_DB_USER=postgres
DEFAULT_DB_PASSWORD=your_password_here
DEFAULT_DB_NAME=postgres

# --- 테이블 및 컬럼 설정 ---
DEFAULT_TABLE=summary
DEFAULT_TIME_COLUMN=datetime
DEFAULT_PEG_COLUMN=peg_name
DEFAULT_VALUE_COLUMN=value
DEFAULT_NE_COLUMN=ne
DEFAULT_CELL_COLUMN=cellid
DEFAULT_HOST_COLUMN=host

# --- 타임존 설정 ---
DEFAULT_TZ_OFFSET=+09:00

# --- 로깅 설정 ---
LOG_LEVEL=INFO
LOG_FORMAT=%(asctime)s - %(levelname)s - %(message)s
LOG_DATE_FORMAT=%Y-%m-%d %H:%M:%S
```

### 2. 시스템 환경변수 설정

```bash
# Linux/macOS
export DEFAULT_DB_HOST="127.0.0.1"
export DEFAULT_DB_PORT="5432"
export DEFAULT_DB_USER="postgres"
export DEFAULT_DB_PASSWORD="your_password"
export DEFAULT_DB_NAME="postgres"

# Windows
set DEFAULT_DB_HOST=127.0.0.1
set DEFAULT_DB_PORT=5432
set DEFAULT_DB_USER=postgres
set DEFAULT_DB_PASSWORD=your_password
set DEFAULT_DB_NAME=postgres
```

## 환경변수 우선순위

설정값은 다음 순서로 적용됩니다:

1. **요청 파라미터** (MCP tool 호출 시 전달되는 값)
2. **환경변수** (.env 파일 또는 시스템 환경변수)
3. **기본값** (코드에 하드코딩된 기본값)

## 주요 환경변수 설명

### LLM API 설정

- `LLM_ENDPOINTS`: LLM 서버 엔드포인트 목록 (쉼표로 구분)
- `LLM_MODEL`: 사용할 LLM 모델명
- `LLM_TIMEOUT`: 요청 타임아웃 (초)
- `LLM_TEMPERATURE`: 생성 온도 (0.0-1.0)
- `LLM_MAX_TOKENS`: 최대 생성 토큰 수

### 데이터베이스 설정

- `DEFAULT_DB_HOST`: PostgreSQL 호스트 주소
- `DEFAULT_DB_PORT`: PostgreSQL 포트 번호
- `DEFAULT_DB_USER`: 데이터베이스 사용자명
- `DEFAULT_DB_PASSWORD`: 데이터베이스 비밀번호
- `DEFAULT_DB_NAME`: 데이터베이스 이름

### 테이블 및 컬럼 설정

- `DEFAULT_TABLE`: 기본 테이블명
- `DEFAULT_TIME_COLUMN`: 시간 컬럼명
- `DEFAULT_PEG_COLUMN`: PEG 이름 컬럼명
- `DEFAULT_VALUE_COLUMN`: 값 컬럼명
- `DEFAULT_NE_COLUMN`: NE 컬럼명
- `DEFAULT_CELL_COLUMN`: 셀 ID 컬럼명
- `DEFAULT_HOST_COLUMN`: 호스트 컬럼명

### PEG (Performance Event Group) 설정

- `PEG_DEFAULT_AGGREGATION`: 기본 집계 방법 (기본값: average)
- `PEG_ENABLE_DERIVED`: 파생 PEG 활성화 (기본값: true)
- `PEG_DEFAULT_TIME_WINDOW`: 기본 시간 윈도우 (기본값: 1h)
- `PEG_MAX_FORMULA_COMPLEXITY`: 최대 수식 복잡도 (기본값: 100)
- `PEG_USE_CHOI`: Choi Deterministic 판정 알고리즘 사용 여부 (기본값: false)

### JSONB 파싱 설정

- `JSONB_MAX_RECURSION_DEPTH`: JSONB 재귀 파싱 최대 깊이 (기본값: 5)
  - 중첩된 index_name 구조를 파싱할 때 최대 재귀 깊이 제한
  - 값이 클수록 더 깊은 중첩 구조 처리 가능하지만 성능에 영향
  - 권장 범위: 3~10

### 프롬프트 설정

- `DEFAULT_MAX_PROMPT_TOKENS`: 최대 프롬프트 토큰 수
- `DEFAULT_MAX_PROMPT_CHARS`: 최대 프롬프트 문자 수
- `DEFAULT_SPECIFIC_MAX_ROWS`: 특정 PEG 분석 시 최대 행 수

### 토큰 추정 설정

- `CHARS_PER_TOKEN_RATIO`: 토큰 추정을 위한 문자/토큰 비율 (기본값: 3.5)
- `FALLBACK_CHARS_PER_TOKEN_RATIO`: 대체 토큰 추정 비율 (기본값: 4.0)
- `PROMPT_TRUNCATE_BUFFER`: 프롬프트 자르기 시 여유 공간 (기본값: 200자)
- `STRING_SUMMARY_LIMIT`: 문자열 요약 최대 길이 (기본값: 2000자)
- `PROMPT_PREVIEW_ROWS`: 프롬프트 미리보기 행 수 (기본값: 200행)

### HTTP 설정

- `HTTP_USER_AGENT`: HTTP 요청 시 사용할 User-Agent
- `MAX_PAYLOAD_SIZE_MB`: 최대 payload 크기 제한 (MB 단위, 기본값: 1MB)

### 로깅 설정

- `LOG_LEVEL`: 로그 레벨 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `LOG_FORMAT`: 로그 포맷 문자열
- `LOG_DATE_FORMAT`: 날짜 포맷 문자열

## 보안 주의사항

- `.env` 파일은 버전 관리에 포함하지 마세요
- 데이터베이스 비밀번호 등 민감한 정보는 환경변수로만 설정하세요
- 프로덕션 환경에서는 더 강력한 비밀번호를 사용하세요

## 예시 사용법

```python
# 환경변수가 설정된 상태에서 MCP tool 호출
request = {
    "n_minus_1": "2025-07-01_00:00~2025-07-01_23:59",
    "n": "2025-07-02_00:00~2025-07-02_23:59",
    # DB 설정은 환경변수에서 자동으로 가져옴
    # 필요시 요청에서 오버라이드 가능
    "db": {
        "host": "custom-db-host",
        "password": "custom-password"
    }
}
```
