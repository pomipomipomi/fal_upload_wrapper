#!/usr/bin/env python3
"""
local_fal_upload.py のラッパースクリプト（SQLite版）
・アップロード前にSQLiteデータベースで重複チェック
・local_fal_upload.py を実行してアップロード
・アップロード後に自動でSQLiteデータベースに登録
・ファイルハッシュによる重複検出に対応
"""

import os
import sys
import subprocess
from pathlib import Path
from fal_upload_db import FalUploadDB

LOCAL_FAL_UPLOAD_SCRIPT = "local_fal_upload.py"

def check_file_in_database(db: FalUploadDB, file_path: str) -> tuple[bool, dict]:
    """
    データベースでファイルの重複をチェック
    ファイル名とハッシュの両方でチェック
    
    Returns:
        (found, record): 見つかった場合はTrue、レコード辞書。見つからない場合はFalse、None
    """
    file_name = os.path.basename(file_path)
    
    # まずファイル名で検索
    record = db.find_by_filename(file_name, validate_url=True)
    if record:
        return True, record
    
    # ファイルが存在する場合、ハッシュでも検索（重複ファイル検出）
    if os.path.exists(file_path):
        file_hash = db.calculate_file_hash(file_path)
        if file_hash:
            record = db.find_by_hash(file_hash, validate_url=True)
            if record:
                print(f"[INFO] 同じ内容のファイルが見つかりました: {record['filename']}")
                return True, record
    
    return False, None

def run_local_fal_upload(file_path):
    """local_fal_upload.py を実行してURLを取得"""
    try:
        # local_fal_upload.py を実行
        result = subprocess.run([
            sys.executable, LOCAL_FAL_UPLOAD_SCRIPT, file_path
        ], capture_output=True, text=True, encoding='utf-8', errors='replace', check=True)
        
        # 出力からアップロードURLを抽出
        output_lines = result.stdout.strip().split('\n')
        uploaded_url = None
        
        for line in output_lines:
            if line.startswith('[SUCCESS] アップロード完了:') or line.startswith('✅ アップロード完了:'):
                # "[SUCCESS] アップロード完了: URL" からURLを抽出
                uploaded_url = line.split(':', 1)[1].strip()
                break
        
        if not uploaded_url:
            print("[ERROR] local_fal_upload.py の出力からURLを取得できませんでした")
            print("標準出力:")
            print(result.stdout)
            if result.stderr:
                print("標準エラー:")
                print(result.stderr)
            return None
            
        return uploaded_url
        
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] local_fal_upload.py 実行エラー: {e}")
        print("標準出力:")
        print(e.stdout)
        print("標準エラー:")
        print(e.stderr)
        return None
    except Exception as e:
        print(f"[ERROR] 予期しないエラー: {e}")
        return None

def upload_with_database_wrapper(file_path):
    """SQLiteデータベース連携付きアップロードラッパー"""
    # ファイルの存在確認
    if not os.path.exists(file_path):
        print(f"[ERROR] ファイルが見つかりません: {file_path}")
        return None
    
    # local_fal_upload.py の存在確認
    if not os.path.exists(LOCAL_FAL_UPLOAD_SCRIPT):
        print(f"[ERROR] local_fal_upload.py が見つかりません: {LOCAL_FAL_UPLOAD_SCRIPT}")
        return None
    
    # データベース初期化
    db = FalUploadDB()
    
    # ファイル名（パス無し）を取得
    file_name = os.path.basename(file_path)
    
    # データベースで重複チェック
    print(f"[INFO] データベースで重複チェック中: {file_name}")
    found, existing_record = check_file_in_database(db, file_path)
    
    if found:
        existing_url = existing_record['url']
        print(f"[SUCCESS] ファイルは既に登録済みです:")
        print(f"   ファイル名: {existing_record['filename']}")
        print(f"   既存URL: {existing_url}")
        print(f"   アップロード日: {existing_record['upload_date']}")
        
        # オプション処理
        if len(sys.argv) > 2 and sys.argv[2] == "--force-upload":
            print("[INFO] --force-upload: 強制的に新しくアップロードを実行します...")
        else:
            # デフォルトは既存URL使用（--use-existingと同じ動作）
            print(f"📎 既存URLを使用します: {existing_url}")
            return existing_url
    
    # ファイル情報を表示
    file_size = os.path.getsize(file_path)
    file_size_mb = file_size / (1024 * 1024)
    print(f"[INFO] アップロード対象ファイル: {file_path}")
    print(f"[INFO] ファイルサイズ: {file_size_mb:.2f} MB")
    
    # local_fal_upload.py を実行
    print("[INFO] local_fal_upload.py を実行中...")
    uploaded_url = run_local_fal_upload(file_path)
    
    if not uploaded_url:
        return None
    
    print("🎉 アップロード成功!")
    print("=" * 60)
    print(f"📎 アップロードURL: {uploaded_url}")
    print("=" * 60)
    
    # データベースに登録
    print(f"[INFO] データベースに登録中: {file_name} -> {uploaded_url}")
    try:
        record_id = db.insert_upload(file_name, uploaded_url, file_path)
        print(f"[SUCCESS] データベースに登録完了 (ID: {record_id})")
    except Exception as e:
        print(f"[WARNING] データベース登録に失敗: {e}（アップロードは成功）")
    
    return uploaded_url

def main():
    """メイン関数"""
    if len(sys.argv) < 2:
        print("使用方法:")
        print("  python fal_upload_wrapper.py <file_path>        # 既存URLがあれば自動使用")
        print("  python fal_upload_wrapper.py <file_path> --force-upload")
        print("  python fal_upload_wrapper.py stats             # 統計情報表示")
        print("")
        print("動作:")
        print("  デフォルト       既存URLがあれば自動で使用、なければ新規アップロード")
        print("  --force-upload   既存URLがあっても強制的に新規アップロード")
        print("")
        print("例:")
        print("  python fal_upload_wrapper.py /path/to/image.png")
        print("  python fal_upload_wrapper.py image.png --force-upload")
        sys.exit(1)
    
    # 特別なコマンド処理
    
    if sys.argv[1] == "stats":
        db = FalUploadDB()
        stats = db.get_stats()
        print("=== データベース統計 ===")
        for key, value in stats.items():
            print(f"{key}: {value}")
        return
    
    # 通常のアップロード処理
    file_path = sys.argv[1]
    result = upload_with_database_wrapper(file_path)
    
    if result:
        print(f"\n🔗 最終アップロードURL:")
        print(f'"{result}"')
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()