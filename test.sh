#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
source ./scripts/env.sh
exec "$task_python" -m unittest discover -s tests -v
