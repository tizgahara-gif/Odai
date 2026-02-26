#!/usr/bin/env bash
set -euo pipefail

# Ubuntu 24.04 で .NET 8 SDK をインストールする最小手順
# 利用例:
#   ./scripts/install-dotnet-ubuntu.sh

if ! command -v apt-get >/dev/null 2>&1; then
  echo "apt-get が見つかりません。Ubuntu環境で実行してください。" >&2
  exit 1
fi

sudo apt-get update -y
sudo apt-get install -y dotnet-sdk-8.0

echo "Installed: $(dotnet --version)"
