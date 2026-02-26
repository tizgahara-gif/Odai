# Silhouette Local Daily (Minimal WinUI 3 Exe)

Windowsで **Exeとして動作する最小構成** の WinUI 3 アプリです。

## 1. 概要
- 種別: WinUI 3 デスクトップアプリ（Windows App SDK）
- 配布方式: **unpackaged Exe**（`WindowsPackageType=None`）
- 目的: 起動確認と最小操作（お題生成）を行うための土台

## 2. ファイル構成
```text
.
├─ README.md
├─ 要件定義_WinUI3.md
└─ src/
   └─ SilhouetteLocalDaily/
      ├─ SilhouetteLocalDaily.csproj  # プロジェクト設定（WinExe / WinUI / unpackaged）
      ├─ Program.cs                   # エントリポイント
      ├─ App.xaml                     # アプリ共通リソース
      ├─ App.xaml.cs                  # 起動時に MainWindow を表示
      ├─ MainWindow.xaml              # メイン画面UI
      └─ MainWindow.xaml.cs           # Generateボタンのロジック
```

## 3. 前提環境
- Windows 10/11
- .NET 8 SDK
- Windows App SDK 対応ランタイム

## 4. 起動方法
### 4.1 開発実行（dotnet run）
```powershell
dotnet run --project .\src\SilhouetteLocalDaily\SilhouetteLocalDaily.csproj
```

### 4.2 Exe発行（self-contained）
```powershell
dotnet publish .\src\SilhouetteLocalDaily\SilhouetteLocalDaily.csproj `
  -c Release -r win-x64 --self-contained true `
  /p:WindowsAppSDKSelfContained=true
```

発行されるExe（例）:
- `src\SilhouetteLocalDaily\bin\Release\net8.0-windows10.0.19041.0\win-x64\publish\SilhouetteLocalDaily.exe`

## 5. 操作方法
1. アプリを起動する。
2. 画面上部に「今日の日付」が表示される。
3. お題カードに現在の `Silhouette` と `Local Rule` が表示される。
4. `Generate` ボタンを押すと、シルエットと局所ルールがランダムで再生成される。

## 6. 現在の実装範囲（最小構成）
- 日付表示
- ランダムお題生成（組み込み配列から抽選）
- 単一ウィンドウUI

> 注意: メモ保存、履歴、画像添付などは未実装です（要件定義は `要件定義_WinUI3.md` を参照）。


## 7. Exe化補助スクリプト
- Windows PowerShell で以下を実行すると、self-contained の Exe を発行できます。

```powershell
.\scripts\publish-exe.ps1
```

- この環境での実行可否と結果は `BUILD_IN_ENVIRONMENT.md` を参照してください。
