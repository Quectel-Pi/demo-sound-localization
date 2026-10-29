#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
skip_system=false
skip_tests=false

usage() {
  cat <<'EOF'
Usage: bash scripts/deploy.sh [options]

Prepare a fresh Debian/Ubuntu development board for Sound Localization.
Download and extract the ASR model separately before running this script.
See docs/deployment.md.

Options:
  --skip-system-packages  Do not run apt-get; required packages must exist.
  --skip-tests            Skip the unit and integration test suite.
  -h, --help              Show this help.
EOF
}

while (($#)); do
  case "$1" in
    --skip-system-packages) skip_system=true ;;
    --skip-tests) skip_tests=true ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

cd "$project_root"

if [[ "$skip_system" == false ]]; then
  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    privilege=()
  else
    command -v sudo >/dev/null 2>&1 || {
      echo 'sudo is required to install system packages; use --skip-system-packages if already prepared.' >&2
      exit 1
    }
    privilege=(sudo)
  fi
  "${privilege[@]}" apt-get update
  "${privilege[@]}" apt-get install -y \
    python3 python3-venv python3-pip python3-numpy python3-tk \
    alsa-utils fonts-noto-cjk ca-certificates
fi

command -v python3 >/dev/null 2>&1 || {
  echo 'python3 is unavailable.' >&2
  exit 1
}
command -v arecord >/dev/null 2>&1 || {
  echo 'arecord is unavailable; install alsa-utils.' >&2
  exit 1
}

if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv --system-site-packages .venv
fi
venv_python="$project_root/.venv/bin/python"

"$venv_python" -m pip install -r requirements-asr.txt
"$venv_python" -c 'import tkinter, numpy, webrtcvad, sherpa_onnx; print("Python dependencies: OK")'

model_dir="$("$venv_python" -c '
import json
from pathlib import Path
path = Path(json.load(open("config.json"))["asr_model_dir"])
print(path if path.is_absolute() else Path.cwd()/path)
')"
model_file="$model_dir/model.int8.onnx"
tokens_file="$model_dir/tokens.txt"

if [[ ! -s "$model_file" || ! -s "$tokens_file" ]]; then
  cat >&2 <<EOF
Required model files are missing:
  $model_file
  $tokens_file

Download and extract the model separately, then rerun this script.
See the model instructions and target directory in docs/deployment.md.
EOF
  exit 1
fi

model_bytes="$(wc -c < "$model_file")"
tokens_bytes="$(wc -c < "$tokens_file")"
if ((model_bytes < 100000000 || tokens_bytes < 1000)); then
  cat >&2 <<EOF
Model files exist but are unexpectedly small or incomplete.
Download and verify the model separately as described in docs/deployment.md.
EOF
  exit 1
fi
printf 'Model: OK (%s bytes, tokens %s bytes)\n' "$model_bytes" "$tokens_bytes"

if [[ "$skip_tests" == false ]]; then
  PYTHONDONTWRITEBYTECODE=1 bash test.sh
fi

cat <<EOF

Deployment completed.

Project: $project_root
Python:  $venv_python
Model:   $model_dir

Next checks:
  bash run.sh --probe --seconds 5
  bash run.sh
EOF
