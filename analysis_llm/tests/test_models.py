"""
데이터 모델 단위 테스트

이 모듈은 models 패키지의 모든 데이터 모델에 대한 단위 테스트를 포함합니다.
"""

import unittest
from datetime import datetime

from analysis_llm.models import (
    AggregatedPEGData,
    AnalysisContext,
    AnalysisRequest,
    AnalysisResponse,
    AnalysisStats,
    DatabaseConfig,
    FilterConfig,
    PEGConfig,
    PEGData,
    PEGStatistics,
    ProcessedPEGData,
    TableConfig,
    TimeRange,
)


class TestRequestModels(unittest.TestCase):
    """요청 모델 테스트"""
    
    def test_database_config_creation(self):
        """DatabaseConfig 생성 테스트"""
        config = DatabaseConfig(
            host="localhost",
            port=5432,
            user="testuser",
            password="testpass",
            dbname="testdb"
        )
        
        self.assertEqual(config.host, "localhost")
        self.assertEqual(config.port, 5432)
        self.assertEqual(config.user, "testuser")
        self.assertEqual(config.dbname, "testdb")
    
    def test_database_config_validation(self):
        """DatabaseConfig 검증 테스트"""
        with self.assertRaises(ValueError):
            DatabaseConfig(host="", user="test", dbname="test")
        
        with self.assertRaises(ValueError):
            DatabaseConfig(host="localhost", user="", dbname="test")
    
    def test_table_config_creation(self):
        """TableConfig 생성 테스트"""
        config = TableConfig(
            table="test_table",
            time_column="timestamp",
            peg_name_column="peg",
            value_column="val"
        )
        
        self.assertEqual(config.table, "test_table")
        self.assertEqual(config.time_column, "timestamp")
        self.assertEqual(config.peg_name_column, "peg")
        self.assertEqual(config.value_column, "val")
    
    def test_filter_config_string_normalization(self):
        """FilterConfig 문자열 정규화 테스트"""
        config = FilterConfig(
            ne="nvgnb#10000,nvgnb#20000",
            cellid="2010,2011,2012",
            host="host1,host2"
        )
        
        self.assertEqual(config.ne, ["nvgnb#10000", "nvgnb#20000"])
        self.assertEqual(config.cellid, ["2010", "2011", "2012"])
        self.assertEqual(config.host, ["host1", "host2"])
    
    def test_peg_config_validation(self):
        """PEGConfig 검증 테스트"""
        config = PEGConfig(peg_definitions={
            "success_rate": "A/B*100",
            "drop_rate": "(C-D)/C*100"
        })
        
        self.assertTrue(config.has_derived_pegs())
        self.assertEqual(len(config.peg_definitions), 2)
        
        # 빈 설정
        empty_config = PEGConfig()
        self.assertFalse(empty_config.has_derived_pegs())
    
    def test_analysis_request_creation(self):
        """AnalysisRequest 생성 테스트"""
        request = AnalysisRequest(
            n_minus_1="2025-01-01_00:00~2025-01-01_23:59",
            n="2025-01-02_00:00~2025-01-02_23:59"
        )
        
        self.assertEqual(request.n_minus_1, "2025-01-01_00:00~2025-01-01_23:59")
        self.assertEqual(request.n, "2025-01-02_00:00~2025-01-02_23:59")
        self.assertEqual(request.output_dir, "./analysis_output")
    
    def test_analysis_request_from_dict(self):
        """AnalysisRequest.from_dict() 테스트"""
        data = {
            "n_minus_1": "2025-01-01_00:00~2025-01-01_23:59",
            "n": "2025-01-02_00:00~2025-01-02_23:59",
            "db": {"host": "testhost", "port": 5432, "user": "testuser", "dbname": "testdb"},
            "preference": "PEG_A,PEG_B",
            "peg_definitions": {"derived_peg": "A/B*100"}
        }
        
        request = AnalysisRequest.from_dict(data)
        
        self.assertEqual(request.db_config.host, "testhost")
        self.assertEqual(request.filter_config.preference, ["PEG_A", "PEG_B"])
        self.assertTrue(request.peg_config.has_derived_pegs())


class TestResponseModels(unittest.TestCase):
    """응답 모델 테스트"""
    
    def test_analysis_stats_creation(self):
        """AnalysisStats 생성 테스트"""
        stats = AnalysisStats(
            total_pegs=100,
            processed_pegs=95,
            derived_pegs=5,
            analysis_duration_seconds=120.5,
            llm_tokens_used=1500
        )
        
        self.assertEqual(stats.total_pegs, 100)
        self.assertEqual(stats.processed_pegs, 95)
        self.assertEqual(stats.derived_pegs, 5)
        self.assertEqual(stats.analysis_duration_seconds, 120.5)
        self.assertEqual(stats.llm_tokens_used, 1500)
    
    def test_peg_statistics_creation(self):
        """PEGStatistics 생성 테스트"""
        stat = PEGStatistics(
            peg_name="Random_access_preamble_count",
            avg_n_minus_1=100.0,
            avg_n=110.0,
            diff=10.0,
            pct_change=10.0
        )
        
        self.assertEqual(stat.peg_name, "Random_access_preamble_count")
        self.assertEqual(stat.avg_n_minus_1, 100.0)
        self.assertEqual(stat.avg_n, 110.0)
        self.assertEqual(stat.diff, 10.0)
        self.assertEqual(stat.pct_change, 10.0)
    
    def test_analysis_response_status_management(self):
        """AnalysisResponse 상태 관리 테스트"""
        response = AnalysisResponse()
        self.assertEqual(response.status, "pending")
        
        response.mark_completed("분석 완료")
        self.assertEqual(response.status, "completed")
        self.assertEqual(response.message, "분석 완료")
        self.assertTrue(response.is_completed())
        
        response.mark_error("오류 발생", {"code": 500})
        self.assertEqual(response.status, "error")
        self.assertTrue(response.is_error())
        self.assertEqual(response.error_details["code"], 500)
    
    def test_analysis_response_factory_methods(self):
        """AnalysisResponse 팩토리 메서드 테스트"""
        success_response = AnalysisResponse.create_success_response("성공")
        self.assertTrue(success_response.is_completed())
        self.assertEqual(success_response.message, "성공")
        
        error_response = AnalysisResponse.create_error_response("실패", {"error": "test"})
        self.assertTrue(error_response.is_error())
        self.assertEqual(error_response.message, "실패")
        self.assertEqual(error_response.error_details["error"], "test")


class TestDomainModels(unittest.TestCase):
    """도메인 모델 테스트"""
    
    def test_time_range_creation(self):
        """TimeRange 생성 테스트"""
        start = datetime(2025, 1, 1, 0, 0)
        end = datetime(2025, 1, 1, 23, 59)
        
        time_range = TimeRange(start_time=start, end_time=end)
        
        self.assertEqual(time_range.start_time, start)
        self.assertEqual(time_range.end_time, end)
        self.assertAlmostEqual(time_range.duration_hours(), 23.98, places=1)
    
    def test_time_range_validation(self):
        """TimeRange 검증 테스트"""
        start = datetime(2025, 1, 1, 12, 0)
        end = datetime(2025, 1, 1, 10, 0)  # 시작보다 이른 종료 시간
        
        with self.assertRaises(ValueError):
            TimeRange(start_time=start, end_time=end)
    
    def test_peg_data_creation(self):
        """PEGData 생성 테스트"""
        timestamp = datetime.now()
        peg = PEGData(
            peg_name="Random_access_preamble_count",
            value=100.5,
            timestamp=timestamp,
            ne="nvgnb#10000",
            cellid="2010"
        )
        
        self.assertEqual(peg.peg_name, "Random_access_preamble_count")
        self.assertEqual(peg.value, 100.5)
        self.assertEqual(peg.timestamp, timestamp)
        self.assertEqual(peg.ne, "nvgnb#10000")
        self.assertTrue(peg.is_valid_value())
    
    def test_aggregated_peg_data_creation(self):
        """AggregatedPEGData 생성 테스트"""
        start = datetime(2025, 1, 1, 0, 0)
        end = datetime(2025, 1, 1, 23, 59)
        time_range = TimeRange(start_time=start, end_time=end)
        
        agg_peg = AggregatedPEGData(
            peg_name="Random_access_preamble_count",
            avg_value=100.0,
            min_value=50.0,
            max_value=150.0,
            count=100,
            time_range=time_range
        )
        
        self.assertEqual(agg_peg.peg_name, "Random_access_preamble_count")
        self.assertEqual(agg_peg.avg_value, 100.0)
        self.assertTrue(agg_peg.has_data())
        
        variance_info = agg_peg.get_variance_info()
        self.assertEqual(variance_info['range'], 100.0)  # 150 - 50
        self.assertEqual(variance_info['spread_ratio'], 1.0)  # 100/100
    
    def test_processed_peg_data_calculations(self):
        """ProcessedPEGData 계산 테스트"""
        start = datetime(2025, 1, 1, 0, 0)
        end = datetime(2025, 1, 1, 23, 59)
        time_range = TimeRange(start_time=start, end_time=end)
        
        n_minus_1 = AggregatedPEGData(
            peg_name="test_peg",
            avg_value=100.0,
            min_value=90.0,
            max_value=110.0,
            count=50,
            time_range=time_range
        )
        
        n = AggregatedPEGData(
            peg_name="test_peg",
            avg_value=120.0,
            min_value=110.0,
            max_value=130.0,
            count=60,
            time_range=time_range
        )
        
        processed = ProcessedPEGData(
            peg_name="test_peg",
            n_minus_1_data=n_minus_1,
            n_data=n
        )
        
        self.assertEqual(processed.diff, 20.0)  # 120 - 100
        self.assertEqual(processed.pct_change, 20.0)  # (20/100) * 100
        self.assertEqual(processed.get_trend(), "increasing")
        self.assertTrue(processed.is_significant_change())
        self.assertTrue(processed.has_both_periods_data())
    
    def test_analysis_context_creation(self):
        """AnalysisContext 생성 테스트"""
        start1 = datetime(2025, 1, 1, 0, 0)
        end1 = datetime(2025, 1, 1, 23, 59)
        start2 = datetime(2025, 1, 2, 0, 0)
        end2 = datetime(2025, 1, 2, 23, 59)
        
        n_minus_1_range = TimeRange(start_time=start1, end_time=end1)
        n_range = TimeRange(start_time=start2, end_time=end2)
        
        context = AnalysisContext(
            analysis_id="test_analysis_001",
            n_minus_1_range=n_minus_1_range,
            n_range=n_range,
            filter_conditions={"ne": ["nvgnb#10000"]},
            derived_peg_definitions={"success_rate": "A/B*100"}
        )
        
        self.assertEqual(context.analysis_id, "test_analysis_001")
        self.assertTrue(context.has_filters())
        self.assertTrue(context.has_derived_pegs())
        self.assertAlmostEqual(context.get_total_duration_hours(), 47.96, places=1)


if __name__ == '__main__':
    # 로깅 레벨 설정 (테스트 중 로그 출력 최소화)
    import logging
    logging.getLogger().setLevel(logging.WARNING)
    
    unittest.main()
