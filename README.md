# Silhouette Local Daily (Minimal WinUI 3 Exe)

Windowsで **Exeとして動作する最小構成** の WinUI 3 アプリです。

## 構成
- `src/SilhouetteLocalDaily`: WinUI 3（Windows App SDK）最小プロジェクト
- 配布方式: **unpackaged**（`WindowsPackageType=None`）

## 前提
- Windows 10/11
- .NET 8 SDK
- Windows App SDK 対応ランタイム

## 実行（開発）
```powershell
dotnet run --project .\src\SilhouetteLocalDaily\SilhouetteLocalDaily.csproj
```

## Exe発行（自己完結）
```powershell
dotnet publish .\src\SilhouetteLocalDaily\SilhouetteLocalDaily.csproj `
  -c Release -r win-x64 --self-contained true `
  /p:WindowsAppSDKSelfContained=true
```

発行後のExe:
- `src\SilhouetteLocalDaily\bin\Release\net8.0-windows10.0.19041.0\win-x64\publish\SilhouetteLocalDaily.exe`

## 画面
- 今日の日付表示
- Generateボタンで「シルエット」「局所ルール」をランダム生成
