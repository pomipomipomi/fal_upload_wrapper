#!/usr/bin/env python3
"""
SQLite ベースのファイルアップロード管理システム
fal_upload_wrapper.py で使用するデータベース操作クラス
"""

import sqlite3
import json
import os
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Tuple
import requests

class FalUploadDB:
    def __init__(self, db_path: str = "fal_uploads.db"):
        """
        データベース初期化
        
        Args:
            db_path: SQLiteデータベースファイルのパス
        """
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """データベースとテーブルを初期化"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS uploads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL,
                    url TEXT NOT NULL,
                    file_path TEXT,
                    file_size INTEGER,
                    file_hash TEXT,
                    upload_date TEXT NOT NULL,
                    last_verified TEXT,
                    is_valid BOOLEAN DEFAULT 1,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # インデックス作成（検索性能向上）
            conn.execute("CREATE INDEX IF NOT EXISTS idx_filename ON uploads(filename)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_file_hash ON uploads(file_hash)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_url ON uploads(url)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_upload_date ON uploads(upload_date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_is_valid ON uploads(is_valid)")
            
            conn.commit()
    
    def calculate_file_hash(self, file_path: str) -> Optional[str]:
        """ファイルのSHA256ハッシュを計算"""
        try:
            hasher = hashlib.sha256()
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception:
            return None
    
    def check_url_validity(self, url: str, timeout: int = 10) -> bool:
        """URLの有効性を確認"""
        try:
            response = requests.head(url, timeout=timeout, allow_redirects=True)
            return response.status_code == 200
        except:
            return False
    
    def find_by_filename(self, filename: str, validate_url: bool = True) -> Optional[Dict]:
        """
        ファイル名で検索（最新のレコードを返す）
        
        Args:
            filename: 検索するファイル名
            validate_url: URLの有効性をチェックするか
            
        Returns:
            見つかった場合はレコード辞書、見つからない場合はNone
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # 最新のレコードを取得
            cursor.execute("""
                SELECT * FROM uploads 
                WHERE filename = ? AND is_valid = 1
                ORDER BY created_at DESC 
                LIMIT 1
            """, (filename,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            record = dict(row)
            
            # URL有効性チェック
            if validate_url and not self.check_url_validity(record['url']):
                # URLが無効な場合、レコードを無効化
                self.invalidate_record(record['id'])
                return None
            
            # 最終確認日時を更新
            cursor.execute("""
                UPDATE uploads 
                SET last_verified = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (datetime.now().isoformat(), record['id']))
            conn.commit()
            
            return record
    
    def find_by_hash(self, file_hash: str, validate_url: bool = True) -> Optional[Dict]:
        """
        ファイルハッシュで検索（重複ファイル検出）
        
        Args:
            file_hash: 検索するファイルハッシュ
            validate_url: URLの有効性をチェックするか
            
        Returns:
            見つかった場合はレコード辞書、見つからない場合はNone
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM uploads 
                WHERE file_hash = ? AND is_valid = 1
                ORDER BY created_at DESC 
                LIMIT 1
            """, (file_hash,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            record = dict(row)
            
            # URL有効性チェック
            if validate_url and not self.check_url_validity(record['url']):
                self.invalidate_record(record['id'])
                return None
            
            return record
    
    def insert_upload(self, filename: str, url: str, file_path: str = None, 
                     metadata: Dict = None) -> int:
        """
        新しいアップロードレコードを挿入
        
        Args:
            filename: ファイル名
            url: アップロードURL
            file_path: ファイルパス（オプション）
            metadata: メタデータ辞書（オプション）
            
        Returns:
            挿入されたレコードのID
        """
        file_size = None
        file_hash = None
        
        # ファイルが存在する場合、サイズとハッシュを計算
        if file_path and os.path.exists(file_path):
            try:
                file_size = os.path.getsize(file_path)
                file_hash = self.calculate_file_hash(file_path)
            except Exception:
                pass
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO uploads (
                    filename, url, file_path, file_size, file_hash,
                    upload_date, last_verified, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                filename, url, file_path, file_size, file_hash,
                datetime.now().isoformat(),
                datetime.now().isoformat(),
                json.dumps(metadata) if metadata else None
            ))
            conn.commit()
            return cursor.lastrowid
    
    def invalidate_record(self, record_id: int):
        """レコードを無効化（物理削除せず、論理削除）"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE uploads 
                SET is_valid = 0, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (record_id,))
            conn.commit()
    
    def cleanup_invalid_urls(self, batch_size: int = 100) -> int:
        """無効なURLのレコードを一括でクリーンアップ"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # 有効とマークされているレコードを取得
            cursor.execute("""
                SELECT id, url FROM uploads 
                WHERE is_valid = 1
                LIMIT ?
            """, (batch_size,))
            
            records = cursor.fetchall()
            invalidated_count = 0
            
            for record in records:
                if not self.check_url_validity(record['url']):
                    self.invalidate_record(record['id'])
                    invalidated_count += 1
            
            return invalidated_count
    
    def get_stats(self) -> Dict:
        """データベース統計情報を取得"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 総レコード数
            cursor.execute("SELECT COUNT(*) FROM uploads")
            total_records = cursor.fetchone()[0]
            
            # 有効レコード数
            cursor.execute("SELECT COUNT(*) FROM uploads WHERE is_valid = 1")
            valid_records = cursor.fetchone()[0]
            
            # 無効レコード数
            cursor.execute("SELECT COUNT(*) FROM uploads WHERE is_valid = 0")
            invalid_records = cursor.fetchone()[0]
            
            # 総ファイルサイズ
            cursor.execute("SELECT SUM(file_size) FROM uploads WHERE is_valid = 1 AND file_size IS NOT NULL")
            total_size = cursor.fetchone()[0] or 0
            
            # 最古・最新のアップロード日
            cursor.execute("SELECT MIN(upload_date), MAX(upload_date) FROM uploads WHERE is_valid = 1")
            date_range = cursor.fetchone()
            
            return {
                'total_records': total_records,
                'valid_records': valid_records,
                'invalid_records': invalid_records,
                'total_size_bytes': total_size,
                'total_size_mb': round(total_size / (1024 * 1024), 2) if total_size else 0,
                'earliest_upload': date_range[0],
                'latest_upload': date_range[1]
            }
    
    def search_uploads(self, query: str = "", limit: int = 100) -> List[Dict]:
        """アップロード履歴を検索"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            if query:
                cursor.execute("""
                    SELECT * FROM uploads 
                    WHERE (filename LIKE ? OR url LIKE ? OR file_path LIKE ?) 
                    AND is_valid = 1
                    ORDER BY created_at DESC 
                    LIMIT ?
                """, (f'%{query}%', f'%{query}%', f'%{query}%', limit))
            else:
                cursor.execute("""
                    SELECT * FROM uploads 
                    WHERE is_valid = 1
                    ORDER BY created_at DESC 
                    LIMIT ?
                """, (limit,))
            
            return [dict(row) for row in cursor.fetchall()]
    
    def migrate_from_json(self, json_file_path: str) -> int:
        """
        既存のJSONファイルからデータをマイグレーション
        
        Args:
            json_file_path: 既存のJSONファイルパス
            
        Returns:
            マイグレーションしたレコード数
        """
        if not os.path.exists(json_file_path):
            return 0
        
        try:
            with open(json_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            migrated_count = 0
            for filename, url in data.items():
                # 既存レコードをチェック
                existing = self.find_by_filename(filename, validate_url=False)
                if not existing:
                    self.insert_upload(filename, url)
                    migrated_count += 1
            
            return migrated_count
            
        except Exception as e:
            print(f"マイグレーションエラー: {e}")
            return 0


def main():
    """テスト・管理用のメイン関数"""
    import sys
    
    if len(sys.argv) < 2:
        print("使用方法:")
        print("  python fal_upload_db.py stats          # 統計情報表示")
        print("  python fal_upload_db.py search [query] # 検索")
        print("  python fal_upload_db.py cleanup        # 無効URL削除")
        print("  python fal_upload_db.py migrate <json> # JSONからマイグレーション")
        return
    
    db = FalUploadDB()
    command = sys.argv[1]
    
    if command == "stats":
        stats = db.get_stats()
        print("=== データベース統計 ===")
        for key, value in stats.items():
            print(f"{key}: {value}")
    
    elif command == "search":
        query = sys.argv[2] if len(sys.argv) > 2 else ""
        results = db.search_uploads(query)
        print(f"=== 検索結果 ('{query}') ===")
        for record in results:
            print(f"ID: {record['id']}, ファイル名: {record['filename']}")
            print(f"URL: {record['url']}")
            print(f"アップロード日: {record['upload_date']}")
            print("-" * 50)
    
    elif command == "cleanup":
        count = db.cleanup_invalid_urls()
        print(f"無効なURL {count} 件を削除しました")
    
    elif command == "migrate":
        if len(sys.argv) < 3:
            print("JSONファイルパスを指定してください")
            return
        json_path = sys.argv[2]
        count = db.migrate_from_json(json_path)
        print(f"{count} 件のレコードをマイグレーションしました")


if __name__ == "__main__":
    main()