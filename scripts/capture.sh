#!/bin/bash
# capture.sh — Quick capture anything into your Second Brain from the terminal
# Usage:
#   ./scripts/capture.sh url "https://example.com"
#   ./scripts/capture.sh note "Meeting idea: use RAG for onboarding"
#   ./scripts/capture.sh pdf ~/Downloads/paper.pdf
#   ./scripts/capture.sh youtube "https://youtube.com/watch?v=..."

set -e
BRAIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

case "$1" in
  url)
    python "$BRAIN_DIR/src/brain.py" ingest --url "$2"
    ;;
  note)
    python "$BRAIN_DIR/src/brain.py" ingest --text "$2"
    ;;
  pdf)
    python "$BRAIN_DIR/src/brain.py" ingest --file "$2"
    ;;
  youtube|yt)
    python "$BRAIN_DIR/src/brain.py" ingest --youtube "$2"
    ;;
  *)
    echo "Usage: capture.sh [url|note|pdf|youtube] <value>"
    exit 1
    ;;
esac
