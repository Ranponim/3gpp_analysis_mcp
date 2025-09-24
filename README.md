# 3GPP Analysis MCP (Model Context Protocol)

## 📋 개요

3GPP KPI 대시보드 시스템의 MCP (Model Context Protocol) 분석 모듈입니다. PostgreSQL의 Raw KPI 데이터를 LLM으로 분석하고, 결과를 백엔드로 전달하는 역할을 담당합니다.

## 🏗️ 아키텍처

```
PostgreSQL (Raw KPI Data) → MCP (analysis_llm.py) → Backend (FastAPI) → MongoDB (Analysis Results) → Frontend (React)
```

### 주요 구성요소

1. **PostgreSQL**: Raw KPI/PEG 데이터 저장소 - 실시간 데이터 조회용
2. **MCP (Model Context Protocol)**: `analysis_llm.py` - 별도 환경에서 실행 (HTTP API로 호출)
3. **Backend**: FastAPI 라우터 - LLM 분석 API 제공, 두 DB 연동 관리
4. **MongoDB**: 분석 결과 및 사용자 설정 저장소 (analysis_results, user_preferences, statistics_results)
5. **Frontend**: React - 분석 트리거/결과 조회 UI

## 🔧 구현된 기능

### 1) MCP 분석 서비스

#### 분석 요청 처리

```python
# MCP에서 받는 요청 구조
{
  "user_id": "default",
  "n_minus_1": "2024-01-01_00:00~2024-01-01_23:59",
  "n": "2024-01-02_00:00~2024-01-02_23:59",
  "enable_mock": false,
  "db_config": {
    "host": "127.0.0.1", "port": 5432,
    "user": "postgres", "password": "secret",
    "dbname": "netperf", "table": "summary"
  }
}
```

#### 응답 구조

```json
{
  "status": "success",
  "time_ranges": {
    "n_minus_1": {"start": "...", "end": "...", "duration_hours": ...},
    "n": {"start": "...", "end": "...", "duration_hours": ...}
  },
  "peg_metrics": {
    "items": [
      {
        "peg_name": "UL_throughput_avg",
        "n_minus_1_value": 102.3,
        "n_value": 110.5,
        "absolute_change": 8.2,
        "percentage_change": 8.01,
        "llm_analysis_summary": "상승 추세"
      }
    ],
    "statistics": {
      "total_pegs": 12,
      "complete_data_pegs": 10,
      "incomplete_data_pegs": 2,
      "positive_changes": 7,
      "negative_changes": 3,
      "no_change": 0,
      "avg_percentage_change": 3.42
    }
  },
  "llm_analysis": {
    "summary": "셀 전반의 Throughput이 안정적으로 상승했습니다.",
    "issues": ["RACH 지연은 여전히 관찰됨"],
    "recommended_actions": ["RACH 파라미터 튜닝"],
    "peg_insights": {
      "Random_access_preamble_count": "파라미터 조정 필요",
      "UL_throughput_avg": "일관된 상승"
    },
    "confidence": 0.78,
    "model": "claude-3.5"
  },
  "metadata": {
    "workflow_version": "4.0",
    "processing_timestamp": "2025-09-24T02:12:33.456Z",
    "request_id": "req-abc123",
    "analysis_id": "analysis-xyz789",
    "analysis_type": "enhanced",
    "selected_pegs": ["UL_throughput_avg", "DL_throughput_avg"],
    "filters": {"ne": ["nvgnb#10000"], "cellid": ["2010"]},
    "total_pegs": 12,
    "complete_data_pegs": 10,
    "source": "mcp.analysis_service"
  },
  "legacy_payload": {
    "results": [...],
    "analysis": ...,
    "analysis_raw_compact": ...
  }
}
```

### 2) 데이터 구조 (DTO)

#### AnalysisRequest

```python
@dataclass
class AnalysisRequest:
    user_id: str
    n_minus_1: str
    n: str
    enable_mock: bool = False
    db_config: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AnalysisRequest":
        # 통합된 요청 파싱 로직
        pass
```

#### AnalysisResponse

```python
@dataclass
class AnalysisResponse:
    status: str
    time_ranges: Dict[str, Any]
    peg_metrics: PegMetricsPayload
    llm_analysis: LLMAnalysisSummary
    metadata: AnalysisMetadataPayload
    legacy_payload: Optional[Dict[str, Any]] = None
```

### 3) 주요 서비스

#### AnalysisService

- 전체 분석 워크플로우 오케스트레이션
- PEGProcessingService와 LLMAnalysisService 위임
- 최종 결과를 DTO 구조로 조립

#### DataProcessor

- PEG 데이터 변환 및 정규화
- DataFrame을 AnalyzedPEGResult dataclass로 직접 변환
- LLM 분석 결과 통합

#### LLMAnalysisService

- LLM 모델 호출 및 분석 실행
- 분석 결과를 구조화된 형태로 반환

## ⚙️ 설정 및 배포

### 필수 의존성

```txt
# MCP 분석 서비스
pandas
numpy
scipy
requests
pydantic
dataclasses
```

### 환경 변수

```bash
# LLM API 설정
ANTHROPIC_API_KEY=your_api_key
OPENAI_API_KEY=your_api_key

# 데이터베이스 설정
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=password
DB_NAME=netperf
```

## 🧪 테스트 방법

### 1) MCP 서비스 테스트

```python
# MCP 분석 서비스 직접 테스트
from analysis_llm.services.analysis_service import AnalysisService

service = AnalysisService()
result = await service.perform_analysis(request_data)
```

### 2) 통합 테스트

```python
# 백엔드와의 통합 테스트
import requests

response = requests.post("http://localhost:8000/api/analysis/trigger-llm-analysis",
                        json=request_data)
```

## 🔍 데이터 흐름

1. **Backend → MCP**: 분석 요청 및 PostgreSQL 연결 설정 전달
2. **MCP → PostgreSQL**: Raw KPI 데이터 쿼리
3. **MCP → LLM**: KPI 데이터 분석 요청
4. **MCP → Backend**: 구조화된 분석 결과 반환
5. **Backend → MongoDB**: 분석 결과 저장

## ⚠️ 현재 제한사항

- MCP 미설정/오류 시 Mock 폴백(자동)
- 실시간 상태는 폴링 기반(추후 SSE/WebSocket 가능)

## 🔄 향후 개선

- 실시간 스트리밍 업데이트(SSE/WebSocket)
- 권장사항/원인분석 자동 생성 강화
- 대량 KPI 성능 튜닝(서버/클라이언트)

_문서 업데이트: 2025-01-14 (DTO 구조 및 비동기 처리 반영)_
