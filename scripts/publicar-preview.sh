#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$REPO_ROOT/frontend"
PREVIEW_DIR="$REPO_ROOT/preview"

cd "$FRONTEND_DIR"
npm ci
npm run build

mkdir -p "$PREVIEW_DIR"
find "$PREVIEW_DIR" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
cp -R "$FRONTEND_DIR/dist/." "$PREVIEW_DIR/"
