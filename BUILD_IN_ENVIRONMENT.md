# この環境での `.exe` 化実行結果

## 実行したこと
1. `dotnet` の存在確認
2. `dotnet build` 実行
3. `apt-get` で SDK インストール試行
4. `dotnet-install.sh` で SDK インストール試行
5. `apt-get install dotnet-sdk-8.0` 実行

## 結果
- この実行環境には `dotnet` がインストールされていません。
- パッケージ取得がプロキシの `403 Forbidden` で遮断されるため、SDK導入ができません。
- そのため、この環境内では WinUI 3 プロジェクトの `.exe` 出力を完了できませんでした。
- 参考: `apt-get install dotnet-sdk-8.0` は依存パッケージ解決までは進むものの、実パッケージ取得時に同じく `403 Forbidden` で失敗しました。

## Windows環境での `.exe` 化（再現手順）
PowerShell で次を実行:

```powershell
.\\scripts\\publish-exe.ps1
```

出力先（既定）:
- `src\\SilhouetteLocalDaily\\bin\\Release\\net8.0-windows10.0.19041.0\\win-x64\\publish\\SilhouetteLocalDaily.exe`


## 補助スクリプト
- `scripts/install-dotnet-ubuntu.sh`: Ubuntuで `dotnet-sdk-8.0` をインストールする手順。
- `scripts/publish-exe.ps1`: Windows PowerShellで Exe を発行する手順。
