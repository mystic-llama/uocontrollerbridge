"""Regression cases for single assignments, phantom bumpers, and native mouse edges."""
import copy
import ctypes
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import controller_bridge as bridge
import app_services as services
from input_validation import mapping_issues
import test_public as public

class PhysicalInputTests(unittest.TestCase):
    def test_stick_deflection_cannot_be_learned_as_bumper(self):
        before={'axes':[0.,0.,0.,0.],'buttons':[False]*8,'hats':[]}
        current=copy.deepcopy(before);current['axes'][2]=.9
        self.assertIsNone(services.detect_source(before,current))
        self.assertEqual(services.detect_source(before,current,axis_only=True),{'axis':2,'rest':0.,'full':1.})
    def test_two_pressed_buttons_are_not_silently_resolved_to_first_id(self):
        before={'axes':[0.,0.],'buttons':[False]*8,'hats':[]}
        current=copy.deepcopy(before);current['buttons'][4]=current['buttons'][6]=True
        self.assertIsNone(services.detect_source(before,current))
    def test_digital_trigger_wins_over_incidental_axis_motion(self):
        before={'axes':[0.,0.,0.,0.],'buttons':[False]*8,'hats':[]}
        current=copy.deepcopy(before);current['buttons'][6]=True;current['axes'][2]=.9
        self.assertEqual(services.detect_source(before,current,prefer_axis=True),{'button':6})
    def test_mouse_trigger_hold_does_not_fire_bad_cursor_axis_bumper(self):
        cfg=public.config();cfg['layers']=[{'name':'base','modifiers':[],'bindings':{'lt':{'action':'mouse_left'},'lb':{'action':'pet_all_follow_me'}}}]
        engine=public.RecordedEngine();mouse=public.RecordedMouse();desktop=types.SimpleNamespace(mouse=mouse,mouse_module=types.SimpleNamespace(Button=types.SimpleNamespace(left='left',right='right')))
        output=bridge.OutputRouter(cfg,engine,desktop);mapper=bridge.InputMapper(cfg,output);joy=public.FakeJoy()
        preset={'controls':{'lt':{'button':0},'lb':{'axis':2,'rest':0.,'full':1.}},'left_stick':[0,1],'right_stick':[2,3]}
        clock=[1.]
        def poll():clock[0]+=.1;return mapper.poll(joy,preset,clock[0],True,True)
        with patch.object(bridge.time,'monotonic',lambda:clock[0]):
            poll();joy.buttons[0]=True;poll();poll();joy.axes[2]=.9
            for _ in range(30):self.assertGreater(poll()[0],0.)
            self.assertEqual(mouse.pressed,['left']);self.assertFalse(mouse.released);self.assertFalse(engine.actions)
            self.assertIn('lb',mapper.mapping_issues);self.assertEqual(output.last_input['control'],'lt')
            joy.buttons[0]=False;poll();poll();self.assertEqual(mouse.released,['left'])
    def test_duplicate_physical_button_and_stick_trigger_are_rejected(self):
        preset={'left_stick':[0,1],'right_stick':[2,3],'controls':{'lb':{'button':4},'lt':{'button':4},'rt':{'axis':3,'rest':-1.,'full':1.}}}
        self.assertEqual(set(mapping_issues(preset)),{'lb','lt','rt'})
    def test_four_button_repair_preserves_sticks_and_game_bindings(self):
        cfg=public.config();cfg['preset']='8bitdo_switch';before=copy.deepcopy(cfg)
        fixed=services.apply_button_calibration(cfg,'Pro Controller','guid',{'lb':{'button':4},'rb':{'button':5},'lt':{'button':6},'rt':{'button':7}})
        self.assertEqual(fixed['layers'],before['layers']);self.assertEqual(fixed['input'],before['input'])
        self.assertEqual(fixed['presets']['learned_controller']['left_stick'],before['presets']['8bitdo_switch']['left_stick'])
        self.assertFalse(mapping_issues(fixed['presets']['learned_controller']))
    def test_removal_preserves_default_profile_and_writes_backup_once(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=services.initialize(root);cfg=json.loads(path.read_text());cfg.pop('assignment_schema')
            cfg['layers']=[{'name':'lb','modifiers':['lb'],'bindings':{'south':{'action':'target_last'}}},{'name':'base','modifiers':[],'bindings':{'south':{'action':'target_self'}}}]
            cfg['assignment_profiles']['Custom']=copy.deepcopy(cfg['layers']);cfg['input']['shift_layer_enabled']=True
            bridge.save_config(path,cfg);services.initialize(root);saved=json.loads(path.read_text())
            self.assertEqual(len(saved['layers']),1);self.assertEqual(saved['layers'][0]['bindings']['south']['action'],'target_self')
            self.assertEqual(len(saved['assignment_profiles']['Custom']),1);self.assertNotIn('shift_layer_enabled',saved['input'])
            backup=(root/'bindings.before-4.0.json').read_bytes();services.initialize(root)
            self.assertEqual((root/'bindings.before-4.0.json').read_bytes(),backup)
    def test_shifted_edits_are_rejected_even_from_old_client(self):
        with self.assertRaises(ValueError):bridge.configure(public.config(),{'binding':{'control':'south','layer':'lb','action':'target_last'}},types.SimpleNamespace())

class NativeMouseTests(unittest.TestCase):
    def test_sendinput_flags_preserve_cursor_and_hold_until_matching_release(self):
        calls=[]
        def send(count,ptr,size):
            event=ctypes.cast(ptr,ctypes.POINTER(bridge.WinInput)).contents
            calls.append((event.type,event.mi.dwFlags,event.mi.dx,event.mi.dy,size));return 1
        pointer=bridge.WindowsPointer.__new__(bridge.WindowsPointer);pointer.user32=types.SimpleNamespace(SendInput=send)
        for button,down in [('left',True),('left',False),('right',True),('right',False)]:self.assertTrue(pointer.button(button,down))
        self.assertEqual([c[1] for c in calls],[2,4,8,16]);self.assertTrue(all(c[2:4]==(0,0) for c in calls))
        self.assertTrue(all(c[4]==ctypes.sizeof(bridge.WinInput) for c in calls))
    def test_rejected_mouse_press_is_reported_and_not_marked_held(self):
        cfg=public.config();desktop=types.SimpleNamespace(mouse_button=lambda button,down:False)
        output=bridge.OutputRouter(cfg,public.RecordedEngine(),desktop);output.begin_control('lb');output.action('mouse_left')
        self.assertFalse(output.mouse_held);self.assertEqual(output.mouse_result,{'button':'left','down':True,'accepted':False})
        self.assertEqual(output.last_input['blocked_reason'],'mouse_rejected')
    def test_failed_release_is_retried_without_replaying_press(self):
        calls=[];release_count=[0]
        def send(button,down):
            calls.append((button,down))
            if not down:release_count[0]+=1;return release_count[0]>1
            return True
        output=bridge.OutputRouter(public.config(),public.RecordedEngine(),types.SimpleNamespace(mouse_button=send))
        output.begin_control('lt');output.action('mouse_left');output.release('lt')
        self.assertIn('lt',output.mouse_held);output.movement(None,False)
        self.assertFalse(output.mouse_held);self.assertEqual(calls,[('left',True),('left',False),('left',False)])

class SimplifiedQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])
    def test_clickable_diagram_list_and_four_consolidated_tabs(self):
        from desktop_app import StudioWindow,STYLE
        from PySide6.QtWidgets import QPushButton
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        self.app.setStyleSheet(STYLE)
        with tempfile.TemporaryDirectory() as folder:
            window=StudioWindow(Path(folder))
            try:
                self.assertEqual([window.tabs.tabText(i) for i in range(window.tabs.count())],['Controller','Assignments','Preferences','Support'])
                self.assertFalse(any('weapon' in b.text().lower() for b in window.findChildren(QPushButton)))
                window.tabs.setCurrentIndex(1);window.show();self.app.processEvents();editor=window.assignments
                self.assertFalse(hasattr(editor,'layers'));self.assertFalse(hasattr(editor,'shift'))
                QTest.mouseClick(editor.diagram.buttons['lb'],Qt.MouseButton.LeftButton);self.assertEqual(editor.control(),'lb')
                editor.actions.setCurrentIndex(editor.actions.findData('pet_all_follow_me'));editor.apply()
                QTest.mouseClick(editor.diagram.buttons['lt'],Qt.MouseButton.LeftButton);self.assertEqual(editor.control(),'lt')
                editor.actions.setCurrentIndex(editor.actions.findData('mouse_left'));editor.apply()
                saved=window.read_config();binding=saved['layers'][0]['bindings']
                self.assertEqual(binding['lb']['action'],'pet_all_follow_me');self.assertEqual(binding['lt']['action'],'mouse_left')
                editor.show_live_input({'active_controls':['lt']});self.assertEqual(editor.diagram.pressed,{'lt'})
                editor.list_view.setChecked(True);self.assertEqual(editor.views.currentIndex(),1)
                editor.list_view.setChecked(False);self.assertEqual(editor.views.currentIndex(),0)
            finally:window.timer.stop();window.tray.hide();window.close()
    def test_button_check_requires_release_and_second_matching_press(self):
        from calibration import CalibrationDialog
        from PySide6.QtWidgets import QDialog
        class Joy:
            buttons=[False]*20
            def get_instance_id(self):return 1
            def get_init(self):return True
            def get_name(self):return 'Pro Controller'
            def get_guid(self):return 'guid'
            def get_numaxes(self):return 6
            def get_numbuttons(self):return 20
            def get_numhats(self):return 1
            def get_axis(self,index):return 0.
            def get_button(self,index):return self.buttons[index]
            def get_hat(self,index):return (0,0)
        joy=Joy();pg=types.SimpleNamespace(display=types.SimpleNamespace(init=lambda:None),joystick=types.SimpleNamespace(init=lambda:None,get_count=lambda:1,Joystick=lambda i:joy),event=types.SimpleNamespace(get=lambda:[],pump=lambda:None),quit=lambda:None,error=RuntimeError)
        cfg=public.config();cfg['preset']='8bitdo_switch';clock=[0.]
        with patch.dict(sys.modules,pygame=pg),patch('calibration.time.monotonic',lambda:clock[0]):
            dialog=CalibrationDialog(cfg,buttons_only=True)
            try:
                dialog.timer.stop();dialog.advance();dialog.advance()
                def frame(stamp,down):clock[0]=stamp;joy.buttons[4]=down;dialog.poll()
                frame(.01,True);frame(.15,True);self.assertEqual(dialog.index,0);self.assertTrue(dialog.release_wait)
                frame(.20,False);frame(.45,False);frame(.5,True);frame(.65,True)
                self.assertEqual(dialog.index,1);self.assertEqual(dialog.learned['lb'],{'button':4})
            finally:dialog.reject()

if __name__=='__main__':unittest.main()
