# FAL Upload Wrapper (SQLite版) - 使用方法・技術仕様

## 概要

`fal_upload_wrapper.py` は、ファイルアップロードの重複を防ぎ、アップロード履歴をSQLiteデータベースで効率的に管理するPythonスクリプトです。

### 主な機能
- **重複チェック**: ファイル名とSHA256ハッシュによる重複検出
- **高速検索**: SQLiteインデックスによる高速検索（1000件以上でも瞬時）
- **自動URL再利用**: 既存URLがあれば対話なしで自動使用（デフォルト動作）
- **URL有効性管理**: 無効URLの自動検出・論理削除
- **メタデータ管理**: アップロード日時、ファイルサイズ、最終確認日の記録
- **統計情報**: データベース統計の表示機能

## インストール・セットアップ

### 1. 必要なファイル
```bash
fal_upload_wrapper.py    # メインスクリプト
fal_upload_db.py        # データベース操作クラス
local_fal_upload.py     # 実際のアップロード処理（別途用意）
```

### 2. 依存関係
```bash
pip install requests
# SQLiteは標準ライブラリに含まれるため追加インストール不要
```

### 3. 他環境での設定変更箇所

#### A. パス設定の変更 (`fal_upload_wrapper.py`)
```python
# 16行目: local_fal_upload.py のパス
LOCAL_FAL_UPLOAD_SCRIPT = "/home/seren/claude-home/local_fal_upload.py"
# ↓ 変更例
LOCAL_FAL_UPLOAD_SCRIPT = "/path/to/your/local_fal_upload.py"
```

#### B. データベースパス設定 (`fal_upload_db.py`)
```python
# 15行目: SQLiteデータベースファイルのパス
def __init__(self, db_path: str = "/home/seren/claude-home/fal_uploads.db"):
# ↓ 変更例
def __init__(self, db_path: str = "/path/to/your/fal_uploads.db"):
```

## 使用方法

### 基本的なアップロード
```bash
# デフォルト動作：既存URLがあれば自動使用、なければ新規アップロード
python3 fal_upload_wrapper.py image.png

# 絶対パスでも可能
python3 fal_upload_wrapper.py /path/to/image.png
```

### オプション付きアップロード
```bash
# 既存URLがあっても強制的に新規アップロード
python3 fal_upload_wrapper.py image.png --force-upload
```

### データベース管理
```bash
# 統計情報表示
python3 fal_upload_wrapper.py stats

# データベース直接操作
python3 fal_upload_db.py stats          # 統計情報
python3 fal_upload_db.py search [query] # 検索
python3 fal_upload_db.py cleanup        # 無効URL削除
```

## 動作パターン

### **1. デフォルト動作（推奨）**
```bash
python3 fal_upload_wrapper.py image.png
```
**動作:**
- 既存URLがあれば**自動で使用**（対話なし）
- 既存URLがなければ新規アップロード実行
- 最も効率的で使いやすい

### **2. `--force-upload` オプション**
```bash
python3 fal_upload_wrapper.py image.png --force-upload
```
**動作:**
- 既存URLがあっても**強制的に新規アップロード**
- 必ず新しいURLを生成したい場合のみ使用

### **結果の違い**

| オプション | 対話 | 既存URL検出時 | アップロード実行 | 新規URL生成 |
|------------|------|---------------|------------------|-------------|
| **指定なし（デフォルト）** | ❌ なし | 既存を自動使用 | 既存なしの場合のみ | 既存なしの場合のみ |
| **--force-upload** | ❌ なし | 無視して強制実行 | ⭕ 必ず実行 | ⭕ 必ず生成 |

### **使い分け**
- **通常利用**: 指定なし（既存URL自動使用、効率的・コスト削減）
- **新規URL必須**: `--force-upload` （必ず新しいURLが必要な場合）

## 技術仕様

### データベーススキーマ
```sql
CREATE TABLE uploads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,           -- ファイル名
    url TEXT NOT NULL,               -- アップロードURL
    file_path TEXT,                  -- 元ファイルパス
    file_size INTEGER,               -- ファイルサイズ（バイト）
    file_hash TEXT,                  -- SHA256ハッシュ
    upload_date TEXT NOT NULL,       -- アップロード日時
    last_verified TEXT,              -- 最終URL確認日時
    is_valid BOOLEAN DEFAULT 1,      -- URL有効性フラグ
    metadata TEXT,                   -- メタデータ（JSON形式）
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### インデックス
```sql
CREATE INDEX idx_filename ON uploads(filename);     -- ファイル名検索
CREATE INDEX idx_file_hash ON uploads(file_hash);   -- ハッシュ検索
CREATE INDEX idx_url ON uploads(url);               -- URL検索
CREATE INDEX idx_upload_date ON uploads(upload_date); -- 日付検索
CREATE INDEX idx_is_valid ON uploads(is_valid);     -- 有効性検索
```

### 重複検出ロジック
1. **ファイル名検索**: 同じファイル名の最新レコードを検索
2. **ハッシュ検索**: ファイル内容が同じものを検索（重複ファイル検出）
3. **URL有効性確認**: 既存URLが有効か自動チェック
4. **論理削除**: 無効URLは物理削除せず `is_valid=0` に設定

### パフォーマンス特性
- **JSON版**: O(n) - 全レコード読み込み必要
- **SQLite版**: O(log n) - インデックス検索で高速化
- **メモリ使用量**: 大幅削減（全データロード不要）

## API仕様

### FalUploadDB クラス

#### 主要メソッド
```python
# 初期化
db = FalUploadDB(db_path="/path/to/database.db")

# ファイル名で検索
record = db.find_by_filename("image.png", validate_url=True)

# ハッシュで検索（重複検出）
record = db.find_by_hash("sha256hash", validate_url=True)

# 新規登録
record_id = db.insert_upload("image.png", "https://...", "/path/to/file")

# 統計情報取得
stats = db.get_stats()

# 検索
results = db.search_uploads("query", limit=100)

```

#### 戻り値形式
```python
# レコード辞書例
{
    'id': 1,
    'filename': 'image.png',
    'url': 'https://v3.fal.media/files/...',
    'file_path': '/path/to/image.png',
    'file_size': 1234567,
    'file_hash': 'abcd1234...',
    'upload_date': '2025-08-04T12:50:43.398560',
    'last_verified': '2025-08-04T12:50:43.398560',
    'is_valid': 1,
    'metadata': None,
    'created_at': '2025-08-04 12:50:43',
    'updated_at': '2025-08-04 12:50:43'
}
```

## 統計情報出力例
```
=== データベース統計 ===
total_records: 1523        # 総レコード数
valid_records: 1498        # 有効レコード数
invalid_records: 25        # 無効レコード数
total_size_bytes: 2147483648  # 総ファイルサイズ（バイト）
total_size_mb: 2048.0      # 総ファイルサイズ（MB）
earliest_upload: 2025-01-01T10:00:00  # 最古アップロード
latest_upload: 2025-08-04T12:50:43    # 最新アップロード
```

## トラブルシューティング

### よくあるエラー

#### 1. `ModuleNotFoundError: No module named 'fal_upload_db'`
**原因**: `fal_upload_db.py` が同じディレクトリにない
**解決**: ファイルの配置を確認、またはPYTHONPATHを設定

#### 2. `local_fal_upload.py が見つかりません`
**原因**: `LOCAL_FAL_UPLOAD_SCRIPT` のパスが間違っている
**解決**: `fal_upload_wrapper.py` の16行目のパスを修正

#### 3. `database is locked`
**原因**: 他のプロセスがデータベースを使用中
**解決**: 他のプロセスを終了するか、しばらく待ってから再実行

#### 4. `UnicodeEncodeError: 'cp932' codec can't encode character` (Windows)
**原因**: Windowsコンソールの文字エンコーディングが日本語(cp932)に設定されている
**解決**: 実行前に以下のコマンドを実行してUTF-8に設定
```cmd
chcp 65001
set PYTHONIOENCODING=utf-8
```
または1行で：
```cmd
chcp 65001 && set PYTHONIOENCODING=utf-8
```

### デバッグ方法
```bash
# データベース内容確認
python3 fal_upload_db.py search

# 特定ファイルの検索
python3 fal_upload_db.py search "image.png"

# 無効URLのクリーンアップ
python3 fal_upload_db.py cleanup
```

## セキュリティ考慮事項

1. **SQLインジェクション対策**: パラメータ化クエリを使用
2. **ファイルパス**: 絶対パスでの指定を推奨
3. **権限**: データベースファイルの適切な権限設定が必要
4. **バックアップ**: 定期的なデータベースバックアップを推奨

## ライセンス・制限事項

- Python 3.6以上が必要
- SQLite 3.x に依存
- `local_fal_upload.py` の実装は別途必要
- ネットワーク接続が必要（URL有効性確認のため）

## 今後の拡張予定

- [ ] タグ・カテゴリ機能
- [ ] アップロード履歴のエクスポート機能
- [ ] Web UI の追加
- [ ] 自動バックアップ機能
- [ ] マルチユーザー対応