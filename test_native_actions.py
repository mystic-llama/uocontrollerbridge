"""Action routing, physical mouse edges, and assignment navigation regressions."""
import copy
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch
import controller_bridge as bridge
from action_catalog import native_actions, BUILTIN_AGENT_ACTIONS
from test_public import FakeJoy, RecordedEngine, RecordedMouse
import test_controller as support

ROOT=Path(__file__).resolve().parent

def config(): return json.loads((ROOT/'bindings.defaults.json').read_text())

class MouseRegressionTests(unittest.TestCase):
    def setUp(self):
        self.cfg=config()
        self.cfg['layers']=[{'name':'lb','modifiers':['lb'],'bindings':{'lb':{'action':'unbound'},'rb':{'action':'unbound'},'south':{'action':'target_last'}}},
                            {'name':'base','modifiers':[],'bindings':{'lb':{'action':'mouse_left'},'rb':{'action':'mouse_right'},'south':{'action':'target_self'}}}]
        self.desktop=types.SimpleNamespace(mouse=RecordedMouse(),mouse_module=types.SimpleNamespace(Button=types.SimpleNamespace(left='left',right='right')))
        self.engine=RecordedEngine();self.output=bridge.OutputRouter(self.cfg,self.engine,self.desktop)
        self.mapper=bridge.InputMapper(self.cfg,self.output)
        self.joy=FakeJoy();self.joy.buttons=[False]*3
        self.preset={'left_stick':[0,1],'right_stick':[2,3],'controls':{'lb':{'button':0},'rb':{'button':1},'south':{'button':2}}}
        self.stamp=1.
        self.clock=patch.object(bridge.time,'monotonic',lambda:self.stamp);self.clock.start();self.addCleanup(self.clock.stop)
        self.poll()
    def poll(self):
        self.stamp+=.03
        return self.mapper.poll(self.joy,self.preset,self.stamp,True,True)
    def button(self,index,value):
        self.joy.buttons[index]=value;self.poll();return self.poll()
    def test_left_bumper_tap_twice_is_two_down_up_pairs_even_when_it_selects_lb_layer(self):
        for _ in range(2): self.button(0,True);self.button(0,False)
        self.assertEqual(self.desktop.mouse.pressed,['left','left'])
        self.assertEqual(self.desktop.mouse.released,['left','left'])
    def test_both_buttons_hold_across_layer_changes_and_right_click_does_not_scroll(self):
        self.button(1,True);self.button(0,True)
        self.joy.axes[2]=.6
        for _ in range(100):self.assertFalse(self.poll()[2])
        self.assertEqual(self.desktop.mouse.pressed,['right','left'])
        self.assertFalse(self.desktop.mouse.released)
        self.button(0,False);self.assertEqual(self.desktop.mouse.released,['left'])
        self.button(1,False);self.assertEqual(self.desktop.mouse.released,['left','right'])
    def test_disable_lb_layer_keeps_normal_gameplay_and_mouse(self):
        self.cfg['input']['shift_layer_enabled']=False
        self.button(0,True);self.button(2,True)
        self.assertEqual(self.engine.actions,['target_self'])
        self.assertEqual(self.desktop.mouse.pressed,['left'])
    def test_mouse_bumper_never_shifts_game_actions_even_if_layer_is_enabled(self):
        self.cfg['input']['shift_layer_enabled']=True
        self.button(0,True);self.button(2,True)
        self.assertEqual(self.engine.actions,['target_self'])
    def test_mouse_assignment_also_overrides_a_legacy_run_modifier(self):
        calls=[];self.engine.movement=lambda heading,running:calls.append((heading,running))
        self.cfg['input']['run_control']='lb';self.joy.axes[0]=.5;self.button(0,True)
        self.assertIsNotNone(calls[-1][0]);self.assertFalse(calls[-1][1])
    def test_mouse_released_on_reset_during_drag(self):
        self.button(0,True);self.mapper.reset()
        self.assertEqual(self.desktop.mouse.released,['left'])

class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):support.GumpTests.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls):support.GumpTests.tearDownClass.__func__(cls)
    def setUp(self):
        self.module['CONFIG'].clear();self.module['CONFIG'].update(config())
        self.scope=self.module['Executor'].execute.__globals__
        self.ui.draft=copy.deepcopy(self.module['CONFIG']);self.ui.changes={};self.ui.applying_request=None
        self.ui.listener.session='test';self.ui.synced=True;self.ui.layer='base';self.ui.page='actions';self.ui.selected='south'
        self.ui.minimized=False;self.ui.confirm_exit=False;self.ui.action_category='all';self.ui.action_page=0
    def test_listener_starts_with_optional_gump_hidden(self):
        self.assertTrue(self.ui.hidden)
    def test_recovery_message_clears_bridge_work_without_cancelling_unrelated_target(self):
        calls=[];listener=self.module['Listener']();listener.session='recovery';listener.movement=('East',True)
        listener.executor.pending_target=('self',999999999);listener.executor.busy_until=999999999
        target=types.SimpleNamespace(HasTarget=lambda:True,Cancel=lambda:calls.append('cancel'))
        with patch.dict(self.scope,Target=target):
            listener.message({'type':'reset_input','session':'recovery','seq':1,'at':0})
            self.assertEqual(calls,['cancel']);self.assertIsNone(listener.movement)
            self.assertIsNone(listener.executor.pending_target);self.assertEqual(listener.executor.busy_until,0)
            listener.message({'type':'reset_input','session':'recovery','seq':2,'at':0})
            self.assertEqual(calls,['cancel'])
    def test_catalog_matches_standalone_listener_and_migration_preserves_bindings(self):
        self.assertEqual(self.module['native_actions'](),native_actions())
        cfg=config();before=copy.deepcopy(cfg['layers'])
        for key in native_actions(): del cfg['actions'][key]
        bridge.ensure_assignment_profiles(cfg)
        self.assertTrue(bridge.migrate_controller_ui(cfg));self.assertEqual(cfg['layers'],before)
        self.assertFalse(bridge.migrate_controller_ui(cfg))
    def test_pet_commands_and_last_weapon(self):
        calls=[];player=types.SimpleNamespace(ChatSay=lambda hue,text:calls.append(text),EquipLastWeapon=lambda:calls.append('arm'))
        with patch.dict(self.scope,Player=player):
            for key in native_actions():
                if key.startswith('pet_'):
                    self.assertEqual(self.module['Executor']().execute(key,1)[0],'ok')
            self.assertEqual(self.module['Executor']().execute('arm_last_weapon',1)[0],'ok')
        self.assertIn('all kill',calls);self.assertIn('all follow me',calls);self.assertIn('arm',calls)
    def test_use_last_item_uses_razor_last_object(self):
        calls=[]
        with patch.dict(self.scope,last_item_serial=lambda:123,Items=types.SimpleNamespace(UseItem=calls.append)):
            self.assertEqual(self.module['Executor']().execute('use_last_item',1)[0],'ok')
            self.assertEqual(calls,[123])
        with patch.dict(self.scope,last_item_serial=lambda:0):
            self.assertEqual(self.module['Executor']().execute('use_last_item',1)[0],'error')
    def test_last_item_reflection_reads_internal_properties(self):
        flags=types.SimpleNamespace(Public=1,NonPublic=2,Static=4,Instance=8)
        class Prop:
            def __init__(self,value): self.value=value
            def GetValue(self,obj,index): return self.value
        class ClrType:
            def __init__(self,name,value): self.name,self.value=name,value
            def GetProperty(self,name,options):
                self_test.assertTrue(options & flags.NonPublic)
                return Prop(self.value) if name==self.name else None
        self_test=self
        player=types.SimpleNamespace(GetType=lambda:ClrType('LastObject',types.SimpleNamespace(Value=321)))
        world=ClrType('Player',player)
        domain=types.SimpleNamespace(CurrentDomain=types.SimpleNamespace(GetAssemblies=lambda:[types.SimpleNamespace(GetType=lambda name,throw:world)]))
        reflection=types.ModuleType('System.Reflection');reflection.BindingFlags=flags
        with patch.dict(sys.modules,{'System.Reflection':reflection}),patch.object(sys.modules['System'],'AppDomain',domain,create=True):
            self.assertEqual(self.scope['last_item_serial'](),321)
    def test_all_agents_start_stop_and_toggle_use_correct_native_methods(self):
        methods={'Organizer':('FStart','FStop','Status'),'Restock':('FStart','FStop','Status'),'Dress':('DressFStart','DressFStop','DressStatus'),
                 'UnDress':('UnDressFStart','UnDressFStop','UnDressStatus'),'BuyAgent':('Enable','Disable','Status'),'SellAgent':('Enable','Disable','Status')}
        for agent in ('AutoLoot','Scavenger','BandageHeal','Organizer','Restock','Dress','UnDress','BuyAgent','SellAgent','DPSMeter'):
            start,stop,status=methods.get(agent,('Start','Stop','Status'));calls=[];active=[False]
            def begin():active[0]=True;calls.append(start)
            def end():active[0]=False;calls.append(stop)
            api=types.SimpleNamespace(**{start:begin,stop:end,status:lambda:active[0]})
            with patch.dict(self.scope,**{'Dress' if agent=='UnDress' else agent:api}):
                for op in ('start','stop','toggle','toggle'):
                    result=self.module['Executor']().execute('agent_'+agent.lower()+'_'+op,1)
                    self.assertEqual(result[0],'ok',(agent,op,result))
            self.assertEqual(calls,[start,stop,start,stop])
    def test_ui_only_agent_handlers_and_friend_are_reachable_without_key_injection(self):
        calls=[]
        with patch.dict(self.scope,invoke_builtin_agent=calls.append,Friend=types.SimpleNamespace(AddFriendTarget=lambda:calls.append('friend'))):
            for key in BUILTIN_AGENT_ACTIONS:
                self.assertEqual(self.module['Executor']().execute(key,1)[0],'ok')
            self.assertEqual(self.module['Executor']().execute('agent_friend_add',1)[0],'ok')
        self.assertEqual(set(calls),set(BUILTIN_AGENT_ACTIONS)|{'friend'})

    def test_builtin_agent_adapter_marshals_fixed_handler_to_ui_thread(self):
        calls=[]
        flags=types.SimpleNamespace(Public=1,NonPublic=2,Static=4)
        class Method:
            def Invoke(self,obj,args):calls.append(('command',args[0]))
        class HotkeyType:
            def GetMethod(self,name,options):
                calls.append(('method',name));return Method()
        class Window:
            InvokeRequired=True
            def Invoke(self,callback): calls.append(('ui',));callback()
        class EngineType:
            def GetProperty(self,name,options):return types.SimpleNamespace(GetValue=lambda obj,index:Window())
        assembly=types.SimpleNamespace(GetType=lambda name,throw:HotkeyType() if name=='RazorEnhanced.HotKey' else EngineType())
        domain=types.SimpleNamespace(CurrentDomain=types.SimpleNamespace(GetAssemblies=lambda:[assembly]))
        reflection=types.ModuleType('System.Reflection');reflection.BindingFlags=flags
        class NetArray:
            def __getitem__(self,element): return list
        with patch.dict(self.scope,Array=NetArray()),patch.dict(sys.modules,{'System.Reflection':reflection}),patch.multiple(sys.modules['System'],AppDomain=domain,Action=lambda callback:callback,Object=object,create=True):
            self.scope['invoke_builtin_agent']('agent_auto_carver_toggle')
            with self.assertRaises(ValueError): self.scope['invoke_builtin_agent']('arbitrary_private_method')
        self.assertEqual(calls,[('method','ProcessAgentAutoCarver'),('ui',),('command','Auto Carver Trigger ON/OFF')])

    def test_disarm_and_restore_both_hands(self):
        held={'LeftHand':types.SimpleNamespace(Serial=10),'RightHand':types.SimpleNamespace(Serial=11)};calls=[]
        def unequip(layer,wait): calls.append(('off',layer,wait));held[layer]=None
        player=types.SimpleNamespace(GetItemOnLayer=lambda layer:held.get(layer),UnEquipItemByLayer=unequip,EquipItem=lambda serial:calls.append(('on',serial)))
        clock=[1.]
        with patch.dict(self.scope,Player=player,now=lambda:clock[0],Items=types.SimpleNamespace(FindBySerial=lambda serial:types.SimpleNamespace(Serial=serial))):
            executor=self.module['Executor']()
            self.assertEqual(executor.execute('disarm_both',1)[0],'ok')
            self.assertEqual(len(calls),1)
            clock[0]+=.61;executor.tick_hands()
            self.assertEqual(executor.execute('arm_both',1)[0],'ok')
            clock[0]+=.61;executor.tick_hands()
            clock[0]+=.61;executor.tick_hands()
        self.assertEqual(calls,[('off','LeftHand',False),('off','RightHand',False),('on',10),('on',11)])
    def test_layer_tabs_explain_editor_selection_and_agent_category_pages_are_reachable(self):
        self.ui.handle(11,None);self.assertEqual(self.ui.layer,'base')
        self.ui.handle(10,None);self.assertEqual(self.ui.layer,'base');self.assertIn('Select',self.ui.status)
        self.ui.page='actions';self.ui.handle(84,None)
        names=self.ui.action_names();self.assertEqual(len(names),38)
        seen=set()
        for page in range((len(names)+11)//12):
            self.ui.action_page=page
            ops=support.GumpTests.render(self,page='actions')
            seen.update(args[4]-2000 for kind,args in ops if kind=='Button' and 2000<=args[4]<10000)
        self.assertEqual(seen,set(range(38)))
        self.ui.handle(2000,None)
        self.assertIn(('binding','base','south'),self.ui.changes)
    def test_mouse_labels_and_removed_layer_setting(self):
        self.assertNotIn('(hold)',self.ui.action_label('mouse_left'))
        self.ui.handle(58,None);self.assertFalse(self.ui.changes)
        with self.assertRaises(ValueError):
            bridge.configure(config(),{'setting':{'name':'shift_layer_enabled','value':True}},types.SimpleNamespace())

if __name__=='__main__':unittest.main()
