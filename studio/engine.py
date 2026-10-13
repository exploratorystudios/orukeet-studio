"""Local media operations, isolated from the GUI in a worker process."""
from pathlib import Path
import json, math, os, subprocess, sys, tempfile, time
ROOT = Path(__file__).resolve().parent.parent
LANGUAGES = {'English': ('en','english','alba'), 'French': ('fr','french','estelle'), 'German': ('de','german','juergen'), 'Spanish': ('es','spanish','lola'), 'Italian': ('it','italian','giovanni'), 'Portuguese': ('pt','portuguese','rafael')}

def worker_python(job):
    """Only GPU speech jobs use the separate CUDA dependencies."""
    if job['action'] in ('speech', 'dub') and job.get('device') == 'cuda':
        python = ROOT / '.venv-tts-gpu' / 'bin' / 'python'
        if not python.is_file():
            raise ValueError('GPU speech is not installed. Run setup-tts-gpu.sh or choose CPU.')
        return str(python)
    return sys.executable

def status(message):
    print('STUDIO:' + message, flush=True)

def run(args):
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr[-2500:])
    return result.stdout

def filter_audio(samples, rate, filters):
    """Run mono float32 samples through an ffmpeg filter chain, in memory."""
    import numpy as np
    result = subprocess.run(
        ['ffmpeg','-v','error','-f','f32le','-ar',str(rate),'-ac','1','-i','pipe:0',
         '-af',filters,'-f','f32le','pipe:1'],
        input=samples.astype('float32').tobytes(), capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace')[-2500:])
    return np.frombuffer(result.stdout, dtype='float32')

def validate(segments):
    previous = 0
    for seg in segments:
        start, end = float(seg['start']), float(seg['end'])
        if not math.isfinite(start + end) or start < previous - .001 or end <= start:
            raise ValueError('Caption times must be non-overlapping, in order, and end after they start.')
        if not str(seg['text']).strip():
            raise ValueError('Captions cannot be empty.')
        previous = end
    return segments

def stamp(seconds, vtt=False):
    ms = round(float(seconds) * 1000)
    hours, ms = divmod(ms, 3600000)
    minutes, ms = divmod(ms, 60000)
    seconds, ms = divmod(ms, 1000)
    return f'{hours:02}:{minutes:02}:{seconds:02}{"." if vtt else ","}{ms:03}'

def captions(segments, vtt=False):
    validate(segments)
    blocks = [f'{i}\n{stamp(s["start"], vtt)} --> {stamp(s["end"], vtt)}\n{s["text"].strip()}' for i,s in enumerate(segments,1)]
    return ('WEBVTT\n\n' if vtt else '') + '\n\n'.join(blocks) + '\n'

def clock(text):
    """Parse an SRT or WebVTT timestamp; both comma and dot decimals, hours optional."""
    parts = text.strip().replace(',', '.').split(':')
    if not 1 <= len(parts) <= 3:
        raise ValueError(f'Unreadable caption timestamp: {text.strip()}')
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + float(part)
    return seconds

def parse_captions(text):
    """Read back an SRT or WebVTT file exported by the studio, or written elsewhere."""
    segments = []
    # Cue blocks are separated by blank lines; an optional identifier line may
    # precede the timing line, and cue settings may follow it.
    for block in [b for b in text.replace('\ufeff', '').replace('\r\n', '\n').replace('\r', '\n').split('\n\n')]:
        lines = [line for line in block.split('\n') if line.strip()]
        if lines and lines[0].strip().upper().startswith('WEBVTT'):
            lines = lines[1:]
        timing = next((i for i, line in enumerate(lines) if '-->' in line), None)
        if timing is None:
            continue
        start, end = lines[timing].split('-->')[:2]
        body = ' '.join(line.strip() for line in lines[timing+1:]).strip()
        if not body:
            raise ValueError(f'Caption {len(segments)+1} in this file has no text.')
        # WebVTT may append cue settings (align, position) after the end time.
        segments.append({'start': clock(start), 'end': clock(end.split()[0]), 'text': body})
    if not segments:
        raise ValueError('No captions found. Choose an SRT or WebVTT file.')
    return validate(segments)

def transcribe(job):
    from orukeet import Orukeet
    config = json.loads((ROOT/'installation.json').read_text())
    status('Loading Orukeet · local speech recognition')
    with Orukeet(config['model'], config['runtime'], device=config['device']) as model:
        status('Transcribing your media…')
        return model.transcribe(job['media'])

def translate(job):
    import argostranslate.package as packages
    import argostranslate.settings as argos_settings
    import argostranslate.translate as translation
    # Argos defaults to compute_type 'auto', which selects int8 on CPUs without
    # avx512. Some packages (es→en 1.9) decode to repeated junk when quantized,
    # so pin float32: slower and larger in memory, but the only correct option.
    argos_settings.compute_type = 'float32'
    source, target = job['source'], job['target']
    if source == target:
        raise ValueError('Choose two different languages for translation.')
    installed = packages.get_installed_packages()
    if not any(p.from_code == source and p.to_code == target for p in installed):
        status('Downloading the selected translation model (first use only)…')
        packages.update_package_index()
        match = next((p for p in packages.get_available_packages() if p.from_code == source and p.to_code == target), None)
        if match is None:
            raise ValueError('No direct offline model for this language pair. Translate through English instead.')
        packages.install_from_path(match.download())
    segments = validate(job['segments'])
    for i, seg in enumerate(segments):
        status(f'Translating caption {i+1} of {len(segments)}')
        seg['text'] = translation.translate(seg['text'], source, target)
    return {'segments':segments}

class VoiceAccessError(RuntimeError):
    """An actionable model-access error suitable for the studio UI."""


def cloning_access_message(code, token_present, login_valid):
    if not token_present:
        return ('Voice cloning needs a Hugging Face login. In Voice studio, open Model access, '
                'accept the Pocket TTS terms, then use Sign in locally with a read token.')
    if code == 401 and not login_valid:
        return ('Hugging Face rejected the saved credential (401 Unauthorized). '
                'Use Voice studio → Sign in locally to replace it with a valid read token. '
                'Accept the Pocket TTS model terms using the same account.')
    return ('This Hugging Face account or token cannot download the cloning model. '
            'Open Model access and accept the Pocket TTS terms using the same account. '
            'If using a fine-grained token, allow access to this gated model, then sign in again.')


def prepare_cloning_weights(language):
    # Fetch explicitly: Pocket TTS catches download errors and silently falls back
    # to non-cloning weights, which otherwise hides the actionable root cause.
    import pocket_tts, yaml
    from pocket_tts.utils.utils import download_if_necessary
    from huggingface_hub import get_token, HfApi
    from huggingface_hub.errors import HfHubHTTPError
    config_path = Path(pocket_tts.__file__).parent / 'config' / (language + '.yaml')
    config = yaml.safe_load(config_path.read_text())
    try:
        download_if_necessary(config['weights_path'])
    except HfHubHTTPError as exc:
        code = getattr(exc.response, 'status_code', None)
        if code not in (401, 403):
            raise VoiceAccessError('The cloning model download failed. Check the connection and retry.') from exc
        token_present = bool(get_token())
        login_valid = False
        if token_present:
            try:
                HfApi().whoami()
                login_valid = True
            except HfHubHTTPError as login_error:
                if getattr(login_error.response, 'status_code', None) != 401:
                    raise VoiceAccessError('Could not verify the Hugging Face login. Check the connection and retry.') from login_error
        raise VoiceAccessError(cloning_access_message(code, token_present, login_valid)) from None


def speech(job):
    import numpy as np
    import soundfile as sf
    import torch
    from pocket_tts import TTSModel
    # Pocket TTS sets this to one on import, so configure it afterwards.
    device = job.get('device', 'cpu')
    if device not in ('cpu', 'cuda'):
        raise ValueError('Choose CPU or NVIDIA GPU for speech generation.')
    if device == 'cuda' and not torch.cuda.is_available():
        raise ValueError('CUDA is unavailable. Choose CPU or install the GPU speech environment.')
    torch.set_num_threads(2 if device == 'cpu' else 1)
    started = time.perf_counter()
    lang = LANGUAGES[job['language']]
    status('Loading voice model · first use may download weights…')
    if job.get('reference'):
        status('Checking reference-voice model access…')
        prepare_cloning_weights(lang[1])
    model = TTSModel.load_model(language=lang[1]).to(device)
    status(f'Voice model loaded in {time.perf_counter()-started:.1f}s · {device.upper()} · float32')
    if job.get('reference') and not model.has_voice_cloning:
        raise VoiceAccessError('The cloning model could not be loaded. Check model access and try again.')
    with tempfile.TemporaryDirectory(prefix='orukeet-voice-') as temp:
        temp = Path(temp)
        reference = job.get('reference')
        if reference:
            status('Preparing reference voice…')
            cleaned = temp/'reference.wav'
            run(['ffmpeg','-v','error','-y','-i',reference,'-t','20','-ac','1','-ar','24000',str(cleaned)])
            state = model.get_state_for_audio_prompt(str(cleaned), truncate=True)
        else:
            state = model.get_state_for_audio_prompt(lang[2])
        output = Path(job['output'])
        output.parent.mkdir(parents=True, exist_ok=True)
        generation_started = time.perf_counter()
        if job['action'] == 'speech':
            status('Generating speech…')
            audio = model.generate_audio(state, job['text']).detach().cpu().numpy()
            sf.write(output, audio, model.sample_rate)
        else:
            segments = validate(job['segments'])
            if not segments:
                raise ValueError('Create captions before generating a dub.')
            rate = model.sample_rate
            duration = float(run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',job['media']]).strip())
            # Write incrementally so long recordings do not allocate a full waveform.
            # A line may run past its own end time into the silence before the next
            # caption: nothing is spoken there, so using it avoids needless speed-up.
            limits = [float(segments[i+1]['start']) if i+1 < len(segments) else max(duration, float(seg['end']))
                      for i, seg in enumerate(segments)]
            with sf.SoundFile(str(output), 'w', samplerate=rate, channels=1, subtype='PCM_16') as dest:
                for i, seg in enumerate(segments):
                    status(f'Dubbing caption {i+1} of {len(segments)}')
                    audio = model.generate_audio(state, seg['text']).detach().cpu().numpy()
                    window = limits[i] - seg['start']
                    spoken = len(audio) / rate
                    ratio = spoken / window
                    if ratio > 2:
                        raise ValueError(
                            f'Caption {i+1} needs {spoken:.1f}s of speech but only {window:.1f}s is free before '
                            f'caption {i+2} starts. Shorten its text or extend its end time; no speech was cut. '
                            f'Caption {i+1}: {seg["text"].strip()[:80]}'
                            if i+1 < len(segments) else
                            f'Caption {i+1} needs {spoken:.1f}s of speech but only {window:.1f}s remains in the '
                            f'media. Shorten its text or extend its end time; no speech was cut. '
                            f'Caption {i+1}: {seg["text"].strip()[:80]}')
                    if ratio > 1:
                        # Only a line that would overrun the next caption is compressed.
                        audio = filter_audio(audio, rate, f'atempo={ratio:.6f},apad,atrim=duration={window:.6f}')
                    target = round(seg['start']*rate)
                    while dest.tell() < target:
                        dest.write(np.zeros(min(rate, target-dest.tell()),dtype=np.float32))
                    dest.write(audio)
                while dest.tell() < round(duration*rate):
                    dest.write(np.zeros(min(rate,round(duration*rate)-dest.tell()),dtype=np.float32))
        elapsed = time.perf_counter() - generation_started
        status(f'Audio generated and written in {elapsed:.1f}s · {device.upper()}')
        return {'output':str(output), 'device':device, 'generation_seconds':elapsed}

def probe(path, entries, stream=None):
    args = ['ffprobe','-v','error']
    if stream:
        args += ['-select_streams', stream]
    return run(args + ['-show_entries',entries,'-of','default=noprint_wrappers=1:nokey=1',str(path)]).strip()

# Codecs an MP4 container holds directly, so the picture can be copied as-is.
MP4_VIDEO = ('h264', 'hevc', 'av1', 'mpeg4', 'vp9', 'mjpeg')

def mux(job):
    codec = probe(job['media'], 'stream=codec_name', 'v:0')
    if not codec:
        raise ValueError('That file has no video track. Choose a video in step 3, or export the WAV instead.')
    if codec in MP4_VIDEO:
        # Only the audio is being replaced, so copying the picture is both exact
        # and far faster than re-encoding it.
        status('Exporting video with the dubbed audio track…')
        video_args = ['-c:v','copy']
    else:
        status(f'Re-encoding {codec} video for MP4 · this takes a while…')
        video_args = ['-c:v','libx264','-preset','fast','-crf','20']
    run(['ffmpeg','-v','error','-y','-i',job['media'],'-i',job['audio'],'-map','0:v:0','-map','1:a:0']
        + video_args + ['-c:a','aac','-b:a','160k','-af','apad','-shortest','-movflags','+faststart',job['output']])
    return {'output':job['output']}

if __name__ == '__main__':
    try:
        job = json.loads(Path(sys.argv[1]).read_text())
        result = {'transcribe':transcribe,'translate':translate,'speech':speech,'dub':speech,'mux':mux}[job['action']](job)
        Path(sys.argv[2]).write_text(json.dumps(result,ensure_ascii=False,indent=2))
        status('Finished')
    except VoiceAccessError as exc:
        Path(sys.argv[2]).write_text(json.dumps({'error':str(exc)}))
        status(str(exc))
        sys.exit(1)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        status(str(exc))
        sys.exit(1)
