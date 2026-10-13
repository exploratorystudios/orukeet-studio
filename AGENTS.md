# AGENTS.md

Local PySide6 desktop studio: Orukeet transcription, SRT/VTT caption editing, Pocket TTS
speech + reference-voice cloning, Argos translation, and dubbed-video muxing. Linux only,
Python 3.12. Single app, no packaging, no CI, no lint/typecheck config.

## Layout and execution flow

- `studio/app.py` — the whole PySide6 GUI. Run with `./launch.sh` (sets `OMP_NUM_THREADS=2`,
  `MKL_NUM_THREADS=2`, then execs `.venv/bin/python studio/app.py`).
- `studio/engine.py` — two roles: pure helpers (`validate`, `captions`, `parse_captions`,
  `stamp`) used by the GUI, plus a worker CLI invoked as a subprocess:
  `python engine.py <request.json> <result.json>`. It prints progress lines prefixed
  `STUDIO:` which `app.py` parses into the status bar. Actions: `transcribe`, `translate`,
  `mux`, and `speech`/`dub` (both dispatch to `speech()`; `dub` is the timed/normalized path).
- `studio/auth.py` — standalone Hugging Face sign-in dialog, launched detached from the GUI.
- `upstream/` — git submodule (Oruk-AI/orukeet), installed editable via `-e ./upstream` in
  `requirements.lock.txt`. Run `git submodule update --init --recursive` before installing;
  importing `orukeet` (and therefore transcription) fails without it.

## Environment (`.venv/` does not exist in a fresh clone)

```sh
git submodule update --init --recursive
python3.12 -m venv .venv
.venv/bin/python -m pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.lock.txt
# transcribe additionally needs installation.json (gitignored, generated locally):
.venv/bin/orukeet install --device cpu --cache ./models/orukeet --output installation.json
```

- Torch/torchaudio are CPU wheels. GPU speech only: `./setup-tts-gpu.sh` (needs `uv`) builds
  `.venv-tts-gpu/` (torch 2.7.1+cu118) and wires it back to `.venv` site-packages via a `.pth`.
  `engine.worker_python()` routes `speech`/`dub` jobs with `device=cuda` to that interpreter;
  every other job runs under `sys.executable`.

## Testing

```sh
.venv/bin/python -m pytest tests -q                 # everything
.venv/bin/python -m pytest tests/test_studio.py -k mux   # focused
```

- `tests/test_studio.py` sets `QT_QPA_PLATFORM=offscreen` at module top and constructs the
  real `Studio` window, so Qt system libraries are required even for headless runs.
- Tests import `app`/`engine` as top-level modules (the file inserts `studio/` on `sys.path`).
  Running them creates `<repo>/projects/.jobs/` (gitignored).
- pytest is the entire automated verification story — also launch the app before calling GUI
  changes done.

## Conventions and gotchas

- **Flat imports.** `from engine import ...` — `studio/` is deliberately not a package. Adding
  `__init__.py` or relative imports breaks the worker subprocess invocation.
- **Dense style.** `app.py`/`engine.py` use one-line `def`/statement style with semicolons.
  Match the surrounding code, do not reformat.
- **Import order is load-bearing.** Heavy libs (torch, pocket_tts, argostranslate, soundfile)
  are imported lazily inside functions so the GUI starts fast. `pocket_tts` resets torch
  threads on import, so `torch.set_num_threads(...)` must run after the import, not before.
- **Pinned behavior.** `engine.translate` must keep `argos_settings.compute_type = 'float32'`
  (Argos' `'auto'` picks int8 on avx2 CPUs and decodes some packages to junk). Tests enforce
  this; don't "clean it up".
- **Language tables.** `engine.LANGUAGES` (6 speech languages: name → argos code, pocket-tts
  language, default voice) and `app.py`'s `source_codes` (25 transcription languages) are
  separate on purpose — speech output is a subset. Don't merge them.
- **Secrets.** Voice cloning needs a Hugging Face token with accepted terms for
  kyutai/pocket-tts; login goes through `studio/auth.py` / the HF client cache. Never put
  tokens in project files, and never commit `projects/`, `exports/`, `models/`,
  `installation.json`, `*.orukeet`, or venvs (all gitignored).
- **Benchmarks.** CPU/GPU timing records live in `benchmarks/` with rerun commands in its
  README (`benchmarks/tts_probe.py`); use them when changing the speech path.
- GUI, modeling behavior, and boundaries are documented in `README.md` — trust it for
  product behavior, trust the code for anything it contradicts.
