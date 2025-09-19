"""
Custom Exception Classes Unit Tests

이 모듈은 exceptions 패키지의 모든 커스텀 예외 클래스에 대한 
종합적인 단위 테스트를 포함합니다.
"""

import json
import unittest

from analysis_llm.exceptions import (
    AnalysisError,
    DatabaseError,
    LLMError,
    RepositoryError,
    ServiceError,
    ValidationError,
)


class TestAnalysisError(unittest.TestCase):
    """AnalysisError 기본 예외 클래스 테스트"""
    
    def test_basic_creation(self):
        """기본 생성 테스트"""
        error = AnalysisError("테스트 메시지")
        
        self.assertEqual(str(error), "테스트 메시지")
        self.assertEqual(error.message, "테스트 메시지")
        self.assertIsNone(error.details)
        self.assertFalse(error.has_details())
    
    def test_creation_with_details_dict(self):
        """딕셔너리 상세 정보와 함께 생성 테스트"""
        details = {"step": "validation", "count": 5}
        error = AnalysisError("오류 발생", details)
        
        self.assertEqual(error.message, "오류 발생")
        self.assertEqual(error.details, details)
        self.assertTrue(error.has_details())
        self.assertEqual(error.get_details_str(), "step=validation, count=5")
        self.assertEqual(error.get_full_message(), "오류 발생 (상세: step=validation, count=5)")
    
    def test_creation_with_details_string(self):
        """문자열 상세 정보와 함께 생성 테스트"""
        error = AnalysisError("오류 발생", "추가 정보")
        
        self.assertEqual(error.details, "추가 정보")
        self.assertEqual(error.get_details_str(), "추가 정보")
        self.assertEqual(error.get_full_message(), "오류 발생 (상세: 추가 정보)")
    
    def test_to_dict(self):
        """딕셔너리 변환 테스트"""
        error = AnalysisError("테스트", {"key": "value"})
        result = error.to_dict()
        
        expected = {
            'error_type': 'AnalysisError',
            'message': '테스트',
            'details': {'key': 'value'}
        }
        self.assertEqual(result, expected)
    
    def test_repr(self):
        """repr 메서드 테스트"""
        error = AnalysisError("테스트", {"key": "value"})
        repr_str = repr(error)
        
        self.assertIn("AnalysisError", repr_str)
        self.assertIn("테스트", repr_str)
        self.assertIn("details", repr_str)


class TestDatabaseError(unittest.TestCase):
    """DatabaseError 예외 클래스 테스트"""
    
    def test_basic_creation(self):
        """기본 생성 테스트"""
        error = DatabaseError("연결 실패")
        
        self.assertIsInstance(error, AnalysisError)
        self.assertEqual(str(error), "연결 실패")
        self.assertIsNone(error.query)
        self.assertEqual(error.connection_info, {})
    
    def test_creation_with_query(self):
        """쿼리 정보와 함께 생성 테스트"""
        query = "SELECT * FROM summary WHERE id = %s"
        error = DatabaseError("쿼리 실행 실패", query=query)
        
        self.assertEqual(error.query, query)
        self.assertEqual(error.get_safe_query(), "SELECT * FROM summary WHERE id = ***")
    
    def test_creation_with_connection_info(self):
        """연결 정보와 함께 생성 테스트"""
        conn_info = {"host": "localhost", "port": 5432, "dbname": "test"}
        error = DatabaseError("연결 실패", connection_info=conn_info)
        
        self.assertEqual(error.connection_info, conn_info)
    
    def test_safe_query_masking(self):
        """안전한 쿼리 마스킹 테스트"""
        queries = [
            ("SELECT * FROM table WHERE name = 'test'", "SELECT * FROM table WHERE name = '***'"),
            ("INSERT INTO table VALUES (%s, %s)", "INSERT INTO table VALUES (***, ***)"),
            (None, None)
        ]
        
        for original, expected in queries:
            error = DatabaseError("테스트", query=original)
            self.assertEqual(error.get_safe_query(), expected)
    
    def test_to_dict(self):
        """딕셔너리 변환 테스트"""
        error = DatabaseError(
            "테스트", 
            {"table": "summary"}, 
            "SELECT * FROM summary", 
            {"host": "localhost"}
        )
        result = error.to_dict()
        
        self.assertEqual(result['error_type'], 'DatabaseError')
        self.assertEqual(result['query'], 'SELECT * FROM summary')
        self.assertEqual(result['connection_info'], {'host': 'localhost'})


class TestLLMError(unittest.TestCase):
    """LLMError 예외 클래스 테스트"""
    
    def test_basic_creation(self):
        """기본 생성 테스트"""
        error = LLMError("API 호출 실패")
        
        self.assertIsInstance(error, AnalysisError)
        self.assertEqual(str(error), "API 호출 실패")
        self.assertIsNone(error.status_code)
        self.assertIsNone(error.endpoint)
        self.assertIsNone(error.model_name)
    
    def test_creation_with_status_code(self):
        """상태 코드와 함께 생성 테스트"""
        error = LLMError("서버 오류", status_code=500)
        
        self.assertEqual(error.status_code, 500)
        self.assertTrue(error.is_server_error())
        self.assertFalse(error.is_client_error())
        self.assertTrue(error.is_retryable())
    
    def test_client_error_detection(self):
        """클라이언트 오류 감지 테스트"""
        error = LLMError("잘못된 요청", status_code=400)
        
        self.assertTrue(error.is_client_error())
        self.assertFalse(error.is_server_error())
        self.assertFalse(error.is_retryable())
    
    def test_retryable_client_errors(self):
        """재시도 가능한 클라이언트 오류 테스트"""
        retryable_codes = [408, 429]  # Request Timeout, Too Many Requests
        
        for code in retryable_codes:
            error = LLMError("재시도 가능 오류", status_code=code)
            self.assertTrue(error.is_retryable(), f"Status code {code} should be retryable")
    
    def test_creation_with_full_context(self):
        """모든 컨텍스트 정보와 함께 생성 테스트"""
        error = LLMError(
            "API 호출 실패",
            {"timeout": 30},
            status_code=503,
            endpoint="http://localhost:10000/api/chat",
            model_name="Gemma-3-27B",
            prompt_preview="분석해주세요..."
        )
        
        self.assertEqual(error.endpoint, "http://localhost:10000/api/chat")
        self.assertEqual(error.model_name, "Gemma-3-27B")
        self.assertEqual(error.prompt_preview, "분석해주세요...")
        self.assertTrue(error.is_server_error())


class TestValidationError(unittest.TestCase):
    """ValidationError 예외 클래스 테스트"""
    
    def test_basic_creation(self):
        """기본 생성 테스트"""
        error = ValidationError("검증 실패")
        
        self.assertIsInstance(error, AnalysisError)
        self.assertEqual(str(error), "검증 실패")
        self.assertIsNone(error.field_name)
        self.assertIsNone(error.validation_rule)
    
    def test_required_field_error(self):
        """필수 필드 오류 테스트"""
        error = ValidationError(
            "필수 필드 누락",
            field_name="n_minus_1",
            validation_rule="required"
        )
        
        self.assertEqual(error.field_name, "n_minus_1")
        self.assertEqual(error.validation_rule, "required")
        self.assertTrue(error.is_required_field_error())
        self.assertFalse(error.is_format_error())
    
    def test_format_error(self):
        """형식 오류 테스트"""
        format_rules = ["format", "pattern", "type"]
        
        for rule in format_rules:
            error = ValidationError("형식 오류", validation_rule=rule)
            self.assertTrue(error.is_format_error(), f"Rule '{rule}' should be a format error")
            self.assertFalse(error.is_required_field_error())
    
    def test_creation_with_field_value(self):
        """필드 값과 함께 생성 테스트"""
        error = ValidationError(
            "잘못된 값",
            field_name="port",
            field_value="invalid",
            validation_rule="type"
        )
        
        self.assertEqual(error.field_value, "invalid")
        result = error.to_dict()
        self.assertEqual(result['field_value'], "invalid")


class TestServiceError(unittest.TestCase):
    """ServiceError 예외 클래스 테스트"""
    
    def test_basic_creation(self):
        """기본 생성 테스트"""
        error = ServiceError("서비스 실행 실패")
        
        self.assertIsInstance(error, AnalysisError)
        self.assertEqual(str(error), "서비스 실행 실패")
        self.assertIsNone(error.service_name)
        self.assertIsNone(error.operation)
        self.assertEqual(error.retry_count, 0)
        self.assertFalse(error.has_retries())
    
    def test_creation_with_service_info(self):
        """서비스 정보와 함께 생성 테스트"""
        error = ServiceError(
            "처리 실패",
            service_name="PEGProcessingService",
            operation="aggregate_data",
            retry_count=1
        )
        
        self.assertEqual(error.service_name, "PEGProcessingService")
        self.assertEqual(error.operation, "aggregate_data")
        self.assertEqual(error.retry_count, 1)
        self.assertTrue(error.has_retries())
    
    def test_retry_increment(self):
        """재시도 횟수 증가 테스트"""
        error = ServiceError("실패")
        
        self.assertEqual(error.retry_count, 0)
        self.assertFalse(error.has_retries())
        
        error.increment_retry()
        self.assertEqual(error.retry_count, 1)
        self.assertTrue(error.has_retries())
        
        error.increment_retry()
        self.assertEqual(error.retry_count, 2)


class TestRepositoryError(unittest.TestCase):
    """RepositoryError 예외 클래스 테스트"""
    
    def test_basic_creation(self):
        """기본 생성 테스트"""
        error = RepositoryError("저장소 접근 실패")
        
        self.assertIsInstance(error, AnalysisError)
        self.assertEqual(str(error), "저장소 접근 실패")
        self.assertIsNone(error.repository_name)
        self.assertIsNone(error.operation_type)
        self.assertIsNone(error.resource)
    
    def test_read_operation_detection(self):
        """읽기 작업 감지 테스트"""
        read_operations = ["READ", "GET", "SELECT", "read", "get", "select"]
        
        for op in read_operations:
            error = RepositoryError("읽기 실패", operation_type=op)
            self.assertTrue(error.is_read_operation(), f"Operation '{op}' should be read operation")
            self.assertFalse(error.is_write_operation())
            self.assertFalse(error.is_delete_operation())
    
    def test_write_operation_detection(self):
        """쓰기 작업 감지 테스트"""
        write_operations = ["WRITE", "POST", "PUT", "INSERT", "UPDATE", "write", "post"]
        
        for op in write_operations:
            error = RepositoryError("쓰기 실패", operation_type=op)
            self.assertTrue(error.is_write_operation(), f"Operation '{op}' should be write operation")
            self.assertFalse(error.is_read_operation())
            self.assertFalse(error.is_delete_operation())
    
    def test_delete_operation_detection(self):
        """삭제 작업 감지 테스트"""
        delete_operations = ["DELETE", "REMOVE", "delete", "remove"]
        
        for op in delete_operations:
            error = RepositoryError("삭제 실패", operation_type=op)
            self.assertTrue(error.is_delete_operation(), f"Operation '{op}' should be delete operation")
            self.assertFalse(error.is_read_operation())
            self.assertFalse(error.is_write_operation())
    
    def test_creation_with_full_context(self):
        """모든 컨텍스트 정보와 함께 생성 테스트"""
        error = RepositoryError(
            "API 호출 실패",
            {"timeout": 30},
            repository_name="BackendClient",
            operation_type="POST",
            resource="/api/analysis/results/"
        )
        
        self.assertEqual(error.repository_name, "BackendClient")
        self.assertEqual(error.operation_type, "POST")
        self.assertEqual(error.resource, "/api/analysis/results/")
        self.assertTrue(error.is_write_operation())


class TestExceptionHierarchy(unittest.TestCase):
    """예외 클래스 계층 구조 테스트"""
    
    def test_inheritance_hierarchy(self):
        """상속 계층 구조 테스트"""
        exceptions = [
            DatabaseError("test"),
            LLMError("test"),
            ValidationError("test"),
            ServiceError("test"),
            RepositoryError("test")
        ]
        
        for exc in exceptions:
            # 모든 커스텀 예외는 AnalysisError를 상속해야 함
            self.assertIsInstance(exc, AnalysisError)
            # AnalysisError는 Exception을 상속해야 함
            self.assertIsInstance(exc, Exception)
            # 직접적인 부모 클래스는 AnalysisError여야 함
            self.assertEqual(exc.__class__.__bases__[0], AnalysisError)
    
    def test_exception_raising(self):
        """예외 발생 테스트"""
        exceptions = [
            (DatabaseError, "DB 오류"),
            (LLMError, "LLM 오류"),
            (ValidationError, "검증 오류"),
            (ServiceError, "서비스 오류"),
            (RepositoryError, "저장소 오류")
        ]
        
        for exc_class, message in exceptions:
            with self.assertRaises(exc_class) as context:
                raise exc_class(message)
            
            self.assertEqual(str(context.exception), message)
            self.assertIsInstance(context.exception, AnalysisError)
    
    def test_json_serialization(self):
        """JSON 직렬화 테스트"""
        error = DatabaseError(
            "테스트 오류",
            {"key": "value"},
            query="SELECT * FROM test",
            connection_info={"host": "localhost"}
        )
        
        # to_dict() 결과가 JSON 직렬화 가능한지 확인
        error_dict = error.to_dict()
        json_str = json.dumps(error_dict, ensure_ascii=False)
        
        # 역직렬화해서 데이터 확인
        restored = json.loads(json_str)
        self.assertEqual(restored['error_type'], 'DatabaseError')
        self.assertEqual(restored['message'], '테스트 오류')
        self.assertEqual(restored['details'], {'key': 'value'})


if __name__ == '__main__':
    # 로깅 레벨 설정 (테스트 중 로그 출력 최소화)
    import logging
    logging.getLogger().setLevel(logging.CRITICAL)
    
    # 테스트 실행
    unittest.main(verbosity=2)
