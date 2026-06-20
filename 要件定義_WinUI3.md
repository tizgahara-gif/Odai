# シルエット×局所ルール 日次お題アプリ 要件定義（WinUI 3）

## 0. 概要
- アプリ名：Silhouette Local Daily
- 目的（1文）：毎日1つの「シルエット×局所ルール」お題を短時間で生成・記録し、継続的な制作習慣を支援する。
- 想定OS：Windows 10/11
- UI：WinUI 3（Windows App SDK）
- 配布形態：unpackaged Exe（将来MSIX化を検討）

## 1. 成功指標（KPI）
- 起動〜今日のお題表示：2秒以内
- 入力操作回数（起動→保存）：5回以内
- 日次ログ欠損率：1%以下
- 継続率：30日中20回以上

## 2. ユーザー像・利用シーン
- 主ユーザー：自分 / 配布想定あり（小規模クリエイターコミュニティ）
- 利用頻度：毎日 / 週7回
- 1セッションの時間：10分
- 典型フロー（箇条書きで）：
  1) 起動
  2) お題生成
  3) メモ/画像追加
  4) 保存
  5) 振り返り（任意）

## 3. スコープ
### 3.1 MVPに含める
- [x] 今日のお題生成
- [x] 日次記録（メモ/実施チェック）
- [x] 画像添付（ドラッグ&ドロップ）
- [x] 履歴一覧（検索最低限）

### 3.2 今回は含めない（将来）
- [x] クラウド同期
- [x] SNS共有
- [x] 高度な統計/分析
- [x] アカウント/ログイン

## 4. 主要概念（ドメインモデル）
### 4.1 エンティティ
#### Theme（お題）
- themeId: string
- silhouetteRule: string
- localRule: string
- tags: string[]（任意）
- notes: string（任意：例・禁則など）

#### DailyEntry（日次）
- date: yyyy-mm-dd
- selectedThemeId: string
- rollHistory: string[]（任意：リロール履歴）
- memo: string（任意）
- didWork: bool
- durationMinutes: int（任意）
- rating: int（任意 1-5）
- attachments: Attachment[]

#### Attachment（添付）
- attachmentId: string
- originalPath: string（参照元）
- storedPath: string（アプリ管理下）
- thumbnailPath: string（任意）
- createdAt: datetime

### 4.2 辞書（候補群）
- silhouetteCandidates: Candidate[]
- localCandidates: Candidate[]
- Candidate:
  - id: string
  - text: string
  - weight: float（抽選重み）
  - enabled: bool
  - tags: string[]（任意）

## 5. 機能要件
### 5.1 お題生成
- FR-001: 起動時に「今日（ローカル日付）」の DailyEntry を自動生成する
- FR-002: 1クリックでお題（silhouetteRule 1つ + localRule 1つ）を生成する
- FR-003: 重複回避（直近 N 日間で同一組み合わせを避ける）
  - N = 14（初期値）
- FR-004: リロール機能（最大 K 回）
  - K = 3（初期値）
- FR-005: ロック機能（ロック中は再生成不可、明示解除でのみ変更）
- FR-006: フィルタ（任意：タグ/難易度/直線系・曲線系など）
  - MVPでは 無

### 5.2 日次記録
- FR-010: メモ入力（単一テキストボックス）
- FR-011: 実施チェック（didWork）
- FR-012: 保存（自動保存/手動保存の方針）
  - 方針：入力変更ごとの自動保存 + 明示保存ボタン
- FR-013: 入力の復元（クラッシュ/再起動後に直前状態を復元）
  - 方式：自動保存 + SQLiteトランザクション

### 5.3 画像添付
- FR-020: ドラッグ&ドロップで画像を添付
- FR-021: 対応拡張子：.png .jpg .jpeg .webp
- FR-022: 添付画像はアプリ管理フォルダにコピーして参照切れを防ぐ
- FR-023: サムネイル生成（任意/必須）
  - 必須度：必須（生成失敗時は原寸縮小表示）

### 5.4 履歴・検索・振り返り
- FR-030: 履歴一覧（日付降順）
- FR-031: 検索（silhouette/local/tags/memo）
- FR-032: カレンダー表示（任意：実施日ハイライト）
  - MVPでは 無
- FR-033: 統計（出現頻度・継続日数）
  - MVPでは 無

### 5.5 辞書編集（候補の管理）
- FR-040: 候補追加/削除/有効化切替
- FR-041: 重み（weight）編集
- FR-042: インポート/エクスポート（JSON）
  - MVPでは 有

### 5.6 設定
- FR-050: 重複回避窓 N の変更
- FR-051: 保存形式（SQLite/JSON）選択（固定でも可）
- FR-052: データ保存先表示（変更可否）
- FR-053: ホットキー（任意）
  - 例：Generate / Roll / Save

## 6. UI要件（WinUI 3）
### 6.1 画面一覧
- Screen-Home: 今日のお題 + 入力 + 添付
- Screen-History: 履歴一覧 + 検索 + 詳細
- Screen-Library: 候補辞書の編集
- Screen-Settings: 設定

### 6.2 ナビゲーション
- NavigationView を使用（左ナビ）
- 画面遷移は FrameNavigation / MVVM（選択）
  - 方針：MVVM + NavigationService

### 6.3 Home 画面（要素）
- 今日の日付表示
- お題カード（silhouette/local）
- ボタン：Generate / Reroll / Lock / Save
- メモ欄
- チェック：やった
- 添付エリア：Drag&Drop + 添付一覧（サムネ）

### 6.4 アクセシビリティ/操作
- キーボード操作：Tab順、ショートカット（Generate: Ctrl+G / Save: Ctrl+S）
- 最小ウィンドウサイズ：960 x 640
- DPI/スケーリング対応：必須

## 7. データ永続化・ファイル構成
### 7.1 ストレージ方式
- 方式：SQLite
- 理由（短く）：履歴検索・重複判定・トランザクション保全が容易で、WinUI 3単体運用でも信頼性が高い。
- 互換性方針：SchemaVersion テーブルでマイグレーション管理（必須）

### 7.2 物理保存先（例）
- UserDataRoot:
  - packaged（MSIX）: LocalFolder
  - unpackaged: %AppData%\SilhouetteLocalDaily
- Attachments:
  - <UserDataRoot>\attachments
- Backups:
  - <UserDataRoot>\backups

### 7.3 バックアップ/復元
- 自動バックアップ頻度：1日1回（起動時）
- 世代数：7
- 破損検知時の挙動：最新バックアップからの復元提案ダイアログを表示

## 8. 非機能要件
- NFR-001: 起動時間 2秒以内（初回3秒以内 / 2回目以降2秒以内）
- NFR-002: オフライン動作（必須）
- NFR-003: 外部通信（禁止）
- NFR-004: 例外処理とログ
  - ログ種別：error/info
  - 保存先：<UserDataRoot>\logs
- NFR-005: クラッシュ耐性：入力ロスを最小化（自動保存）
- NFR-006: パフォーマンス：履歴 10,000件でも検索 300ms以内

## 9. 受け入れ基準（Given/When/Then）
### 9.1 お題生成
- AC-001:
  - Given 直近N日に同一組み合わせが存在する
  - When 今日のお題を生成する
  - Then その組み合わせは出ない（候補不足時はNを段階的に縮小し、最終的に警告付きで重複許可）

### 9.2 添付
- AC-010:
  - Given 画像をD&D
  - When 保存
  - Then アプリ管理フォルダにコピーされ、再起動後も表示される

### 9.3 データ保全
- AC-020:
  - Given 入力途中
  - When アプリ強制終了
  - Then 次回起動で直前状態が復元される

## 10. フォールバック/例外設計
- 候補不足（重複回避で出せない）時：
  - 方針：重複回避窓を14→7→3→1の順で段階的に緩和し、最後にユーザーへ警告表示
- 添付コピー失敗時：
  - 方針：参照のみで一時登録し、保存完了前に再試行を促す警告を表示
- データ破損時：
  - 方針：バックアップ復元UIを起動し、復元前に現行データを退避

## 11. テスト要件
- Unit：お題生成ロジック（重複回避/重み抽選）
- Integration：永続化（読み書き、マイグレーション）
- UI：最低限の操作シナリオ（MVP）

## 12. ビルド/配布（Exe化）
- 配布：unpackaged
- 更新方式：手動（新バージョンを上書きインストール）
- 署名：必要（社内配布時は自己署名、公開時は正式証明書）
- 依存：Windows App SDK バージョン 1.6

---

## 付録A：初期同梱お題セット（例）
- silhouette:
  1) 直線＋欠け
  2) 大円弧＋垂下
  3) S字長物＋薄膜
  4) 点群外周
- local:
  1) 分節
  2) 孔群
  3) 張力線
  4) サイズグラデ鱗/棘
