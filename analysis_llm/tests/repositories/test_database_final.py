"""
Database Repository 최종 단위 테스트

실제 구현에 맞춘 정확한 테스트 케이스들
"""

import os
import sys
import unittest
from unittest.mock import Mock, patch

# 프로젝트 루트를 Python path에 추가
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)

from repositories import DatabaseError, DatabaseRepository, PostgreSQLRepository


class TestDatabaseRepositoryInterface(unittest.TestCase):
    """DatabaseRepository 인터페이스 테스트"""
    
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


class TestDatabaseError(unittest.TestCase):
    """DatabaseError 예외 클래스 테스트"""
    
    def test_database_error_basic_creation(self):
        """DatabaseError 기본 생성 테스트"""
        error = DatabaseError(
            message="테스트 데이터베이스 오류",
            query="SELECT * FROM test_table",
            connection_info={'host': 'localhost', 'database': 'test_db'}
        )
        
        # 기본 속성 확인
        self.assertEqual(error.message, "테스트 데이터베이스 오류")
        self.assertEqual(error.query, "SELECT * FROM test_table")
        self.assertEqual(error.connection_info['host'], 'localhost')
        
        # 상속 관계 확인
        from exceptions import AnalysisError
        self.assertIsInstance(error, AnalysisError)
        self.assertIsInstance(error, Exception)
    
    def test_database_error_utility_methods(self):
        """DatabaseError 유틸리티 메서드 테스트"""
        # SELECT 오류
        select_error = DatabaseError(
            message="SELECT 오류",
            query="SELECT * FROM users"
        )
        
        self.assertTrue(select_error.is_read_operation())
        self.assertFalse(select_error.is_write_operation())
        self.assertFalse(select_error.is_delete_operation())
        
        # INSERT 오류
        insert_error = DatabaseError(
            message="INSERT 오류", 
            query="INSERT INTO users VALUES (1, 'test')"
        )
        
        self.assertFalse(insert_error.is_read_operation())
        self.assertTrue(insert_error.is_write_operation())
        self.assertFalse(insert_error.is_delete_operation())
        
        # DELETE 오류
        delete_error = DatabaseError(
            message="DELETE 오류",
            query="DELETE FROM users WHERE id = 1"
        )
        
        self.assertFalse(delete_error.is_read_operation())
        self.assertFalse(delete_error.is_write_operation())
        self.assertTrue(delete_error.is_delete_operation())
    
    def test_database_error_safe_query(self):
        """DatabaseError 안전한 쿼리 반환 테스트"""
        # 민감한 정보가 포함된 쿼리
        sensitive_query = "SELECT * FROM users WHERE password = 'secret123'"
        
        error = DatabaseError(
            message="민감한 쿼리 오류",
            query=sensitive_query
        )
        
        safe_query = error.get_safe_query()
        
        # 민감한 정보가 마스킹되었는지 확인
        self.assertNotIn('secret123', safe_query)
        self.assertIn('***', safe_query)
    
    def test_database_error_serialization(self):
        """DatabaseError 직렬화 테스트"""
        error = DatabaseError(
            message="직렬화 테스트",
            query="UPDATE test SET value = %s WHERE id = %s",
            connection_info={'host': 'test_host', 'port': 5432}
        )
        
        # 딕셔너리 변환
        error_dict = error.to_dict()
        
        # 필수 키 확인
        expected_keys = {
            'error_type', 'message', 'query', 'connection_info'
        }
        self.assertTrue(expected_keys.issubset(error_dict.keys()))
        
        # 값 확인
        self.assertEqual(error_dict['message'], "직렬화 테스트")
        self.assertEqual(error_dict['connection_info']['host'], 'test_host')


class TestPostgreSQLRepositoryMocked(unittest.TestCase):
    """PostgreSQLRepository Mock 기반 테스트"""
    
    @patch('psycopg2.pool.SimpleConnectionPool')
    def test_initialization_success(self, mock_pool_class):
        """PostgreSQLRepository 초기화 성공 테스트"""
        mock_pool = Mock()
        mock_pool_class.return_value = mock_pool
        
        mock_config = {
            'db_host': 'test_host',
            'db_port': 5432,
            'db_name': 'test_db',
            'db_user': 'test_user',
            'db_password': 'test_pass'
        }
        
        # Repository 생성
        repo = PostgreSQLRepository(config_override=mock_config)
        
        # 초기화 확인
        self.assertIsInstance(repo, PostgreSQLRepository)
        self.assertIsInstance(repo, DatabaseRepository)
        
        # 연결 풀 생성 확인
        mock_pool_class.assert_called_once()
        call_args = mock_pool_class.call_args[1]  # kwargs
        
        self.assertEqual(call_args['host'], 'test_host')
        self.assertEqual(call_args['port'], 5432)
        self.assertEqual(call_args['database'], 'test_db')
        self.assertEqual(call_args['user'], 'test_user')
        self.assertEqual(call_args['password'], 'test_pass')
    
    @patch('psycopg2.pool.SimpleConnectionPool')
    def test_context_manager_protocol(self, mock_pool_class):
        """컨텍스트 매니저 프로토콜 테스트"""
        mock_pool = Mock()
        mock_pool_class.return_value = mock_pool
        
        mock_config = {
            'db_host': 'context_test',
            'db_name': 'context_db',
            'db_user': 'context_user',
            'db_password': 'context_pass'
        }
        
        # 컨텍스트 매니저로 사용
        with PostgreSQLRepository(config_override=mock_config) as repo:
            self.assertIsInstance(repo, PostgreSQLRepository)
        
        # close가 호출되었는지 확인
        mock_pool.closeall.assert_called_once()
    
    @patch('psycopg2.pool.SimpleConnectionPool')
    def test_test_connection_method(self, mock_pool_class):
        """test_connection 메서드 테스트"""
        mock_pool = Mock()
        mock_connection = Mock()
        mock_cursor = Mock()
        
        mock_pool_class.return_value = mock_pool
        mock_pool.getconn.return_value = mock_connection
        mock_connection.cursor.return_value = mock_cursor
        
        mock_config = {
            'db_host': 'connection_test',
            'db_name': 'connection_db',
            'db_user': 'connection_user',
            'db_password': 'connection_pass'
        }
        
        repo = PostgreSQLRepository(config_override=mock_config)
        
        # 성공적인 연결 테스트
        result = repo.test_connection()
        
        # 결과 확인 (연결 풀에서 연결을 가져와서 테스트 쿼리 실행)
        self.assertTrue(result)
        mock_pool.getconn.assert_called()
        mock_connection.cursor.assert_called()
        mock_cursor.execute.assert_called_with("SELECT 1")
        mock_pool.putconn.assert_called_with(mock_connection)
    
    @patch('psycopg2.pool.SimpleConnectionPool')
    def test_close_method(self, mock_pool_class):
        """close 메서드 테스트"""
        mock_pool = Mock()
        mock_pool_class.return_value = mock_pool
        
        mock_config = {
            'db_host': 'close_test',
            'db_name': 'close_db',
            'db_user': 'close_user',
            'db_password': 'close_pass'
        }
        
        repo = PostgreSQLRepository(config_override=mock_config)
        
        # close 메서드 호출
        repo.close()
        
        # 연결 풀 종료 확인
        mock_pool.closeall.assert_called_once()


class TestPostgreSQLRepositoryIntegration(unittest.TestCase):
    """PostgreSQLRepository 통합 테스트 (실제 동작 시뮬레이션)"""
    
    @patch('psycopg2.pool.SimpleConnectionPool')
    def test_fetch_data_workflow(self, mock_pool_class):
        """fetch_data 워크플로우 시뮬레이션"""
        # Mock 설정
        mock_pool = Mock()
        mock_connection = Mock()
        mock_cursor = Mock()
        
        mock_pool_class.return_value = mock_pool
        mock_pool.getconn.return_value = mock_connection
        mock_connection.cursor.return_value = mock_cursor
        
        # Mock 데이터 반환
        mock_data = [
            {'peg_name': 'preamble_count', 'value': 1000.0},
            {'peg_name': 'response_count', 'value': 950.0}
        ]
        mock_cursor.fetchall.return_value = mock_data
        
        # Repository 생성
        repo = PostgreSQLRepository(config_override={
            'db_host': 'workflow_test',
            'db_name': 'workflow_db',
            'db_user': 'workflow_user',
            'db_password': 'workflow_pass'
        })
        
        # fetch_data 실행
        result = repo.fetch_data(
            table='summary',
            columns=['peg_name', 'value'],
            where_conditions={'ne': 'nvgnb#10000'},
            limit=100
        )
        
        # 결과 검증
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['peg_name'], 'preamble_count')
        
        # 연결 풀 사용 확인
        mock_pool.getconn.assert_called()
        mock_pool.putconn.assert_called()
        
        # 쿼리 실행 확인
        mock_cursor.execute.assert_called()
        executed_query = mock_cursor.execute.call_args[0][0]
        
        # 기본 SQL 구조 확인
        self.assertIn('SELECT', executed_query)
        self.assertIn('FROM summary', executed_query)
        self.assertIn('LIMIT', executed_query)
    
    @patch('psycopg2.pool.SimpleConnectionPool')
    def test_error_handling_workflow(self, mock_pool_class):
        """오류 처리 워크플로우 테스트"""
        # Mock 설정
        mock_pool = Mock()
        mock_pool_class.return_value = mock_pool
        
        # 연결 실패 시뮬레이션
        import psycopg2
        mock_pool.getconn.side_effect = psycopg2.OperationalError("Connection failed")
        
        # Repository 생성
        repo = PostgreSQLRepository(config_override={
            'db_host': 'error_test',
            'db_name': 'error_db',
            'db_user': 'error_user',
            'db_password': 'error_pass'
        })
        
        # 오류 발생 확인
        with self.assertRaises(DatabaseError) as context:
            repo.fetch_data('summary', ['peg_name'])
        
        # DatabaseError 세부 정보 확인
        error = context.exception
        self.assertIn("데이터 조회 실패", error.message)
        self.assertIsNotNone(error.query)


if __name__ == '__main__':
    # 테스트 실행
    unittest.main(verbosity=2)
