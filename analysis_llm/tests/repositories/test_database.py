"""
Database Repository 단위 테스트

PostgreSQLRepository와 DatabaseRepository 인터페이스의
모든 공개 메서드에 대한 포괄적인 단위 테스트를 제공합니다.
"""

import os
import sys
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor

# 프로젝트 루트를 Python path에 추가
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)

from models import TimeRange
from repositories import DatabaseError, DatabaseRepository, PostgreSQLRepository


class TestDatabaseRepository(unittest.TestCase):
    """DatabaseRepository ABC 테스트"""
    
    def test_abstract_base_class(self):
        """DatabaseRepository가 추상 기본 클래스인지 검증"""
        with self.assertRaises(TypeError):
            # 추상 클래스는 직접 인스턴스화할 수 없음
            DatabaseRepository()
    
    def test_abstract_methods_defined(self):
        """추상 메서드들이 올바르게 정의되었는지 검증"""
        abstract_methods = DatabaseRepository.__abstractmethods__
        expected_methods = {
            'connect', 'disconnect', 'fetch_data', 
            'execute_query', 'test_connection'
        }
        
        self.assertEqual(abstract_methods, expected_methods)


class TestPostgreSQLRepository(unittest.TestCase):
    """PostgreSQLRepository 단위 테스트"""
    
    def setUp(self):
        """테스트 설정"""
        # Mock 설정으로 PostgreSQLRepository 초기화
        self.mock_config = {
            'db_host': 'test_host',
            'db_port': 5432,
            'db_name': 'test_db',
            'db_user': 'test_user',
            'db_password': 'test_pass'
        }
        
        # PostgreSQL 관련 모듈들을 Mock으로 패치
        self.patcher_psycopg2 = patch('repositories.database.psycopg2')
        self.patcher_pool = patch('psycopg2.pool.SimpleConnectionPool')
        self.patcher_get_settings = patch('repositories.database.get_settings')
        
        self.mock_psycopg2 = self.patcher_psycopg2.start()
        self.mock_pool_class = self.patcher_pool.start()
        self.mock_get_settings = self.patcher_get_settings.start()
        
        # Mock 설정 반환
        mock_settings = Mock()
        mock_settings.db_host = 'test_host'
        mock_settings.db_port = 5432
        mock_settings.db_name = 'test_db'
        mock_settings.db_user = 'test_user'
        mock_settings.db_password = Mock()
        mock_settings.db_password.get_secret_value.return_value = 'test_pass'
        self.mock_get_settings.return_value = mock_settings
        
        # Mock 연결 풀
        self.mock_pool = Mock()
        self.mock_pool_class.return_value = self.mock_pool
        
        # Mock 연결
        self.mock_connection = Mock()
        self.mock_cursor = Mock()
        self.mock_connection.cursor.return_value = self.mock_cursor
        self.mock_pool.getconn.return_value = self.mock_connection
        
        # PostgreSQLRepository 인스턴스 생성
        self.repo = PostgreSQLRepository(config_override=self.mock_config)
    
    def tearDown(self):
        """테스트 정리"""
        self.patcher_psycopg2.stop()
        self.patcher_pool.stop()
        self.patcher_get_settings.stop()
    
    def test_initialization_with_config_override(self):
        """설정 오버라이드로 초기화 테스트"""
        # 설정 오버라이드가 올바르게 적용되었는지 확인
        self.assertEqual(self.repo.host, 'test_host')
        self.assertEqual(self.repo.port, 5432)
        self.assertEqual(self.repo.database, 'test_db')
        self.assertEqual(self.repo.user, 'test_user')
        self.assertEqual(self.repo.password, 'test_pass')
    
    def test_initialization_with_configuration_manager(self):
        """Configuration Manager로 초기화 테스트"""
        # 새로운 인스턴스 생성 (설정 오버라이드 없음)
        repo_with_config = PostgreSQLRepository()
        
        # Configuration Manager에서 설정이 로드되었는지 확인
        self.mock_get_settings.assert_called()
        self.assertEqual(repo_with_config.host, 'test_host')
    
    def test_connection_pool_creation(self):
        """연결 풀 생성 테스트"""
        # 연결 풀이 올바른 매개변수로 생성되었는지 확인
        self.mock_pool_class.assert_called_once_with(
            minconn=1,
            maxconn=10,
            host='test_host',
            port=5432,
            database='test_db',
            user='test_user',
            password='test_pass'
        )
    
    @patch('repositories.database.PostgreSQLRepository.get_connection')
    def test_fetch_data_success(self, mock_get_connection):
        """fetch_data 성공 시나리오 테스트"""
        # Mock 컨텍스트 매니저 설정
        mock_context = Mock()
        mock_get_connection.return_value = mock_context
        mock_context.__enter__ = Mock(return_value=self.mock_connection)
        mock_context.__exit__ = Mock(return_value=None)
        
        # Mock 커서 결과 설정
        mock_data = [
            {'peg_name': 'preamble_count', 'avg_value': 1000.0, 'period': 'N-1'},
            {'peg_name': 'response_count', 'avg_value': 950.0, 'period': 'N-1'}
        ]
        self.mock_cursor.fetchall.return_value = mock_data
        
        # 테스트 실행
        result = self.repo.fetch_data(
            table='summary',
            columns=['peg_name', 'avg_value', 'period'],
            where_conditions={'period': 'N-1'},
            limit=100
        )
        
        # 결과 검증
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['peg_name'], 'preamble_count')
        
        # SQL 실행 확인
        self.mock_cursor.execute.assert_called_once()
        executed_query = self.mock_cursor.execute.call_args[0][0]
        self.assertIn('SELECT', executed_query)
        self.assertIn('summary', executed_query)
        self.assertIn('LIMIT', executed_query)
    
    @patch('repositories.database.PostgreSQLRepository.get_connection')
    def test_fetch_data_empty_result(self, mock_get_connection):
        """fetch_data 빈 결과 테스트"""
        # Mock 설정
        mock_context = Mock()
        mock_get_connection.return_value = mock_context
        mock_context.__enter__ = Mock(return_value=self.mock_connection)
        mock_context.__exit__ = Mock(return_value=None)
        
        # 빈 결과 설정
        self.mock_cursor.fetchall.return_value = []
        
        # 테스트 실행
        result = self.repo.fetch_data('summary', ['peg_name'])
        
        # 결과 검증
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 0)
    
    @patch('repositories.database.PostgreSQLRepository.get_connection')
    def test_fetch_data_database_error(self, mock_get_connection):
        """fetch_data 데이터베이스 오류 테스트"""
        # Mock 컨텍스트에서 예외 발생
        mock_get_connection.side_effect = psycopg2.OperationalError("Connection failed")
        
        # 테스트 실행 및 예외 확인
        with self.assertRaises(DatabaseError) as context:
            self.repo.fetch_data('summary', ['peg_name'])
        
        # 오류 세부 정보 확인
        error = context.exception
        self.assertIn("데이터 조회 실패", error.message)
        self.assertEqual(error.operation_type, "SELECT")
    
    @patch('repositories.database.PostgreSQLRepository.get_connection')
    def test_fetch_peg_data_success(self, mock_get_connection):
        """fetch_peg_data 성공 시나리오 테스트"""
        # Mock 설정
        mock_context = Mock()
        mock_get_connection.return_value = mock_context
        mock_context.__enter__ = Mock(return_value=self.mock_connection)
        mock_context.__exit__ = Mock(return_value=None)
        
        # Mock 데이터 설정
        mock_data = [
            {
                'datetime': datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc),
                'peg_name': 'preamble_count',
                'value': 1000.0
            }
        ]
        self.mock_cursor.fetchall.return_value = mock_data
        
        # 시간 범위 설정
        time_range = TimeRange(
            start=datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc),
            end=datetime(2025, 1, 1, 18, 0, tzinfo=timezone.utc)
        )
        
        # 테스트 실행
        result = self.repo.fetch_peg_data(
            time_range=time_range,
            table='summary',
            filters={'ne': 'nvgnb#10000'}
        )
        
        # 결과 검증
        self.assertIsInstance(result, pd.DataFrame)
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]['peg_name'], 'preamble_count')
        
        # SQL 실행 확인
        self.mock_cursor.execute.assert_called_once()
        executed_query = self.mock_cursor.execute.call_args[0][0]
        self.assertIn('WHERE', executed_query)
        self.assertIn('datetime >=', executed_query)
        self.assertIn('datetime <', executed_query)
    
    @patch('repositories.database.PostgreSQLRepository.get_connection')
    def test_execute_query_success(self, mock_get_connection):
        """execute_query 성공 시나리오 테스트"""
        # Mock 설정
        mock_context = Mock()
        mock_get_connection.return_value = mock_context
        mock_context.__enter__ = Mock(return_value=self.mock_connection)
        mock_context.__exit__ = Mock(return_value=None)
        
        # 영향받은 행 수 설정
        self.mock_cursor.rowcount = 1
        
        # 테스트 실행
        result = self.repo.execute_query(
            "INSERT INTO test_table (name) VALUES (%s)",
            ('test_value',)
        )
        
        # 결과 검증
        self.assertEqual(result, 1)
        
        # SQL 실행 및 커밋 확인
        self.mock_cursor.execute.assert_called_once_with(
            "INSERT INTO test_table (name) VALUES (%s)",
            ('test_value',)
        )
        self.mock_connection.commit.assert_called_once()
    
    @patch('repositories.database.PostgreSQLRepository.get_connection')
    def test_execute_query_error_rollback(self, mock_get_connection):
        """execute_query 오류 시 롤백 테스트"""
        # Mock 설정
        mock_context = Mock()
        mock_get_connection.return_value = mock_context
        mock_context.__enter__ = Mock(return_value=self.mock_connection)
        mock_context.__exit__ = Mock(return_value=None)
        
        # 실행 중 오류 발생
        self.mock_cursor.execute.side_effect = psycopg2.IntegrityError("Constraint violation")
        
        # 테스트 실행 및 예외 확인
        with self.assertRaises(DatabaseError) as context:
            self.repo.execute_query("INSERT INTO test_table (name) VALUES (%s)", ('test',))
        
        # 롤백 확인
        self.mock_connection.rollback.assert_called_once()
        
        # 오류 세부 정보 확인
        error = context.exception
        self.assertIn("쿼리 실행 실패", error.message)
        self.assertEqual(error.operation_type, "DML")
    
    def test_get_connection_context_manager(self):
        """get_connection 컨텍스트 매니저 테스트"""
        # get_connection이 컨텍스트 매니저를 반환하는지 확인
        with self.repo.get_connection() as conn:
            self.assertIsNotNone(conn)
        
        # 연결 풀에서 연결 가져오기/반환 확인
        self.mock_pool.getconn.assert_called()
        self.mock_pool.putconn.assert_called()
    
    def test_test_connection_success(self):
        """test_connection 성공 테스트"""
        with patch.object(self.repo, 'get_connection') as mock_get_connection:
            # Mock 컨텍스트 설정
            mock_context = Mock()
            mock_get_connection.return_value = mock_context
            mock_context.__enter__ = Mock(return_value=self.mock_connection)
            mock_context.__exit__ = Mock(return_value=None)
            
            # 테스트 실행
            result = self.repo.test_connection()
            
            # 결과 검증
            self.assertTrue(result)
            
            # SELECT 1 쿼리 실행 확인
            self.mock_cursor.execute.assert_called_with("SELECT 1")
    
    def test_test_connection_failure(self):
        """test_connection 실패 테스트"""
        with patch.object(self.repo, 'get_connection') as mock_get_connection:
            # 연결 실패 시뮬레이션
            mock_get_connection.side_effect = psycopg2.OperationalError("Connection failed")
            
            # 테스트 실행
            result = self.repo.test_connection()
            
            # 결과 검증
            self.assertFalse(result)
    
    def test_close_connection_pool(self):
        """연결 풀 종료 테스트"""
        # close 메서드 실행
        self.repo.close()
        
        # 연결 풀 closeall 호출 확인
        self.mock_pool.closeall.assert_called_once()
    
    def test_sql_injection_prevention(self):
        """SQL 인젝션 방지 테스트"""
        with patch.object(self.repo, 'get_connection') as mock_get_connection:
            mock_context = Mock()
            mock_get_connection.return_value = mock_context
            mock_context.__enter__ = Mock(return_value=self.mock_connection)
            mock_context.__exit__ = Mock(return_value=None)
            
            # 악의적인 입력으로 테스트
            malicious_input = "'; DROP TABLE users; --"
            
            # 테스트 실행
            self.repo.fetch_data(
                table='summary',
                columns=['peg_name'],
                where_conditions={'ne': malicious_input}
            )
            
            # 매개변수화된 쿼리 사용 확인
            self.mock_cursor.execute.assert_called_once()
            call_args = self.mock_cursor.execute.call_args
            query = call_args[0][0]
            params = call_args[0][1] if len(call_args[0]) > 1 else None
            
            # 쿼리에 직접 문자열이 포함되지 않았는지 확인
            self.assertNotIn("DROP TABLE", query)
            
            # 매개변수로 전달되었는지 확인
            if params:
                self.assertIn(malicious_input, params)
    
    def test_dynamic_query_construction(self):
        """동적 쿼리 생성 테스트"""
        with patch.object(self.repo, 'get_connection') as mock_get_connection:
            mock_context = Mock()
            mock_get_connection.return_value = mock_context
            mock_context.__enter__ = Mock(return_value=self.mock_connection)
            mock_context.__exit__ = Mock(return_value=None)
            
            # 복잡한 조건으로 테스트
            self.repo.fetch_data(
                table='performance_data',
                columns=['datetime', 'peg_name', 'value'],
                where_conditions={
                    'ne': 'nvgnb#10000',
                    'cellid': ['2010', '2011'],
                    'host': '192.168.1.1'
                },
                limit=500
            )
            
            # 생성된 쿼리 검증
            self.mock_cursor.execute.assert_called_once()
            executed_query = self.mock_cursor.execute.call_args[0][0]
            
            # 기본 쿼리 구조 확인
            self.assertIn('SELECT', executed_query)
            self.assertIn('FROM performance_data', executed_query)
            self.assertIn('WHERE', executed_query)
            self.assertIn('LIMIT 500', executed_query)
            
            # 조건들이 포함되었는지 확인
            self.assertIn('ne =', executed_query)
            self.assertIn('cellid IN', executed_query)
            self.assertIn('host =', executed_query)
    
    def test_real_dict_cursor_usage(self):
        """RealDictCursor 사용 확인 테스트"""
        with patch.object(self.repo, 'get_connection') as mock_get_connection:
            mock_context = Mock()
            mock_get_connection.return_value = mock_context
            mock_context.__enter__ = Mock(return_value=self.mock_connection)
            mock_context.__exit__ = Mock(return_value=None)
            
            # 테스트 실행
            self.repo.fetch_data('summary', ['peg_name'])
            
            # RealDictCursor 사용 확인
            self.mock_connection.cursor.assert_called_with(cursor_factory=RealDictCursor)
    
    def test_error_details_in_database_error(self):
        """DatabaseError 상세 정보 테스트"""
        with patch.object(self.repo, 'get_connection') as mock_get_connection:
            # 특정 데이터베이스 오류 시뮬레이션
            db_error = psycopg2.ProgrammingError("syntax error at or near 'INVALID'")
            mock_get_connection.side_effect = db_error
            
            # 테스트 실행 및 예외 확인
            with self.assertRaises(DatabaseError) as context:
                self.repo.fetch_data('invalid_table', ['invalid_column'])
            
            # DatabaseError 세부 정보 확인
            error = context.exception
            self.assertIsInstance(error, DatabaseError)
            self.assertIn("데이터 조회 실패", error.message)
            self.assertEqual(error.operation_type, "SELECT")
            self.assertIn("invalid_table", error.query)
            
            # 연결 정보 확인
            connection_info = error.connection_info
            self.assertEqual(connection_info['host'], 'test_host')
            self.assertEqual(connection_info['database'], 'test_db')
    
    def test_context_manager_protocol(self):
        """컨텍스트 매니저 프로토콜 테스트"""
        # with 문으로 사용 가능한지 확인
        with self.repo as repo:
            self.assertIsInstance(repo, PostgreSQLRepository)
        
        # 자동으로 close가 호출되는지 확인
        self.mock_pool.closeall.assert_called()


class TestDatabaseRepositoryIntegration(unittest.TestCase):
    """Database Repository 통합 테스트"""
    
    def setUp(self):
        """통합 테스트 설정"""
        self.mock_config = {
            'db_host': 'integration_test_host',
            'db_port': 5432,
            'db_name': 'integration_test_db',
            'db_user': 'integration_user',
            'db_password': 'integration_pass'
        }
    
    @patch('repositories.database.psycopg2')
    @patch('repositories.database.SimpleConnectionPool')
    def test_full_workflow_with_time_range(self, mock_pool_class, mock_psycopg2):
        """시간 범위를 포함한 전체 워크플로우 테스트"""
        # Mock 설정
        mock_pool = Mock()
        mock_pool_class.return_value = mock_pool
        
        mock_connection = Mock()
        mock_cursor = Mock()
        mock_connection.cursor.return_value = mock_cursor
        mock_pool.getconn.return_value = mock_connection
        
        # Repository 생성
        repo = PostgreSQLRepository(config_override=self.mock_config)
        
        # Mock 데이터 설정
        mock_data = [
            {
                'datetime': datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
                'peg_name': 'preamble_count',
                'value': 1000.0,
                'ne': 'nvgnb#10000',
                'cellid': '2010'
            }
        ]
        mock_cursor.fetchall.return_value = mock_data
        
        # 시간 범위 정의
        time_range = TimeRange(
            start=datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc),
            end=datetime(2025, 1, 1, 18, 0, tzinfo=timezone.utc)
        )
        
        # fetch_peg_data 실행
        result_df = repo.fetch_peg_data(
            time_range=time_range,
            table='summary',
            filters={'ne': 'nvgnb#10000', 'cellid': ['2010', '2011']}
        )
        
        # 결과 검증
        self.assertIsInstance(result_df, pd.DataFrame)
        self.assertEqual(len(result_df), 1)
        
        # 시간 범위 조건이 쿼리에 포함되었는지 확인
        executed_query = mock_cursor.execute.call_args[0][0]
        self.assertIn('datetime >=', executed_query)
        self.assertIn('datetime <', executed_query)
        
        # 필터 조건 확인
        self.assertIn('ne =', executed_query)
        self.assertIn('cellid IN', executed_query)


if __name__ == '__main__':
    # 테스트 실행
    unittest.main(verbosity=2)
