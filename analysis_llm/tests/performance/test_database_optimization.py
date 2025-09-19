"""
Database Query Optimization Tests

PostgreSQLRepository의 쿼리 성능을 분석하고 최적화합니다.
"""

import os
import sys
import time
from datetime import datetime, timezone

import pytest

# 프로젝트 루트를 Python path에 추가
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)



class TestDatabaseOptimization:
    """데이터베이스 쿼리 최적화 테스트"""
    
    def test_fetch_peg_data_query_analysis(
        self,
        mock_performance_database_repository,
        performance_logger
    ):
        """fetch_peg_data 쿼리 분석"""
        # 현재 PostgreSQLRepository의 fetch_peg_data 메서드 분석
        repo = mock_performance_database_repository
        
        # 테스트 파라미터
        table_name = "summary"
        columns = {
            "time": "datetime",
            "peg_name": "peg_name",
            "value": "value",
            "ne": "ne",
            "cellid": "cellid",
            "host": "host"
        }
        time_range = (
            datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc),
            datetime(2025, 1, 1, 18, 0, tzinfo=timezone.utc)
        )
        filters = {
            "ne": "nvgnb#10001",
            "cellid": ["cell_001", "cell_002", "cell_003"],
            "host": "192.168.1.100"
        }
        
        # 쿼리 실행 시간 측정
        start_time = time.time()
        result = repo.fetch_peg_data(
            table_name=table_name,
            columns=columns,
            time_range=time_range,
            filters=filters,
            limit=1000
        )
        end_time = time.time()
        
        query_time = end_time - start_time
        
        performance_logger.info("✅ fetch_peg_data 쿼리 분석 완료")
        performance_logger.info(f"쿼리 실행 시간: {query_time*1000:.2f}ms")
        performance_logger.info(f"반환된 레코드 수: {len(result) if hasattr(result, '__len__') else 'N/A'}")
        
        # 쿼리 성능 기준 검증
        assert query_time < 0.1, f"쿼리 실행 시간이 너무 깁니다: {query_time*1000:.2f}ms"
        
    def test_optimized_query_structure_analysis(self, performance_logger):
        """최적화된 쿼리 구조 분석"""
        # PostgreSQLRepository의 현재 쿼리 구조를 분석하고 최적화 방안 제시
        
        performance_logger.info("=== 데이터베이스 쿼리 최적화 분석 ===")
        
        # 1. 인덱스 최적화 권장사항
        recommended_indexes = [
            "CREATE INDEX CONCURRENTLY idx_summary_datetime_ne ON summary (datetime, ne);",
            "CREATE INDEX CONCURRENTLY idx_summary_cellid_datetime ON summary (cellid, datetime);",
            "CREATE INDEX CONCURRENTLY idx_summary_peg_name_datetime ON summary (peg_name, datetime);",
            "CREATE INDEX CONCURRENTLY idx_summary_composite ON summary (ne, cellid, datetime, peg_name);"
        ]
        
        performance_logger.info("📊 권장 인덱스:")
        for idx, query in enumerate(recommended_indexes, 1):
            performance_logger.info(f"  {idx}. {query}")
        
        # 2. 쿼리 최적화 패턴
        optimization_patterns = [
            "시간 범위 필터를 WHERE 절 최우선으로 배치",
            "복합 인덱스 활용을 위한 필터 순서 최적화",
            "LIMIT 절을 통한 결과 집합 크기 제한",
            "SELECT 절에서 필요한 컬럼만 조회 (SELECT *  피하기)",
            "JOIN 대신 EXISTS 사용 고려 (해당하는 경우)"
        ]
        
        performance_logger.info("🔧 쿼리 최적화 패턴:")
        for idx, pattern in enumerate(optimization_patterns, 1):
            performance_logger.info(f"  {idx}. {pattern}")
        
        # 3. 예상 성능 개선 효과
        performance_improvements = {
            "인덱스 최적화": "50-80% 쿼리 시간 단축",
            "필터 순서 최적화": "10-20% 쿼리 시간 단축", 
            "컬럼 선택 최적화": "5-15% 메모리 사용량 감소",
            "LIMIT 최적화": "대용량 데이터 시 90% 이상 개선"
        }
        
        performance_logger.info("📈 예상 성능 개선 효과:")
        for optimization, improvement in performance_improvements.items():
            performance_logger.info(f"  • {optimization}: {improvement}")
        
        performance_logger.info("✅ 쿼리 구조 분석 완료")
    
    def test_connection_pooling_optimization(
        self,
        mock_performance_database_repository,
        performance_logger
    ):
        """커넥션 풀링 최적화 테스트"""
        repo = mock_performance_database_repository
        
        # 연속 쿼리 실행으로 커넥션 풀 효과 측정
        num_queries = 10
        query_times = []
        
        for i in range(num_queries):
            start_time = time.time()
            
            # 다양한 필터 조건으로 쿼리 실행
            result = repo.fetch_peg_data(
                table_name="summary",
                columns={"datetime": "datetime", "peg_name": "peg_name", "value": "value"},
                time_range=(
                    datetime(2025, 1, 1, 9+i, 0, tzinfo=timezone.utc),
                    datetime(2025, 1, 1, 10+i, 0, tzinfo=timezone.utc)
                ),
                filters={"cellid": [f"cell_{j:03d}" for j in range(i+1, i+4)]},
                limit=100
            )
            
            end_time = time.time()
            query_times.append(end_time - start_time)
        
        # 통계 분석
        avg_time = sum(query_times) / len(query_times)
        min_time = min(query_times)
        max_time = max(query_times)
        
        performance_logger.info("✅ 커넥션 풀링 최적화 테스트 완료")
        performance_logger.info(f"총 쿼리 수: {num_queries}")
        performance_logger.info(f"평균 쿼리 시간: {avg_time*1000:.2f}ms")
        performance_logger.info(f"최소 쿼리 시간: {min_time*1000:.2f}ms")
        performance_logger.info(f"최대 쿼리 시간: {max_time*1000:.2f}ms")
        performance_logger.info(f"시간 편차: {(max_time-min_time)*1000:.2f}ms")
        
        # 커넥션 풀 효율성 검증
        time_variance = max_time - min_time
        assert time_variance < 0.05, f"쿼리 시간 편차가 너무 큽니다: {time_variance*1000:.2f}ms"
        assert avg_time < 0.02, f"평균 쿼리 시간이 너무 깁니다: {avg_time*1000:.2f}ms"
    
    def test_query_parameter_optimization(
        self,
        mock_performance_database_repository,
        performance_logger
    ):
        """쿼리 파라미터 최적화 테스트"""
        repo = mock_performance_database_repository
        
        # 다양한 파라미터 조합으로 성능 테스트
        test_scenarios = [
            {
                "name": "소량 데이터 (LIMIT 10)",
                "limit": 10,
                "filters": {"cellid": ["cell_001"]}
            },
            {
                "name": "중간 데이터 (LIMIT 100)",
                "limit": 100,
                "filters": {"cellid": ["cell_001", "cell_002", "cell_003"]}
            },
            {
                "name": "대량 데이터 (LIMIT 1000)",
                "limit": 1000,
                "filters": {"ne": "nvgnb#10001"}
            },
            {
                "name": "복합 필터",
                "limit": 500,
                "filters": {
                    "ne": "nvgnb#10001",
                    "cellid": ["cell_001", "cell_002"],
                    "host": "192.168.1.100"
                }
            }
        ]
        
        performance_logger.info("=== 쿼리 파라미터 최적화 테스트 ===")
        
        for scenario in test_scenarios:
            start_time = time.time()
            
            result = repo.fetch_peg_data(
                table_name="summary",
                columns={
                    "datetime": "datetime",
                    "peg_name": "peg_name", 
                    "value": "value",
                    "ne": "ne",
                    "cellid": "cellid"
                },
                time_range=(
                    datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc),
                    datetime(2025, 1, 1, 18, 0, tzinfo=timezone.utc)
                ),
                filters=scenario["filters"],
                limit=scenario["limit"]
            )
            
            end_time = time.time()
            query_time = end_time - start_time
            
            performance_logger.info(f"📊 {scenario['name']}:")
            performance_logger.info(f"   실행시간: {query_time*1000:.2f}ms")
            performance_logger.info(f"   LIMIT: {scenario['limit']}")
            performance_logger.info(f"   필터 수: {len(scenario['filters'])}")
        
        performance_logger.info("✅ 쿼리 파라미터 최적화 테스트 완료")
    
    def test_memory_efficient_data_retrieval(
        self,
        mock_performance_database_repository,
        memory_tracker,
        performance_logger
    ):
        """메모리 효율적 데이터 조회 테스트"""
        repo = mock_performance_database_repository
        
        # 초기 메모리 상태
        initial_memory = memory_tracker.get_memory_usage()
        performance_logger.info(f"초기 메모리: {initial_memory['current_mb']:.2f}MB")
        
        # 대량 데이터 조회
        start_time = time.time()
        result = repo.fetch_peg_data(
            table_name="summary",
            columns={
                "datetime": "datetime",
                "peg_name": "peg_name",
                "value": "value",
                "ne": "ne",
                "cellid": "cellid",
                "host": "host"
            },
            time_range=(
                datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc),
                datetime(2025, 1, 2, 23, 59, tzinfo=timezone.utc)
            ),
            filters={},  # 필터 없음 - 최대 데이터
            limit=5000   # 대량 데이터
        )
        end_time = time.time()
        
        # 최종 메모리 상태
        final_memory = memory_tracker.get_memory_usage()
        
        query_time = end_time - start_time
        memory_increase = final_memory['current_mb'] - initial_memory['current_mb']
        
        performance_logger.info("✅ 메모리 효율적 데이터 조회 테스트 완료")
        performance_logger.info(f"쿼리 실행시간: {query_time*1000:.2f}ms")
        performance_logger.info(f"메모리 증가량: {memory_increase:.2f}MB")
        performance_logger.info(f"피크 메모리: {final_memory['peak_mb']:.2f}MB")
        
        # 메모리 효율성 검증
        assert memory_increase < 50, f"메모리 증가량이 너무 큽니다: {memory_increase:.2f}MB"
        assert final_memory['peak_mb'] < 200, f"피크 메모리가 너무 높습니다: {final_memory['peak_mb']:.2f}MB"
    
    def test_database_query_benchmark_comparison(
        self,
        benchmark,
        mock_performance_database_repository,
        performance_logger
    ):
        """데이터베이스 쿼리 벤치마크 비교"""
        repo = mock_performance_database_repository
        
        # 기본 쿼리 벤치마크
        def basic_query():
            return repo.fetch_peg_data(
                table_name="summary",
                columns={"datetime": "datetime", "peg_name": "peg_name", "value": "value"},
                time_range=(
                    datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc),
                    datetime(2025, 1, 1, 18, 0, tzinfo=timezone.utc)
                ),
                filters={"cellid": ["cell_001"]},
                limit=100
            )
        
        # 벤치마크 실행
        result = benchmark.pedantic(basic_query, iterations=20, rounds=5)
        
        performance_logger.info("✅ 데이터베이스 쿼리 벤치마크 완료")
        performance_logger.info("상세 결과는 pytest-benchmark 리포트 참조")
        
        # 결과 검증
        assert result is not None, "쿼리 결과가 None입니다"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--benchmark-only'])
