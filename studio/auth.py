"""Local token-entry window. Credentials never enter job files or command arguments."""
import sys
from PySide6.QtCore import QThread, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication,QDialog,QVBoxLayout,QLabel,QLineEdit,QPushButton

class LoginWorker(QThread):
    result=Signal(bool,str)
    def __init__(self,token,parent=None):
        super().__init__(parent);self.token=token
    def run(self):
        try:
            from huggingface_hub import login
            from huggingface_hub.utils import logging
            logging.set_verbosity_error()
            login(token=self.token,add_to_git_credential=False,skip_if_logged_in=False)
            self.result.emit(True,'Signed in. You can close this window and retry voice generation in Studio.')
        except Exception as exc:
            code=getattr(getattr(exc,'response',None),'status_code',None)
            message=('Hugging Face rejected this token. Copy a valid personal read token and try again.'
                     if code in (401,403) or isinstance(exc,ValueError)
                     else 'Sign-in could not complete. Check your internet connection and try again.')
            self.result.emit(False,message)
        finally:
            self.token=''

class LoginDialog(QDialog):
    def __init__(self):
        super().__init__();self.worker=None
        self.setWindowTitle('Orukeet Studio · Hugging Face sign-in');self.setMinimumWidth(530)
        layout=QVBoxLayout(self);layout.setContentsMargins(28,28,28,28);layout.setSpacing(18)
        title=QLabel('Connect your Hugging Face account');title.setStyleSheet('font-size:20px;font-weight:700');layout.addWidget(title)
        note=QLabel('Paste your personal read token below. It is sent to Hugging Face for verification and saved locally by its official client.');note.setWordWrap(True);layout.addWidget(note)
        layout.addWidget(QLabel('Hugging Face token'))
        self.entry=QLineEdit();self.entry.setEchoMode(QLineEdit.Password);self.entry.setPlaceholderText('Paste your hf_… token here');self.entry.setAccessibleName('Hugging Face token');layout.addWidget(self.entry)
        self.submit=QPushButton('Sign in');self.submit.clicked.connect(self.start_login);self.entry.returnPressed.connect(self.start_login);layout.addWidget(self.submit)
        self.status=QLabel('');self.status.setWordWrap(True);layout.addWidget(self.status)
        terms=QPushButton('Open Pocket TTS model terms');terms.clicked.connect(lambda:QDesktopServices.openUrl(QUrl('https://huggingface.co/kyutai/pocket-tts')));layout.addWidget(terms)
        self.entry.setFocus()
    def start_login(self):
        if self.worker and self.worker.isRunning():return
        token=self.entry.text().strip()
        if not token.startswith('hf_'):
            self.status.setText('Paste a Hugging Face personal token beginning with hf_.');return
        self.entry.clear();self.entry.setEnabled(False);self.submit.setEnabled(False);self.status.setText('Verifying and saving your login…')
        self.worker=LoginWorker(token,self);self.worker.result.connect(self.show_result);self.worker.start()
    def show_result(self,success,message):
        self.status.setText(message);self.entry.setEnabled(not success);self.submit.setEnabled(not success)
    def closeEvent(self,event):
        if self.worker and self.worker.isRunning():event.ignore()
        else:event.accept()
    def reject(self):
        if not self.worker or not self.worker.isRunning():super().reject()

if __name__=='__main__':
    app=QApplication(sys.argv);app.setStyle('Fusion')
    app.setStyleSheet('QWidget{background:#10151e;color:#e7edf6;font-size:14px;} QLineEdit{background:#202b3c;border:1px solid #52677f;padding:12px;border-radius:6px;} QPushButton{background:#28594f;border:1px solid #52d5bd;padding:12px;border-radius:6px;} QPushButton:disabled{color:#8996a8;}')
    dialog=LoginDialog();dialog.show();sys.exit(app.exec())
