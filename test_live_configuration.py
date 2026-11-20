"""Exercises Apply/Resume through the actual host polling loop with fake hardware."""
import json
import logging
from pathlib import Path
import queue
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import controller_bridge as bridge


class LiveConfigurationTests(unittest.TestCase):
    def run_host(self,customize=None,desktop_schedule=None,desktop_requests=None):
        engine_list=[];tick=[0];clock=[0.0]
        class Engine:
            def __init__(self,cfg):
                self.commands=queue.Queue();self.ready=threading.Event();self.ready.set()
                self.client_pid=42;self.actions=[];self.moves=[];self.messages=[]
                engine_list.append(self)
            def action(self,name,value=1): self.actions.append(name)
            def movement(self,name,running): self.moves.append(name)
            def publish(self,message): self.messages.append(message)
            def control(self,*args,**kwargs): pass
            def discard_actions(self): pass
            def close(self): pass
        class Desktop:
            def __init__(self,cfg,**kwargs): self.cfg=cfg
            def reset(self): pass
            def pointer(self,*args): pass
            def close(self): pass
            def key(self,name): return name
        class Guard:
            def __init__(self,cfg): self.pid=42;self.title='Test UO';self.process='ClassicUO.exe';self.elevated=False
            def allowed(self): return True
        class Joy:
            def get_instance_id(self): return 0
            def get_init(self): return True
            def get_name(self): return 'Test Controller'
            def get_guid(self): return 'test'
            def get_numbuttons(self): return 2
            def get_numaxes(self): return 4
            def get_numhats(self): return 0
            def get_axis(self,index): return .9 if index==0 and tick[0]>=21 else 0.
            def get_button(self,index): return index==0 and 15<=tick[0]<=19
            def quit(self): pass
        class Clock:
            def tick(self,hz):
                tick[0]+=1;clock[0]+=.02
                if desktop_schedule and tick[0] in desktop_schedule:
                    bridge.save_config(control_path,{'sequence':tick[0],'paused':desktop_schedule[tick[0]],'heartbeat':1000+clock[0]})
                if desktop_requests and tick[0] in desktop_requests:
                    bridge.save_config(control_path,{'sequence':tick[0],'paused':False,'heartbeat':1000+clock[0],'request':desktop_requests[tick[0]]})
                if customize: customize(tick[0],engine_list[0])
                if tick[0]>=28: raise KeyboardInterrupt()
        joy=Joy()
        pg=SimpleNamespace(display=SimpleNamespace(init=lambda:None),joystick=SimpleNamespace(init=lambda:None,get_count=lambda:1,Joystick=lambda index:joy),
            event=SimpleNamespace(get=lambda:[]),time=SimpleNamespace(Clock=Clock),quit=lambda:None,error=RuntimeError,
            JOYDEVICEADDED=1,JOYDEVICEREMOVED=2,JOYAXISMOTION=3,JOYBUTTONDOWN=4,JOYBUTTONUP=5,JOYHATMOTION=6)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'bindings.json'
            control_path=Path(folder)/'control.json'
            bridge.save_config(control_path,{'sequence':0,'paused':False,'heartbeat':1000})
            cfg=json.loads((Path(__file__).parent/'bindings.defaults.json').read_text())
            cfg['presets']['test']={'controls':{'south':{'button':0},'rs':{'button':1}},'left_stick':[0,1],'right_stick':[2,3]}
            cfg['preset']='test';cfg['device_name_contains']='';cfg.pop('device_guid',None)
            bridge.migrate_controller_ui(cfg);bridge.save_config(path,cfg)
            handlers=list(bridge.LOG.handlers)
            try:
                with patch.dict(sys.modules,pygame=pg),patch.object(bridge,'SocketServer',Engine),patch.object(bridge,'DesktopOutput',Desktop),patch.object(bridge,'FocusGuard',Guard),patch.object(bridge,'host_elevated',return_value=False),patch.object(bridge,'time',SimpleNamespace(monotonic=lambda:clock[0],time=lambda:1000+clock[0],sleep=lambda _:None)),patch.object(bridge,'enable_dpi_awareness'):
                    bridge.main(['--config',str(path)]+(['--control',str(control_path)] if desktop_schedule or desktop_requests else []))
                return engine_list[0],json.loads(path.read_text())
            finally:
                for handler in bridge.LOG.handlers[:]:
                    if handler not in handlers: bridge.LOG.removeHandler(handler);handler.close()

    def test_apply_resume_then_new_binding_and_movement_work_without_restart(self):
        def command(tick,engine):
            if tick==3: engine.commands.put({'type':'configure','payload':{'paused':True}})
            if tick==6: engine.commands.put({'type':'configure','payload':{'changes':[{'binding':{'control':'south','layer':'base','action':'unbound','cast':{'school':'Magery','spell':'Heal','target':'self'}}}],'expected_revision':0,'paused':True}})
            if tick==10: engine.commands.put({'type':'configure','payload':{'paused':False}})
        engine,cfg=self.run_host(command)
        bound=next(row for row in cfg['layers'] if row['name']=='base')['bindings']['south']['action']
        self.assertIn(bound,engine.actions)
        self.assertIn('East',engine.moves)
        self.assertFalse(engine.messages[-1].get('paused',False))

    def test_app_pause_resume_during_gump_editing_keeps_game_paused_until_gump_resume(self):
        def command(tick,engine):
            if tick==3: engine.commands.put({'type':'configure','request':'edit-pause','payload':{'paused':True}})
            if tick==14: engine.commands.put({'type':'configure','request':'gump-resume','payload':{'paused':False}})
        engine,_=self.run_host(command,desktop_schedule={6:True,9:False})
        snapshots=[message for message in engine.messages if message['type']=='configuration_result']
        # Desktop resumed while editing: game pause must still belong to the Gump.
        resumed_desktop=[m for m in snapshots if not m.get('request') and m.get('pause_reason')=='gump']
        self.assertTrue(resumed_desktop)
        self.assertTrue(all(m['paused'] for m in resumed_desktop))
        final=next(m for m in snapshots if m.get('request')=='gump-resume')
        self.assertFalse(final['paused']);self.assertEqual(final['pause_reason'],'')
        self.assertIn('East',engine.moves)

    def test_gump_resume_does_not_silently_override_application_pause(self):
        def command(tick,engine):
            if tick==10: engine.commands.put({'type':'configure','request':'gump-resume','payload':{'paused':False}})
        engine,_=self.run_host(command,desktop_schedule={6:True})
        final=next(m for m in engine.messages if m.get('request')=='gump-resume')
        self.assertTrue(final['paused']);self.assertEqual(final['pause_reason'],'application')
        self.assertFalse(engine.actions)
        self.assertNotIn('East',engine.moves)


    def test_resume_immediately_followed_by_button_and_stick_does_not_strand_game_input(self):
        def command(tick,engine):
            if tick==3: engine.commands.put({'type':'configure','payload':{'paused':True}})
            if tick==6: engine.commands.put({'type':'configure','payload':{'changes':[{'binding':{'control':'south','layer':'base','action':'unbound','cast':{'school':'Magery','spell':'Heal','target':'self'}}}],'expected_revision':0,'paused':True}})
            if tick==14: engine.commands.put({'type':'configure','payload':{'paused':False}})
        engine,cfg=self.run_host(command)
        bound=next(row for row in cfg['layers'] if row['name']=='base')['bindings']['south']['action']
        self.assertIn(bound,engine.actions)
        self.assertIn('East',engine.moves)

    def test_desktop_apply_and_recover_work_through_live_host_without_restart(self):
        request={'id':'apply-1','kind':'apply','payload':{'changes':[{'binding':{'control':'south','layer':'base','action':'target_self'}}],'expected_revision':0}}
        def command(tick,engine):
            if tick==3:engine.commands.put({'type':'configure','payload':{'paused':True}})
        engine,cfg=self.run_host(command,desktop_requests={6:request,8:request,10:{'id':'recover-1','kind':'recover'}})
        self.assertEqual(cfg['revision'],1)
        self.assertIn('target_self',engine.actions);self.assertIn('East',engine.moves)
        self.assertEqual(sum(message['type']=='reset_input' for message in engine.messages),2)



if __name__=='__main__': unittest.main()
