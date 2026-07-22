#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="${1:-v0.2.20}"
NAME="qiban-companion-portable-${VERSION}"
DIST="$ROOT/dist"
ZIP_PATH="$DIST/${NAME}.zip"

mkdir -p "$DIST"

if ! git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "需要在 Git 仓库中运行打包脚本。"
  exit 1
fi

if [ -n "$(git -C "$ROOT" status --porcelain)" ]; then
  echo "当前有未提交改动。请先提交，再生成发行 ZIP。"
  exit 1
fi

git -C "$ROOT" archive \
  --format zip \
  --prefix "qiban-companion/" \
  --output "$ZIP_PATH" \
  HEAD

unzip -t "$ZIP_PATH" >/dev/null
echo "$ZIP_PATH"
