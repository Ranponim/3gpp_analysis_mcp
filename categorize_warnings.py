
import os

def categorize_warnings(file_path):
    print(f"Analyzing {file_path}...")
    try:
        # Try reading with utf-16 or utf-8
        try:
            with open(file_path, 'r', encoding='utf-16') as f:
                content = f.readlines()
        except UnicodeError:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.readlines()
                
        print(f"Total lines: {len(content)}")
        
        # Categorize warnings
        categories = {
            "파생 PEG 계산 실패": [],
            "큰 폭의 감소 (-20% 이상)": [],
            "급증 패턴 (0->N)": [],
            "급감 패턴 (N->0)": [],
            "소멸 패턴 (N->NaN)": [],
            "신규 발생 (NaN->N)": [],
            "기타 WARNING": []
        }
        
        for i, line in enumerate(content):
            if "WARNING" not in line:
                continue
                
            if "파생 PEG" in line and "계산 실패" in line:
                categories["파생 PEG 계산 실패"].append(f"Line {i+1}: {line.strip()}")
            elif "큰 폭의 감소" in line:
                categories["큰 폭의 감소 (-20% 이상)"].append(f"Line {i+1}: {line.strip()}")
            elif "급증 패턴" in line:
                categories["급증 패턴 (0->N)"].append(f"Line {i+1}: {line.strip()}")
            elif "급감 패턴" in line:
                categories["급감 패턴 (N->0)"].append(f"Line {i+1}: {line.strip()}")
            elif "소멸 패턴" in line:
                categories["소멸 패턴 (N->NaN)"].append(f"Line {i+1}: {line.strip()}")
            elif "신규 발생" in line:
                categories["신규 발생 (NaN->N)"].append(f"Line {i+1}: {line.strip()}")
            else:
                categories["기타 WARNING"].append(f"Line {i+1}: {line.strip()}")
        
        # Print summary
        print("\n=== WARNING 카테고리별 요약 ===")
        for category, warnings in categories.items():
            print(f"\n{category}: {len(warnings)}개")
            for w in warnings[:5]:  # Show first 5
                print(f"  {w}")
            if len(warnings) > 5:
                print(f"  ... (총 {len(warnings)}개)")
                
    except Exception as e:
        print(f"Failed to read file: {e}")

if __name__ == "__main__":
    # Use the copy in artifacts
    log_path = r"C:\Users\aruca\.gemini\antigravity\brain\73155e49-13f5-47c2-b42d-56ee85c50336\longlog_copy.md"
    
    with open("warning_analysis_report.txt", "w", encoding="utf-8") as f:
        import sys
        sys.stdout = f
        try:
            categorize_warnings(log_path)
        except Exception as e:
            print(f"❌ Error: {e}")
        finally:
            sys.stdout = sys.__stdout__
