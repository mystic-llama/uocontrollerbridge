"""Spell expansion integration tests; no physical controller or game is used."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import controller_bridge as bridge
from spell_catalog import SCHOOL_ORDER,SPELL_CATALOG,SPELL_METHODS,make_spell_action
import test_controller as gump_test_support

ROOT=Path(__file__).resolve().parent


def cfg():
    result=json.loads((ROOT/'bindings.defaults.json').read_text())
    bridge.migrate_controller_ui(result)
    return result


class Keys:
    def key(self,name): return name


class CatalogTests(unittest.TestCase):
    def test_complete_unique_counts_and_native_methods(self):
        self.assertEqual([len(SPELL_CATALOG[s]) for s in SCHOOL_ORDER],[64,16,17,16,6,8,10])
        for school,rows in SPELL_CATALOG.items():
            self.assertEqual(len(rows),len({r['id'] for r in rows}))
            self.assertEqual(len(rows),len({r['name'] for r in rows}))
            self.assertTrue(SPELL_METHODS[school].startswith('Cast'))

    def test_every_spell_can_be_bound_without_populating_full_catalog(self):
        original=cfg()
        for school in SCHOOL_ORDER:
            for spell in SPELL_CATALOG[school]:
                with self.subTest(school=school,spell=spell['name']):
                    result=bridge.configure(original,{'changes':[{'binding':{'layer':'base','control':'south','action':'unbound',
                        'cast':{'school':school,'spell':spell['name'],'target':'none'}}}],'expected_revision':0},Keys())
                    action=next(r for r in result['layers'] if r['name']=='base')['bindings']['south']['action']
                    self.assertEqual(result['actions'][action]['spell'],spell['name'])
                    self.assertEqual(sum(1 for a in result['actions'].values() if a.get('catalog_spell')),1)
        self.assertFalse(any(a.get('catalog_spell') for a in original['actions'].values()))

    def test_invalid_spell_target_and_recovery_are_rejected(self):
        for args in [('Unknown','Heal','none',0),('Magery','Not a spell','none',0),
                     ('Magery','Heal','enemy',0),('Bushido','Confidence','self',0),
                     ('Magery','Heal','none',-1),('Magery','Heal','none',10001)]:
            with self.subTest(args=args),self.assertRaises(ValueError): make_spell_action(*args)

    def test_different_target_or_recovery_variants_never_overwrite(self):
        names={make_spell_action('Magery','Heal',target,recovery)[0] for target in ('none','self','last') for recovery in (0,1000)}
        self.assertEqual(len(names),6)

    def test_inactive_profiles_keep_their_selected_spells_and_unused_variants_are_removed(self):
        current=cfg()
        def apply(changes):
            nonlocal current
            current=bridge.configure(current,{'changes':changes,'expected_revision':current.get('revision',0)},Keys())
        def spell(school,name,target):
            return {'binding':{'layer':'base','control':'south','action':'unbound','cast':{'school':school,'spell':name,'target':target}}}
        apply([{'assignment_profile':'Caster'},spell('Magery','Greater Heal','self')])
        caster=next(r for r in current['layers'] if r['name']=='base')['bindings']['south']['action']
        apply([{'assignment_profile':'Dexxer'},spell('Bushido','Confidence','none')])
        old=next(r for r in current['layers'] if r['name']=='base')['bindings']['south']['action']
        apply([spell('Ninjitsu','Death Strike','none')])
        self.assertIn(caster,current['actions']);self.assertNotIn(old,current['actions'])
        apply([{'assignment_profile':'Caster'}])
        self.assertEqual(next(r for r in current['layers'] if r['name']=='base')['bindings']['south']['action'],caster)

    def test_rejected_spell_keeps_batch_atomic(self):
        original=cfg();before=copy.deepcopy(original)
        with self.assertRaises(ValueError): bridge.configure(original,{'changes':[{'assignment_profile':'Caster'},{'binding':{'layer':'base','control':'south','action':'unbound','cast':{'school':'Magery','spell':'Wrong'}}}],'expected_revision':0},Keys())
        self.assertEqual(original,before)


class SpellGumpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): gump_test_support.GumpTests.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls): gump_test_support.GumpTests.tearDownClass.__func__(cls)
    render=gump_test_support.GumpTests.render

    def setUp(self):
        current=cfg();self.module['CONFIG'].clear();self.module['CONFIG'].update(current)
        self.ui.draft=copy.deepcopy(current);self.ui.changes={};self.ui.applying_request=None
        self.ui.listener.features=['spell_bindings_v1'];self.ui.listener.session='test'
        self.ui.synced=True;self.ui.layer='base';self.ui.selected='south'
        self.ui.page='spells';self.ui.spell_query='';self.ui.spell_circle=0;self.ui.spell_page=0
        self.ui.spell_school='Magery';self.ui.spell_selected=None
        self.ui.minimized=False;self.ui.confirm_exit=False

    def test_embedded_catalog_matches_host_exactly(self):
        self.assertEqual(self.module['SPELL_CATALOG'],SPELL_CATALOG)
        self.assertEqual(self.module['SPELL_METHODS'],SPELL_METHODS)

    def test_search_circle_and_legacy_pdf_names(self):
        self.assertEqual(len(self.ui.spell_rows()),64)
        self.ui.spell_query='remove trap'
        self.assertEqual([s['name'] for s in self.ui.spell_rows()],['Magic Untrap'])
        self.ui.spell_query='';self.ui.spell_circle=8
        self.assertEqual(len(self.ui.spell_rows()),8)
        self.ui.spell_circle=0;self.ui.spell_school='Spellweaving';self.ui.spell_query="nature's fury"
        self.assertEqual([s['name'] for s in self.ui.spell_rows()],['Natures Fury'])

    def test_every_school_page_has_reachable_unique_spell_buttons(self):
        for school in SCHOOL_ORDER:
            self.ui.spell_school=school;self.ui.spell_circle=0;self.ui.spell_query=''
            total=len(SPELL_CATALOG[school]);seen=set()
            for page in range((total+11)//12):
                self.ui.spell_page=page;ops=self.render(page='spells')
                ids=[args[4] for kind,args in ops if kind=='Button' and 1000<=args[4]<1064]
                self.assertEqual(len(ids),len(set(ids)));seen.update(ids)
                for kind,args in ops:
                    if kind in ('Button','Html','Background','TextEntry'):
                        self.assertTrue(0<=args[0]<800 and 0<=args[1]<660)
            self.assertEqual(seen,set(range(1000,1000+total)))

    def test_staged_spell_applies_through_real_host_validator(self):
        self.ui.spell_selected='Greater Heal';self.ui.spell_target='self';self.ui.spell_recovery=1400
        self.ui.stage_spell()
        self.assertEqual(self.ui.page,'bindings')
        before=cfg();result=bridge.configure(before,{'changes':list(self.ui.changes.values()),'expected_revision':0},Keys())
        action=next(r for r in result['layers'] if r['name']=='base')['bindings']['south']['action']
        self.assertEqual(result['actions'][action]['target'],'self')
        self.assertEqual(result['actions'][action]['recovery_ms'],1400)

    def test_old_host_has_clear_upgrade_message(self):
        self.ui.listener.features=[];self.ui.page='actions';self.ui.handle(400,None)
        self.assertEqual(self.ui.page,'actions');self.assertIn('rebuilt 3.1',self.ui.status)

    def test_requested_window_art_and_compact_close_confirmation(self):
        ops=self.render(page='bindings')
        art={args[4]:args[2:4] for kind,args in ops if kind=='Button' and args[4] in (1,2)}
        self.assertEqual(art,{1:(4015,4016),2:(4018,4019)})
        ops=self.render(minimized=True)
        art={args[4]:args[2:4] for kind,args in ops if kind=='Button'}
        self.assertEqual(art[4],(4006,4007));self.assertEqual(art[2],(4018,4019))
        self.ui.handle(2,None);self.assertFalse(self.ui.minimized);self.assertTrue(self.ui.confirm_exit)

    def test_all_137_spells_dispatch_to_the_correct_native_school(self):
        executor=self.module['Executor'];scope=executor.execute.__globals__
        calls=[]
        class Spells:
            def __getattr__(self,name): return lambda spell:calls.append((name,spell))
        class Target:
            @staticmethod
            def HasTarget(): return False
            @staticmethod
            def GetLast(): return 123
        with patch.dict(scope,Spells=Spells(),Target=Target()):
            for school in SCHOOL_ORDER:
                for spell in SPELL_CATALOG[school]:
                    name,action=make_spell_action(school,spell['name'])
                    scope['CONFIG']['actions'][name]=action
                    status,detail=executor().execute(name,1.0)
                    self.assertEqual(status,'ok',(school,spell['name'],detail))
                    self.assertEqual(calls[-1],(SPELL_METHODS[school],spell['name']))

    def test_self_target_waits_for_the_new_cursor_and_timeout_does_not_leave_pending_state(self):
        executor_class=self.module['Executor'];scope=executor_class.execute.__globals__
        calls=[]
        class Spells:
            def CastMagery(self,name): calls.append(name)
        class Target:
            active=False
            def HasTarget(self): return self.active
            def Self(self): calls.append('target-self')
        target=Target()
        with patch.dict(scope,Spells=Spells(),Target=target,now=lambda:0):
            name,action=make_spell_action('Magery','Heal','self')
            scope['CONFIG']['actions'][name]=action
            instance=executor_class();self.assertEqual(instance.execute(name,1.0)[0],'ok')
            instance.tick();self.assertEqual(calls,['Heal'])
            target.active=True;instance.tick()
            self.assertEqual(calls,['Heal','target-self']);self.assertIsNone(instance.pending_target)
            target.active=False;instance=executor_class();instance.execute(name,1.0)
            with patch.dict(scope,now=lambda:11): instance.tick()
            self.assertIsNone(instance.pending_target)

    def test_last_target_cast_rejects_before_casting_when_no_last_target_exists(self):
        executor=self.module['Executor'];scope=executor.execute.__globals__
        class Target:
            def HasTarget(self): return False
            def GetLast(self): return 0
        name,action=make_spell_action('Magery','Energy Bolt','last');scope['CONFIG']['actions'][name]=action
        with patch.dict(scope,Target=Target()):
            status,detail=executor().execute(name,1.0)
            self.assertNotEqual(status,'ok');self.assertIn('last target',detail)


    def test_control_telemetry_explains_blocked_action_and_layer(self):
        listener=self.ui.listener;listener.session='status-test';listener.last_seq=0
        listener.paused=False;self.ui.changes={};self.ui.applying_request=None
        listener.message({'type':'control','session':'status-test','seq':1,'at':0,
            'control':'south','layer':'base','down':True,'action':'unbound','blocked_reason':'unassigned'})
        self.assertIn('Unassigned',self.ui.status);self.assertIn('Normal',self.ui.status)
        listener.message({'type':'control','session':'status-test','seq':2,'at':0,
            'control':'south','layer':'lb','down':True,'action':'cast_heal','blocked_reason':'neutral_required'})
        self.assertIn('center',self.ui.status);self.assertIn('[lb]',self.ui.status)

    def test_gump_resume_explains_application_pause_instead_of_claiming_to_resume(self):
        self.ui.listener.paused=True;self.ui.listener.pause_reason='application'
        before=self.ui.request;self.ui.handle(3,None)
        self.assertEqual(self.ui.request,before)
        self.assertIn('Resume all input',self.ui.status)



if __name__=='__main__': unittest.main()
