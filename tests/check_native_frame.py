"""Real Windows hit tests and Qt pointer clicks on the current application's window."""
import ctypes
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from qa_support import QA_ROOT, qa_path
from PySide6.QtCore import QObject,QPointF,Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtQuick import QQuickWindow,QSGRendererInterface
from PySide6.QtTest import QTest
from main import create_engine,dispose_engine
from backend.settings import SettingsController

QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.OpenGL)
app=QApplication([]);app.setQuitOnLastWindowClosed(False)
(QA_ROOT/'profiles'/'native-frame').mkdir(parents=True,exist_ok=True)
profile=tempfile.TemporaryDirectory(dir=QA_ROOT/'profiles'/'native-frame')
settings=SettingsController('light',Path(profile.name)/'settings.json');settings.setAnimations(False)
engine,memory,settings=create_engine(app,settings=settings)
def pump():
    end=time.monotonic()+.2
    while time.monotonic()<end:app.processEvents();time.sleep(.002)
pump()
window=next(w for w in app.allWindows() if w.objectName()=='mainWindow')
button=window.findChild(QObject,'themeToggle')
user32=ctypes.WinDLL('user32',use_last_error=True)
from ctypes.wintypes import POINT,RECT
user32.ClientToScreen.argtypes=[ctypes.c_void_p,ctypes.POINTER(POINT)]
user32.GetClientRect.argtypes=[ctypes.c_void_p,ctypes.POINTER(RECT)]
user32.SendMessageW.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_size_t,ctypes.c_ssize_t]
user32.SendMessageW.restype=ctypes.c_ssize_t
def hit(x,y):
    point=POINT(x,y);assert user32.ClientToScreen(window.winId(),ctypes.byref(point))
    return user32.SendMessageW(window.winId(),0x84,0,(point.x&0xffff)|((point.y&0xffff)<<16)),[point.x,point.y]
reports=[]
try:
    for position in ((100,100),(-1500,100),(100,-650),(-1500,-650)):
        window.setPosition(*position);pump()
        scene=button.mapToScene(QPointF(button.width()/2,button.height()/2))
        result,screen=hit(round(scene.x()*window.devicePixelRatio()),round(scene.y()*window.devicePixelRatio()))
        assert result==1,(position,screen,result)
        before=settings.theme
        QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,scene.toPoint());pump()
        assert settings.theme!=before,(position,'pointer click did not reach the button')
        rect=RECT();assert user32.GetClientRect(window.winId(),ctypes.byref(rect))
        bottom,_=hit(rect.right//2,rect.bottom-1);assert bottom==15,bottom
        left,_=hit(1,rect.bottom//2);assert left==10,left
        reports.append(dict(position=list(position),screenPoint=screen,clientHit=result,buttonClicked=True,bottomHit=bottom,leftHit=left))
finally:dispose_engine(app,engine,memory);profile.cleanup()
report=dict(passed=True,cases=reports)
(QA_ROOT/'insights_visual'/'native_frame.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
