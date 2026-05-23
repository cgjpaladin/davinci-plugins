#!/bin/bash
set -e; SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SYNC_EXTRA_DIRS=""
source "$SCRIPT_DIR/../tools/publish.sh"
