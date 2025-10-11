"""
설정값 확인 스크립트

현재 로드된 설정값을 확인하여 환경변수가 제대로 적용되었는지 검증합니다.
"""

import os
from config.settings import get_settings

def main():
    print("=" * 60)
    print("현재 설정값 확인")
    print("=" * 60)
    
    # 환경변수 직접 확인
    print("\n[환경변수 직접 확인]")
    print(f"PEG_FILTER_ENABLED (env): {os.getenv('PEG_FILTER_ENABLED', 'NOT SET')}")
    print(f"PEG_FILTER_DEFAULT_FILE (env): {os.getenv('PEG_FILTER_DEFAULT_FILE', 'NOT SET')}")
    print(f"PEG_FILTER_DIR_PATH (env): {os.getenv('PEG_FILTER_DIR_PATH', 'NOT SET')}")
    
    # Settings 객체 확인
    print("\n[Settings 객체 확인]")
    try:
        settings = get_settings()
        print(f"peg_filter_enabled: {settings.peg_filter_enabled}")
        print(f"peg_filter_default_file: {settings.peg_filter_default_file}")
        print(f"peg_filter_dir_path: {settings.peg_filter_dir_path}")
        
        # 전체 경로 확인
        full_path = os.path.join(settings.peg_filter_dir_path, settings.peg_filter_default_file)
        print(f"\n[CSV 파일 전체 경로]")
        print(f"경로: {full_path}")
        print(f"파일 존재 여부: {os.path.exists(full_path)}")
        
        # 파일이 없으면 가능한 경로들 확인
        if not os.path.exists(full_path):
            print("\n[가능한 경로들 확인]")
            possible_paths = [
                os.path.join("config", "peg_filters", settings.peg_filter_default_file),
                os.path.join("config/peg_filters", settings.peg_filter_default_file),
                os.path.join(".", "config", "peg_filters", settings.peg_filter_default_file),
            ]
            for path in possible_paths:
                exists = os.path.exists(path)
                print(f"  {path}: {'존재' if exists else '없음'}")
        
        print("\n[필터링 기능 활성화 여부]")
        if settings.peg_filter_enabled:
            print("✅ CSV 필터링 기능이 활성화되어 있습니다!")
        else:
            print("❌ CSV 필터링 기능이 비활성화되어 있습니다.")
            print("\n해결 방법:")
            print("1. .env 파일에 다음 추가:")
            print("   PEG_FILTER_ENABLED=true")
            print("2. 또는 환경변수 설정:")
            print("   $env:PEG_FILTER_ENABLED='true'")
            
    except Exception as e:
        print(f"❌ 설정 로드 실패: {e}")
        import traceback
        traceback.print_exc()
    
    print("=" * 60)

if __name__ == "__main__":
    main()

