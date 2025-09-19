# 데이터베이스 최적화 권고사항

## 📊 권장 인덱스 생성

### 1. 기본 인덱스

```sql
-- 시간 범위 + NE 복합 인덱스 (가장 중요)
CREATE INDEX CONCURRENTLY idx_summary_datetime_ne
ON summary (datetime, ne);

-- 셀 ID + 시간 복합 인덱스
CREATE INDEX CONCURRENTLY idx_summary_cellid_datetime
ON summary (cellid, datetime);

-- PEG 이름 + 시간 복합 인덱스
CREATE INDEX CONCURRENTLY idx_summary_peg_name_datetime
ON summary (peg_name, datetime);
```

### 2. 고성능 복합 인덱스

```sql
-- 최적화된 복합 인덱스 (모든 주요 필터 컬럼 포함)
CREATE INDEX CONCURRENTLY idx_summary_composite
ON summary (ne, cellid, datetime, peg_name);

-- 호스트 기반 조회용 인덱스
CREATE INDEX CONCURRENTLY idx_summary_host_datetime
ON summary (host, datetime);
```

## 🔧 쿼리 최적화 패턴

### 1. WHERE 절 최적화

- ✅ 시간 범위 필터를 WHERE 절 최우선으로 배치
- ✅ 복합 인덱스 활용을 위한 필터 순서: `ne` → `cellid` → `peg_name` → `host`
- ✅ IN 절에서 빈 리스트 체크 추가
- ✅ SQL 인젝션 방지를 위한 컬럼명 검증

### 2. SELECT 절 최적화

- ✅ 필요한 컬럼만 조회 (SELECT \* 방지)
- ✅ 컬럼 별칭 사용으로 결과 일관성 보장
- ✅ 메모리 효율적인 데이터 변환

### 3. ORDER BY 및 LIMIT 최적화

- ✅ 시간순 정렬로 인덱스 활용
- ✅ LIMIT으로 결과 집합 크기 제한
- ✅ 대용량 데이터 처리 시 성능 향상

## 📈 예상 성능 개선 효과

| 최적화 항목          | 예상 개선 효과           | 적용 상황          |
| -------------------- | ------------------------ | ------------------ |
| **인덱스 최적화**    | 50-80% 쿼리 시간 단축    | 모든 쿼리          |
| **필터 순서 최적화** | 10-20% 쿼리 시간 단축    | 복합 필터 쿼리     |
| **컬럼 선택 최적화** | 5-15% 메모리 사용량 감소 | 대용량 결과 집합   |
| **LIMIT 최적화**     | 90% 이상 개선            | 대용량 데이터 조회 |

## ⚡ 성능 모니터링

### 1. 쿼리 실행 시간 추적

- 100ms 초과 쿼리에 대한 자동 경고
- 실행 시간 로깅으로 성능 트렌드 모니터링

### 2. 메모리 사용량 최적화

- RealDictRow → dict 변환 최적화
- 커넥션 풀 활용으로 연결 오버헤드 감소

### 3. 인덱스 효율성 검증

```sql
-- 인덱스 사용량 확인
EXPLAIN (ANALYZE, BUFFERS)
SELECT datetime, peg_name, value, ne, cellid
FROM summary
WHERE datetime >= '2025-01-01 09:00:00'
  AND datetime < '2025-01-01 18:00:00'
  AND ne = 'nvgnb#10001'
  AND cellid IN ('cell_001', 'cell_002')
ORDER BY datetime
LIMIT 1000;
```

## 🚀 구현 상태

### ✅ 완료된 최적화

1. **쿼리 구조 최적화**: WHERE 절 순서, SELECT 절 최적화
2. **인덱스 활용 최적화**: 복합 인덱스를 고려한 필터 순서
3. **성능 모니터링**: 실행 시간 추적 및 경고 시스템
4. **메모리 최적화**: 효율적인 데이터 변환 및 처리

### 🔄 추가 최적화 고려사항

1. **파티셔닝**: 시간 기반 테이블 파티셔닝 (월별/일별)
2. **쿼리 캐싱**: 자주 사용되는 쿼리 결과 캐싱
3. **배치 처리**: 대용량 데이터 조회 시 청크 단위 처리
4. **읽기 전용 복제본**: 읽기 부하 분산을 위한 슬레이브 DB 활용

## 📋 데이터베이스 관리 체크리스트

### 일일 모니터링

- [ ] 쿼리 실행 시간 100ms 초과 건수 확인
- [ ] 인덱스 사용률 모니터링
- [ ] 커넥션 풀 상태 확인

### 주간 최적화

- [ ] 느린 쿼리 로그 분석
- [ ] 인덱스 효율성 검토
- [ ] 테이블 통계 업데이트

### 월간 검토

- [ ] 파티셔닝 필요성 검토
- [ ] 인덱스 재구성 고려
- [ ] 용량 계획 및 확장성 검토
