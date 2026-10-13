# TTS measurements — 2026-09-15

Machine: Intel i5-10300H (4 cores / 8 threads), GTX 1650 Ti (4 GB).
English model, Alba voice, default float32 weights and sampler settings.
Text: “Welcome to Orukeet Studio. This is a test of the speech generation pipeline.”
Seed: 1234. Three repetitions per setting, one model load per process.

| Backend | Median generation | Audio length |
| --- | ---: | ---: |
| Original CPU, 1 thread | 2.670 s | 4.40 s |
| Corrected CPU, 2 threads | 2.445 s | 4.40 s |
| CPU, 4 threads | 2.633 s | 4.40 s |
| GPU, 1 CPU thread | 0.970 s | 4.48 s |

Two CPU threads reduced median generation latency by 8.4%. The GPU median
was 2.52× faster than the corrected CPU. Its first generation took 1.566 s;
subsequent generations took 0.970 and 0.877 s. These are generation measurements,
not end-to-end launch latency. GUI workers load a model per job; GPU initialization
can outweigh the gain for a short one-off clip. Dubbing reuses the loaded model
across captions. Downloads and other desktop activity can affect timings.

The CPU environment uses torch 2.14.0+cpu; the separate GPU environment uses
2.7.1+cu118. Consequently, the comparison includes the runtime difference.
The CUDA 11.8 wheel choice follows the [official PyTorch installation matrix](https://docs.pytorch.org/get-started/previous-versions/)
and ran successfully with the installed NVIDIA 535 driver.

## Quality checks and limits

No quantization, reduced precision, shortened text, reduced sampler steps, or
changes to voice/model selection were applied. Two CPU threads produced the same
length as one thread, with a maximum absolute float waveform difference of
0.0000462. CPU and CUDA random sampling produces different waveforms even with the
same seed. Repeating the GPU run with the same seed produced identical samples.
Local Orukeet recognition returned identical words for both backends (including
the same “Orikeet” spelling of the product name); raw transcripts are in `results/`.
This is a content sanity check, not a comprehensive perceptual quality evaluation
across languages and reference voices.

An experimental outer `torch.inference_mode()` failed because Pocket TTS updates
inference tensors from its decoder thread. It is not used by the studio.

## Reproduce

From the project root:

```sh
.venv/bin/python benchmarks/tts_probe.py --output /tmp/orukeet-cpu-check
./setup-tts-gpu.sh
.venv-tts-gpu/bin/python benchmarks/tts_probe.py --device cuda --output /tmp/orukeet-gpu-check
```

The script saves WAV files and raw JSON timings. Model loading is logged separately.
The checked-in `results/` contains the measured timing and transcription records.
