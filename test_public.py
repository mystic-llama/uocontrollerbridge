"""Regression tests for public-release behavior; never inject real OS/game input."""
import copy
import hashlib
import hmac
import json
import os
from pathlib import Path
import socket
import tempfile
import time
import unittest
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.setdefault('SDL_VIDEODRIVER','dummy')
import app_services as services
import controller_bridge as bridge

ROOT=Path(__file__).resolve().parent


def config():
    cfg=json.loads((ROOT/'bindings.defaults.json').read_text(encoding='utf-8'))
    bridge.migrate_controller_ui(cfg)
    return cfg


class Keys:
    def key(self,name): return name


class PublicConfigTests(unittest.TestCase):
    def test_fresh_configuration_loads_and_has_unique_token(self):
        with tempfile.TemporaryDirectory() as a,tempfile.TemporaryDirectory() as b:
            one=bridge.load_config(services.initialize(Path(a)))
            two=bridge.load_config(services.initialize(Path(b)))
            self.assertNotEqual(one['token'],two['token']);self.assertEqual(len(one['token']),64)
            self.assertFalse(one['focus']['window_title_contains'])
            self.assertTrue(one['desktop']['global_cursor'])
            self.assertTrue(all(x['action']=='unbound' for row in one['layers'] for x in row['bindings'].values()))

    def test_initialize_preserves_existing_token_and_calibration(self):
        with tempfile.TemporaryDirectory() as folder:
            path=services.initialize(Path(folder));cfg=bridge.load_config(path);cfg['device_guid']='test-guid';bridge.save_config(path,cfg)
            services.initialize(Path(folder));again=bridge.load_config(path)
            self.assertEqual(cfg['token'],again['token']);self.assertEqual(again['device_guid'],'test-guid')

    def test_profiles_do_not_mix_class_actions(self):
        cfg=config()
        for row in cfg['assignment_profiles']['Caster']:
            for binding in row['bindings'].values():
                self.assertNotIn(binding['action'],('bandage_self','attack_last','primary_ability','secondary_ability','switch_weapon'))
        for row in cfg['assignment_profiles']['Dexxer']:
            for binding in row['bindings'].values():
                self.assertNotEqual(cfg['actions'][binding['action']]['type'],'cast')
                self.assertNotEqual(binding['action'],'meditate')
        self.assertTrue(all(b['action']=='unbound' for r in cfg['assignment_profiles']['Blank'] for b in r['bindings'].values()))

    def test_profile_edits_survive_switch_and_chords_are_independent(self):
        cfg=config()
        def apply(change):
            nonlocal cfg
            cfg=bridge.configure(cfg,change,Keys())
        apply({'assignment_profile':'Caster'})
        apply({'binding':{'layer':'base','control':'south','action':'unbound','keys':'ctrl+f1'}})
        caster=next(r for r in cfg['layers'] if r['name']=='base')['bindings']['south']['action']
        apply({'assignment_profile':'Dexxer'})
        apply({'binding':{'layer':'base','control':'south','action':'unbound','keys':'alt+f2'}})
        dexxer=next(r for r in cfg['layers'] if r['name']=='base')['bindings']['south']['action']
        self.assertNotEqual(caster,dexxer)
        apply({'assignment_profile':'Caster'})
        self.assertEqual(next(r for r in cfg['layers'] if r['name']=='base')['bindings']['south']['action'],caster)
        self.assertEqual(cfg['actions'][caster]['keys'],['ctrl','f1'])

    def test_batch_profile_is_loaded_before_bindings_and_original_unchanged(self):
        cfg=config();original=copy.deepcopy(cfg)
        result=bridge.configure(cfg,{'changes':[{'binding':{'layer':'base','control':'south','action':'target_self'}}, {'assignment_profile':'Caster'}], 'expected_revision':0},Keys())
        self.assertEqual(result['active_assignment_profile'],'Caster')
        self.assertEqual(next(r for r in result['assignment_profiles']['Caster'] if r['name']=='base')['bindings']['south']['action'],'target_self')
        self.assertEqual(cfg,original)

    def test_invalid_batch_keeps_original(self):
        cfg=config();original=copy.deepcopy(cfg)
        with self.assertRaises(ValueError): bridge.configure(cfg,{'changes':[{'assignment_profile':'Caster'},{'setting':{'name':'cursor_curve','value':99}}],'expected_revision':0},Keys())
        self.assertEqual(cfg,original)

    def test_stale_revision_rejected(self):
        with self.assertRaises(ValueError): bridge.configure(config(),{'changes':[],'expected_revision':99},Keys())

    def test_another_character_same_executable_does_not_match(self):
        focus={'window_title_contains':['Character A - ClassicUO'],'process_names':['ClassicUO.exe']}
        self.assertTrue(bridge.window_matches(focus,'Character A - ClassicUO','ClassicUO.exe'))
        self.assertFalse(bridge.window_matches(focus,'Character B - ClassicUO','ClassicUO.exe'))
        self.assertFalse(bridge.window_matches(focus,'Character A - ClassicUO','Notepad.exe'))
        self.assertFalse(bridge.window_matches(focus,'Character A - ClassicUO - Razor','ClassicUO.exe'))

    def test_listener_installation_points_to_shared_settings_and_backs_up(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);data=root/'settings';services.initialize(data)
            target=services.install_listener(data,root/'Scripts with spaces é')
            self.assertEqual(target.name,'razor_listener.py')
            pointer=json.loads(target.with_name('controller_studio_connection.json').read_text())
            self.assertEqual(pointer['config_path'],str((data/'bindings.json').resolve()))
            target.write_text('previous listener')
            services.install_listener(data,root/'Scripts with spaces é')
            self.assertEqual(target.with_name('razor_listener.previous.py').read_text(),'previous listener')

    def test_diagnostics_redact_secrets(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);cfg=bridge.load_config(services.initialize(root))
            cfg['device_name_contains']='PrivateController';cfg['actions']['switch_weapon']['serials']=['0x12345'];bridge.save_config(root/'bindings.json',cfg)
            bridge.save_config(root/'host_status.json',{'controller':'PrivateController','error':'C:/secret/name'})
            text=services.diagnostics(root)
            for secret in (cfg['token'],'PrivateController','0x12345','C:/secret/name'): self.assertNotIn(secret,text)


class CalibrationTests(unittest.TestCase):
    def setUp(self):
        self.base={'axes':[0,0,0,0,-1,-1],'buttons':[False]*20,'hats':[(0,0)]}

    def test_detects_button_hat_and_trigger(self):
        current=copy.deepcopy(self.base);current['buttons'][3]=True
        self.assertEqual(services.detect_source(self.base,current),{'button':3})
        current=copy.deepcopy(self.base);current['hats'][0]=(0,1)
        self.assertEqual(services.detect_source(self.base,current),{'hat':0,'component':1,'sign':1})
        current=copy.deepcopy(self.base);current['axes'][4]=.7
        self.assertEqual(services.detect_source(self.base,current,prefer_axis=True),{'axis':4,'rest':-1,'full':1})

    def test_drift_does_not_assign_axis(self):
        current=copy.deepcopy(self.base);current['axes'][0]=.15
        self.assertIsNone(services.detect_source(self.base,current,True))

    def test_opposite_hat_directions_have_different_identities(self):
        self.assertNotEqual(services.source_identity({'hat':0,'component':0,'sign':1}),services.source_identity({'hat':0,'component':0,'sign':-1}))

    def test_calibration_preserves_bindings_and_learns_signs(self):
        learned={key:{'axis':i,'rest':0,'full':-1 if i==1 else 1} for i,key in enumerate(['left_x','left_y','right_x','right_y'])}
        learned['south']={'button':3};cfg=config()
        result=services.apply_calibration(cfg,'Pro Controller','guid',learned)
        self.assertEqual(result['layers'],cfg['layers']);self.assertEqual(result['presets']['learned_controller']['left_stick_sign'],[1,-1])
        self.assertTrue(result['setup_complete'])

    def test_duplicate_stick_axis_rejected(self):
        learned={key:{'axis':0,'rest':0,'full':1} for key in ['left_x','left_y','right_x','right_y']}
        with self.assertRaises(ValueError): services.apply_calibration(config(),'Controller','guid',learned)


class FakeJoy:
    def __init__(self): self.axes=[0.,0.,0.,0.];self.buttons=[False]*2
    def get_axis(self,i): return self.axes[i]
    def get_numbuttons(self): return len(self.buttons)
    def get_button(self,i): return self.buttons[i]
    def get_numaxes(self): return len(self.axes)


class RecordedEngine:
    def __init__(self): self.actions=[];self.moves=[]
    def action(self,name,value): self.actions.append(name)
    def movement(self,heading,running): self.moves.append(heading)
    def close(self): pass


class RecordedMouse:
    def __init__(self): self.pressed=[];self.released=[]
    def press(self,button): self.pressed.append(button)
    def release(self,button): self.released.append(button)


class InputSeparationTests(unittest.TestCase):
    def setUp(self):
        self.cfg=config();self.cfg['layers']=[{'name':'base','modifiers':[],'bindings':{'south':{'action':'bandage_self'},'rs':{'action':'mouse_left'}}}]
        self.engine=RecordedEngine();self.desktop=type('Desktop',(),{})();self.desktop.mouse=RecordedMouse()
        self.desktop.mouse_module=type('MouseModule',(),{'Button':type('Button',(),{'left':'left','right':'right'})})
        self.output=bridge.OutputRouter(self.cfg,self.engine,self.desktop);self.mapper=bridge.InputMapper(self.cfg,self.output)
        self.joy=FakeJoy();self.preset={'left_stick':[0,1],'right_stick':[2,3],'controls':{'south':{'button':0},'rs':{'button':1}}}
        self.now=1.;self.poll(False)

    def poll(self,game):
        self.now+=.1
        return self.mapper.poll(self.joy,self.preset,self.now,True,game)

    def test_cursor_works_without_game_focus_but_actions_do_not(self):
        self.joy.axes[2]=.8
        self.assertGreater(self.poll(False)[0],0)
        self.joy.buttons[0]=True;self.poll(False);self.poll(False)
        self.assertFalse(self.engine.actions)

    def test_mouse_buttons_work_without_game_focus_and_release(self):
        self.joy.buttons[1]=True;self.poll(False);self.poll(False)
        self.assertEqual(self.desktop.mouse.pressed,['left'])
        self.joy.buttons[1]=False;self.poll(False);self.poll(False)
        self.assertEqual(self.desktop.mouse.released,['left'])

    def test_held_game_input_does_not_fire_when_focus_returns(self):
        self.joy.buttons[0]=True;self.poll(False);self.poll(False);self.poll(True)
        self.assertFalse(self.engine.actions)
        self.joy.buttons[0]=False;self.poll(True);self.poll(True)
        self.joy.buttons[0]=True;self.poll(True);self.poll(True)
        self.assertEqual(self.engine.actions,['bandage_self'])

    def test_movement_waits_for_neutral_after_focus_gain(self):
        self.joy.axes[0]=1;self.poll(False);self.poll(True)
        self.assertIsNone(self.engine.moves[-1])
        self.joy.axes[0]=0;self.poll(True)
        self.joy.axes[0]=1;self.poll(True)
        self.assertEqual(self.engine.moves[-1],'East')

    def test_reset_releases_held_mouse(self):
        self.joy.buttons[1]=True;self.poll(False);self.poll(False);self.mapper.reset()
        self.assertEqual(self.desktop.mouse.released,['left'])
        self.assertFalse(self.mapper.armed)

    def test_gump_pause_suppresses_gameplay_but_keeps_mouse(self):
        self.output.paused=True;self.poll(True)
        self.joy.buttons=[True,True];self.poll(True);self.poll(True)
        self.assertFalse(self.engine.actions);self.assertEqual(self.desktop.mouse.pressed,['left'])


class SocketTests(unittest.TestCase):
    def setUp(self):
        self.cfg=dict(config()['bridge'],port=0,token='local-test-secret')
        self.server=bridge.SocketServer(self.cfg)
        self.client=socket.create_connection(('127.0.0.1',self.server.bound_port),timeout=1)
        self.reader=self.client.makefile('rb');self.hello=json.loads(self.reader.readline())

    def tearDown(self):
        self.reader.close();self.client.close();self.server.close()

    def send(self,**message):
        self.client.sendall((json.dumps(dict(message,session=self.hello['session']))+'\n').encode())

    def wait_ready(self):
        return self.server.ready.wait(.8)

    def test_authenticated_handshake_and_process_pairing(self):
        self.assertNotIn('token',self.hello)
        expected=hmac.new(self.cfg['token'].encode(),(self.hello['session']+':host').encode(),hashlib.sha256).hexdigest()
        self.assertEqual(self.hello['auth'],expected)
        signature=hmac.new(self.cfg['token'].encode(),(self.hello['session']+':listener').encode(),hashlib.sha256).hexdigest()
        self.send(type='ready',pid=4321,auth=signature)
        self.assertTrue(self.wait_ready());self.assertEqual(self.server.client_pid,4321)
        self.assertEqual(self.server.commands.get(timeout=.8)['type'],'sync')

    def test_wrong_token_rejected(self):
        self.send(type='ready',pid=4321,auth='wrong')
        self.assertFalse(self.wait_ready());self.assertEqual(self.server.client_pid,0)

    def test_configuration_before_authentication_rejected(self):
        self.send(type='configure',payload={'paused':False})
        self.assertFalse(self.wait_ready());self.assertTrue(self.server.commands.empty())

    def test_disconnected_actions_are_not_queued(self):
        self.server.action('bandage_self')
        self.assertTrue(self.server.actions.empty())


class DesktopSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def test_all_pages_render_and_settings_can_be_saved(self):
        from desktop_app import StudioWindow
        with tempfile.TemporaryDirectory() as folder:
            window=StudioWindow(Path(folder))
            try:
                for i in range(4):
                    window.tabs.setCurrentIndex(i);window.show();self.app.processEvents()
                    self.assertFalse(window.grab().isNull())
                window.assignments.profiles.setCurrentText('Caster');window.assignments.apply()
                self.assertEqual(window.read_config()['active_assignment_profile'],'Caster')
                self.assertTrue(window.start_button.isEnabled())
            finally: window.timer.stop();window.tray.hide();window.close()

    def test_control_file_contains_live_heartbeat_and_pause(self):
        from desktop_app import StudioWindow
        with tempfile.TemporaryDirectory() as folder:
            window=StudioWindow(Path(folder))
            try:
                window.desktop_paused=True;window.sequence=3;window.write_control()
                value=json.loads(window.control_path.read_text())
                self.assertEqual(value['sequence'],3);self.assertTrue(value['paused']);self.assertLess(abs(time.time()-value['heartbeat']),2)
                window.write_control(True);self.assertTrue(json.loads(window.control_path.read_text())['stop'])
            finally: window.timer.stop();window.tray.hide();window.close()



class WindowsCursorTests(unittest.TestCase):
    def test_direct_cursor_moves_on_negative_monitor_and_clamps(self):
        import ctypes
        class User:
            def __init__(self): self.moves=[]
            def GetCursorPos(self,pointer):
                point=ctypes.cast(pointer,ctypes.POINTER(bridge.WinPoint)).contents
                point.x=-100;point.y=50;return 1
            def GetSystemMetrics(self,index): return {76:-1920,77:0,78:5760,79:1080}[index]
            def SetCursorPos(self,x,y): self.moves.append((x,y));return 1
        pointer=bridge.WindowsPointer.__new__(bridge.WindowsPointer)
        pointer.backend='windows_desktop';pointer.user32=User();pointer.last_warning=0
        self.assertTrue(pointer.move(-20,10));self.assertEqual(pointer.user32.moves[-1],(-120,60))
        pointer.move(-99999,99999);self.assertEqual(pointer.user32.moves[-1],(-1920,1079))

    def test_failed_get_cursor_position_never_teleports(self):
        pointer=bridge.WindowsPointer.__new__(bridge.WindowsPointer)
        pointer.backend='windows_desktop'
        pointer.user32=type('User',(),{'GetCursorPos':lambda self,point:0})()
        self.assertFalse(pointer.move(2,2))

if __name__=='__main__': unittest.main()
