# 운영 가이드

## 📋 개요

이 가이드는 3GPP Analysis MCP 시스템의 일상적인 운영, 모니터링, 문제 해결을 위한 종합적인 절차를 제공합니다.
프로덕션 환경에서 안정적인 서비스 운영을 위한 모든 필수 정보를 포함합니다.

## 🎯 운영 목표

### 서비스 수준 목표 (SLO)

| 메트릭       | 목표         | 측정 방법              |
| ------------ | ------------ | ---------------------- |
| **가용성**   | 99.9%        | 월간 업타임            |
| **응답시간** | P95 < 50ms   | API 응답시간           |
| **처리량**   | > 20 요청/초 | 동시 처리 능력         |
| **오류율**   | < 1%         | 실패한 요청 비율       |
| **복구시간** | < 15분       | 장애 발생 시 복구 시간 |

### 성능 기준선

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
성능 기준선 (Baseline):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
메트릭                    정상 범위        경고 임계값      위험 임계값
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
평균 응답시간             < 25ms          > 50ms         > 100ms
P95 응답시간              < 50ms          > 100ms        > 200ms
처리량                    > 20 req/s      < 10 req/s     < 5 req/s
오류율                    < 0.5%          > 2%           > 5%
메모리 사용량             < 200MB         > 400MB        > 600MB
CPU 사용률                < 50%           > 80%          > 95%
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## 📊 모니터링 체계

### 1. 애플리케이션 모니터링

#### 핵심 메트릭

```bash
# 1. 응답시간 모니터링
curl -s http://localhost:8000/health | jq '.components'

# 2. 성능 메트릭 수집
docker-compose logs analysis-service | grep "execution_time_ms" | tail -20

# 3. 오류율 계산
error_count=$(docker-compose logs analysis-service | grep "ERROR" | wc -l)
total_requests=$(docker-compose logs analysis-service | grep "분석 완료" | wc -l)
error_rate=$(echo "scale=2; $error_count / $total_requests * 100" | bc)
echo "오류율: ${error_rate}%"
```

#### 실시간 모니터링 스크립트

```bash
#!/bin/bash
# monitor.sh - 실시간 모니터링 스크립트

while true; do
    clear
    echo "🔍 3GPP Analysis MCP 실시간 모니터링"
    echo "========================================"
    echo "📅 시간: $(date)"
    echo ""

    # 1. 서비스 상태
    echo "🏥 서비스 상태:"
    health_status=$(curl -s http://localhost:8000/health | jq -r '.status')
    echo "   애플리케이션: $health_status"

    # 2. 컨테이너 상태
    echo "🐳 컨테이너 상태:"
    docker-compose -f docker-compose.prod.yml ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

    # 3. 리소스 사용량
    echo "💻 리소스 사용량:"
    docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}"

    # 4. 최근 로그 (오류만)
    echo "🚨 최근 오류 로그:"
    docker-compose -f docker-compose.prod.yml logs --tail=5 analysis-service | grep ERROR || echo "   오류 없음"

    sleep 30
done
```

### 2. 인프라 모니터링

#### 시스템 리소스 모니터링

```bash
#!/bin/bash
# system_monitor.sh - 시스템 리소스 모니터링

# CPU 사용률
cpu_usage=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | awk -F'%' '{print $1}')

# 메모리 사용률
mem_usage=$(free | grep Mem | awk '{printf("%.1f", $3/$2 * 100.0)}')

# 디스크 사용률
disk_usage=$(df -h /opt/3gpp-analysis | awk 'NR==2{print $5}' | sed 's/%//')

# 네트워크 연결 수
conn_count=$(netstat -an | grep :8000 | grep ESTABLISHED | wc -l)

echo "시스템 리소스 현황:"
echo "CPU: ${cpu_usage}%"
echo "메모리: ${mem_usage}%"
echo "디스크: ${disk_usage}%"
echo "활성 연결: ${conn_count}개"

# 임계값 확인 및 알람
if (( $(echo "$cpu_usage > 80" | bc -l) )); then
    echo "⚠️ CPU 사용률 높음: ${cpu_usage}%"
fi

if (( $(echo "$mem_usage > 80" | bc -l) )); then
    echo "⚠️ 메모리 사용률 높음: ${mem_usage}%"
fi

if [ "$disk_usage" -gt 80 ]; then
    echo "⚠️ 디스크 사용률 높음: ${disk_usage}%"
fi
```

### 3. 로그 모니터링

#### 구조화된 로그 분석

```bash
# 1. 오류 로그 분석
docker-compose logs analysis-service | jq -r 'select(.level=="ERROR") | "\(.timestamp) \(.message)"'

# 2. 성능 로그 분석
docker-compose logs analysis-service | jq -r 'select(.execution_time_ms) | "\(.timestamp) \(.execution_time_ms)ms"'

# 3. 요청 통계
docker-compose logs analysis-service | jq -r 'select(.function=="analyze_peg_data") | .status' | sort | uniq -c

# 4. 느린 요청 식별
docker-compose logs analysis-service | jq -r 'select(.execution_time_ms > 50) | "\(.timestamp) \(.execution_time_ms)ms \(.request_id)"'
```

#### 로그 알람 설정

```bash
#!/bin/bash
# log_alert.sh - 로그 기반 알람 스크립트

LOG_FILE="/opt/3gpp-analysis/logs/app.log"
ALERT_EMAIL="admin@your-company.com"

# 최근 5분간 오류 로그 확인
error_count=$(tail -n 1000 $LOG_FILE | jq -r 'select(.level=="ERROR" and (.timestamp | strptime("%Y-%m-%dT%H:%M:%SZ") | mktime) > (now - 300))' | wc -l)

if [ "$error_count" -gt 10 ]; then
    echo "🚨 높은 오류율 감지: 최근 5분간 ${error_count}개 오류" | mail -s "3GPP Analysis Alert" $ALERT_EMAIL
fi

# 응답시간 모니터링
slow_requests=$(tail -n 1000 $LOG_FILE | jq -r 'select(.execution_time_ms > 100)' | wc -l)

if [ "$slow_requests" -gt 5 ]; then
    echo "⚠️ 느린 응답 감지: 최근 ${slow_requests}개 요청이 100ms 초과" | mail -s "3GPP Analysis Performance Alert" $ALERT_EMAIL
fi
```

## 🔧 일상 운영 절차

### 일일 체크리스트

#### 오전 점검 (09:00)

```bash
#!/bin/bash
# daily_morning_check.sh

echo "🌅 일일 오전 점검 시작 - $(date)"

# 1. 서비스 상태 확인
echo "1. 서비스 상태 확인:"
curl -s http://localhost:8000/health | jq '.'

# 2. 밤새 발생한 오류 확인
echo "2. 밤새 오류 로그 (최근 12시간):"
docker-compose logs --since="12h" analysis-service | grep ERROR | wc -l

# 3. 디스크 사용량 확인
echo "3. 디스크 사용량:"
df -h /opt/3gpp-analysis

# 4. 데이터베이스 연결 상태
echo "4. 데이터베이스 상태:"
curl -s http://localhost:8000/health/db | jq '.connection_pool'

# 5. 성능 요약 (어제)
echo "5. 어제 성능 요약:"
docker-compose logs --since="24h" analysis-service | jq -r 'select(.execution_time_ms) | .execution_time_ms' | awk '{sum+=$1; count++} END {if(count>0) printf "평균 응답시간: %.1fms, 총 요청: %d개\n", sum/count, count}'

echo "✅ 오전 점검 완료"
```

#### 저녁 점검 (18:00)

```bash
#!/bin/bash
# daily_evening_check.sh

echo "🌆 일일 저녁 점검 시작 - $(date)"

# 1. 금일 성능 통계
echo "1. 금일 성능 통계:"
docker-compose logs --since="1d" analysis-service | jq -r 'select(.execution_time_ms) | .execution_time_ms' | awk '
{
    sum+=$1; count++;
    if($1>max) max=$1;
    if(min=="" || $1<min) min=$1
}
END {
    if(count>0) {
        printf "총 요청: %d개\n", count
        printf "평균 응답시간: %.1fms\n", sum/count
        printf "최소 응답시간: %.1fms\n", min
        printf "최대 응답시간: %.1fms\n", max
    }
}'

# 2. 오류 통계
echo "2. 금일 오류 통계:"
total_requests=$(docker-compose logs --since="1d" analysis-service | jq -r 'select(.status)' | wc -l)
error_requests=$(docker-compose logs --since="1d" analysis-service | jq -r 'select(.status=="error")' | wc -l)
if [ "$total_requests" -gt 0 ]; then
    error_rate=$(echo "scale=2; $error_requests / $total_requests * 100" | bc)
    echo "   총 요청: ${total_requests}개"
    echo "   오류 요청: ${error_requests}개"
    echo "   오류율: ${error_rate}%"
fi

# 3. 리소스 사용량 트렌드
echo "3. 리소스 사용량:"
docker stats --no-stream --format "   {{.Container}}: CPU {{.CPUPerc}}, 메모리 {{.MemUsage}}"

# 4. 로그 로테이션 확인
echo "4. 로그 파일 크기:"
ls -lh /opt/3gpp-analysis/logs/

echo "✅ 저녁 점검 완료"
```

### 주간 체크리스트

#### 주간 리뷰 (매주 월요일 10:00)

```bash
#!/bin/bash
# weekly_review.sh

echo "📅 주간 리뷰 시작 - $(date)"

# 1. 지난 주 성능 요약
echo "1. 지난 주 성능 요약:"
docker-compose logs --since="7d" analysis-service | jq -r 'select(.execution_time_ms) | .execution_time_ms' | awk '
{
    sum+=$1; count++;
    if($1>max) max=$1;
    if(min=="" || $1<min) min=$1;
    if($1<25) fast++;
    if($1>=25 && $1<50) normal++;
    if($1>=50) slow++;
}
END {
    if(count>0) {
        printf "총 요청: %d개\n", count
        printf "평균 응답시간: %.1fms\n", sum/count
        printf "최소/최대: %.1f/%.1fms\n", min, max
        printf "빠름(<25ms): %d개 (%.1f%%)\n", fast, fast/count*100
        printf "보통(25-50ms): %d개 (%.1f%%)\n", normal, normal/count*100
        printf "느림(>50ms): %d개 (%.1f%%)\n", slow, slow/count*100
    }
}'

# 2. 오류 패턴 분석
echo "2. 오류 패턴 분석:"
docker-compose logs --since="7d" analysis-service | jq -r 'select(.level=="ERROR") | .error_type' | sort | uniq -c | sort -nr

# 3. 리소스 사용량 트렌드
echo "3. 리소스 사용량 트렌드:"
echo "   평균 메모리: $(docker stats --no-stream --format '{{.MemUsage}}' | head -1)"
echo "   평균 CPU: $(docker stats --no-stream --format '{{.CPUPerc}}' | head -1)"

# 4. 데이터베이스 성능
echo "4. 데이터베이스 성능:"
docker-compose exec postgres psql -U 3gpp_user -d 3gpp_analysis_prod -c "
SELECT
    schemaname,
    tablename,
    n_tup_ins as inserts,
    n_tup_upd as updates,
    n_tup_del as deletes,
    n_live_tup as live_tuples
FROM pg_stat_user_tables
WHERE tablename = 'summary';"

echo "✅ 주간 리뷰 완료"
```

#### 주간 최적화 작업

```bash
#!/bin/bash
# weekly_optimization.sh

echo "🔧 주간 최적화 작업 시작"

# 1. 데이터베이스 통계 업데이트
echo "1. 데이터베이스 통계 업데이트:"
docker-compose exec postgres psql -U 3gpp_user -d 3gpp_analysis_prod -c "
ANALYZE summary;
REINDEX TABLE summary;
VACUUM ANALYZE summary;"

# 2. Docker 이미지 정리
echo "2. Docker 이미지 정리:"
docker image prune -f
docker volume prune -f

# 3. 로그 압축 및 정리
echo "3. 로그 정리:"
find /opt/3gpp-analysis/logs -name "*.log" -mtime +7 -exec gzip {} \;
find /opt/3gpp-analysis/logs -name "*.gz" -mtime +30 -delete

# 4. 백업 정리
echo "4. 오래된 백업 정리:"
find /opt/3gpp-analysis/backups -name "*.sql.gz" -mtime +30 -delete

echo "✅ 주간 최적화 완료"
```

### 월간 체크리스트

#### 월간 검토 (매월 1일)

```bash
#!/bin/bash
# monthly_review.sh

echo "📊 월간 검토 시작 - $(date)"

# 1. 월간 성능 리포트 생성
echo "1. 월간 성능 리포트 생성:"
monthly_report="/opt/3gpp-analysis/reports/monthly_$(date +%Y%m).md"
mkdir -p /opt/3gpp-analysis/reports

cat > $monthly_report << EOF
# 월간 성능 리포트 - $(date +%Y년\ %m월)

## 성능 요약
$(docker-compose logs --since="30d" analysis-service | jq -r 'select(.execution_time_ms) | .execution_time_ms' | awk '{sum+=$1; count++} END {if(count>0) printf "총 요청: %d개, 평균 응답시간: %.1fms", count, sum/count}')

## 가용성
$(docker-compose logs --since="30d" analysis-service | jq -r 'select(.status) | .status' | awk '{total++; if($1=="success") success++} END {if(total>0) printf "성공률: %.2f%% (%d/%d)", success/total*100, success, total}')

## 주요 이슈
$(docker-compose logs --since="30d" analysis-service | jq -r 'select(.level=="ERROR") | .message' | sort | uniq -c | sort -nr | head -5)
EOF

echo "   리포트 생성: $monthly_report"

# 2. 용량 계획
echo "2. 용량 계획:"
current_size=$(du -sh /opt/3gpp-analysis | cut -f1)
echo "   현재 사용량: $current_size"

# 3. 보안 업데이트 확인
echo "3. 보안 업데이트 확인:"
docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.CreatedSince}}" | grep 3gpp-analysis

echo "✅ 월간 검토 완료"
```

## 🚨 알람 및 경고 시스템

### 알람 규칙

#### 1. 응답시간 알람

```bash
# Prometheus 알람 규칙
groups:
  - name: 3gpp_analysis_alerts
    rules:
      - alert: HighResponseTime
        expr: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 0.1
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "높은 응답시간 감지"
          description: "95th percentile 응답시간이 100ms를 초과했습니다."

      - alert: VeryHighResponseTime
        expr: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 0.2
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "매우 높은 응답시간 감지"
          description: "95th percentile 응답시간이 200ms를 초과했습니다."
```

#### 2. 오류율 알람

```bash
      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) > 0.05
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "높은 오류율 감지"
          description: "오류율이 5%를 초과했습니다."

      - alert: ServiceDown
        expr: up{job="3gpp-analysis"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "서비스 다운"
          description: "3GPP Analysis 서비스가 응답하지 않습니다."
```

#### 3. 리소스 알람

```bash
      - alert: HighMemoryUsage
        expr: container_memory_usage_bytes{name="3gpp-analysis-prod"} / container_spec_memory_limit_bytes > 0.8
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "높은 메모리 사용률"
          description: "메모리 사용률이 80%를 초과했습니다."

      - alert: HighCPUUsage
        expr: rate(container_cpu_usage_seconds_total{name="3gpp-analysis-prod"}[5m]) > 0.8
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "높은 CPU 사용률"
          description: "CPU 사용률이 80%를 초과했습니다."
```

### 알람 대응 절차

#### 응답시간 지연 대응

```bash
# 1. 즉시 확인 사항
curl http://localhost:8000/health
docker stats --no-stream

# 2. 원인 분석
docker-compose logs --tail=100 analysis-service | grep "execution_time_ms"
docker-compose logs --tail=100 postgres | grep "ERROR\|SLOW"

# 3. 임시 조치
# - 연결 풀 크기 증가
# - 캐시 활성화
# - 불필요한 프로세스 종료

# 4. 근본 원인 해결
# - 쿼리 최적화
# - 인덱스 추가
# - 리소스 확장
```

#### 오류율 증가 대응

```bash
# 1. 오류 패턴 분석
docker-compose logs --since="1h" analysis-service | jq -r 'select(.level=="ERROR") | "\(.error_type): \(.message)"' | sort | uniq -c

# 2. 외부 의존성 확인
curl -f http://your-llm-endpoint:10000/health
docker-compose exec postgres pg_isready

# 3. 롤백 결정
# 오류율 > 10% 시 즉시 롤백 고려
```

## 🔄 백업 및 복구 절차

### 자동 백업 시스템

#### 데이터베이스 백업

```bash
#!/bin/bash
# backup_database.sh - 데이터베이스 자동 백업

BACKUP_DIR="/opt/3gpp-analysis/backups"
timestamp=$(date +%Y%m%d_%H%M%S)
retention_days=30

echo "📦 데이터베이스 백업 시작 - $timestamp"

# 1. 풀 백업 (구조 + 데이터)
docker-compose exec -T postgres pg_dump -U 3gpp_user -v 3gpp_analysis_prod > $BACKUP_DIR/full_backup_$timestamp.sql

# 2. 스키마만 백업
docker-compose exec -T postgres pg_dump -U 3gpp_user -s 3gpp_analysis_prod > $BACKUP_DIR/schema_backup_$timestamp.sql

# 3. 백업 압축
gzip $BACKUP_DIR/full_backup_$timestamp.sql
gzip $BACKUP_DIR/schema_backup_$timestamp.sql

# 4. 백업 검증
if [ -f "$BACKUP_DIR/full_backup_$timestamp.sql.gz" ]; then
    backup_size=$(stat -f%z "$BACKUP_DIR/full_backup_$timestamp.sql.gz" 2>/dev/null || stat -c%s "$BACKUP_DIR/full_backup_$timestamp.sql.gz")
    echo "✅ 백업 완료: $(($backup_size / 1024 / 1024))MB"
else
    echo "❌ 백업 실패"
    exit 1
fi

# 5. 오래된 백업 정리
find $BACKUP_DIR -name "*_backup_*.sql.gz" -mtime +$retention_days -delete

# 6. 백업 로그 기록
echo "$(date): 백업 완료 - full_backup_$timestamp.sql.gz ($(($backup_size / 1024 / 1024))MB)" >> $BACKUP_DIR/backup.log

echo "📦 데이터베이스 백업 완료"
```

#### 설정 파일 백업

```bash
#!/bin/bash
# backup_config.sh - 설정 파일 백업

BACKUP_DIR="/opt/3gpp-analysis/backups/config"
timestamp=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# 1. 환경 설정 백업
cp /opt/3gpp-analysis/config/.env $BACKUP_DIR/env_backup_$timestamp
cp /opt/3gpp-analysis/app/docker-compose.prod.yml $BACKUP_DIR/compose_backup_$timestamp.yml

# 2. Nginx 설정 백업
cp /opt/3gpp-analysis/app/nginx.conf $BACKUP_DIR/nginx_backup_$timestamp.conf

# 3. 백업 압축
tar -czf $BACKUP_DIR/config_backup_$timestamp.tar.gz -C $BACKUP_DIR *backup_$timestamp*
rm $BACKUP_DIR/*backup_$timestamp*

echo "✅ 설정 파일 백업 완료: config_backup_$timestamp.tar.gz"
```

### 복구 절차

#### 데이터베이스 복구

```bash
#!/bin/bash
# restore_database.sh - 데이터베이스 복구

BACKUP_FILE="$1"  # 복구할 백업 파일 경로

if [ -z "$BACKUP_FILE" ]; then
    echo "사용법: $0 <backup_file.sql.gz>"
    echo "사용 가능한 백업:"
    ls -lt /opt/3gpp-analysis/backups/*backup*.sql.gz | head -10
    exit 1
fi

echo "🔄 데이터베이스 복구 시작: $BACKUP_FILE"

# 1. 서비스 중지 (데이터 일관성 보장)
echo "1. 애플리케이션 서비스 중지..."
docker-compose -f docker-compose.prod.yml stop analysis-service

# 2. 현재 데이터베이스 백업 (안전장치)
echo "2. 현재 상태 백업..."
current_backup="/opt/3gpp-analysis/backups/pre_restore_$(date +%Y%m%d_%H%M%S).sql"
docker-compose exec -T postgres pg_dump -U 3gpp_user 3gpp_analysis_prod > $current_backup
gzip $current_backup

# 3. 데이터베이스 초기화
echo "3. 데이터베이스 초기화..."
docker-compose exec postgres psql -U 3gpp_user -d postgres -c "
DROP DATABASE IF EXISTS 3gpp_analysis_prod;
CREATE DATABASE 3gpp_analysis_prod;
GRANT ALL PRIVILEGES ON DATABASE 3gpp_analysis_prod TO 3gpp_user;"

# 4. 백업에서 복구
echo "4. 백업에서 복구..."
gunzip -c $BACKUP_FILE | docker-compose exec -T postgres psql -U 3gpp_user -d 3gpp_analysis_prod

# 5. 데이터 무결성 검증
echo "5. 데이터 무결성 검증..."
record_count=$(docker-compose exec postgres psql -U 3gpp_user -d 3gpp_analysis_prod -t -c "SELECT COUNT(*) FROM summary;")
echo "   복구된 레코드 수: $record_count"

# 6. 인덱스 재생성
echo "6. 인덱스 재생성..."
docker-compose exec postgres psql -U 3gpp_user -d 3gpp_analysis_prod -f /opt/3gpp-analysis/sql/create_indexes.sql

# 7. 서비스 재시작
echo "7. 서비스 재시작..."
docker-compose -f docker-compose.prod.yml start analysis-service

# 8. 헬스체크
echo "8. 헬스체크..."
sleep 30
if curl -f http://localhost:8000/health; then
    echo "✅ 데이터베이스 복구 완료"
else
    echo "❌ 복구 실패 - 이전 백업으로 롤백 필요"
    exit 1
fi
```

## 🔧 문제 해결 가이드

### 일반적인 문제 및 해결책

#### 1. 높은 응답시간 (> 100ms)

**증상:**

- API 응답이 느림
- 사용자 불만 증가
- 타임아웃 오류 발생

**진단 절차:**

```bash
# 1. 현재 성능 확인
curl -w "@curl-format.txt" -s http://localhost:8000/health

# 2. 시스템 리소스 확인
top
iostat -x 1 5

# 3. 데이터베이스 성능 확인
docker-compose exec postgres psql -U 3gpp_user -d 3gpp_analysis_prod -c "
SELECT query, mean_exec_time, calls, total_exec_time
FROM pg_stat_statements
WHERE mean_exec_time > 100
ORDER BY mean_exec_time DESC
LIMIT 10;"

# 4. 애플리케이션 로그 분석
docker-compose logs analysis-service | grep "execution_time_ms" | awk '$NF > 100' | tail -20
```

**해결 방법:**

1. **데이터베이스 최적화**

   ```sql
   -- 느린 쿼리 분석
   SELECT * FROM pg_stat_activity WHERE state = 'active' AND query_start < now() - interval '30 seconds';

   -- 인덱스 사용률 확인
   SELECT schemaname, tablename, indexname, idx_scan, idx_tup_read, idx_tup_fetch
   FROM pg_stat_user_indexes
   WHERE idx_scan = 0;
   ```

2. **애플리케이션 튜닝**

   ```bash
   # 연결 풀 크기 증가
   export DB_POOL_SIZE=20

   # LLM 타임아웃 조정
   export LLM_TIMEOUT=120

   # 서비스 재시작
   docker-compose -f docker-compose.prod.yml restart analysis-service
   ```

#### 2. 메모리 부족

**증상:**

- OOMKilled 오류
- 컨테이너 재시작 반복
- 응답시간 급증

**진단 절차:**

```bash
# 1. 메모리 사용량 확인
docker stats --format "table {{.Container}}\t{{.MemUsage}}\t{{.MemPerc}}"

# 2. 메모리 누수 확인
docker-compose logs analysis-service | grep "memory_usage_mb" | tail -50

# 3. 가비지 컬렉션 상태
docker-compose exec analysis-service python -c "
import gc
import psutil
import os
print(f'메모리 사용량: {psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024:.1f}MB')
print(f'GC 통계: {gc.get_stats()}')
"
```

**해결 방법:**

1. **메모리 제한 조정**

   ```yaml
   # docker-compose.prod.yml
   services:
     analysis-service:
       deploy:
         resources:
           limits:
             memory: 8G # 4G에서 8G로 증가
   ```

2. **메모리 최적화**

   ```bash
   # DataFrame 청크 크기 조정
   export PEG_CHUNK_SIZE=500

   # 가비지 컬렉션 강제 실행
   docker-compose exec analysis-service python -c "import gc; gc.collect()"
   ```

#### 3. 외부 서비스 연결 실패

**증상:**

- LLM API 호출 실패
- 데이터베이스 연결 오류
- 백엔드 서비스 연결 실패

**진단 절차:**

```bash
# 1. 네트워크 연결 확인
ping your-llm-endpoint
telnet your-db-host 5432

# 2. DNS 해결 확인
nslookup your-llm-endpoint
nslookup your-db-host

# 3. 방화벽 확인
sudo ufw status
iptables -L

# 4. 서비스 로그 확인
docker-compose logs analysis-service | grep "연결\|connection\|timeout"
```

**해결 방법:**

1. **재시도 설정 조정**

   ```bash
   export LLM_MAX_RETRIES=5
   export LLM_RETRY_DELAY=2.0
   export DB_TIMEOUT=60
   ```

2. **Failover 엔드포인트 추가**
   ```bash
   export LLM_ENDPOINTS="http://primary:10000,http://secondary:10000,http://tertiary:10000"
   ```

## 📈 성능 튜닝 가이드

### 데이터베이스 튜닝

#### PostgreSQL 설정 최적화

```sql
-- postgresql.conf 주요 설정
shared_buffers = 256MB                    -- 메모리의 25%
effective_cache_size = 1GB                -- 시스템 메모리의 75%
work_mem = 4MB                           -- 정렬/해시 작업용 메모리
maintenance_work_mem = 64MB              -- 유지보수 작업용 메모리
checkpoint_completion_target = 0.9       -- 체크포인트 최적화
wal_buffers = 16MB                       -- WAL 버퍼
random_page_cost = 1.1                   -- SSD 사용 시 낮게 설정

-- 연결 설정
max_connections = 100                    -- 최대 연결 수
shared_preload_libraries = 'pg_stat_statements'  -- 쿼리 통계 수집
```

#### 인덱스 모니터링

```sql
-- 인덱스 사용률 확인
SELECT
    schemaname,
    tablename,
    indexname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
ORDER BY idx_scan DESC;

-- 사용되지 않는 인덱스 확인
SELECT
    schemaname,
    tablename,
    indexname,
    pg_size_pretty(pg_relation_size(indexrelid)) as size
FROM pg_stat_user_indexes
WHERE idx_scan = 0
  AND schemaname = 'public';
```

### 애플리케이션 튜닝

#### 환경 변수 최적화

```bash
# 프로덕션 최적화 설정
export APP_LOG_LEVEL=WARNING              # 로그 레벨 최적화
export DB_POOL_SIZE=20                    # 연결 풀 크기
export LLM_MAX_TOKENS=6000               # 토큰 제한
export LLM_TEMPERATURE=0.1               # 일관된 응답
export ENABLE_CACHING=true               # 캐싱 활성화
export CACHE_TTL=300                     # 캐시 TTL (5분)
```

#### JVM 튜닝 (해당하는 경우)

```bash
# Python GC 튜닝
export PYTHONOPTIMIZE=1                  # 최적화 모드
export PYTHONUNBUFFERED=1                # 버퍼링 비활성화
export MALLOC_ARENA_MAX=2                # 메모리 할당 최적화
```

## 📊 용량 계획

### 성장 예측

#### 데이터 증가율 분석

```sql
-- 월별 데이터 증가율
SELECT
    DATE_TRUNC('month', datetime) as month,
    COUNT(*) as record_count,
    pg_size_pretty(pg_total_relation_size('summary')) as table_size
FROM summary
WHERE datetime >= NOW() - INTERVAL '12 months'
GROUP BY DATE_TRUNC('month', datetime)
ORDER BY month;
```

#### 리소스 사용량 예측

```bash
# 현재 사용량 기준 예측
current_records=$(docker-compose exec postgres psql -U 3gpp_user -d 3gpp_analysis_prod -t -c "SELECT COUNT(*) FROM summary;")
current_size=$(docker-compose exec postgres psql -U 3gpp_user -d 3gpp_analysis_prod -t -c "SELECT pg_size_pretty(pg_total_relation_size('summary'));")

echo "현재 레코드 수: $current_records"
echo "현재 테이블 크기: $current_size"

# 연간 예상 증가율 (예: 월 10% 증가)
monthly_growth=1.1
yearly_records=$(echo "$current_records * $monthly_growth^12" | bc -l)
echo "1년 후 예상 레코드 수: $(printf "%.0f" $yearly_records)"
```

### 확장 계획

#### 수직 확장 (Scale Up)

```yaml
# 리소스 증가 계획
services:
  analysis-service:
    deploy:
      resources:
        limits:
          cpus: "4.0" # 2.0 → 4.0
          memory: 8G # 4G → 8G

  postgres:
    deploy:
      resources:
        limits:
          cpus: "2.0" # 1.0 → 2.0
          memory: 4G # 2G → 4G
```

#### 수평 확장 (Scale Out)

```yaml
# 다중 인스턴스 배포
services:
  analysis-service:
    deploy:
      replicas: 3 # 인스턴스 3개

  nginx:
    # 로드 밸런서 설정
    volumes:
      - ./nginx-lb.conf:/etc/nginx/nginx.conf
```

## 🔒 보안 운영

### 정기 보안 점검

#### 주간 보안 체크

```bash
#!/bin/bash
# security_check.sh - 주간 보안 점검

echo "🔒 보안 점검 시작 - $(date)"

# 1. 컨테이너 보안 스캔
echo "1. 컨테이너 보안 스캔:"
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  aquasec/trivy image 3gpp-analysis:latest

# 2. 환경 변수 보안 확인
echo "2. 환경 변수 보안:"
ls -la /opt/3gpp-analysis/config/.env
stat -c "%a %n" /opt/3gpp-analysis/config/.env

# 3. 네트워크 포트 스캔
echo "3. 열린 포트 확인:"
netstat -tlnp | grep -E ":8000|:5432"

# 4. 로그인 시도 분석
echo "4. 의심스러운 로그인 시도:"
docker-compose logs nginx | grep "401\|403" | tail -10

# 5. SSL 인증서 만료일 확인
echo "5. SSL 인증서 상태:"
openssl x509 -in /opt/3gpp-analysis/ssl/cert.pem -noout -dates

echo "✅ 보안 점검 완료"
```

#### 월간 보안 업데이트

```bash
#!/bin/bash
# security_update.sh - 월간 보안 업데이트

echo "🛡️ 보안 업데이트 시작"

# 1. 시스템 패키지 업데이트
sudo apt update && sudo apt upgrade -y

# 2. Docker 이미지 업데이트
docker pull postgres:14
docker pull nginx:alpine

# 3. Python 의존성 보안 스캔
pip install safety
safety check

# 4. 비밀번호 로테이션 (필요시)
# 데이터베이스 비밀번호 변경
# API 키 로테이션

echo "✅ 보안 업데이트 완료"
```

## 📞 운영 지원

### 24/7 운영 체계

#### 운영팀 연락처

| 역할                  | 담당자            | 연락처           | 대응 시간   |
| --------------------- | ----------------- | ---------------- | ----------- |
| **Primary On-call**   | DevOps Engineer   | +82-10-1234-5678 | 24/7        |
| **Secondary On-call** | Backend Developer | +82-10-2345-6789 | 24/7        |
| **Database Admin**    | DBA               | +82-10-3456-7890 | 09:00-18:00 |
| **Security Team**     | Security Engineer | +82-10-4567-8901 | 09:00-18:00 |

#### 에스컬레이션 절차

1. **Level 1** (0-15분): 자동 복구 시도
2. **Level 2** (15-30분): Primary On-call 대응
3. **Level 3** (30-60분): Secondary On-call 및 전문가 투입
4. **Level 4** (60분+): 관리자 및 고위 기술진 투입

### 운영 도구

#### 대시보드 접근

- **Grafana**: http://monitoring.your-domain.com:3000
- **Kibana**: http://logs.your-domain.com:5601
- **Prometheus**: http://metrics.your-domain.com:9090

#### 유용한 스크립트

```bash
# 빠른 상태 확인
alias status='curl -s http://localhost:8000/health | jq .'
alias logs='docker-compose -f docker-compose.prod.yml logs -f analysis-service'
alias stats='docker stats --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}"'

# 긴급 재시작
alias emergency-restart='docker-compose -f docker-compose.prod.yml restart analysis-service'

# 백업 실행
alias backup-now='/opt/3gpp-analysis/scripts/backup_database.sh'
```

## 📚 운영 문서

### 변경 관리

#### 변경 요청 절차

1. **변경 계획서 작성**

   - 변경 내용 및 목적
   - 영향 범위 분석
   - 롤백 계획
   - 테스트 계획

2. **승인 절차**

   - 기술 리뷰
   - 보안 검토
   - 운영팀 승인

3. **변경 실행**
   - 백업 수행
   - 변경 적용
   - 검증 테스트
   - 문서 업데이트

#### 인시던트 관리

```markdown
# 인시던트 보고서 템플릿

## 인시던트 정보

- **ID**: INC-2025-001
- **발생 시간**: 2025-09-19 16:30:00 KST
- **감지 시간**: 2025-09-19 16:32:00 KST
- **해결 시간**: 2025-09-19 16:45:00 KST
- **영향 범위**: 전체 서비스

## 증상

- API 응답시간 급증 (평균 200ms)
- 오류율 15% 증가
- 사용자 불만 접수

## 원인 분석

- 데이터베이스 연결 풀 고갈
- 장시간 실행 쿼리로 인한 락 대기

## 해결 조치

1. 연결 풀 크기 증가 (10 → 20)
2. 장시간 쿼리 강제 종료
3. 인덱스 재구성

## 예방 조치

- 쿼리 성능 모니터링 강화
- 연결 풀 크기 자동 조정
- 알람 임계값 조정

## 학습 사항

- 피크 시간대 리소스 부족 현상
- 모니터링 사각지대 발견
```

### 운영 매뉴얼

#### 일상 운영 체크리스트

**매일 09:00 (업무 시작)**

- [ ] 시스템 헬스체크 실행
- [ ] 밤새 발생한 오류 로그 검토
- [ ] 성능 메트릭 확인 (응답시간, 처리량)
- [ ] 디스크 사용량 점검
- [ ] 백업 상태 확인

**매일 18:00 (업무 종료)**

- [ ] 금일 성능 통계 리뷰
- [ ] 오류 패턴 분석
- [ ] 리소스 사용량 트렌드 확인
- [ ] 다음날 예상 부하 검토

**매주 월요일 10:00**

- [ ] 주간 성능 리포트 생성
- [ ] 데이터베이스 통계 업데이트
- [ ] 시스템 최적화 작업
- [ ] 보안 점검 실행

**매월 1일**

- [ ] 월간 성능 리포트 생성
- [ ] 용량 계획 검토
- [ ] 보안 업데이트 적용
- [ ] 재해 복구 테스트

## 🎯 성공적인 운영을 위한 권장사항

### 모니터링 모범 사례

1. **계층적 모니터링**: 인프라 → 애플리케이션 → 비즈니스 메트릭
2. **예방적 알람**: 문제 발생 전 조기 감지
3. **자동화**: 반복적인 작업의 스크립트화
4. **문서화**: 모든 절차와 결정사항 기록

### 성능 최적화 지속

1. **정기적 벤치마킹**: 월 1회 성능 테스트 실행
2. **프로파일링**: 분기별 상세 성능 분석
3. **용량 계획**: 분기별 리소스 요구사항 검토
4. **기술 부채 관리**: 분기별 리팩토링 계획

### 팀 협업

1. **운영 회의**: 주 1회 운영 현황 공유
2. **포스트모템**: 인시던트 발생 시 학습 세션
3. **지식 공유**: 월 1회 기술 세미나
4. **교육**: 분기별 신규 기능 교육

---

이 운영 가이드를 통해 안정적이고 효율적인 시스템 운영을 달성하세요! 🎯
