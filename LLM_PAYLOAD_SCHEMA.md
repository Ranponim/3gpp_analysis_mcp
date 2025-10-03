# LLM Payload Strategy (Dual Database Architecture)

## 전략: PostgreSQL + MongoDB Hybrid

- **PostgreSQL**: Raw KPI/PEG 실시간 데이터 저장 및 조회
- **MongoDB**: 분석 결과, 사용자 설정, 통계 결과 저장

## Payload Structure: 확장된 분석 결과 스키마

- `results`: KPI별 상세 분석 결과 목록
- `stats`: 통계 분석 결과 목록
- `target_scope`: 다중 타겟 분석 범위 (NE/Cell/Host)
- `results_overview`: 운영 요약 (핵심 소견/경보/권장사항)
- `analysis_raw_compact`: 압축된 원본 분석 데이터

## MongoDB Document Shape (AnalysisResult)

```json
{
  "_id": "ObjectId(...)",
  "analysis_id": "ff321396-97eb-4b3d-abd6-d43e7315682f",
  "analysis_type": "llm_analysis",
  "analysis_date": "2025-08-14T10:00:00Z",
  "status": "success",
  "target_scope": {
    "ne_ids": ["nvgnb#10000"],
    "cell_ids": ["2010"],
    "host_ids": ["host01"],
    "scope_type": "specific_target",
    "target_combinations": [
      { "ne": "nvgnb#10000", "cell": "2010", "host": "host01" }
    ]
  },
  "results": [
    {
      "kpi_name": "RACH Success Rate",
      "value": 98.5,
      "threshold": 95.0,
      "status": "normal",
      "unit": "%"
    }
  ],
  "stats": [
    {
      "period": "N-1",
      "kpi_name": "RACH Success Rate",
      "avg": 97.8,
      "std": 1.2,
      "min": 95.0,
      "max": 99.5,
      "count": 144
    }
  ],
  "results_overview": {
    "summary": "Top issues and recommendations...",
    "key_findings": ["..."],
    "recommended_actions": ["..."]
  },
  "analysis_raw_compact": {
    "top_k_segments": ["..."],
    "percentiles": { "p50": 98.1, "p90": 99.2 },
    "notes": "truncated..."
  },
  "request_params": {
    "user_id": "default",
    "n_minus_1": "2024-01-01_00:00~2024-01-01_23:59",
    "n": "2024-01-02_00:00~2024-01-02_23:59",
    "enable_mock": false
  },
  "source_metadata": {
    "db_config": {
      "host": "127.0.0.1",
      "port": 5432,
      "user": "postgres",
      "dbname": "netperf"
    },
    "time_ranges": { "n_minus_1": "...", "n": "..." }
  },
  "metadata": {
    "created_at": "2025-08-14T10:00:00Z",
    "analysis_type": "llm_analysis",
    "version": "1.0",
    "processing_time": 3.21
  },
  "completed_at": "2025-08-14T10:00:03.210Z"
}
```

## 주의사항

- API accepts camelCase via alias (e.g., `analysisDate`, `neId`, `cellId`), stored as snake_case.
- `analysis_raw_compact` is optional and excluded from detail by default; include with `?includeRaw=true`.
- `results_overview` is small, intended for list/detail default views.

## FastAPI Models (현재 구현)

- `AnalysisResultBase`: 공통 필드 정의 (analysis_date, target_scope, results, stats 등)
- `AnalysisResultCreate`: 분석 결과 생성 요청 모델
- `AnalysisResultModel`: 데이터베이스 조회 응답 모델 (MongoDB ObjectId 포함)
- `AnalysisResultSummary`: 목록 조회용 요약 모델
- `AnalysisDetail`: 개별 KPI 분석 결과
- `StatDetail`: 통계 분석 결과
- `TargetScope`: 다중 타겟 범위 정의 (NE/Cell/Host)
- `FilterMetadata`: 필터링 메타데이터

## 주요 특징

- **다중 타겟 지원**: NE, Cell, Host의 조합으로 분석 범위 지정
- **하위 호환성**: 기존 `ne_id`, `cell_id` 필드 유지
- **확장된 필터링**: Host 기반 필터링 지원
- **별칭 지원**: camelCase/snake_case 모두 허용

## Endpoints (현재 구현)

- **POST `/api/analysis/trigger-llm-analysis`**: LLM 분석 트리거 (PostgreSQL → MCP → MongoDB)
- **GET `/api/analysis/llm-analysis/{id}`**: 분석 결과 조회 (MongoDB)
- **POST `/api/analysis/results`**: 분석 결과 생성 (MongoDB 저장)
- **GET `/api/analysis/results`**: 분석 결과 목록 조회 (MongoDB)
- **GET `/api/analysis/results/{id}`**: 단일 분석 결과 상세 조회 (MongoDB)
- **PUT `/api/analysis/results/{id}`**: 분석 결과 업데이트
- **DELETE `/api/analysis/results/{id}`**: 분석 결과 삭제



