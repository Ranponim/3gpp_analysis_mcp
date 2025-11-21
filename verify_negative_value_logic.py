
import sys
import os
import pandas as pd
import logging
from datetime import datetime

# Add project root to path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from analysis_llm.services.peg_processing_service import PEGProcessingService
from analysis_llm.repositories.database import DatabaseRepository

# Setup logging to capture output
logging.basicConfig(level=logging.DEBUG)
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)

# Capture logs to a list
class ListHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.logs = []
    def emit(self, record):
        msg = self.format(record)
        self.logs.append(msg)
        # print(f"[CAPTURED] {msg}") # Debug print

list_handler = ListHandler()
root_logger.addHandler(list_handler)

class MockDatabaseRepository(DatabaseRepository):
    def connect(self): pass
    def disconnect(self): pass
    def fetch_data(self, **kwargs): return []
    def execute_query(self, **kwargs): return 0
    def test_connection(self): return True
    def fetch_peg_data(self, **kwargs): return []

def verify_negative_logic():
    print("=== Starting Verification of Negative Value Logic ===")
    
    # 1. Setup Data
    # Case 1: Valid Negative (dBm)
    # Case 2: Invalid Negative (Byte)
    # Case 3: Suspicious Negative (MCS -1.0)
    
    n1_data = [
        {"peg_name": "InterferencePowerAvg(dBm)", "value": -110.5, "timestamp": datetime(2023, 1, 1)},
        {"peg_name": "AirMacDLByte(Kbytes)", "value": -500.0, "timestamp": datetime(2023, 1, 1)},
        {"peg_name": "DLTransmittedMcsAvg(MCS)", "value": -1.0, "timestamp": datetime(2023, 1, 1)},
        {"peg_name": "NormalPEG", "value": 100.0, "timestamp": datetime(2023, 1, 1)},
    ]
    
    n_data = [
        {"peg_name": "InterferencePowerAvg(dBm)", "value": -112.0, "timestamp": datetime(2023, 1, 2)},
        {"peg_name": "AirMacDLByte(Kbytes)", "value": 100.0, "timestamp": datetime(2023, 1, 2)},
        {"peg_name": "DLTransmittedMcsAvg(MCS)", "value": 15.0, "timestamp": datetime(2023, 1, 2)},
        {"peg_name": "NormalPEG", "value": 120.0, "timestamp": datetime(2023, 1, 2)},
    ]
    
    n1_df = pd.DataFrame(n1_data)
    n_df = pd.DataFrame(n_data)
    
    # 2. Process Data
    repo = MockDatabaseRepository()
    service = PEGProcessingService(repo)
    
    print("\n--- Processing Data ---")
    service._process_with_calculator(
        n1_df, n_df, peg_config={}, filters={}, derived_pegs=[]
    )
    
    # 3. Verify Logs
    print("\n--- Verifying Logs ---")
    
    errors = [log for log in list_handler.logs if "ERROR" in log]
    
    print(f"Total Errors Found: {len(errors)}")
    for err in errors:
        print(err)
        
    # Check specific expectations
    has_dbm_error = any("InterferencePowerAvg(dBm)" in err for err in errors)
    has_byte_error = any("AirMacDLByte(Kbytes)" in err for err in errors)
    has_mcs_error = any("DLTransmittedMcsAvg(MCS)" in err for err in errors)
    
    print(f"\nHas dBm Error (Should be False after fix): {has_dbm_error}")
    print(f"Has Byte Error (Should be True): {has_byte_error}")
    print(f"Has MCS Error (Should be True): {has_mcs_error}")

if __name__ == "__main__":
    # Redirect stdout to file
    with open("verify_negative_result.txt", "w", encoding="utf-8") as f:
        sys.stdout = f
        try:
            verify_negative_logic()
        except Exception as e:
            print(f"❌ Error: {e}")
        finally:
            sys.stdout = sys.__stdout__
