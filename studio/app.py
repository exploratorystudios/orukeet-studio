from pathlib import Path
import json, os, sys, uuid
from PySide6.QtCore import Qt, QProcess, QUrl, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QDesktopServices, QFont, QColor
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QFileDialog,QComboBox,QPlainTextEdit,QTableWidget,QTableWidgetItem,QHeaderView,QStackedWidget,QFrame,QProgressBar,QMessageBox,QSlider,QSplitter,QGraphicsOpacityEffect)
from PySide6.QtMultimedia import QMediaPlayer,QAudioOutput
from engine import ROOT, LANGUAGES, captions, parse_captions, validate, worker_python

STYLE = '''
QWidget { background:#10151e; color:#e7edf6; font-family:"DejaVu Sans"; font-size:14px; }
QMainWindow {background:#10151e;} QLabel { background:transparent; }
QFrame#sidebar { background:#0b1018; border-right:1px solid #263040; }
QLabel#brand {font-size:24px;font-weight:700;letter-spacing:1px;color:#fff;}
QLabel#eyebrow {color:#55d8c4;font-size:12px;font-weight:700;letter-spacing:2px;}
QLabel#title {font-size:30px;font-weight:700;}
QLabel#muted {color:#9aa9bd;} QLabel#section {font-size:17px;font-weight:600;}
QPushButton { background:#202b3c; border:1px solid #354156; padding:11px 17px;border-radius:8px; }
QPushButton:hover { background:#2b3d54; border-color:#6987a5; }
QPushButton:pressed {background:#354e64;}
QPushButton:disabled {color:#67758a;background:#19212e;border-color:#263040;}
QPushButton#primary {background:#52d5bd;color:#081d1a;border:none;font-weight:700;}
QPushButton#primary:hover {background:#7ee7d5;}
QPushButton#primary:disabled {background:#244d48;color:#92aaa4;}
QPushButton#nav {text-align:left;border:none;background:transparent;padding:15px;}
QPushButton#nav:checked {background:#1c3037;color:#68e1cf;border-left:3px solid #52d5bd;}
QPushButton#nav:hover {background:#1c2635;}
QPlainTextEdit,QTableWidget,QComboBox {background:#151e2b;border:1px solid #334155;border-radius:8px;padding:9px;selection-background-color:#28594f;}
QPlainTextEdit {font-size:16px;line-height:1.5;}
QComboBox {min-width:120px;padding:10px;}
QComboBox QAbstractItemView {background:#202b3c;selection-background-color:#28594f;}
QTableWidget {gridline-color:#263347;alternate-background-color:#192434;}
QHeaderView::section {background:#1c2838;color:#a9b8cc;border:0;padding:12px;text-align:left;}
QTableCornerButton::section {background:#1c2838;border:0;}
QProgressBar {background:#263040;border:none;border-radius:3px;max-height:5px;}
QProgressBar::chunk {background:#52d5bd;}
QSlider::groove:horizontal {background:#2b3a50;height:5px;border-radius:2px;}
QSlider::handle:horizontal {background:#63dfc8;width:14px;margin:-5px 0;border-radius:7px;}
QToolTip {background:#263347;color:#fff;border:1px solid #52677f;}
'''

def label(text, name=None):
    w=QLabel(text)
    if name:w.setObjectName(name)
    w.setWordWrap(True)
    return w

def button(text, callback, primary=False):
    b=QPushButton(text); b.clicked.connect(callback)
    if primary:b.setObjectName('primary')
    b.setCursor(Qt.PointingHandCursor)
    return b

class Studio(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Orukeet Studio');self.resize(1240,850);self.setMinimumSize(930,700)
        self.media='';self.video='';self.reference='';self.output='';self.audio_output='';self.project_path=None;self.last_backup=None;self.audio_stale=False;self.busy=False;self.dirty=False
        self.jobs=ROOT/'projects'/'.jobs';self.jobs.mkdir(exist_ok=True,parents=True)
        self.process=QProcess(self);self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_log);self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.process_error)
        root=QWidget();self.setCentralWidget(root);layout=QHBoxLayout(root);layout.setContentsMargins(0,0,0,0);layout.setSpacing(0)
        sidebar=QFrame();sidebar.setObjectName('sidebar');sidebar.setFixedWidth(220);side=QVBoxLayout(sidebar);side.setContentsMargins(22,32,22,24)
        side.addWidget(label('◒  orukeet','brand'));side.addWidget(label('AUDIO STUDIO','eyebrow'));side.addSpacing(36)
        self.nav=[]
        self.stack=QStackedWidget()
        self.fade_effect=QGraphicsOpacityEffect(self.stack);self.stack.setGraphicsEffect(self.fade_effect)
        self.fade=QPropertyAnimation(self.fade_effect,b'opacity',self);self.fade.setDuration(180);self.fade.setStartValue(.35);self.fade.setEndValue(1.0);self.fade.setEasingCurve(QEasingCurve.OutCubic)
        for index,title in enumerate(['01   Transcribe','02   Voice studio','03   Dubbing']):
            b=button(title,lambda checked=False,i=index:self.navigate(i));b.setObjectName('nav');b.setCheckable(True);side.addWidget(b);self.nav.append(b)
        side.addStretch();side.addWidget(label('ON YOUR COMPUTER','eyebrow'));side.addWidget(label('Orukeet · Pocket TTS\nArgos Translate','muted'));side.addSpacing(15)
        side.addWidget(button('Open project',self.open_project));side.addWidget(button('Save project',self.save_project));side.addWidget(button('Output folder',lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(ROOT/'exports')))))
        layout.addWidget(sidebar)
        content=QWidget();main=QVBoxLayout(content);main.setContentsMargins(30,26,30,22);main.setSpacing(18);layout.addWidget(content,1)
        top=QHBoxLayout();top.addWidget(label('WORKSPACE','eyebrow'));top.addStretch();privacy=label('●  Local processing','muted');privacy.setWordWrap(False);top.addWidget(privacy);main.addLayout(top)
        main.addWidget(self.stack,1)
        self.build_transcribe();self.build_voice();self.build_dub()
        self.status=label('Ready. Import audio or video to begin.','muted');self.progress=QProgressBar();self.progress.setTextVisible(False);self.progress.hide()
        main.addWidget(self.progress);main.addWidget(self.status)
        self.details=QPlainTextEdit();self.details.setReadOnly(True);self.details.setMaximumHeight(90);self.details.hide();main.addWidget(self.details)
        footer=QHBoxLayout();self.cancel=button('Cancel task',self.cancel_task);self.cancel.hide();footer.addWidget(self.cancel)
        footer.addStretch();footer.addWidget(button('Show / hide log',lambda:self.details.setVisible(not self.details.isVisible())));main.addLayout(footer)
        self.player=QMediaPlayer(self);self.audio=QAudioOutput(self);self.player.setAudioOutput(self.audio);self.audio.setVolume(.8)
        self.player.positionChanged.connect(self.position_changed);self.player.durationChanged.connect(lambda d:self.seek.setRange(0,d))
        self.player.errorOccurred.connect(lambda error,message:self.status.setText('Playback: '+message))
        self.navigate(0)
        self.autosave=QTimer(self);self.autosave.timeout.connect(self.auto_save);self.autosave.start(15000)

    def page(self,title,description):
        w=QWidget();v=QVBoxLayout(w);v.setContentsMargins(0,0,0,0);v.setSpacing(16)
        v.addWidget(label(title,'title'));v.addWidget(label(description,'muted'));self.stack.addWidget(w);return v

    def build_transcribe(self):
        v=self.page('Turn speech into a first draft.','Import a recording, transcribe locally, then refine and export your captions.')
        row=QHBoxLayout();self.import_btn=button('＋  Import media',self.import_media,True);row.addWidget(self.import_btn)
        self.file_label=label('No recording selected','muted');row.addWidget(self.file_label,1)
        self.transcribe_btn=button('Transcribe',self.transcribe,True);row.addWidget(self.transcribe_btn);v.addLayout(row)
        playback=QHBoxLayout();playback.addWidget(button('▶ / Ⅱ',self.play_pause));self.seek=QSlider(Qt.Horizontal);self.seek.sliderMoved.connect(lambda p:self.player.setPosition(p));playback.addWidget(self.seek,1);self.time=label('00:00','muted');playback.addWidget(self.time);v.addLayout(playback)
        v.addWidget(label('Caption editor','section'))
        self.empty_hint=label('Your transcript starts here. Import a recording above, or add captions manually.','muted');v.addWidget(self.empty_hint)
        self.table=QTableWidget(0,3);self.table.setHorizontalHeaderLabels(['Start · seconds','End · seconds','Caption text']);self.table.horizontalHeader().setSectionResizeMode(2,QHeaderView.Stretch);self.table.setColumnWidth(0,125);self.table.setColumnWidth(1,125);self.table.setWordWrap(True);self.table.setAlternatingRowColors(True);self.table.itemChanged.connect(self.captions_changed);self.table.cellDoubleClicked.connect(self.seek_caption);v.addWidget(self.table,1)
        row=QHBoxLayout();row.addWidget(button('＋ Caption',self.add_caption));row.addWidget(button('Remove selected',self.remove_caption));row.addStretch()
        row.addWidget(button('Import SRT / VTT',self.import_captions))
        for ext in ('srt','vtt','txt'):row.addWidget(button('Export '+ext.upper(),lambda checked=False,e=ext:self.export_captions(e)))
        v.addLayout(row);v.addWidget(label('Edit text or timing directly. Double-click a caption time to seek. Orukeet supports 25 languages; select the source language below when translating.','muted'))

    def build_voice(self):
        v=self.page('A voice for your next story.','Generate narration with a built-in voice or a short reference recording.')
        row=QHBoxLayout();row.addWidget(label('Spoken language'));self.voice_language=QComboBox();self.voice_language.addItems(LANGUAGES);row.addWidget(self.voice_language);row.addStretch();v.addLayout(row)
        row=QHBoxLayout();row.addWidget(label('Speech processor'));self.tts_device=QComboBox();self.tts_device.addItem('CPU','cpu');self.tts_device.addItem('NVIDIA GPU','cuda');self.tts_device.currentIndexChanged.connect(self.mark_dirty);row.addWidget(self.tts_device);row.addWidget(label('Also used for dubbing.','muted'));row.addStretch();v.addLayout(row)
        v.addWidget(label('Reference voice','section'));self.voice_label=label('Built-in voice · no reference selected','muted');v.addWidget(self.voice_label)
        row=QHBoxLayout();row.addWidget(button('Choose reference audio',self.choose_voice));row.addWidget(button('Use built-in voice',self.clear_voice));row.addStretch();v.addLayout(row)
        v.addWidget(label('Use a clean, single-speaker recording of a voice you have permission to use. The first 20 seconds are used; the reference is shared with Dubbing.','muted'))
        v.addWidget(label('Reference cloning requires access to the Pocket TTS model. Accept its terms, then sign in locally. Built-in voices work without an account.','muted'))
        access=QHBoxLayout();access.addWidget(button('1 · Model access',lambda:QDesktopServices.openUrl(QUrl('https://huggingface.co/kyutai/pocket-tts'))));access.addWidget(button('2 · Sign in locally',lambda:QProcess.startDetached(sys.executable,[str(ROOT/'studio'/'auth.py')])));access.addStretch();v.addLayout(access)
        v.addWidget(label('Script','section'));self.script=QPlainTextEdit();self.script.setPlaceholderText('Write the words you want to bring to life…');self.script.textChanged.connect(self.mark_dirty);v.addWidget(self.script,1)
        row=QHBoxLayout();self.generate_btn=button('Generate voice',self.generate,True);row.addWidget(self.generate_btn);row.addStretch();row.addWidget(button('Play latest output',self.play_output));v.addLayout(row)
        v.addWidget(label('Pocket TTS · English, French, German, Spanish, Italian and Portuguese. New language models download on first use.','muted'))

    def build_dub(self):
        v=self.page('Take your story across languages.','Translate your edited captions, then generate speech aligned to their timing.')
        v.addWidget(label('1   Translate captions','section'));row=QHBoxLayout();self.source_language=QComboBox();self.target_language=QComboBox()
        # Orukeet source languages; translation package availability is checked per pair.
        self.source_codes={'English':'en','French':'fr','German':'de','Spanish':'es','Italian':'it','Portuguese':'pt','Dutch':'nl','Polish':'pl','Russian':'ru','Ukrainian':'uk','Czech':'cs','Danish':'da','Finnish':'fi','Greek':'el','Hungarian':'hu','Romanian':'ro','Swedish':'sv','Turkish':'tr','Bulgarian':'bg','Croatian':'hr','Estonian':'et','Latvian':'lv','Lithuanian':'lt','Slovak':'sk','Slovenian':'sl'}
        self.source_language.addItems(self.source_codes);self.target_language.addItems(LANGUAGES);self.target_language.setCurrentText('Spanish')
        row.addWidget(label('From'));row.addWidget(self.source_language);row.addWidget(label('To'));row.addWidget(self.target_language);row.addStretch();self.translate_btn=button('Translate captions',self.translate,True);row.addWidget(self.translate_btn);v.addLayout(row)
        v.addWidget(label('Translation replaces the editable captions and saves a backup first. Missing language packs download automatically. Review the wording before dubbing.','muted'))
        v.addSpacing(15);v.addWidget(label('2   Create a timed voice track','section'))
        self.dub_voice=label('Voice: built-in voice. Choose a reference in Voice studio to clone a voice.','muted');v.addWidget(self.dub_voice)
        v.addWidget(label('The target language above is used for speech. Each line starts at its caption time. Long lines are sped up by at most 2×; lines that still do not fit must be edited.','muted'))
        self.dub_btn=button('Generate dubbed WAV',self.dub,True);v.addWidget(self.dub_btn)
        v.addSpacing(15);v.addWidget(label('3   Export your video','section'));v.addWidget(label('Creates an MP4 using your original video and the new voice track. This replaces the original audio, including background music. The picture is copied rather than re-encoded, so the export is quick and loses no quality.','muted'))
        self.video_label=label('','muted');v.addWidget(self.video_label)
        row=QHBoxLayout();self.video_btn=button('Choose video',self.choose_video);row.addWidget(self.video_btn);self.video_clear_btn=button('Use imported media',self.clear_video);row.addWidget(self.video_clear_btn);row.addStretch();v.addLayout(row)
        self.update_video()
        row=QHBoxLayout();self.mux_btn=button('Export dubbed video',self.export_video);row.addWidget(self.mux_btn);row.addWidget(button('Play latest output',self.play_output));row.addStretch();v.addLayout(row);v.addStretch()

    def navigate(self,index):
        self.stack.setCurrentIndex(index)
        self.fade.stop();self.fade.start()
        for i,b in enumerate(self.nav):b.setChecked(i==index)
    def captions_changed(self,*args):
        self.audio_stale=bool(self.audio_output);self.empty_hint.setVisible(self.table.rowCount()==0);self.update_video();self.mark_dirty()
    def mark_dirty(self,*args):self.dirty=True
    def show_error(self,message):QMessageBox.warning(self,'Orukeet Studio',str(message))
    def choose_file(self,title):return QFileDialog.getOpenFileName(self,title,str(Path.home()),'Media (*.wav *.mp3 *.flac *.m4a *.ogg *.opus *.mp4 *.mkv *.mov *.webm);;All files (*)')[0]
    def import_media(self):
        path=self.choose_file('Import audio or video')
        if not path:return
        if self.table.rowCount():
            self.backup('before-import');self.table.setRowCount(0)
        self.media=path;self.audio_output='';self.audio_stale=False;self.output='';self.file_label.setText(Path(path).name);self.update_video();self.player.setSource(QUrl.fromLocalFile(path));self.mark_dirty()
    def choose_voice(self):
        path=self.choose_file('Choose reference audio')
        if path:self.reference=path;self.update_voice();self.mark_dirty()
    def clear_voice(self):self.reference='';self.update_voice();self.mark_dirty()
    def choose_video(self):
        path=QFileDialog.getOpenFileName(self,'Choose video to dub',str(Path.home()),'Video (*.mp4 *.mkv *.mov *.webm *.avi);;All files (*)')[0]
        if path:self.video=path;self.update_video();self.mark_dirty()
    def clear_video(self):self.video='';self.update_video();self.mark_dirty()
    def update_video(self):
        if self.video:text='Video: '+Path(self.video).name
        elif self.media:text='Video: '+Path(self.media).name+' · the media imported in Transcribe'
        else:text='No video selected. Import media in Transcribe, or choose a video here.'
        if not self.audio_output:text+='\nVoice track: none yet · generate the dubbed WAV in step 2.'
        elif self.audio_stale:text+='\nVoice track: '+Path(self.audio_output).name+' · captions changed since it was generated.'
        else:text+='\nVoice track: '+Path(self.audio_output).name
        self.video_label.setText(text)
    def update_voice(self):
        text=Path(self.reference).name if self.reference else 'Built-in voice · no reference selected'
        self.voice_label.setText(text);self.dub_voice.setText('Reference voice: '+text)
    def play_pause(self):
        if self.player.playbackState()==QMediaPlayer.PlayingState:self.player.pause()
        else:self.player.play()
    def play_output(self):
        if self.output:QDesktopServices.openUrl(QUrl.fromLocalFile(self.output))
        else:self.show_error('Generate a voice or dub first.')
    def position_changed(self,p):
        if not self.seek.isSliderDown():self.seek.setValue(p)
        self.time.setText(f'{p//60000:02}:{p//1000%60:02}')
    def seek_caption(self,row,col):
        if col<2:
            try:self.player.setPosition(int(float(self.table.item(row,0).text())*1000))
            except (ValueError,AttributeError):pass
    def get_segments(self):
        segments=[]
        for row in range(self.table.rowCount()):
            values=[self.table.item(row,col).text() if self.table.item(row,col) else '' for col in range(3)]
            segments.append({'start':float(values[0]),'end':float(values[1]),'text':values[2]})
        return validate(segments)
    def set_segments(self,segments):
        self.table.setRowCount(0)
        for seg in segments:
            row=self.table.rowCount();self.table.insertRow(row)
            for col,key in enumerate(('start','end','text')):self.table.setItem(row,col,QTableWidgetItem(str(seg[key])))
            self.table.setRowHeight(row,64)
    def add_caption(self):
        try:
            segments=self.get_segments();end=segments[-1]['end'] if segments else 0
            segments.append({'start':end,'end':end+3,'text':'New caption'});self.set_segments(segments)
        except Exception as exc:self.show_error(exc)
    def remove_caption(self):
        for row in sorted({i.row() for i in self.table.selectedIndexes()},reverse=True):self.table.removeRow(row)
        self.captions_changed()
    def snapshot(self):return {'version':1,'tts_device':self.tts_device.currentData(),'media':self.media,'video':self.video,'segments':self.get_segments(),'reference':self.reference,'script':self.script.toPlainText(),'voice_language':self.voice_language.currentText(),'source_language':self.source_language.currentText(),'target_language':self.target_language.currentText(),'audio_output':self.audio_output,'output':self.output}
    def backup(self,prefix):
        path=ROOT/'projects'/(prefix+'-'+uuid.uuid4().hex[:8]+'.orukeet');self.write_project(path);self.last_backup=path;return path
    def write_project(self,path):
        data=self.snapshot();path=Path(path);temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data,ensure_ascii=False,indent=2));temp.replace(path)
    def auto_save(self):
        if not self.dirty:return
        try:self.write_project(ROOT/'projects'/'autosave.orukeet');self.dirty=False
        except (ValueError,OSError):pass
    def save_project(self):
        path=QFileDialog.getSaveFileName(self,'Save project',str(ROOT/'projects'/'Untitled.orukeet'),'Orukeet project (*.orukeet)')[0]
        if path:
            try:self.write_project(path);self.status.setText('Project saved.');self.dirty=False
            except Exception as exc:self.show_error(exc)
    def open_project(self):
        if self.busy:return
        path=QFileDialog.getOpenFileName(self,'Open project',str(ROOT/'projects'),'Orukeet project (*.orukeet)')[0]
        if path:
            try:
                data=json.loads(Path(path).read_text());validate(data['segments']);self.auto_save()
                self.media=data.get('media','');self.video=data.get('video','');self.reference=data.get('reference','');self.set_segments(data['segments']);self.script.setPlainText(data.get('script',''));self.update_voice();self.update_video();self.file_label.setText(Path(self.media).name);self.player.setSource(QUrl.fromLocalFile(self.media))
                for key in ('voice_language','source_language','target_language'):getattr(self,key).setCurrentText(data.get(key,'English'))
                self.tts_device.setCurrentIndex(max(0,self.tts_device.findData(data.get('tts_device','cpu'))))
                self.output=data.get('output','');self.audio_output=data.get('audio_output','');self.status.setText('Project loaded.');self.mark_dirty()
            except Exception as exc:self.show_error(exc)
    def import_captions(self):
        path=QFileDialog.getOpenFileName(self,'Import captions',str(ROOT/'exports'),'Subtitles (*.srt *.vtt);;All files (*)')[0]
        if not path:return
        try:
            segments=parse_captions(Path(path).read_text(encoding='utf-8-sig'))
            if self.table.rowCount():self.backup('before-captions')
            self.set_segments(segments);self.status.setText(f'{len(segments)} captions imported from '+Path(path).name);self.mark_dirty()
        except Exception as exc:self.show_error(exc)
    def export_captions(self,ext):
        try:
            segments=self.get_segments()
            if not segments:raise ValueError('Create captions first.')
            path=QFileDialog.getSaveFileName(self,'Export captions',str(ROOT/'exports'/('captions.'+ext)),ext.upper()+' (*.'+ext+')')[0]
            if path:Path(path).write_text('\n'.join(s['text'] for s in segments) if ext=='txt' else captions(segments,ext=='vtt'));self.status.setText('Captions exported.')
        except Exception as exc:self.show_error(exc)
    def launch_job(self,job):
        if self.busy:return
        if job['action'] in ('speech','dub'):job=dict(job,device=self.tts_device.currentData())
        try:python=worker_python(job)
        except ValueError as exc:return self.show_error(exc)
        self.busy=True;self.current_job=job;self.log='';self.details.clear();self.result_file=self.jobs/(uuid.uuid4().hex+'.result.json');request=self.result_file.with_suffix('.request.json');request.write_text(json.dumps(job));self.progress.setRange(0,0);self.progress.show();self.cancel.show();self.status.setText('Starting…')
        self.set_controls(False);self.process.setWorkingDirectory(str(ROOT));self.process.start(python,[str(ROOT/'studio'/'engine.py'),str(request),str(self.result_file)])
    def set_controls(self,enabled):
        self.stack.setEnabled(enabled)
        for w in (self.import_btn,self.transcribe_btn,self.generate_btn,self.translate_btn,self.dub_btn,self.video_btn,self.video_clear_btn,self.mux_btn,self.table,self.script,self.voice_language,self.source_language,self.target_language):w.setEnabled(enabled)
    def read_log(self):
        chunk=bytes(self.process.readAllStandardOutput()).decode(errors='replace');self.log+=chunk;self.details.appendPlainText(chunk.strip())
        for line in chunk.splitlines():
            if line.startswith('STUDIO:'):self.status.setText(line[7:])
    def process_error(self,error):
        if error==QProcess.FailedToStart:self.finished(1,QProcess.CrashExit)
    def finished(self,code,exit_status):
        self.read_log();self.busy=False;self.set_controls(True);self.progress.hide();self.cancel.hide()
        if code or not self.result_file.exists():
            message='Task stopped. Your project is preserved. See the log for details.'
            if self.result_file.exists():
                try:message=json.loads(self.result_file.read_text()).get('error',message)
                except (ValueError,OSError):pass
            self.status.setText(message);self.details.show();return
        try:
            data=json.loads(self.result_file.read_text());action=self.current_job['action']
            if 'segments' in data:self.set_segments(data['segments']);self.navigate(0)
            # The captions now hold the target language, so that becomes the source
            # of any further translation.
            if action=='translate':self.source_language.setCurrentText(self.target_language.currentText())
            if 'output' in data:
                self.output=data['output']
                if action=='dub':self.audio_output=self.output;self.audio_stale=False
            self.update_video()
            if action=='translate':
                message=f'Captions are now in {self.target_language.currentText()}. Original saved as '+(self.last_backup.name if self.last_backup else 'a before-translation project')+'.'
            else:
                message='Finished · '+(Path(self.output).name if 'output' in data else f'{self.table.rowCount()} captions ready to edit.')
            self.status.setText(message);self.mark_dirty();self.auto_save()
        except Exception as exc:self.show_error(exc)
    def cancel_task(self):self.process.kill()
    def transcribe(self):
        if not Path(self.media).is_file():return self.show_error('Import an audio or video file first.')
        self.auto_save();self.launch_job({'action':'transcribe','media':self.media})
    def translate(self):
        try:
            segments=self.get_segments()
            if not segments:raise ValueError('Transcribe a recording or add captions first.')
            if self.source_language.currentText()==self.target_language.currentText():
                raise ValueError('From and To are both '+self.source_language.currentText()+'. The captions were already translated into '
                                 +self.target_language.currentText()+'; choose a different target language, or use Open project on the latest '
                                 'before-translation file to restore the original captions.')
            self.backup('before-translation')
            self.launch_job({'action':'translate','segments':segments,'source':self.source_codes[self.source_language.currentText()],'target':LANGUAGES[self.target_language.currentText()][0]})
        except Exception as exc:self.show_error(exc)
    def output_path(self,name,ext='wav'):return str(ROOT/'exports'/(name+'-'+uuid.uuid4().hex[:8]+'.'+ext))
    def generate(self):
        text=self.script.toPlainText().strip()
        if not text:return self.show_error('Write a script first.')
        self.launch_job({'action':'speech','language':self.voice_language.currentText(),'reference':self.reference,'text':text,'output':self.output_path('voice')})
    def dub(self):
        try:
            segments=self.get_segments()
            if not segments or not Path(self.media).is_file():raise ValueError('Import media and prepare captions first.')
            self.launch_job({'action':'dub','language':self.target_language.currentText(),'reference':self.reference,'media':self.media,'segments':segments,'output':self.output_path('dub')})
        except Exception as exc:self.show_error(exc)
    def export_video(self):
        if not self.audio_output:return self.show_error('There is no voice track yet. Use Generate dubbed WAV in step 2 first.')
        if not Path(self.audio_output).is_file():return self.show_error('The voice track '+Path(self.audio_output).name+' is no longer in exports. Generate the dubbed WAV again.')
        video=self.video or self.media
        if not Path(video).is_file():return self.show_error('Choose the video you want to dub first.')
        if self.audio_stale and QMessageBox.question(self,'Orukeet Studio','The captions changed after '+Path(self.audio_output).name+' was generated, so the voice track does not match them.\n\nExport with this older voice track anyway?')!=QMessageBox.Yes:
            return
        self.launch_job({'action':'mux','media':video,'audio':self.audio_output,'output':self.output_path('dubbed-video','mp4')})
    def closeEvent(self,event):
        if self.busy:
            self.show_error('Cancel the running task before closing the studio.');event.ignore();return
        self.auto_save();event.accept()

if __name__=='__main__':
    app=QApplication(sys.argv);app.setApplicationName('Orukeet Studio');app.setStyle('Fusion');app.setStyleSheet(STYLE)
    window=Studio();window.show();sys.exit(app.exec())
