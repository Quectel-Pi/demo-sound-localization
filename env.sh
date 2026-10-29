#!/usr/bin/env bash
# Source from project launchers. Host-local dependencies are never used on ARM.
sound_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
dependency_root="$sound_root"
if [[ ! -d "$dependency_root/.deps/root/usr/lib/python3/dist-packages/numpy" &&
      -d "$sound_root/../sound_loca_demo/.deps/root/usr/lib/python3/dist-packages/numpy" ]]; then
  dependency_root="$(cd "$sound_root/../sound_loca_demo" && pwd)"
fi
local_root="$dependency_root/.deps/root"
if [[ "$(uname -m)" == "x86_64" && "$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')" == "3.10" && -d "$local_root/usr/lib/python3/dist-packages/numpy" ]]; then
  export PYTHONPATH="$dependency_root/.venv/lib/python3.10/site-packages:$dependency_root/.deps/voice:$local_root/usr/lib/python3/dist-packages:$local_root/usr/lib/python3.10:$local_root/usr/lib/python3.10/lib-dynload${PYTHONPATH:+:$PYTHONPATH}"
  export LD_LIBRARY_PATH="$local_root/usr/lib:$local_root/usr/lib/x86_64-linux-gnu:$local_root/usr/lib/x86_64-linux-gnu/blas:$local_root/usr/lib/x86_64-linux-gnu/lapack${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
  export TK_LIBRARY="$local_root/usr/share/tcltk/tk8.6"
fi
task_python=python3
if [[ -x "$sound_root/.venv/bin/python" ]]; then task_python="$sound_root/.venv/bin/python"; fi
if [[ "$task_python" == python3 && -x "$dependency_root/.venv/bin/python" ]]; then
  task_python="$dependency_root/.venv/bin/python"
fi
