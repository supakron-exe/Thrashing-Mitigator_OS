"""Regression: client controls must remain clickable on negative-coordinate monitors."""
import ctypes
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vendor'))
from qa_support import QA_ROOT, qa_path
import FluentUI.FluFrameless as frame

@unittest.skipUnless(sys.platform=='win32','Windows native frame')
class NativeFrameTests(unittest.TestCase):
    def hit(self,origin,local,size=(1180,740)):
        message=frame.MSG()
        message.hWnd=7;message.message=0x84
        x,y=origin[0]+local[0],origin[1]+local[1]
        message.lParam=(x&0xffff)|((y&0xffff)<<16)
        window=SimpleNamespace(_current=7,_isWindows11OrGreater=False,_margins=8,_fixSize=False,
            _isFullScreen=lambda:False,_isMaximized=lambda:False,_hitAppBar=lambda:False)
        def screen_to_client(hwnd,pointer):
            point=ctypes.cast(pointer,ctypes.POINTER(frame.POINT)).contents
            point.x-=origin[0];point.y-=origin[1]
            return True
        def client_rect(hwnd,pointer):
            rectangle=ctypes.cast(pointer,ctypes.POINTER(frame.RECTL)).contents
            rectangle.left=rectangle.top=0;rectangle.right=size[0];rectangle.bottom=size[1]
            return True
        with patch.object(frame,'ScreenToClient',screen_to_client),patch.object(frame,'GetClientRect',client_rect):
            return frame.FluFrameless.nativeEventFilter(window,frame.qtNativeEventType,ctypes.addressof(message))

    def test_client_area_on_primary_left_and_upper_monitors(self):
        for origin in ((200,100),(-1920,0),(0,-1080),(-1920,-1080)):
            for point in ((40,180),(380,320),(900,500)):
                with self.subTest(origin=origin,point=point):self.assertEqual(self.hit(origin,point),(True,1))

    def test_resize_edges_and_corners_still_work(self):
        points=[((1,300),10),((1179,300),11),((400,1),12),((400,739),15),
                ((1,1),13),((1179,1),14),((1,739),16),((1179,739),17)]
        for origin in ((0,0),(-1920,-1080)):
            for point,expected in points:
                with self.subTest(origin=origin,point=point):self.assertEqual(self.hit(origin,point),(True,expected))

if __name__=='__main__':unittest.main()
