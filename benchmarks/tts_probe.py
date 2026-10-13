"""Fixed-seed TTS benchmark; run with either the CPU or GPU Python environment."""
import argparse
import json
from pathlib import Path
import time
import torch
from pocket_tts import TTSModel
import soundfile as sf

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
parser.add_argument('--language', default='english')
parser.add_argument('--voice', default='alba')
parser.add_argument('--repeats', type=int, default=3)
parser.add_argument('--output', type=Path, default=Path('/tmp/orukeet-tts-benchmark'))
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
torch.set_num_threads(1)
started = time.perf_counter()
model = TTSModel.load_model(language=args.language).to(args.device)
print(json.dumps({'load_seconds': time.perf_counter() - started, 'torch': torch.__version__, 'device': args.device}), flush=True)
state = model.get_state_for_audio_prompt(args.voice)
reference = None
rows = []
for repeat in range(args.repeats):
    for threads in ([1, 2, 4] if args.device == 'cpu' else [1]):
        torch.set_num_threads(threads)
        torch.manual_seed(1234)
        if args.device == 'cuda':
            torch.cuda.synchronize()
        started = time.perf_counter()
        audio = model.generate_audio(state, 'Welcome to Orukeet Studio. This is a test of the speech generation pipeline.').detach().cpu()
        elapsed = time.perf_counter() - started
        if reference is None:
            reference = audio
        same_shape = audio.shape == reference.shape
        row = {'threads': threads, 'repeat': repeat, 'seconds': elapsed,
               'audio_seconds': audio.numel() / model.sample_rate,
               'equal': torch.equal(audio, reference),
               'max_difference': (audio-reference).abs().max().item() if same_shape else None}
        rows.append(row)
        sf.write(args.output / f'{args.device}-{threads}-{repeat}.wav', audio.numpy(), model.sample_rate)
        print(json.dumps(row), flush=True)
(args.output / f'{args.device}.json').write_text(json.dumps(rows, indent=2))
