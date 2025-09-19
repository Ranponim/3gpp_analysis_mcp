"""
Database Repository 간단한 단위 테스트

Mock 의존성 없이 기본적인 기능을 테스트합니다.
"""

import os
import sys
import unittest
from unittest.mock import Mock, patch

# 프로젝트 루트를 Python path에 추가
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)

from repositories import DatabaseError, DatabaseRepository, PostgreSQLRepository


class TestDatabaseRepositoryABC(unittest.TestCase):
    """DatabaseRepository 추상 기본 클래스 테스트"""
    
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


class TestPostgreSQLRepositoryBasic(unittest.TestCase):
    """PostgreSQLRepository 기본 기능 테스트"""
    
    def test_initialization_with_config_override(self):
        """설정 오버라이드로 초기화 테스트"""
        mock_config = {
            'db_host': 'test_host',
            'db_port': 5432,
            'db_name': 'test_db', 
            'db_user': 'test_user',
            'db_password': 'test_pass'
        }
        
        # Mock을 사용하여 연결 풀 생성 우회
        with patch('psycopg2.pool.SimpleConnectionPool') as mock_pool_class:
            mock_pool = Mock()
            mock_pool_class.return_value = mock_pool
            
            # PostgreSQLRepository 생성
            repo = PostgreSQLRepository(config_override=mock_config)
            
            # 설정이 올바르게 적용되었는지 확인
            self.assertEqual(repo.host, 'test_host')
            self.assertEqual(repo.port, 5432)
            self.assertEqual(repo.database, 'test_db')
            self.assertEqual(repo.user, 'test_user')
            self.assertEqual(repo.password, 'test_pass')
            
            # 연결 풀이 생성되었는지 확인
            mock_pool_class.assert_called_once()
    
    def test_database_error_creation(self):
        """DatabaseError 생성 테스트"""
        error = DatabaseError(
            message="테스트 오류",
            query="SELECT * FROM test",
            operation_type="SELECT",
            connection_info={'host': 'localhost'}
        )
        
        # 기본 속성 확인
        self.assertEqual(error.message, "테스트 오류")
        self.assertEqual(error.query, "SELECT * FROM test")
        self.assertEqual(error.operation_type, "SELECT")
        self.assertEqual(error.connection_info['host'], 'localhost')
        
        # 유틸리티 메서드 확인
        self.assertTrue(error.is_read_operation())
        self.assertFalse(error.is_write_operation())
        self.assertFalse(error.is_delete_operation())
        
        # 안전한 쿼리 반환 확인
        safe_query = error.get_safe_query()
        self.assertIsInstance(safe_query, str)
        self.assertIn("SELECT", safe_query)
    
    def test_database_error_serialization(self):
        """DatabaseError 직렬화 테스트"""
        error = DatabaseError(
            message="직렬화 테스트",
            query="INSERT INTO test VALUES (%s)",
            operation_type="INSERT"
        )
        
        # 딕셔너리 변환
        error_dict = error.to_dict()
        
        # 필수 키 확인
        expected_keys = {
            'error_type', 'message', 'query', 'operation_type',
            'connection_info', 'repository_name', 'resource'
        }
        self.assertTrue(expected_keys.issubset(error_dict.keys()))
        
        # 값 확인
        self.assertEqual(error_dict['message'], "직렬화 테스트")
        self.assertEqual(error_dict['operation_type'], "INSERT")
    
    @patch('psycopg2.pool.SimpleConnectionPool')
    def test_repository_context_manager(self, mock_pool_class):
        """Repository 컨텍스트 매니저 테스트"""
        mock_pool = Mock()
        mock_pool_class.return_value = mock_pool
        
        mock_config = {
            'db_host': 'test_host',
            'db_name': 'test_db',
            'db_user': 'test_user', 
            'db_password': 'test_pass'
        }
        
        # 컨텍스트 매니저로 사용
        with PostgreSQLRepository(config_override=mock_config) as repo:
            self.assertIsInstance(repo, PostgreSQLRepository)
        
        # close가 호출되었는지 확인
        mock_pool.closeall.assert_called_once()
    
    def test_repository_info_methods(self):
        """Repository 정보 메서드 테스트"""
        with patch('psycopg2.pool.SimpleConnectionPool') as mock_pool_class:
            mock_pool = Mock()
            mock_pool_class.return_value = mock_pool
            
            mock_config = {
                'db_host': 'info_test_host',
                'db_name': 'info_test_db',
                'db_user': 'info_user',
                'db_password': 'info_pass'
            }
            
            repo = PostgreSQLRepository(config_override=mock_config)
            
            # Repository 정보 확인
            self.assertEqual(repo.host, 'info_test_host')
            self.assertEqual(repo.database, 'info_test_db')
            self.assertEqual(repo.user, 'info_user')
            
            # 문자열 표현 확인
            repo_str = str(repo)
            self.assertIn('PostgreSQLRepository', repo_str)
            self.assertIn('info_test_host', repo_str)


if __name__ == '__main__':
    # 테스트 실행
    unittest.main(verbosity=2)
