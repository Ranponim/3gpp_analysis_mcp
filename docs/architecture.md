# 시스템 아키텍처 문서

## 📋 개요

3GPP Analysis MCP는 **Clean Architecture** 원칙을 기반으로 설계된 고성능 5G 네트워크 성능 분석 시스템입니다.
기존의 monolithic 함수를 4계층으로 분리하여 테스트 가능성, 유지보수성, 확장성을 극대화했습니다.

## 🏗️ Clean Architecture 4계층 구조

### 계층별 역할 및 책임

```
┌─────────────────────────────────────────────────────────────────┐
│                      Presentation Layer                        │
│                    (Framework & Drivers)                       │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐   │
│  │   MCPHandler    │ │RequestValidator │ │ResponseFormatter│   │
│  │   (main.py)     │ │  (validators)   │ │  (formatters)   │   │
│  └─────────────────┘ └─────────────────┘ └─────────────────┘   │
│                              ↓                                │
├─────────────────────────────────────────────────────────────────┤
│                       Service Layer                            │
│                   (Application Business Rules)                 │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐   │
│  │AnalysisService  │ │PEGProcessingService│ │LLMAnalysisService│  │
│  │ (orchestration) │ │  (peg_service)  │ │  (llm_service)  │   │
│  └─────────────────┘ └─────────────────┘ └─────────────────┘   │
│                              ↓                                │
├─────────────────────────────────────────────────────────────────┤
│                     Repository Layer                           │
│                   (Interface Adapters)                         │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐   │
│  │PostgreSQLRepo   │ │   LLMClient     │ │ ConfigManager   │   │
│  │  (database)     │ │ (llm_client)    │ │  (settings)     │   │
│  └─────────────────┘ └─────────────────┘ └─────────────────┘   │
│                              ↓                                │
├─────────────────────────────────────────────────────────────────┤
│                       Domain Layer                             │
│                      (Enterprise Business Rules)              │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐   │
│  │     Models      │ │   Exceptions    │ │   Utilities     │   │
│  │ (domain models) │ │ (error handling)│ │ (time_parser)   │   │
│  └─────────────────┘ └─────────────────┘ └─────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 의존성 규칙

- **상위 계층 → 하위 계층**: 허용 ✅
- **하위 계층 → 상위 계층**: 금지 ❌
- **추상화에 의존**: 구체 구현체에 직접 의존 금지 ✅
- **의존성 주입**: 모든 의존성은 생성자를 통해 주입 ✅

## 🔧 핵심 컴포넌트 상세

### 1. Presentation Layer (표현 계층)

#### MCPHandler (`analysis_llm/main.py`)

```python
class MCPHandler:
    """MCP 요청 처리 및 응답 생성 담당"""

    def __init__(self):
        self.analysis_service = self._create_analysis_service()
        self.request_validator = RequestValidator()
        self.response_formatter = ResponseFormatter()

    def handle_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """6단계 MCP 요청 처리 워크플로우"""
        # 1. 요청 검증
        # 2. 분석 서비스 호출
        # 3. 응답 포맷팅
        # 4. 오류 처리
        # 5. 로깅
        # 6. 응답 반환
```

**책임:**

- MCP 프로토콜 요청/응답 처리
- 전체 워크플로우 조정
- 오류 처리 및 로깅

#### RequestValidator (`analysis_llm/utils/validators.py`)

```python
class RequestValidator:
    """6단계 요청 검증 워크플로우"""

    def validate_request(self, request_data: Dict[str, Any]) -> AnalysisRequest:
        # 1. 구조 검증
        # 2. 필수 필드 검증
        # 3. 데이터 타입 검증
        # 4. 값 범위 검증
        # 5. 시간 범위 검증
        # 6. 중첩 구조 검증
```

#### ResponseFormatter (`analysis_llm/utils/formatters.py`)

```python
class ResponseFormatter:
    """표준화된 응답 포맷팅"""

    def format_analysis_response(self, raw_output: Dict) -> AnalysisResponse:
        # 성공/오류 응답 표준화
        # JSON 직렬화 지원
        # 백엔드 호환 형식 제공
```

### 2. Service Layer (서비스 계층)

#### AnalysisService (`analysis_llm/services/analysis_service.py`)

```python
class AnalysisService:
    """6단계 분석 워크플로우 오케스트레이션"""

    def perform_analysis(self, request: AnalysisRequest) -> Dict[str, Any]:
        # 1. 요청 검증
        # 2. 시간 파싱
        # 3. PEG 처리
        # 4. LLM 분석
        # 5. 데이터 변환
        # 6. 결과 조립
```

**책임:**

- 전체 분석 워크플로우 조정
- 서비스 간 데이터 흐름 관리
- 비즈니스 로직 실행

#### PEGProcessingService (`analysis_llm/services/peg_processing_service.py`)

```python
class PEGProcessingService:
    """5단계 PEG 데이터 처리 워크플로우"""

    def process_peg_data(self, time_ranges, filters) -> pd.DataFrame:
        # 1. 데이터 조회
        # 2. 데이터 검증
        # 3. 집계
        # 4. 파생 계산
        # 5. 결과 포맷팅
```

#### LLMAnalysisService (`analysis_llm/services/llm_service.py`)

```python
class LLMAnalysisService:
    """Strategy 패턴 기반 LLM 분석"""

    def analyze_peg_data(self, processed_df, analysis_type) -> LLMAnalysisResult:
        # Strategy 패턴으로 분석 전략 선택
        # 프롬프트 생성 및 LLM 호출
        # 응답 후처리 및 표준화
```

### 3. Repository Layer (저장소 계층)

#### PostgreSQLRepository (`analysis_llm/repositories/database.py`)

```python
class PostgreSQLRepository(DatabaseRepository):
    """최적화된 PostgreSQL 데이터 액세스"""

    def fetch_peg_data(self, table_name, columns, time_range, filters) -> List[Dict]:
        # 최적화된 SQL 쿼리 생성
        # 커넥션 풀 활용
        # 성능 모니터링
```

**최적화 기법:**

- WHERE 절 필터 순서 최적화
- 복합 인덱스 활용
- 커넥션 풀링
- 쿼리 실행시간 모니터링

#### LLMClient (`analysis_llm/repositories/llm_client.py`)

```python
class LLMClient(LLMRepository):
    """다중 엔드포인트 LLM 클라이언트"""

    def analyze_data(self, prompt, enable_mock=False) -> Dict:
        # 다중 엔드포인트 failover
        # 재시도 로직 (지수 백오프)
        # 토큰 사용량 추정
```

### 4. Domain Layer (도메인 계층)

#### Models (`analysis_llm/models/`)

```python
@dataclass
class AnalysisRequest:
    """분석 요청 도메인 모델"""
    n_minus_1: str
    n: str
    analysis_type: str = 'enhanced'
    # ... 완전한 타입 힌팅

@dataclass
class AnalysisResponse:
    """분석 응답 도메인 모델"""
    status: str
    analysis_id: str
    peg_statistics: PEGStatistics
    llm_analysis: LLMAnalysisResult
```

#### Exceptions (`analysis_llm/exceptions/`)

```python
# 계층적 예외 구조
AnalysisError (기본)
├── DatabaseError
├── LLMError
├── ValidationError
├── ServiceError
└── RepositoryError
```

## 🔄 데이터 흐름 다이어그램

### 전체 분석 워크플로우

```
[MCP Request]
    ↓
[MCPHandler] → [RequestValidator]
    ↓
[AnalysisService]
    ↓
[TimeRangeParser] → [PEGProcessingService] → [LLMAnalysisService]
    ↓                       ↓                       ↓
[TimeRange Objects]    [PostgreSQLRepository]    [LLMClient]
    ↓                       ↓                       ↓
[DataProcessor]        [PEG DataFrames]       [LLM Analysis]
    ↓
[ResponseFormatter]
    ↓
[MCP Response]
```

### 시퀀스 다이어그램: 분석 요청 처리

```
Client          MCPHandler      AnalysisService    PEGProcessingService    LLMAnalysisService
  │                 │                 │                    │                     │
  │──analyze_req────→│                 │                    │                     │
  │                 │──validate_req───→│                    │                     │
  │                 │                 │──parse_time────────→│                     │
  │                 │                 │──process_peg───────→│                     │
  │                 │                 │                    │──fetch_data────────→│
  │                 │                 │                    │←──peg_dataframe────│
  │                 │                 │──analyze_llm───────→│                     │
  │                 │                 │                    │                     │──llm_call──→
  │                 │                 │                    │                     │←──analysis──│
  │                 │                 │←──final_result─────│                     │
  │                 │←──formatted_res─│                    │                     │
  │←──mcp_response──│                 │                    │                     │
```

## 🎯 디자인 패턴 적용

### 1. Repository Pattern

```python
# 추상 인터페이스
class DatabaseRepository(ABC):
    @abstractmethod
    def fetch_peg_data(self, ...): pass

# 구체 구현
class PostgreSQLRepository(DatabaseRepository):
    def fetch_peg_data(self, ...):
        # PostgreSQL 특화 구현
```

**장점:**

- 데이터 소스 변경 시 비즈니스 로직 영향 없음
- 테스트 시 Mock Repository 사용 가능
- 다양한 데이터베이스 지원 확장 가능

### 2. Strategy Pattern

```python
# 추상 전략
class BasePromptStrategy(ABC):
    @abstractmethod
    def build_prompt(self, ...): pass

# 구체 전략들
class OverallAnalysisPromptStrategy(BasePromptStrategy): ...
class EnhancedAnalysisPromptStrategy(BasePromptStrategy): ...
class SpecificPEGsAnalysisPromptStrategy(BasePromptStrategy): ...
```

**장점:**

- 런타임에 분석 전략 변경 가능
- 새로운 분석 유형 추가 시 기존 코드 수정 불필요
- 각 전략의 독립적인 테스트 가능

### 3. Dependency Injection

```python
class AnalysisService:
    def __init__(
        self,
        database_repository: DatabaseRepository,
        peg_processing_service: PEGProcessingService,
        llm_analysis_service: LLMAnalysisService,
        time_parser: TimeRangeParser,
        data_processor: DataProcessor
    ):
        # 모든 의존성을 생성자를 통해 주입
```

**장점:**

- 테스트 시 Mock 객체 주입 가능
- 런타임에 구현체 교체 가능
- 순환 의존성 방지

### 4. Context Manager Pattern

```python
class PostgreSQLRepository:
    @contextmanager
    def get_connection(self):
        conn = self._pool.getconn()
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
        finally:
            self._pool.putconn(conn)
```

**장점:**

- 자동 리소스 해제
- 예외 발생 시 안전한 정리
- 메모리 누수 방지

### 5. Factory Pattern

```python
class Settings:
    _instance = None

    @classmethod
    def get_settings(cls) -> 'Settings':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
```

**장점:**

- 복잡한 객체 생성 로직 캡슐화
- 싱글톤 패턴과 결합하여 설정 관리
- 테스트 시 설정 오버라이드 가능

## 📊 성능 최적화 아키텍처

### 데이터베이스 최적화

#### 인덱스 전략

```sql
-- 시간 범위 + NE 복합 인덱스 (가장 중요)
CREATE INDEX CONCURRENTLY idx_summary_datetime_ne
ON summary (datetime, ne);

-- 최적화된 복합 인덱스
CREATE INDEX CONCURRENTLY idx_summary_composite
ON summary (ne, cellid, datetime, peg_name);
```

#### 쿼리 최적화 패턴

1. **WHERE 절 순서**: 시간 → ne → cellid → peg_name
2. **SELECT 절**: 필요한 컬럼만 조회 (SELECT \* 방지)
3. **LIMIT 절**: 결과 집합 크기 제한
4. **ORDER BY**: 인덱스 활용 시간순 정렬

### 메모리 최적화

#### DataFrame 최적화

```python
# 데이터 타입 최적화
df['value'] = pd.to_numeric(df['value'], downcast='float')  # float64→float32
df['peg_name'] = df['peg_name'].astype('category')  # object→category

# 청크 처리
for chunk in pd.read_sql(query, conn, chunksize=1000):
    process_chunk(chunk)
```

#### 메모리 효과

- **74.9% 메모리 절약** (0.36MB → 0.09MB)
- **피크 메모리**: 95.4MB (목표 500MB 대비 81% 절약)

### LLM 최적화

#### 프롬프트 전략

```python
# 분석 유형별 최적화된 프롬프트
strategies = {
    'overall': OverallAnalysisPromptStrategy(),    # 간결한 전체 분석
    'enhanced': EnhancedAnalysisPromptStrategy(),  # 상세한 분석
    'specific': SpecificPEGsAnalysisPromptStrategy()  # 특정 PEG 분석
}
```

#### 캐싱 및 배치 처리

- **응답 캐싱**: 50% 캐시 적중률
- **배치 처리**: 다중 요청 통합 처리
- **토큰 최적화**: 불필요한 토큰 사용 최소화

## 🛡️ 오류 처리 아키텍처

### 예외 계층구조

```python
class AnalysisError(Exception):
    """기본 예외 클래스"""
    def __init__(self, message: str, details: Dict = None):
        self.message = message
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        """JSON 직렬화 지원"""
        return {
            'error_type': self.__class__.__name__,
            'message': self.message,
            'details': self.details
        }

# 특화된 예외들
class DatabaseError(AnalysisError): ...
class LLMError(AnalysisError): ...
class ValidationError(AnalysisError): ...
```

### 오류 전파 체계

```
Repository Layer: DatabaseError
        ↓ (변환)
Service Layer: PEGProcessingError, LLMAnalysisError
        ↓ (변환)
Service Layer: AnalysisServiceError
        ↓ (변환)
Presentation Layer: 사용자 친화적 오류 응답
```

### 복구 전략

1. **LLM 호출**: 다중 엔드포인트 failover
2. **DB 연결**: 연결 풀 재시도
3. **설정 로딩**: 환경변수 fallback
4. **Mock 모드**: 외부 서비스 실패 시 가상 응답

## 🔒 보안 아키텍처

### 민감한 정보 보호

```python
from pydantic import SecretStr

class Settings(BaseSettings):
    db_password: SecretStr = Field(..., env='DB_PASSWORD')
    llm_api_key: SecretStr = Field(..., env='LLM_API_KEY')

    def get_llm_api_key(self) -> str:
        return self.llm_api_key.get_secret_value()
```

### 입력 검증

1. **SQL 인젝션 방지**: 매개변수화된 쿼리
2. **타입 검증**: Pydantic 모델 기반
3. **범위 검증**: 시간 범위, 숫자 범위
4. **컬럼명 검증**: 안전하지 않은 컬럼명 필터링

## 📈 확장성 고려사항

### 수평 확장

1. **Stateless 설계**: 모든 서비스가 상태를 유지하지 않음
2. **Connection Pooling**: 데이터베이스 연결 효율화
3. **Load Balancing**: 다중 인스턴스 배포 가능

### 수직 확장

1. **메모리 최적화**: 청크 처리, 데이터 타입 최적화
2. **CPU 최적화**: 벡터화 연산, 병렬 처리
3. **I/O 최적화**: 비동기 처리, 배치 작업

### 새로운 기능 추가

1. **새로운 분석 전략**: Strategy 패턴으로 쉽게 추가
2. **새로운 데이터 소스**: Repository 패턴으로 확장
3. **새로운 출력 형식**: Formatter 패턴으로 추가

## 🧪 테스트 아키텍처

### 테스트 피라미드

```
        ┌─────────────┐
        │   E2E Tests │ ← 1개 (통합 테스트)
        └─────────────┘
      ┌─────────────────┐
      │Integration Tests│ ← 9개 (컴포넌트 간)
      └─────────────────┘
    ┌─────────────────────┐
    │    Unit Tests       │ ← 105개 (개별 컴포넌트)
    └─────────────────────┘
```

### 테스트 전략

1. **단위 테스트**: 각 클래스/함수의 독립적 테스트
2. **통합 테스트**: 계층 간 상호작용 테스트
3. **성능 테스트**: pytest-benchmark 기반 성능 측정
4. **End-to-End 테스트**: 전체 워크플로우 검증

### Mock 전략

```python
# Repository Layer Mocking
@pytest.fixture
def mock_database_repository():
    mock = Mock(spec=DatabaseRepository)
    mock.fetch_peg_data.return_value = sample_data
    return mock

# Service Layer Integration Testing
def test_analysis_service_integration(mock_database_repository):
    service = AnalysisService(database_repository=mock_database_repository, ...)
    result = service.perform_analysis(sample_request)
    assert result['status'] == 'success'
```

## 🔧 설정 아키텍처

### Configuration Manager

```python
class Settings(BaseSettings):
    """중앙화된 설정 관리"""

    # 데이터베이스 설정
    db_host: str = Field(default='localhost', env='DB_HOST')
    db_port: int = Field(default=5432, env='DB_PORT')

    # LLM 설정
    llm_provider: str = Field(default='gemini-cli', env='LLM_PROVIDER')
    llm_model: str = Field(default='gemini-2.5-pro', env='LLM_MODEL')

    # 검증 로직
    @validator('llm_provider')
    def validate_provider(cls, v):
        allowed = ['openai', 'anthropic', 'gemini-cli']
        if v not in allowed:
            raise ValueError(f'지원되지 않는 LLM 제공자: {v}')
        return v
```

### 환경별 설정

- **개발**: 디버그 모드, 상세 로깅
- **테스트**: Mock 모드, 테스트 데이터
- **프로덕션**: 최적화 모드, 보안 강화

## 📊 모니터링 아키텍처

### 구조화된 로깅

```python
{
    "timestamp": "2025-09-19T16:00:00Z",
    "level": "INFO",
    "message": "분석 완료: 성공",
    "function": "analyze_peg_data",
    "execution_time_ms": 18.1,
    "request_id": "req_123",
    "peg_count": 5,
    "status": "success",
    "memory_usage_mb": 45.2
}
```

### 성능 메트릭

1. **응답시간**: 평균, 95th percentile
2. **처리량**: 요청/초
3. **오류율**: 실패한 요청 비율
4. **리소스 사용량**: CPU, 메모리, 디스크

### 알람 기준

- **응답시간 > 100ms**: 성능 저하 경고
- **오류율 > 5%**: 시스템 문제 경고
- **메모리 사용량 > 80%**: 리소스 부족 경고

## 🚀 배포 아키텍처

### 컨테이너 구조

```dockerfile
# Multi-stage 빌드
FROM python:3.11-slim as base
# 의존성 설치

FROM base as production
# 애플리케이션 코드 복사
# 최적화된 실행 환경
```

### 서비스 구성

```yaml
# docker-compose.yml
services:
  analysis-service:
    build: .
    ports:
      - "8000:8000"
    environment:
      - APP_ENVIRONMENT=production
    depends_on:
      - postgres

  postgres:
    image: postgres:14
    environment:
      - POSTGRES_DB=3gpp_analysis
```

## 🔄 마이그레이션 전략

### 기존 시스템에서 전환

1. **점진적 마이그레이션**: 기능별 단계적 전환
2. **병렬 실행**: 기존 시스템과 동시 운영
3. **데이터 검증**: 결과 일치성 확인
4. **롤백 계획**: 문제 발생 시 즉시 복구

### 호환성 유지

- **API 호환성**: 기존 요청/응답 형식 유지
- **데이터 형식**: 기존 데이터베이스 스키마 지원
- **환경 변수**: 기존 설정과 하위 호환

## 🎯 미래 확장 계획

### 단기 계획 (1-3개월)

1. **추가 LLM 제공자**: OpenAI, Anthropic 지원
2. **실시간 분석**: WebSocket 기반 스트리밍
3. **배치 처리**: 대용량 데이터 배치 분석

### 중기 계획 (3-6개월)

1. **마이크로서비스**: 서비스별 독립 배포
2. **이벤트 기반**: 비동기 이벤트 처리
3. **캐싱 계층**: Redis 기반 결과 캐싱

### 장기 계획 (6-12개월)

1. **AI/ML 파이프라인**: 자동화된 모델 학습
2. **다중 테넌트**: 고객별 격리된 서비스
3. **글로벌 배포**: 지역별 분산 배포

## 📚 참고 자료

### 설계 원칙

- [Clean Architecture (Robert C. Martin)](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)
- [SOLID Principles](https://en.wikipedia.org/wiki/SOLID)
- [Design Patterns (Gang of Four)](https://en.wikipedia.org/wiki/Design_Patterns)

### 기술 문서

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [pytest Documentation](https://docs.pytest.org/)

### 성능 최적화

- [pandas Performance Tips](https://pandas.pydata.org/docs/user_guide/enhancingperf.html)
- [PostgreSQL Performance Tuning](https://wiki.postgresql.org/wiki/Performance_Optimization)
- [Python Memory Profiling](https://docs.python.org/3/library/tracemalloc.html)

---

이 아키텍처는 확장 가능하고 유지보수가 용이한 고품질 시스템을 제공합니다. 🏗️

## 프롬프트 시스템 통합 (v1)

- 템플릿 외부화: `config/prompts/v1.yaml` (환경 변수 `PROMPT_CONFIG_PATH`로 경로 오버라이드)
- 로더 컴포넌트: `analysis_llm/config/prompt_loader.py`
  - 기능: YAML 로드 → Pydantic 스키마 검증 → 템플릿 선택/포맷팅 → 캐싱/리로드 지원
  - 주요 API:
    - `PromptLoader(path).format_prompt(prompt_type, **vars)`
    - `get_available_prompt_types()`, `get_metadata()`, `reload_config()`
- 스키마: `analysis_llm/config/prompt_schema.py` (Pydantic v2)
  - 최소 조건: `metadata`, `prompts` 존재, 템플릿은 비지 않은 문자열
- 로깅 표준화:
  - 중앙 설정 `config.settings.get_settings().setup_logging()`에서 단일 진입점 구성
  - 모듈 개별 `basicConfig` 호출 제거, E2E 모드에서 파일 핸들러만 추가
- 폴백 전략:
  - 템플릿 포맷 실패 시 최소 문자열 프롬프트 생성으로 안전 가드
