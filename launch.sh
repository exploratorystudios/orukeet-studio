#!/usr/bin/env bash
set -e
cd "$(dirname "$(readlink -f "$0")")"
export OMP_NUM_THREADS=2
export MKL_NUM_THREADS=2
export QT_LOGGING_RULES='qt.multimedia.ffmpeg.debug=false'
exec .venv/bin/python studio/app.py "$@"
