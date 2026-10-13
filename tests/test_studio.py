import os, sys
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'studio'))
import pytest
from engine import captions,validate,stamp

def test_subtitle_formats():
    segments=[{'start':59.9996,'end':62,'text':'Hello → world'}]
    assert stamp(59.9996)=='00:01:00,000'
    assert '00:01:00,000 --> 00:01:02,000' in captions(segments)
    assert captions(segments,True).startswith('WEBVTT\n\n1\n00:01:00.000')

@pytest.mark.parametrize('segments',[[{'start':-1,'end':1,'text':'A'}],[{'start':0,'end':float('nan'),'text':'A'}],[{'start':1,'end':0,'text':'A'}],[{'start':0,'end':1,'text':''}],[{'start':0,'end':2,'text':'A'},{'start':1,'end':3,'text':'B'}]])
def test_invalid_captions(segments):
    with pytest.raises(ValueError):validate(segments)

def test_project_roundtrip(tmp_path):
    from app import QApplication, Studio
    app=QApplication.instance() or QApplication([])
    w=Studio();w.autosave.stop()
    segments=[{'start':0.2,'end':2.5,'text':'Café, 世界'}]
    w.set_segments(segments);w.script.setPlainText('Test narration')
    path=tmp_path/'test.orukeet';w.write_project(path)
    import json
    data=json.loads(path.read_text())
    assert data['segments']==segments
    assert data['script']=='Test narration'
    w.navigate(2);assert w.nav[2].isChecked()
    w.dirty=False;w.close()

@pytest.mark.parametrize('code,token,valid,expected',[
    (401,False,False,'needs a Hugging Face login'),
    (401,True,False,'rejected the saved credential'),
    (403,True,True,'account or token cannot download'),
])
def test_cloning_access_diagnostics(code,token,valid,expected):
    from engine import cloning_access_message
    assert expected in cloning_access_message(code,token,valid)

def test_caption_import_roundtrip():
    from engine import parse_captions
    segments=[{'start':1.0,'end':3.5,'text':'Hola, hola Juanjo.'},{'start':4.0,'end':6.0,'text':'Café 世界'}]
    assert parse_captions(captions(segments))==segments
    assert parse_captions(captions(segments,True))==segments

def test_caption_import_tolerates_real_files():
    from engine import parse_captions
    srt='﻿1\r\n00:00:01,000 --> 00:00:03,500\r\nHello there\r\nsecond line\r\n\r\n2\r\n00:00:04,000 --> 00:00:06,000\r\nBye\r\n'
    assert parse_captions(srt)==[{'start':1.0,'end':3.5,'text':'Hello there second line'},{'start':4.0,'end':6.0,'text':'Bye'}]
    vtt='WEBVTT\n\n00:01.000 --> 00:03.000 align:start position:50%\nCue settings ignored\n'
    assert parse_captions(vtt)==[{'start':1.0,'end':3.0,'text':'Cue settings ignored'}]

@pytest.mark.parametrize('text',['','notes with no timings','1\n00:00:02,000 --> 00:00:01,000\nBackwards\n'])
def test_caption_import_rejects_bad_files(text):
    from engine import parse_captions
    with pytest.raises(ValueError):parse_captions(text)

def test_translate_refuses_identical_languages(monkeypatch):
    from app import QApplication, Studio
    app=QApplication.instance() or QApplication([])
    w=Studio();w.autosave.stop()
    w.set_segments([{'start':0.0,'end':2.0,'text':'Already translated'}])
    w.source_language.setCurrentText('English');w.target_language.setCurrentText('English')
    launched=[];errors=[]
    monkeypatch.setattr(w,'launch_job',lambda job:launched.append(job))
    monkeypatch.setattr(w,'show_error',lambda message:errors.append(str(message)))
    w.translate()
    assert not launched
    assert 'before-translation' in errors[0]
    w.dirty=False;w.close()

def test_translate_pins_float32_compute_type(monkeypatch):
    """Argos' 'auto' selects int8 on avx2 CPUs, which decodes some packages to junk."""
    import argostranslate.settings as argos_settings
    import engine
    monkeypatch.setattr(argos_settings,'compute_type','auto',raising=False)
    with pytest.raises(ValueError):
        engine.translate({'segments':[],'source':'es','target':'es'})
    assert argos_settings.compute_type=='float32'

def test_mux_copies_compatible_video(monkeypatch):
    import engine
    calls=[]
    monkeypatch.setattr(engine,'probe',lambda *a,**k:'h264')
    monkeypatch.setattr(engine,'run',lambda args:calls.append(args) or '')
    engine.mux({'media':'in.mp4','audio':'dub.wav','output':'out.mp4'})
    assert ['-c:v','copy']==[calls[0][i] for i in range(len(calls[0])) if calls[0][i] in ('-c:v','copy')]
    assert 'libx264' not in calls[0]

def test_mux_reencodes_incompatible_video(monkeypatch):
    import engine
    calls=[]
    monkeypatch.setattr(engine,'probe',lambda *a,**k:'theora')
    monkeypatch.setattr(engine,'run',lambda args:calls.append(args) or '')
    engine.mux({'media':'in.ogv','audio':'dub.wav','output':'out.mp4'})
    assert 'libx264' in calls[0]

def test_mux_rejects_audio_only_source(monkeypatch):
    import engine
    monkeypatch.setattr(engine,'probe',lambda *a,**k:'')
    with pytest.raises(ValueError):
        engine.mux({'media':'voice.wav','audio':'dub.wav','output':'out.mp4'})

@pytest.mark.parametrize('action', ['speech', 'dub', 'transcribe', 'translate', 'mux'])
def test_worker_environment_routing(monkeypatch, tmp_path, action):
    import engine
    monkeypatch.setattr(engine, 'ROOT', tmp_path)
    gpu_python = tmp_path / '.venv-tts-gpu' / 'bin' / 'python'
    gpu_python.parent.mkdir(parents=True)
    gpu_python.touch()
    assert engine.worker_python({'action': action, 'device': 'cpu'}) == sys.executable
    assert engine.worker_python({'action': action, 'device': 'cuda'}) == (
        str(gpu_python) if action in ('speech', 'dub') else sys.executable)


def test_missing_gpu_environment_has_actionable_error(monkeypatch, tmp_path):
    import engine
    monkeypatch.setattr(engine, 'ROOT', tmp_path)
    with pytest.raises(ValueError, match='setup-tts-gpu.sh'):
        engine.worker_python({'action': 'speech', 'device': 'cuda'})


def test_speech_rejects_unavailable_cuda_before_loading(monkeypatch):
    import engine
    import torch
    monkeypatch.setattr(torch.cuda, 'is_available', lambda: False)
    with pytest.raises(ValueError, match='CUDA is unavailable'):
        engine.speech({'action': 'speech', 'device': 'cuda'})


def test_speech_processor_saved_in_project():
    from app import QApplication, Studio
    app = QApplication.instance() or QApplication([])
    w = Studio(); w.autosave.stop()
    w.tts_device.setCurrentIndex(w.tts_device.findData('cuda'))
    assert w.snapshot()['tts_device'] == 'cuda'
    w.dirty = False; w.close()
