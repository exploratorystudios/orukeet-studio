#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
uv venv --allow-existing .venv-tts-gpu --python .venv/bin/python
uv pip install --python .venv-tts-gpu/bin/python torch==2.7.1 torchaudio==2.7.1 --index-url https://download.pytorch.org/whl/cu118
# Reuse the studio's pinned application packages, after CUDA's own dependencies.
.venv/bin/python - <<'PY'
from pathlib import Path
import sys
version = f'python{sys.version_info.major}.{sys.version_info.minor}'
site = Path('.venv-tts-gpu/lib') / version / 'site-packages'
(site / 'studio-dependencies.pth').write_text(str((Path('.venv/lib') / version / 'site-packages').resolve()) + '\n')
PY
.venv-tts-gpu/bin/python -c 'import torch; assert torch.cuda.is_available(), "CUDA is unavailable"; print(torch.__version__, torch.cuda.get_device_name())'
