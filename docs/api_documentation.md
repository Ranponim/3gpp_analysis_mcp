# API 문서

## 📋 개요

3GPP Analysis MCP API는 5G 네트워크 성능 데이터(PEG: Performance Event Group)를 분석하는 RESTful API입니다.
Clean Architecture 기반으로 구현되어 높은 성능과 안정성을 제공합니다.

## 🚀 기본 정보

- **Base URL**: `http://localhost:8000`
- **API Version**: v1.0
- **Content-Type**: `application/json`
- **Character Encoding**: UTF-8
- **응답 시간**: 평균 18.1ms

## 📊 주요 엔드포인트

### 1. 셀 성능 분석

#### POST /analyze_cell_performance_with_llm

5G 셀의 성능 데이터를 LLM으로 분석합니다.

**요청 구조:**

```json
{
  "n_minus_1": "string (required)",
  "n": "string (required)",
  "output_dir": "string (optional)",
  "backend_url": "string (optional)",
  "table": "string (optional, default: 'summary')",
  "analysis_type": "string (optional, default: 'enhanced')",
  "enable_mock": "boolean (optional, default: false)",
  "max_prompt_tokens": "integer (optional, default: 8000)",
  "db": {
    "host": "string (required)",
    "port": "integer (optional, default: 5432)",
    "dbname": "string (required)",
    "user": "string (required)",
    "password": "string (required)"
  },
  "columns": {
    "time": "string (optional, default: 'datetime')",
    "peg_name": "string (optional, default: 'peg_name')",
    "value": "string (optional, default: 'value')",
    "ne": "string (optional, default: 'ne')",
    "cellid": "string (optional, default: 'cellid')",
    "host": "string (optional, default: 'host')"
  },
  "filters": {
    "ne": "string (optional)",
    "cellid": "array of strings (optional)",
    "host": "string (optional)"
  },
  "selected_pegs": "array of strings (optional)",
  "peg_definitions": {
    "derived_peg_name": "string (formula)"
  }
}
```

**필수 매개변수:**

| 매개변수      | 타입   | 설명                  | 예시                                  |
| ------------- | ------ | --------------------- | ------------------------------------- |
| `n_minus_1`   | string | N-1 기간 시간 범위    | `"2025-01-01_09:00~2025-01-01_18:00"` |
| `n`           | string | N 기간 시간 범위      | `"2025-01-02_09:00~2025-01-02_18:00"` |
| `db.host`     | string | 데이터베이스 호스트   | `"localhost"`                         |
| `db.dbname`   | string | 데이터베이스 이름     | `"3gpp_analysis"`                     |
| `db.user`     | string | 데이터베이스 사용자   | `"postgres"`                          |
| `db.password` | string | 데이터베이스 비밀번호 | `"your_password"`                     |

**선택적 매개변수:**

| 매개변수            | 타입    | 기본값       | 설명                                               |
| ------------------- | ------- | ------------ | -------------------------------------------------- |
| `analysis_type`     | string  | `"enhanced"` | 분석 유형: `"overall"`, `"enhanced"`, `"specific"` |
| `enable_mock`       | boolean | `false`      | Mock 모드 활성화 (테스트용)                        |
| `table`             | string  | `"summary"`  | 조회할 테이블명                                    |
| `max_prompt_tokens` | integer | `8000`       | LLM 프롬프트 최대 토큰 수                          |

**요청 예시:**

```json
{
  "n_minus_1": "2025-01-01_09:00~2025-01-01_18:00",
  "n": "2025-01-02_09:00~2025-01-02_18:00",
  "analysis_type": "enhanced",
  "enable_mock": true,
  "db": {
    "host": "localhost",
    "port": 5432,
    "dbname": "3gpp_analysis",
    "user": "postgres",
    "password": "your_password"
  },
  "filters": {
    "ne": "nvgnb#10001",
    "cellid": ["cell_001", "cell_002", "cell_003"],
    "host": "192.168.1.100"
  },
  "selected_pegs": [
    "preamble_count",
    "response_count",
    "success_count",
    "handover_count"
  ],
  "peg_definitions": {
    "success_rate": "response_count/preamble_count*100",
    "efficiency_ratio": "success_count/response_count*100"
  }
}
```

**응답 구조:**

```json
{
  "status": "string",
  "analysis_id": "string",
  "timestamp": "string (ISO 8601)",
  "execution_time_ms": "number",
  "peg_statistics": {
    "total_pegs": "integer",
    "processed_pegs": "integer",
    "derived_pegs": "integer",
    "success_rate": "number",
    "average_change_rate": "number"
  },
  "analysis_stats": {
    "n_minus_1_records": "integer",
    "n_records": "integer",
    "processing_time_ms": "number",
    "llm_tokens_used": "integer"
  },
  "llm_analysis": {
    "integrated_analysis": "string",
    "specific_peg_analysis": "string",
    "recommendations": "string",
    "model_used": "string",
    "tokens_used": "integer"
  },
  "processed_data": "array of objects",
  "error_details": "object (오류 시에만)"
}
```

**성공 응답 예시:**

```json
{
  "status": "success",
  "analysis_id": "analysis_20250919_160000",
  "timestamp": "2025-09-19T16:00:00Z",
  "execution_time_ms": 18.1,
  "peg_statistics": {
    "total_pegs": 5,
    "processed_pegs": 5,
    "derived_pegs": 2,
    "success_rate": 100.0,
    "average_change_rate": 8.5
  },
  "analysis_stats": {
    "n_minus_1_records": 1250,
    "n_records": 1380,
    "processing_time_ms": 12.3,
    "llm_tokens_used": 1250
  },
  "llm_analysis": {
    "integrated_analysis": "전반적인 성능 개선이 관찰됨. 주요 KPI들이 안정적으로 향상되었습니다.",
    "specific_peg_analysis": "preamble_count: +10.2%, response_count: +8.7%, success_count: +12.1%",
    "recommendations": "현재 최적화 상태를 유지하고 지속적인 모니터링을 권장합니다.",
    "model_used": "gemini-2.5-pro",
    "tokens_used": 1250
  },
  "processed_data": [
    {
      "peg_name": "preamble_count",
      "n_minus_1_value": 1000.5,
      "n_value": 1102.3,
      "change_pct": 10.2,
      "trend": "increasing",
      "has_complete_data": true
    }
  ]
}
```

**오류 응답 예시:**

```json
{
  "status": "error",
  "analysis_id": "analysis_20250919_160001",
  "timestamp": "2025-09-19T16:00:01Z",
  "execution_time_ms": 5.2,
  "error_details": {
    "error_type": "ValidationError",
    "message": "시간 형식이 올바르지 않습니다",
    "field_name": "n_minus_1",
    "field_value": "invalid_time_format",
    "validation_rule": "YYYY-MM-DD_HH:MM~YYYY-MM-DD_HH:MM",
    "hint": "올바른 형식: 2025-01-01_09:00~2025-01-01_18:00"
  }
}
```

### 2. 헬스체크 엔드포인트

#### GET /health

애플리케이션의 전반적인 상태를 확인합니다.

**응답:**

```json
{
  "status": "healthy",
  "timestamp": "2025-09-19T16:00:00Z",
  "version": "1.0.0",
  "uptime_seconds": 3600,
  "components": {
    "database": "healthy",
    "llm_service": "healthy",
    "configuration": "healthy"
  }
}
```

#### GET /health/db

데이터베이스 연결 상태를 확인합니다.

**응답:**

```json
{
  "status": "healthy",
  "connection_pool": {
    "active_connections": 2,
    "max_connections": 5,
    "available_connections": 3
  },
  "last_query_time_ms": 3.2
}
```

#### GET /health/llm

LLM 서비스 연결 상태를 확인합니다.

**응답:**

```json
{
  "status": "healthy",
  "endpoints": [
    {
      "url": "http://10.251.204.93:10000",
      "status": "healthy",
      "response_time_ms": 45.2
    },
    {
      "url": "http://100.105.188.117:8888",
      "status": "healthy",
      "response_time_ms": 52.1
    }
  ],
  "failover_enabled": true
}
```

## 🔧 시간 형식 지원

### 지원되는 시간 형식

| 형식            | 예시                                      | 설명                         |
| --------------- | ----------------------------------------- | ---------------------------- |
| **기본 형식**   | `2025-01-01_09:00~2025-01-01_18:00`       | 시작시간~종료시간            |
| **날짜만**      | `2025-01-01`                              | 해당 날짜 전체 (00:00~23:59) |
| **하이픈 구분** | `2025-01-01-09:00~2025-01-01-18:00`       | 하이픈 구분자 지원           |
| **초 단위**     | `2025-01-01_09:00:30~2025-01-01_18:30:45` | 초 단위 정밀도               |

### 타임존 처리

- **기본 타임존**: `+09:00` (KST)
- **UTC 변환**: 자동 변환 지원
- **환경 변수**: `APP_TIMEZONE`, `DATA_TIMEZONE`으로 설정 가능

## 🎯 분석 유형

### 1. Overall Analysis (`"overall"`)

```json
{
  "analysis_type": "overall"
}
```

- **목적**: 전체적인 성능 트렌드 파악
- **특징**: 간결한 요약, 빠른 실행
- **토큰 사용량**: 낮음 (~800 토큰)

### 2. Enhanced Analysis (`"enhanced"`)

```json
{
  "analysis_type": "enhanced"
}
```

- **목적**: 상세한 성능 분석 및 인사이트
- **특징**: 심화 분석, 권장사항 제공
- **토큰 사용량**: 중간 (~1200 토큰)

### 3. Specific PEGs Analysis (`"specific"`)

```json
{
  "analysis_type": "specific",
  "selected_pegs": ["preamble_count", "response_count"]
}
```

- **목적**: 특정 PEG에 대한 집중 분석
- **특징**: 맞춤형 분석, 세부 메트릭
- **토큰 사용량**: 가변 (PEG 수에 따라)

## 🔍 필터링 옵션

### 네트워크 요소 필터

```json
{
  "filters": {
    "ne": "nvgnb#10001", // 특정 NE만 조회
    "cellid": ["cell_001", "cell_002"], // 특정 셀들만 조회
    "host": "192.168.1.100" // 특정 호스트만 조회
  }
}
```

### PEG 선택 필터

```json
{
  "selected_pegs": [
    "preamble_count", // 프리앰블 카운트
    "response_count", // 응답 카운트
    "success_count", // 성공 카운트
    "handover_count" // 핸드오버 카운트
  ]
}
```

### 파생 PEG 정의

```json
{
  "peg_definitions": {
    "success_rate": "response_count/preamble_count*100",
    "efficiency_ratio": "success_count/response_count*100",
    "handover_rate": "handover_count/total_attempts*100"
  }
}
```

**지원되는 연산자:**

- **산술**: `+`, `-`, `*`, `/`
- **함수**: `abs()`, `round()`, `min()`, `max()`
- **상수**: 숫자 리터럴

## 🛡️ 오류 코드 및 처리

### HTTP 상태 코드

| 코드  | 상태                  | 설명                  |
| ----- | --------------------- | --------------------- |
| `200` | OK                    | 성공적인 분석 완료    |
| `400` | Bad Request           | 잘못된 요청 매개변수  |
| `422` | Unprocessable Entity  | 검증 실패             |
| `500` | Internal Server Error | 서버 내부 오류        |
| `503` | Service Unavailable   | 외부 서비스 연결 실패 |

### 오류 응답 구조

```json
{
  "status": "error",
  "analysis_id": "analysis_20250919_160001",
  "timestamp": "2025-09-19T16:00:01Z",
  "execution_time_ms": 5.2,
  "error_details": {
    "error_type": "ValidationError",
    "message": "사용자 친화적 오류 메시지",
    "field_name": "n_minus_1",
    "field_value": "invalid_value",
    "validation_rule": "expected_format",
    "hint": "해결 방법 제시"
  }
}
```

### 주요 오류 유형

#### 1. 시간 파싱 오류 (`TimeParsingError`)

```json
{
  "error_type": "TimeParsingError",
  "message": "시간 형식이 올바르지 않습니다",
  "error_code": "FORMAT_ERROR",
  "hint": "올바른 형식: YYYY-MM-DD_HH:MM~YYYY-MM-DD_HH:MM"
}
```

#### 2. 데이터베이스 오류 (`DatabaseError`)

```json
{
  "error_type": "DatabaseError",
  "message": "데이터베이스 연결 실패",
  "connection_info": {
    "host": "localhost",
    "database": "3gpp_analysis",
    "masked_error": "connection timeout"
  }
}
```

#### 3. LLM 서비스 오류 (`LLMError`)

```json
{
  "error_type": "LLMError",
  "message": "LLM API 호출 실패",
  "status_code": 503,
  "endpoint": "http://10.251.204.93:10000",
  "is_retryable": true
}
```

#### 4. 검증 오류 (`RequestValidationError`)

```json
{
  "error_type": "RequestValidationError",
  "message": "필수 필드가 누락되었습니다",
  "field_name": "db.host",
  "validation_rule": "required_field"
}
```

## 🎛️ 고급 설정

### 성능 튜닝

```json
{
  "max_prompt_tokens": 12000, // 더 상세한 분석
  "db": {
    "pool_size": 10, // 연결 풀 크기 (환경변수)
    "timeout": 30 // 쿼리 타임아웃 (환경변수)
  }
}
```

### Mock 모드

개발 및 테스트 환경에서 외부 의존성 없이 실행:

```json
{
  "enable_mock": true,
  "analysis_type": "enhanced"
}
```

**Mock 모드 특징:**

- 실제 데이터베이스 연결 불필요
- 가상 PEG 데이터 생성
- 가상 LLM 응답 반환
- 빠른 테스트 실행 (< 5ms)

## 📊 성능 특성

### 응답 시간

| 시나리오          | 평균 응답시간 | 95th Percentile |
| ----------------- | ------------- | --------------- |
| **Overall 분석**  | 12.5ms        | 18.2ms          |
| **Enhanced 분석** | 18.1ms        | 25.3ms          |
| **Specific 분석** | 15.7ms        | 22.1ms          |
| **Mock 모드**     | 3.2ms         | 5.1ms           |

### 처리량

- **동시 요청**: 최대 50개
- **처리량**: 45.9 요청/초
- **메모리 사용량**: 평균 95MB

### 제한사항

| 항목          | 제한값 | 설명                          |
| ------------- | ------ | ----------------------------- |
| **요청 크기** | 10MB   | JSON 요청 최대 크기           |
| **PEG 수**    | 100개  | 한 번에 처리 가능한 PEG 수    |
| **시간 범위** | 30일   | 최대 분석 가능 기간           |
| **필터 항목** | 1000개 | cellid 등 배열 필터 최대 크기 |

## 🔒 보안 고려사항

### 입력 검증

1. **SQL 인젝션 방지**: 모든 쿼리 매개변수화
2. **타입 검증**: Pydantic 모델 기반 런타임 검증
3. **범위 검증**: 시간 범위, 숫자 범위 검증
4. **길이 제한**: 문자열 필드 최대 길이 제한

### 민감한 정보 처리

- **데이터베이스 비밀번호**: 로그에 노출되지 않음
- **API 키**: 마스킹 처리 (\*\*\*)
- **오류 메시지**: 민감한 정보 제외하고 반환

## 🧪 테스트 및 개발

### API 테스트

```bash
# 기본 분석 요청
curl -X POST http://localhost:8000/analyze_cell_performance_with_llm \
  -H "Content-Type: application/json" \
  -d '{
    "n_minus_1": "2025-01-01_09:00~2025-01-01_18:00",
    "n": "2025-01-02_09:00~2025-01-02_18:00",
    "enable_mock": true,
    "db": {
      "host": "localhost",
      "dbname": "test",
      "user": "test",
      "password": "test"
    }
  }'

# 헬스체크
curl http://localhost:8000/health

# 데이터베이스 헬스체크
curl http://localhost:8000/health/db
```

### Python 클라이언트 예시

```python
import requests
import json

# API 클라이언트 클래스
class AnalysisAPIClient:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url

    def analyze_cell_performance(self, request_data: dict) -> dict:
        """셀 성능 분석 요청"""
        url = f"{self.base_url}/analyze_cell_performance_with_llm"

        response = requests.post(
            url,
            json=request_data,
            headers={"Content-Type": "application/json"},
            timeout=60
        )

        return response.json()

    def health_check(self) -> dict:
        """헬스체크"""
        response = requests.get(f"{self.base_url}/health")
        return response.json()

# 사용 예시
client = AnalysisAPIClient()

request_data = {
    "n_minus_1": "2025-01-01_09:00~2025-01-01_18:00",
    "n": "2025-01-02_09:00~2025-01-02_18:00",
    "enable_mock": True,
    "analysis_type": "enhanced",
    "db": {
        "host": "localhost",
        "dbname": "3gpp_analysis",
        "user": "postgres",
        "password": "your_password"
    }
}

try:
    result = client.analyze_cell_performance(request_data)
    print(f"분석 결과: {result['status']}")
    print(f"실행시간: {result['execution_time_ms']}ms")
    print(f"LLM 분석: {result['llm_analysis']['integrated_analysis']}")

except requests.exceptions.RequestException as e:
    print(f"API 호출 실패: {e}")
```

## 📈 모니터링 및 메트릭

### 로그 구조

```json
{
  "timestamp": "2025-09-19T16:00:00Z",
  "level": "INFO",
  "message": "분석 완료: 성공",
  "function": "analyze_peg_data",
  "execution_time_ms": 18.1,
  "request_id": "req_123",
  "peg_count": 5,
  "status": "success",
  "memory_usage_mb": 45.2,
  "db_query_time_ms": 3.2,
  "llm_call_time_ms": 12.5
}
```

### 성능 메트릭

#### 응답시간 분포

- **P50 (중간값)**: 15.2ms
- **P95**: 25.3ms
- **P99**: 42.1ms
- **최대**: 65.7ms

#### 리소스 사용량

- **CPU**: 평균 15%
- **메모리**: 평균 95MB (피크 150MB)
- **네트워크**: 평균 50KB/요청

## 🔄 버전 관리

### API 버전 정책

- **Major Version**: 호환성 없는 변경
- **Minor Version**: 하위 호환 기능 추가
- **Patch Version**: 버그 수정

### 현재 버전: v1.0.0

**변경 이력:**

- `v1.0.0`: Clean Architecture 리팩토링 완료
- `v0.9.0`: 성능 최적화 완료
- `v0.8.0`: 통합 테스트 추가
- `v0.7.0`: 단위 테스트 완료

## 📚 추가 리소스

### 관련 문서

- **[아키텍처 가이드](architecture.md)**: 상세한 시스템 설계
- **[배포 가이드](deployment_guide.md)**: 프로덕션 배포 절차
- **[운영 가이드](operations_guide.md)**: 모니터링 및 운영 절차

### 개발 도구

- **OpenAPI Spec**: `/docs` (Swagger UI)
- **ReDoc**: `/redoc` (대안 API 문서)
- **Health Check**: `/health` (시스템 상태)

---

이 API는 높은 성능과 안정성을 제공하는 프로덕션 준비 완료 시스템입니다. 🚀

## Prompt Configuration API

- Path resolution order: ctor `config_path` > env `PROMPT_CONFIG_PATH` > default `config/prompts/v1.yaml`
- Basic usage:

```python
from analysis_llm.config.prompt_loader import PromptLoader
from analysis_llm.utils.data_formatter import format_dataframe_for_prompt

def build_enhanced_prompt(df, n1, n):
    loader = PromptLoader()  # will honor PROMPT_CONFIG_PATH
    preview = format_dataframe_for_prompt(df)
    return loader.format_prompt(
        'enhanced', n1_range=n1, n_range=n, data_preview=preview
    )
```

- Metadata & types:

```python
loader.get_metadata()
loader.get_available_prompt_types()
```

- Reload on file change:

```python
loader.reload_config()
```
