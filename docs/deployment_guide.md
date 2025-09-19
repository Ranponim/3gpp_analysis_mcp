# 배포 가이드

## 📋 개요

이 가이드는 3GPP Analysis MCP 시스템을 프로덕션 환경에 배포하는 단계별 절차를 제공합니다.
Docker 기반 배포를 기본으로 하며, 보안, 성능, 모니터링을 고려한 완전한 배포 가이드입니다.

## 🎯 배포 요구사항

### 시스템 요구사항

#### 최소 요구사항

- **CPU**: 2 Core (2.0GHz+)
- **메모리**: 4GB RAM
- **디스크**: 20GB 여유 공간
- **네트워크**: 1Gbps

#### 권장 요구사항

- **CPU**: 4 Core (2.5GHz+)
- **메모리**: 8GB RAM
- **디스크**: 100GB SSD
- **네트워크**: 10Gbps

### 소프트웨어 요구사항

- **Docker**: 20.10.0+
- **Docker Compose**: 2.0.0+
- **PostgreSQL**: 12.0+ (외부 DB 사용 시)
- **운영체제**: Linux (Ubuntu 20.04+ 권장)

## 🚀 배포 절차

### 1단계: 환경 준비

#### 서버 설정

```bash
# 1. Docker 설치 (Ubuntu 기준)
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 2. Docker Compose 설치
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# 3. 사용자를 docker 그룹에 추가
sudo usermod -aG docker $USER
newgrp docker

# 4. 방화벽 설정
sudo ufw allow 8000/tcp  # API 포트
sudo ufw allow 5432/tcp  # PostgreSQL 포트 (필요시)
```

#### 디렉토리 구조 생성

```bash
# 프로덕션 디렉토리 생성
sudo mkdir -p /opt/3gpp-analysis
sudo chown $USER:$USER /opt/3gpp-analysis
cd /opt/3gpp-analysis

# 필요한 디렉토리 생성
mkdir -p {data,logs,config,backups}
```

### 2단계: 소스 코드 배포

#### Git 저장소에서 배포

```bash
# 1. 저장소 복제
git clone <repository-url> /opt/3gpp-analysis/app
cd /opt/3gpp-analysis/app

# 2. 프로덕션 브랜치로 전환
git checkout main

# 3. 태그 확인 (릴리즈 버전)
git tag -l
git checkout v1.0.0  # 최신 안정 버전
```

#### Docker 이미지 빌드

```bash
# 프로덕션 이미지 빌드
docker build -t 3gpp-analysis:v1.0.0 .

# 이미지 확인
docker images | grep 3gpp-analysis
```

### 3단계: 환경 변수 설정

#### 프로덕션 환경 변수 파일 생성

```bash
# 보안을 위해 제한된 권한으로 생성
touch /opt/3gpp-analysis/config/.env
chmod 600 /opt/3gpp-analysis/config/.env
```

#### 필수 환경 변수 설정

```bash
# /opt/3gpp-analysis/config/.env
# =====================================
# 3GPP Analysis MCP - 프로덕션 설정
# =====================================

# --- 애플리케이션 설정 ---
APP_ENVIRONMENT=production
APP_NAME=3gpp-analysis-mcp
APP_VERSION=1.0.0
APP_LOG_LEVEL=INFO
APP_TIMEZONE=Asia/Seoul

# --- 데이터베이스 설정 ---
DB_HOST=your-production-db-host
DB_PORT=5432
DB_NAME=3gpp_analysis_prod
DB_USER=3gpp_user
DB_PASSWORD=your-secure-password
DB_POOL_SIZE=10
DB_TIMEOUT=30

# --- LLM API 설정 ---
LLM_PROVIDER=gemini-cli
LLM_MODEL=gemini-2.5-pro
LLM_API_KEY=your-gemini-api-key
LLM_ENDPOINTS=http://your-llm-endpoint:10000
LLM_TIMEOUT=60
LLM_MAX_RETRIES=3
LLM_TEMPERATURE=0.2
LLM_MAX_TOKENS=8000

# --- 백엔드 연동 설정 ---
BACKEND_URL=https://your-backend-api.com/api/analysis/results
BACKEND_TIMEOUT=30
BACKEND_AUTH_TOKEN=your-backend-token

# --- 보안 설정 ---
SECRET_KEY=your-very-secure-secret-key
ALLOWED_HOSTS=your-domain.com,localhost
CORS_ORIGINS=https://your-frontend.com

# --- 모니터링 설정 ---
ENABLE_METRICS=true
METRICS_PORT=9090
LOG_FORMAT=json
LOG_DESTINATION=file
LOG_FILE_PATH=/opt/3gpp-analysis/logs/app.log
```

### 4단계: 데이터베이스 설정

#### PostgreSQL 설정 (외부 DB 사용 시)

```sql
-- 1. 데이터베이스 및 사용자 생성
CREATE DATABASE 3gpp_analysis_prod;
CREATE USER 3gpp_user WITH PASSWORD 'your-secure-password';
GRANT ALL PRIVILEGES ON DATABASE 3gpp_analysis_prod TO 3gpp_user;

-- 2. 성능 최적화 인덱스 생성
\c 3gpp_analysis_prod;

-- 기본 인덱스
CREATE INDEX CONCURRENTLY idx_summary_datetime_ne
ON summary (datetime, ne);

CREATE INDEX CONCURRENTLY idx_summary_cellid_datetime
ON summary (cellid, datetime);

-- 복합 인덱스
CREATE INDEX CONCURRENTLY idx_summary_composite
ON summary (ne, cellid, datetime, peg_name);

-- 성능 통계 업데이트
ANALYZE summary;
```

#### Docker Compose 데이터베이스 설정

```yaml
# docker-compose.prod.yml
version: "3.8"

services:
  postgres:
    image: postgres:14
    environment:
      POSTGRES_DB: 3gpp_analysis_prod
      POSTGRES_USER: 3gpp_user
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./sql/init.sql:/docker-entrypoint-initdb.d/init.sql
    ports:
      - "5432:5432"
    restart: unless-stopped

volumes:
  postgres_data:
```

### 5단계: 프로덕션 배포

#### Docker Compose 프로덕션 설정

```yaml
# docker-compose.prod.yml
version: "3.8"

services:
  analysis-service:
    image: 3gpp-analysis:v1.0.0
    container_name: 3gpp-analysis-prod
    ports:
      - "8000:8000"
    environment:
      - APP_ENVIRONMENT=production
    env_file:
      - /opt/3gpp-analysis/config/.env
    volumes:
      - /opt/3gpp-analysis/logs:/app/logs
      - /opt/3gpp-analysis/data:/app/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    depends_on:
      - postgres
    networks:
      - 3gpp-network

  postgres:
    image: postgres:14
    container_name: 3gpp-postgres-prod
    environment:
      POSTGRES_DB: ${DB_NAME}
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - /opt/3gpp-analysis/backups:/backups
    ports:
      - "5432:5432"
    restart: unless-stopped
    networks:
      - 3gpp-network

  nginx:
    image: nginx:alpine
    container_name: 3gpp-nginx-prod
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/nginx/ssl
    depends_on:
      - analysis-service
    restart: unless-stopped
    networks:
      - 3gpp-network

volumes:
  postgres_data:

networks:
  3gpp-network:
    driver: bridge
```

#### 배포 실행

```bash
# 1. 프로덕션 환경 변수 로드
cd /opt/3gpp-analysis/app
export $(cat /opt/3gpp-analysis/config/.env | xargs)

# 2. Docker Compose로 배포
docker-compose -f docker-compose.prod.yml up -d

# 3. 서비스 상태 확인
docker-compose -f docker-compose.prod.yml ps

# 4. 로그 확인
docker-compose -f docker-compose.prod.yml logs -f analysis-service
```

### 6단계: 배포 검증

#### 헬스체크 검증

```bash
# 1. 기본 헬스체크
curl http://localhost:8000/health
# 예상 응답: {"status": "healthy", ...}

# 2. 데이터베이스 연결 확인
curl http://localhost:8000/health/db
# 예상 응답: {"status": "healthy", "connection_pool": {...}}

# 3. LLM 서비스 연결 확인
curl http://localhost:8000/health/llm
# 예상 응답: {"status": "healthy", "endpoints": [...]}
```

#### 기능 테스트

```bash
# Mock 모드로 기본 기능 테스트
curl -X POST http://localhost:8000/analyze_cell_performance_with_llm \
  -H "Content-Type: application/json" \
  -d '{
    "n_minus_1": "2025-01-01_09:00~2025-01-01_18:00",
    "n": "2025-01-02_09:00~2025-01-02_18:00",
    "enable_mock": true,
    "analysis_type": "enhanced",
    "db": {
      "host": "localhost",
      "dbname": "test",
      "user": "test",
      "password": "test"
    }
  }'
```

#### 성능 테스트

```bash
# 부하 테스트 (Apache Bench)
ab -n 100 -c 10 -T 'application/json' -p test_request.json http://localhost:8000/analyze_cell_performance_with_llm

# 예상 결과:
# - 평균 응답시간: < 50ms
# - 성공률: > 99%
# - 처리량: > 20 요청/초
```

## 🔒 보안 설정

### SSL/TLS 설정

#### Nginx 프록시 설정

```nginx
# /opt/3gpp-analysis/app/nginx.conf
events {
    worker_connections 1024;
}

http {
    upstream analysis_backend {
        server analysis-service:8000;
    }

    server {
        listen 80;
        server_name your-domain.com;
        return 301 https://$server_name$request_uri;
    }

    server {
        listen 443 ssl http2;
        server_name your-domain.com;

        ssl_certificate /etc/nginx/ssl/cert.pem;
        ssl_certificate_key /etc/nginx/ssl/key.pem;
        ssl_protocols TLSv1.2 TLSv1.3;

        location / {
            proxy_pass http://analysis_backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;

            # 타임아웃 설정
            proxy_read_timeout 60s;
            proxy_connect_timeout 10s;
        }

        location /health {
            proxy_pass http://analysis_backend/health;
            access_log off;
        }
    }
}
```

### 방화벽 설정

```bash
# UFW 방화벽 설정
sudo ufw enable
sudo ufw allow ssh
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw deny 8000/tcp   # 직접 API 접근 차단 (Nginx를 통해서만)
sudo ufw deny 5432/tcp   # 직접 DB 접근 차단
```

### 환경 변수 보안

```bash
# 1. 환경 변수 파일 권한 설정
chmod 600 /opt/3gpp-analysis/config/.env
chown root:docker /opt/3gpp-analysis/config/.env

# 2. Docker secrets 사용 (Docker Swarm 환경)
echo "your-db-password" | docker secret create db_password -
echo "your-api-key" | docker secret create llm_api_key -
```

## 📊 모니터링 설정

### 로그 수집 설정

#### Logrotate 설정

```bash
# /etc/logrotate.d/3gpp-analysis
/opt/3gpp-analysis/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
    postrotate
        docker-compose -f /opt/3gpp-analysis/app/docker-compose.prod.yml restart analysis-service
    endscript
}
```

#### 중앙 로그 수집 (ELK Stack)

```yaml
# docker-compose.monitoring.yml
version: "3.8"

services:
  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.8.0
    environment:
      - discovery.type=single-node
      - "ES_JAVA_OPTS=-Xms512m -Xmx512m"
    volumes:
      - elasticsearch_data:/usr/share/elasticsearch/data
    ports:
      - "9200:9200"

  kibana:
    image: docker.elastic.co/kibana/kibana:8.8.0
    ports:
      - "5601:5601"
    environment:
      - ELASTICSEARCH_HOSTS=http://elasticsearch:9200
    depends_on:
      - elasticsearch

  filebeat:
    image: docker.elastic.co/beats/filebeat:8.8.0
    volumes:
      - /opt/3gpp-analysis/logs:/logs:ro
      - ./filebeat.yml:/usr/share/filebeat/filebeat.yml:ro
    depends_on:
      - elasticsearch

volumes:
  elasticsearch_data:
```

### 메트릭 수집 설정

#### Prometheus 설정

```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: "3gpp-analysis"
    static_configs:
      - targets: ["analysis-service:9090"]
    metrics_path: /metrics
    scrape_interval: 10s
```

#### Grafana 대시보드

```json
{
  "dashboard": {
    "title": "3GPP Analysis MCP Monitoring",
    "panels": [
      {
        "title": "응답시간",
        "type": "graph",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))",
            "legendFormat": "95th Percentile"
          }
        ]
      },
      {
        "title": "처리량",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(http_requests_total[5m])",
            "legendFormat": "Requests/sec"
          }
        ]
      },
      {
        "title": "오류율",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(http_requests_total{status=~\"5..\"}[5m]) / rate(http_requests_total[5m])",
            "legendFormat": "Error Rate"
          }
        ]
      }
    ]
  }
}
```

## 🔄 배포 자동화

### CI/CD 파이프라인 (GitHub Actions)

```yaml
# .github/workflows/deploy.yml
name: Deploy to Production

on:
  push:
    tags:
      - "v*"

jobs:
  deploy:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v3

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v2

      - name: Login to Docker Hub
        uses: docker/login-action@v2
        with:
          username: ${{ secrets.DOCKER_USERNAME }}
          password: ${{ secrets.DOCKER_PASSWORD }}

      - name: Build and push Docker image
        uses: docker/build-push-action@v4
        with:
          context: .
          push: true
          tags: |
            your-registry/3gpp-analysis:latest
            your-registry/3gpp-analysis:${{ github.ref_name }}

      - name: Deploy to production
        uses: appleboy/ssh-action@v0.1.5
        with:
          host: ${{ secrets.PROD_HOST }}
          username: ${{ secrets.PROD_USER }}
          key: ${{ secrets.PROD_SSH_KEY }}
          script: |
            cd /opt/3gpp-analysis/app
            git pull origin main
            docker-compose -f docker-compose.prod.yml pull
            docker-compose -f docker-compose.prod.yml up -d --no-deps analysis-service

      - name: Health check
        run: |
          sleep 30
          curl -f http://${{ secrets.PROD_HOST }}/health
```

### 배포 스크립트

```bash
#!/bin/bash
# deploy.sh - 프로덕션 배포 스크립트

set -e  # 오류 발생 시 스크립트 중단

# 설정
DEPLOY_DIR="/opt/3gpp-analysis"
APP_DIR="$DEPLOY_DIR/app"
BACKUP_DIR="$DEPLOY_DIR/backups"

echo "🚀 3GPP Analysis MCP 프로덕션 배포 시작..."

# 1. 현재 상태 백업
echo "📦 현재 상태 백업 중..."
timestamp=$(date +%Y%m%d_%H%M%S)
docker-compose -f $APP_DIR/docker-compose.prod.yml exec postgres pg_dump -U 3gpp_user 3gpp_analysis_prod > $BACKUP_DIR/db_backup_$timestamp.sql

# 2. 새 버전 다운로드
echo "⬇️ 새 버전 다운로드 중..."
cd $APP_DIR
git fetch --tags
latest_tag=$(git describe --tags --abbrev=0)
git checkout $latest_tag

# 3. Docker 이미지 빌드
echo "🔨 Docker 이미지 빌드 중..."
docker build -t 3gpp-analysis:$latest_tag .

# 4. 서비스 재시작
echo "🔄 서비스 재시작 중..."
docker-compose -f docker-compose.prod.yml up -d --no-deps analysis-service

# 5. 헬스체크
echo "🏥 헬스체크 실행 중..."
sleep 30

if curl -f http://localhost:8000/health; then
    echo "✅ 배포 성공! 버전: $latest_tag"
else
    echo "❌ 헬스체크 실패. 롤백 실행 중..."
    # 롤백 로직
    docker-compose -f docker-compose.prod.yml down
    # 이전 이미지로 복구
    echo "🔄 롤백 완료"
    exit 1
fi

echo "🎉 배포 완료!"
```

## 🛡️ 백업 및 복구

### 데이터베이스 백업

#### 자동 백업 스크립트

```bash
#!/bin/bash
# backup.sh - 자동 백업 스크립트

BACKUP_DIR="/opt/3gpp-analysis/backups"
timestamp=$(date +%Y%m%d_%H%M%S)

# 1. 데이터베이스 백업
docker-compose -f /opt/3gpp-analysis/app/docker-compose.prod.yml exec -T postgres pg_dump -U 3gpp_user 3gpp_analysis_prod > $BACKUP_DIR/db_backup_$timestamp.sql

# 2. 압축
gzip $BACKUP_DIR/db_backup_$timestamp.sql

# 3. 오래된 백업 삭제 (30일 이상)
find $BACKUP_DIR -name "db_backup_*.sql.gz" -mtime +30 -delete

# 4. 백업 성공 로그
echo "$(date): 데이터베이스 백업 완료 - db_backup_$timestamp.sql.gz" >> $BACKUP_DIR/backup.log
```

#### Cron 설정

```bash
# crontab -e
# 매일 새벽 2시에 백업 실행
0 2 * * * /opt/3gpp-analysis/scripts/backup.sh

# 매주 일요일에 전체 시스템 백업
0 3 * * 0 /opt/3gpp-analysis/scripts/full_backup.sh
```

### 복구 절차

#### 데이터베이스 복구

```bash
# 1. 서비스 중지
docker-compose -f docker-compose.prod.yml stop analysis-service

# 2. 백업에서 복구
gunzip -c /opt/3gpp-analysis/backups/db_backup_20250919_020000.sql.gz | \
docker-compose -f docker-compose.prod.yml exec -T postgres psql -U 3gpp_user -d 3gpp_analysis_prod

# 3. 서비스 재시작
docker-compose -f docker-compose.prod.yml start analysis-service

# 4. 헬스체크
curl http://localhost:8000/health
```

#### 애플리케이션 롤백

```bash
# 1. 이전 버전으로 롤백
cd /opt/3gpp-analysis/app
git checkout v0.9.0  # 이전 안정 버전

# 2. 이전 이미지로 복구
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml up -d

# 3. 검증
curl http://localhost:8000/health
```

## 📈 성능 튜닝

### 시스템 최적화

#### Linux 커널 매개변수

```bash
# /etc/sysctl.conf
# TCP 성능 최적화
net.core.somaxconn = 65535
net.core.netdev_max_backlog = 5000
net.ipv4.tcp_max_syn_backlog = 65535
net.ipv4.tcp_keepalive_time = 600

# 메모리 최적화
vm.swappiness = 10
vm.dirty_ratio = 15
vm.dirty_background_ratio = 5

# 적용
sudo sysctl -p
```

#### Docker 리소스 제한

```yaml
# docker-compose.prod.yml에 추가
services:
  analysis-service:
    deploy:
      resources:
        limits:
          cpus: "2.0"
          memory: 4G
        reservations:
          cpus: "1.0"
          memory: 2G
```

### 애플리케이션 최적화

#### 환경 변수 튜닝

```bash
# 프로덕션 최적화 설정
DB_POOL_SIZE=20                    # 연결 풀 크기 증가
LLM_MAX_RETRIES=5                  # 재시도 횟수 증가
LLM_TIMEOUT=120                    # 타임아웃 증가
APP_LOG_LEVEL=WARNING              # 로그 레벨 최적화
ENABLE_PERFORMANCE_METRICS=true    # 성능 메트릭 활성화
```

## 🚨 장애 대응

### 일반적인 문제 및 해결책

#### 1. 높은 응답시간 (> 100ms)

**진단:**

```bash
# 1. 시스템 리소스 확인
docker stats
top

# 2. 데이터베이스 성능 확인
docker-compose exec postgres psql -U 3gpp_user -d 3gpp_analysis_prod -c "
SELECT query, mean_exec_time, calls
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;"

# 3. 애플리케이션 로그 확인
docker-compose logs analysis-service | grep "execution_time_ms" | tail -100
```

**해결책:**

- 데이터베이스 인덱스 추가
- 연결 풀 크기 조정
- 쿼리 최적화

#### 2. 메모리 부족

**진단:**

```bash
# 메모리 사용량 확인
free -h
docker stats --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}"
```

**해결책:**

- 컨테이너 메모리 제한 조정
- 가비지 컬렉션 튜닝
- 청크 처리 크기 조정

#### 3. LLM API 연결 실패

**진단:**

```bash
# LLM 엔드포인트 연결 테스트
curl -X POST http://your-llm-endpoint:10000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "gemini-2.5-pro", "messages": [{"role": "user", "content": "test"}]}'
```

**해결책:**

- 엔드포인트 URL 확인
- API 키 유효성 검증
- 네트워크 연결 상태 확인
- Failover 엔드포인트 추가

### 응급 복구 절차

#### 1. 서비스 완전 중단 시

```bash
# 1. 모든 서비스 중지
docker-compose -f docker-compose.prod.yml down

# 2. 시스템 리소스 정리
docker system prune -f
docker volume prune -f

# 3. 이전 안정 버전으로 복구
git checkout v0.9.0
docker build -t 3gpp-analysis:rollback .

# 4. 서비스 재시작
docker-compose -f docker-compose.prod.yml up -d

# 5. 헬스체크
sleep 60
curl http://localhost:8000/health
```

#### 2. 데이터베이스 손상 시

```bash
# 1. 서비스 중지
docker-compose -f docker-compose.prod.yml stop analysis-service

# 2. 최신 백업에서 복구
latest_backup=$(ls -t /opt/3gpp-analysis/backups/db_backup_*.sql.gz | head -1)
gunzip -c $latest_backup | docker-compose -f docker-compose.prod.yml exec -T postgres psql -U 3gpp_user -d 3gpp_analysis_prod

# 3. 데이터 무결성 검증
docker-compose -f docker-compose.prod.yml exec postgres psql -U 3gpp_user -d 3gpp_analysis_prod -c "SELECT COUNT(*) FROM summary;"

# 4. 서비스 재시작
docker-compose -f docker-compose.prod.yml start analysis-service
```

## 📋 배포 체크리스트

### 배포 전 확인사항

- [ ] **코드 리뷰**: 모든 변경사항 리뷰 완료
- [ ] **테스트**: 모든 테스트 통과 (단위, 통합, 성능)
- [ ] **환경 변수**: 프로덕션 설정 검증
- [ ] **백업**: 현재 상태 백업 완료
- [ ] **롤백 계획**: 롤백 절차 준비

### 배포 중 확인사항

- [ ] **이미지 빌드**: Docker 이미지 빌드 성공
- [ ] **서비스 시작**: 모든 컨테이너 정상 시작
- [ ] **헬스체크**: 모든 헬스체크 통과
- [ ] **기능 테스트**: 주요 기능 정상 동작
- [ ] **성능 테스트**: 응답시간 및 처리량 확인

### 배포 후 확인사항

- [ ] **모니터링**: 메트릭 수집 정상 동작
- [ ] **로그**: 로그 수집 및 분석 가능
- [ ] **알람**: 알람 시스템 정상 동작
- [ ] **문서**: 배포 기록 및 변경사항 문서화
- [ ] **팀 공지**: 배포 완료 및 변경사항 공유

## 🔧 환경별 배포

### 개발 환경

```bash
# 개발용 배포
docker-compose -f docker-compose.yml -f docker-compose.override.yml up -d

# 특징:
# - 코드 변경 시 자동 재로드
# - 상세한 디버그 로깅
# - Mock 모드 기본 활성화
```

### 스테이징 환경

```bash
# 스테이징용 배포
docker-compose -f docker-compose.yml -f docker-compose.staging.yml up -d

# 특징:
# - 프로덕션과 동일한 설정
# - 테스트 데이터 사용
# - 성능 테스트 실행
```

### 프로덕션 환경

```bash
# 프로덕션용 배포
docker-compose -f docker-compose.prod.yml up -d

# 특징:
# - 최적화된 성능 설정
# - 보안 강화
# - 완전한 모니터링
```

## 📞 지원 및 문의

### 배포 관련 문의

- **기술 지원**: tech-support@your-company.com
- **긴급 상황**: +82-10-xxxx-xxxx (24/7)
- **문서 피드백**: docs@your-company.com

### 유용한 명령어

```bash
# 서비스 상태 확인
docker-compose -f docker-compose.prod.yml ps

# 로그 실시간 모니터링
docker-compose -f docker-compose.prod.yml logs -f analysis-service

# 컨테이너 리소스 사용량
docker stats

# 디스크 사용량 확인
df -h
du -sh /opt/3gpp-analysis/*

# 네트워크 연결 확인
netstat -tlnp | grep :8000
```

---

이 가이드를 따라 안전하고 안정적인 프로덕션 배포를 수행하세요! 🚀
