# 3GPP Cell Performance LLM 분석기 (MCP Server)

3GPP 이동통신망의 셀 성능 데이터를 LLM으로 분석하는 MCP (Model Context Protocol) 서버입니다.

## 🚀 빠른 시작

### 1. 환경 설정

```bash
# .env 파일 생성 및 설정
cp .env.example .env
# .env 파일을 열어서 실제 환경에 맞게 수정하세요
```

### 2. Docker Compose로 실행

```bash
# MCP 서버 시작
docker-compose up -d mcp-server

# 로그 확인
docker-compose logs -f mcp-server

# 서버 중지
docker-compose down
```

### 3. 개발 환경에서 실행

```bash
# 개발용으로 실행 (소스 코드 실시간 반영)
docker-compose -f docker-compose.yml -f docker-compose.override.yml up -d

# 개발용 로그 확인
docker-compose -f docker-compose.yml -f docker-compose.override.yml logs -f
```

## 📋 환경 변수 설정

### 필수 환경 변수

| 변수명 | 설명 | 기본값 |
|--------|------|--------|
| `LLM_ENDPOINTS` | LLM API 엔드포인트들 (쉼표로 구분) | `http://localhost:10000,http://localhost:8888` |
| `LLM_MODEL` | 사용할 LLM 모델 | `Gemma-3-27B` |
| `DB_HOST` | PostgreSQL 호스트 | `localhost` |
| `DB_PORT` | PostgreSQL 포트 | `5432` |
| `DB_USER` | 데이터베이스 사용자 | `postgres` |
| `DB_PASSWORD` | 데이터베이스 비밀번호 | `pass` |
| `DB_NAME` | 데이터베이스 이름 | `netperf` |

### 선택 환경 변수

| 변수명 | 설명 | 기본값 |
|--------|------|--------|
| `BACKEND_ANALYSIS_URL` | 분석 결과 전송할 백엔드 URL | `http://localhost:8001/api/analysis/results/` |
| `DEFAULT_TZ_OFFSET` | 타임존 오프셋 | `+09:00` |

## 🔧 MCP 서버 사용법

서버가 실행되면 다음 엔드포인트를 통해 MCP 기능을 사용할 수 있습니다:

### 분석 요청 예시

```json
{
  "n_minus_1": "2025-07-01_00:00~2025-07-01_23:59",
  "n": "2025-07-02_00:00~2025-07-02_23:59",
  "output_dir": "./analysis_output",
  "backend_url": "http://localhost:8000/api/analysis-result",
  "db": {
    "host": "127.0.0.1",
    "port": 5432,
    "user": "postgres",
    "password": "pass",
    "dbname": "netperf"
  },
  "table": "summary",
  "columns": {
    "time": "datetime",
    "peg_name": "peg_name",
    "value": "value"
  },
  "preference": "Random_access_preamble_count,Random_access_response",
  "peg_definitions": {
    "telus_RACH_Success": "Random_access_preamble_count/Random_access_response*100"
  }
}
```

## 📁 프로젝트 구조

```
├── analysis_llm.py          # MCP 서버 메인 파일
├── requirements.txt         # Python 의존성
├── Dockerfile              # Docker 이미지 정의
├── docker-compose.yml      # Docker Compose 설정
├── docker-compose.override.yml  # 개발 환경 오버라이드
└── analysis_output/        # 분석 결과 출력 디렉토리
```

## 🐳 Docker 이미지 빌드

### 로컬에서 빌드

```bash
# Docker 이미지 빌드
docker build -t 3gpp-analysis-mcp .

# 컨테이너 실행
docker run -p 8000:8000 \
  -e LLM_ENDPOINTS="http://localhost:10000" \
  -e DB_HOST="your-db-host" \
  -e DB_PASSWORD="your-password" \
  3gpp-analysis-mcp
```

### GitHub Actions를 통한 빌드

릴리즈를 생성하면 자동으로 Docker Hub에 이미지가 푸시됩니다.

## 🔍 문제 해결

### 자주 발생하는 문제들

1. **matplotlib 관련 빌드 오류**
   - Dockerfile에 필요한 시스템 라이브러리들이 설치되어 있는지 확인
   - Python 3.11 slim 이미지 사용 권장

2. **데이터베이스 연결 실패**
   - 환경 변수 설정 확인
   - 데이터베이스 서버가 실행 중인지 확인

3. **LLM API 연결 실패**
   - LLM_ENDPOINTS 환경 변수 설정 확인
   - LLM 서버가 실행 중인지 확인

### 로그 확인

```bash
# 컨테이너 로그 확인
docker-compose logs mcp-server

# 실시간 로그 모니터링
docker-compose logs -f mcp-server
```

## 📊 성능 모니터링

### 리소스 사용량 확인

```bash
# 컨테이너 리소스 사용량
docker stats

# 특정 컨테이너 상세 정보
docker inspect 3gpp_analysis_mcp
```

## 🤝 기여하기

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 라이선스

This project is licensed under the MIT License - see the LICENSE file for details.
