# Orukeet Studio

A local, native Qt desktop studio for Orukeet transcription, subtitle editing,
Pocket TTS speech generation and reference-voice cloning, and Argos translation.

## Open

Run `./launch.sh` from the project directory. On the original installation,
**Orukeet Studio** is also available in the application menu.

## Install from GitHub

The current launcher targets Linux and requires Python 3.12+, FFmpeg (including
`ffprobe`), and the system libraries needed by Qt. Clone with submodules to obtain
the pinned upstream Orukeet source:

```sh
git clone --recurse-submodules https://github.com/exploratorystudios/orukeet-studio.git
cd orukeet-studio
python3.12 -m venv .venv
.venv/bin/python -m pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.lock.txt
.venv/bin/orukeet install --device cpu --cache ./models/orukeet --output installation.json
./launch.sh
```

For an existing clone, run `git submodule update --init --recursive` first.
The requirements file records the original environment's package versions;
availability of those versions on a fresh machine has not been verified.
Model downloads and `installation.json` are generated locally. Virtual
environments, projects, exported media, videos, and reference voice samples are
excluded from Git. Optional NVIDIA speech support is described below.

## Use the studio

1. **Transcribe:** import audio/video and click Transcribe. Edit caption text and
   start/end times; export SRT, WebVTT or plain text, and import SRT or WebVTT back
   in — including files the studio exported earlier. Playback seeks from a caption
   time. Audio recognition uses the verified Orukeet Q8 model on CPU.
2. **Voice studio:** select the spoken language, write a script, and generate a
   built-in voice. To clone a reference voice, use the Model access and Sign in
   locally buttons first, then select clean audio of a voice you may use.
3. **Dubbing:** choose the correct source language and target language; translate
   the captions, review the translated text, and generate the timed WAV. Export
   dubbed video to replace the video's audio with the generated voice track; the
   picture is copied rather than re-encoded whenever the MP4 container allows it.

Supported speech output languages: English, French, German, Spanish, Italian,
Portuguese. Other Orukeet source languages can be transcribed and translated when
Argos provides the selected language pair. Missing models download on first use.
English and Spanish speech models and English → Spanish translation are prepared.

## Faster speech generation

In **Voice studio → Speech processor**, choose **NVIDIA GPU** to use the installed
CUDA speech environment. This selection also applies to dubbing and is saved in
projects. Restart an already-open studio to see the new selector. CPU remains the
default and now correctly uses two threads after Pocket TTS finishes importing.

On this machine, the English benchmark's median generation time was 2.45 seconds
on CPU and 0.97 seconds on the GTX 1650 Ti, for about 4.4 seconds of audio. GPU
startup adds overhead; longer scripts and multi-caption dubbing benefit most.
Both paths use the same float32 model and sampling defaults. See
[benchmark results and quality-check limits](benchmarks/README.md).

To recreate GPU support, run `./setup-tts-gpu.sh` (requires `uv`). It installs
PyTorch/Torchaudio 2.7.1 with CUDA 11.8 in `.venv-tts-gpu/` and reuses application
packages from `.venv/`. Only GPU speech jobs use this environment; the original
CPU environment continues to handle recognition and translation. The worker log
reports the selected device, model-load time, and generation/export time.

## Voice cloning access

The reference-voice integration is installed, but Kyutai gates the cloning weights.
Accept the model terms at https://huggingface.co/kyutai/pocket-tts, then run:

```sh
.venv/bin/hf auth login
```

Use your Hugging Face read token in the terminal. Do not put tokens in project
files. The official Hugging Face client manages the local credential. The studio
uses the ungated built-in voice models when cloning access is unavailable.

## Projects and outputs

- `projects/`: saved `.orukeet` projects, automatic recovery snapshot, and backups
  before importing new media or captions, or replacing captions with translations.
- `exports/`: generated audio/video. Files use unique names.
- Projects refer to source and reference media by absolute path; keep those files
  in place. Open `projects/autosave.orukeet` to recover the most recent valid edit.
- Orukeet models: `models/orukeet/`. Pocket TTS uses the Hugging Face cache;
  Argos uses its normal per-user package directory.
- The GUI uses separate worker processes to keep the interface responsive and
  releases model memory after each job. Cancel stops the worker.

## Boundaries

This is single-voice dubbing, with no speaker diarization, lip sync, music
separation or voice conversion. Video export replaces all original audio,
including background music. Translation quality and caption timing need review.
Long generated lines speed up by at most 2× to fit; the task reports an error if
more adjustment is needed. Short lines are followed by silence.

No media is uploaded by the studio. Initial model downloads and account login
require internet access. Models are cached; upstream libraries may still check
remote metadata on later starts. It is not configured as an air-gapped system.

## Development and validation

Python 3.12 virtual environment at `.venv/`; upstream Orukeet source is preserved
under `upstream/`. `requirements.lock.txt` records installed versions. Torch and
Torchaudio in the primary environment are CPU wheels from https://download.pytorch.org/whl/cpu.

```sh
.venv/bin/python -m pytest tests -q
```

Automated tests cover timing validation, subtitle formatting and project data.
Real-media checks exercised Orukeet transcription, built-in speech generation,
English → Spanish translation, timed dubbing, and video muxing. Reference cloning
was attempted and correctly reported that the account needs model access.

Upstream projects and license information:
- https://github.com/Oruk-AI/orukeet (code MIT; weights CC BY-SA 4.0)
- https://github.com/kyutai-labs/pocket-tts
- https://github.com/argosopentech/argos-translate
- PySide6 / Qt: https://doc.qt.io/qtforpython-6/licenses.html
