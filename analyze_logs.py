
import os

def analyze_log(file_path):
    with open("log_analysis_report.txt", "w", encoding="utf-8") as report_file:
        def log_print(msg):
            print(msg)
            report_file.write(msg + "\n")

        log_print(f"Analyzing {file_path}...")
        try:
            # Try reading with utf-16 (common for PowerShell output) or utf-8
            try:
                with open(file_path, 'r', encoding='utf-16') as f:
                    content = f.readlines()
            except UnicodeError:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.readlines()
                    
            log_print(f"Total lines: {len(content)}")
            
            errors = []
            warnings = []
            
            for i, line in enumerate(content):
                if "ERROR" in line:
                    errors.append(f"Line {i+1}: {line.strip()}")
                if "WARNING" in line:
                    warnings.append(f"Line {i+1}: {line.strip()}")
                    
            log_print(f"\nFound {len(errors)} ERRORs and {len(warnings)} WARNINGs.")
            
            log_print("\n--- Top 20 ERRORs ---")
            for e in errors[:20]:
                log_print(e)
                
            log_print("\n--- Top 20 WARNINGs ---")
            for w in warnings[:20]:
                log_print(w)
                
            # Check for specific date 2025-10-22
            log_print("\n--- Logs for 2025-10-22 (First 20) ---")
            date_logs = [line.strip() for line in content if "2025-10-22" in line]
            for l in date_logs[:20]:
                log_print(l)
                
        except Exception as e:
            log_print(f"Failed to read file: {e}")

if __name__ == "__main__":
    # Use the copy in artifacts
    log_path = r"C:\Users\aruca\.gemini\antigravity\brain\73155e49-13f5-47c2-b42d-56ee85c50336\longlog_copy.md"
    analyze_log(log_path)
