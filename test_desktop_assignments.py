"""Real Qt editor transactions, shortcut recording, input recovery and key worker checks."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import controller_bridge as bridge
from hotkeys import normalize_hotkey,HotkeyWorker
import test_public as public

class MovementArmingTests(unittest.TestCase):
    def test_held_game_button_does_not_block_movement_after_focus_returns(self):
        cfg=public.config();cfg['layers']=[{'name':'base','modifiers':[],'bindings':{'south':{'action':'target_self'}}}]
        engine=public.RecordedEngine();desktop=SimpleNamespace(mouse=public.RecordedMouse(),mouse_module=SimpleNamespace(Button=SimpleNamespace(left='left',right='right')))
        output=bridge.OutputRouter(cfg,engine,desktop);mapper=bridge.InputMapper(cfg,output);joy=public.FakeJoy()
        preset={'controls':{'south':{'button':0}},'left_stick':[0,1],'right_stick':[2,3]};stamp=0.
        def poll(game):
            nonlocal stamp
            stamp+=.1;mapper.poll(joy,preset,stamp,True,game)
        poll(False);joy.buttons[0]=True;poll(False);poll(False)
        poll(True);joy.axes[0]=.9;poll(True)
        self.assertEqual(engine.moves[-1],'East');self.assertFalse(engine.actions)
        joy.buttons[0]=False;poll(True);poll(True)
        joy.buttons[0]=True;poll(True);poll(True)
        self.assertEqual(engine.actions,['target_self'])
    def test_cursor_deflection_and_held_button_at_reset_cannot_strand_movement_or_fire(self):
        cfg=public.config();cfg['layers']=[{'name':'base','modifiers':[],'bindings':{'south':{'action':'target_self'}}}]
        engine=public.RecordedEngine();mapper=bridge.InputMapper(cfg,engine);joy=public.FakeJoy();joy.axes[2]=.8;joy.buttons[0]=True
        preset={'controls':{'south':{'button':0}},'left_stick':[0,1],'right_stick':[2,3]}
        mapper.poll(joy,preset,0.,True,True);self.assertTrue(mapper.armed)
        joy.axes[0]=.9
        for stamp in (.1,.2,.3):mapper.poll(joy,preset,stamp,True,True)
        self.assertEqual(engine.moves[-1],'East');self.assertFalse(engine.actions)
        joy.buttons[0]=False;mapper.poll(joy,preset,.4,True,True);mapper.poll(joy,preset,.5,True,True)
        joy.buttons[0]=True;mapper.poll(joy,preset,.6,True,True);mapper.poll(joy,preset,.7,True,True)
        self.assertEqual(engine.actions,['target_self'])
    def test_legacy_non_mouse_lb_no_longer_shifts_assignments(self):
        cfg=public.config();cfg['input']['shift_layer_enabled']=True
        cfg['layers']=[{'name':'lb','modifiers':['lb'],'bindings':{'south':{'action':'target_last'}}},{'name':'base','modifiers':[],'bindings':{'south':{'action':'target_self'},'lb':{'action':'unbound'}}}]
        mapper=bridge.InputMapper(cfg,public.RecordedEngine());joy=public.FakeJoy()
        preset={'controls':{'lb':{'button':0},'south':{'button':1}},'left_stick':[0,1],'right_stick':[2,3]}
        mapper.poll(joy,preset,0.,True);joy.buttons[0]=True;mapper.poll(joy,preset,.1,True);mapper.poll(joy,preset,.2,True)
        self.assertEqual(mapper.layer()['name'],'base')

class HotkeyTests(unittest.TestCase):
    def test_normalizer_handles_recorded_and_typed_chords_and_rejects_modifier_only(self):
        self.assertEqual(normalize_hotkey('Ctrl+F1'),['ctrl','f1'])
        self.assertEqual(normalize_hotkey('Control + Shift + PgDown'),['ctrl','shift','page_down'])
        for value in ('Ctrl','ctrl+f1,ctrl+f2','ctrl+','imaginary','ctrl+ctrl+f1'):
            with self.assertRaises(ValueError):normalize_hotkey(value)
    def worker(self,allowed=lambda:True):
        calls=[];ended=threading.Event();pressed=threading.Event()
        class Keyboard:
            def press(self,key):
                calls.append(('down',key,time.monotonic(),threading.get_ident()))
                if key=='f1':pressed.set()
            def release(self,key):
                calls.append(('up',key,time.monotonic(),threading.get_ident()))
                if key=='ctrl':ended.set()
        worker=HotkeyWorker(Keyboard(),lambda key:key,allowed,tap_ms=8);self.addCleanup(worker.close)
        return worker,calls,ended,pressed
    def test_ctrl_f1_runs_off_poll_thread_and_holds_long_enough(self):
        worker,calls,ended,_=self.worker();worker.submit(['ctrl','f1']);self.assertTrue(ended.wait(1))
        self.assertEqual([(c[0],c[1]) for c in calls],[('down','ctrl'),('down','f1'),('up','f1'),('up','ctrl')])
        self.assertGreaterEqual(calls[1][2]-calls[0][2],.015);self.assertGreaterEqual(calls[2][2]-calls[1][2],.05)
        self.assertNotEqual(calls[0][3],threading.get_ident());self.assertEqual(worker.result['status'],'sent')
    def test_cancel_releases_pressed_keys_and_does_not_replay(self):
        worker,calls,ended,pressed=self.worker();worker.submit(['ctrl','f1']);self.assertTrue(pressed.wait(1));worker.cancel();self.assertTrue(ended.wait(1))
        self.assertEqual(sum(c[0]=='down' for c in calls),2);self.assertEqual(sum(c[0]=='up' for c in calls),2)
        self.assertEqual(worker.result['status'],'blocked')
    def test_shortcut_does_not_send_to_other_foreground_windows(self):
        worker,calls,_,_=self.worker(lambda:False);worker.submit(['ctrl','f1'])
        deadline=time.monotonic()+1
        while not worker.result and time.monotonic()<deadline:worker.stop.wait(.01)
        self.assertEqual(calls,[]);self.assertEqual(worker.result['status'],'blocked')

class DesktopTransactionTests(unittest.TestCase):
    def test_stale_revision_and_old_listener_leave_saved_settings_unchanged(self):
        cfg=public.config();before=copy.deepcopy(cfg)
        desktop=SimpleNamespace(key=lambda n:n);output=bridge.OutputRouter(cfg,public.RecordedEngine(),desktop)
        engine=SimpleNamespace(ready=threading.Event(),client_features=[])
        engine.ready.set()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'bindings.json';bridge.save_config(path,cfg)
            request={'id':'one','kind':'apply','payload':{'changes':[],'expected_revision':cfg.get('revision',0)}}
            result,_=bridge.apply_desktop_request(cfg,request,desktop,output,None,engine,path,False)
            self.assertEqual(result['status'],'error');self.assertIn('Razor listener',result['detail']);self.assertEqual(cfg,before)
            engine.client_features=['desktop_editor_v1'];request['payload']['expected_revision']=99
            result,_=bridge.apply_desktop_request(cfg,request,desktop,output,None,engine,path,False)
            self.assertEqual(result['status'],'error');self.assertEqual(json.loads(path.read_text()),before)

class EditorQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        from desktop_app import StudioWindow,STYLE
        self.app.setStyleSheet(STYLE)
        self.temp=tempfile.TemporaryDirectory();self.window=StudioWindow(Path(self.temp.name));self.editor=self.window.assignments
        self.window.tabs.setCurrentIndex(1);self.window.show();self.app.processEvents()
    def tearDown(self):
        self.window.timer.stop();self.window.tray.hide();self.window.close();self.temp.cleanup()
    def select(self,control):self.editor.table.setCurrentCell(self.editor.controls.index(control),0);self.editor.select_control()
    def binding(self,control):
        cfg=self.window.read_config();binding=next(r for r in cfg['layers'] if r['name']=='base')['bindings'][control]
        return cfg,cfg['actions'][binding['action']]
    def test_mouse_assignments_save_in_app_and_disable_modifier(self):
        for control,action in [('lb','mouse_left'),('rb','mouse_right')]:
            self.select(control);self.editor.mode.setCurrentIndex(0);self.editor.actions.setCurrentIndex(self.editor.actions.findData(action));self.editor.apply()
            cfg,definition=self.binding(control);self.assertEqual(definition['type'],'mouse_button')
        self.assertFalse(hasattr(self.editor,'shift'));self.assertFalse(hasattr(self.editor,'layers'))
        self.assertNotIn('shift_layer_enabled',cfg['input'])
    def test_real_shortcut_widget_records_ctrl_f1_and_saves_keys(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        self.select('south');self.editor.mode.setCurrentIndex(2);self.editor.recorder.setFocus();self.app.processEvents()
        QTest.keyClick(self.editor.recorder,Qt.Key.Key_F1,Qt.KeyboardModifier.ControlModifier)
        self.editor.apply();cfg,definition=self.binding('south')
        self.assertEqual(definition,{'type':'hotkey','keys':['ctrl','f1']})
        self.assertIn('Saved and applied',self.editor.feedback.text())
    def test_spell_picker_saves_target_and_recovery(self):
        self.select('south');e=self.editor;e.mode.setCurrentIndex(1);e.school.setCurrentText('Magery');e.spell.setCurrentText('Heal');e.target.setCurrentIndex(1);e.recovery.setValue(900);e.apply()
        _,a=self.binding('south');self.assertEqual((a['spell'],a['target'],a['recovery_ms']),('Heal','self',900))
    def test_live_request_waits_for_matching_ack_and_preserves_rejected_draft(self):
        from PySide6.QtCore import QProcess
        self.select('south');e=self.editor;e.mode.setCurrentIndex(0);e.actions.setCurrentIndex(e.actions.findData('target_self'))
        self.window.process=SimpleNamespace(state=lambda:QProcess.ProcessState.Running)
        try:
            e.apply();self.assertTrue(e.pending);request=json.loads(self.window.control_path.read_text())['request']
            self.window.check_request({'desktop_reply':{'id':'another','status':'ok'}});self.assertTrue(e.pending)
            self.window.check_request({'desktop_reply':{'id':request['id'],'status':'error','detail':'Revision changed'}})
            self.assertFalse(e.pending);self.assertIn('Revision changed',e.feedback.text());self.assertTrue(e.draft.changes)
        finally:self.window.process=None
    def test_support_copy_redacts_new_free_form_error_fields(self):
        import app_services
        private='C:/Users/PrivateName/secret-bindings.json'
        bridge.save_config(self.window.status_path,{'last_ack':{'status':'error','detail':private},'desktop_reply':{'id':'x','status':'error','detail':private},'hotkey_result':{'status':'error','detail':private}})
        text=app_services.diagnostics(self.window.directory)
        self.assertNotIn(private,text);self.assertIn('error',text)
    def test_all_four_tabs_render_and_optional_gump_defaults_off(self):
        self.assertEqual(self.window.tabs.count(),4)
        for i in range(4):
            self.window.tabs.setCurrentIndex(i);self.app.processEvents();self.assertFalse(self.window.grab().isNull())
        self.assertFalse(self.window.read_config()['razor']['show_gump'])
        self.window.tabs.setCurrentIndex(1);self.app.processEvents();self.assertTrue(self.window.grab().save(str(Path(self.temp.name)/'assignments.png')))

if __name__=='__main__':unittest.main()
