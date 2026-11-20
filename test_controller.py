"""Hardware-free checks. Run: .controller-venv\\Scripts\\python.exe -m unittest test_controller"""
import copy
import json
import math
import os
import runpy
import shutil
import tempfile
import unittest
from pathlib import Path

import controller_bridge as bridge

ROOT = Path(__file__).resolve().parent
DEFAULTS = json.loads((ROOT / 'bindings.defaults.json').read_text(encoding='utf-8'))


class FakeDesktop:
    def key(self, name):
        return name


class BridgeTests(unittest.TestCase):
    def test_cursor_curve_keeps_direction_and_top_speed(self):
        x, y = bridge.cursor_curve(0.3, 0.4, 2.0)
        self.assertAlmostEqual(math.hypot(x, y), 0.25)
        self.assertAlmostEqual(math.atan2(y, x), math.atan2(0.4, 0.3))
        self.assertAlmostEqual(math.hypot(*bridge.cursor_curve(0.6, 0.8, 2.5)), 1.0)
        self.assertEqual(bridge.cursor_curve(0, 0, 2), (0, 0))

    def test_window_matching(self):
        focus = {'window_title_contains': ['ExampleMage - ClassicUO'], 'process_names': ['ClassicUO.exe']}
        self.assertTrue(bridge.window_matches(focus, 'ExampleMage - ClassicUO [dev] - 1.1.0.334', 'ClassicUO.exe'))
        self.assertFalse(bridge.window_matches(focus, 'Othername - ClassicUO [dev] - 1.2', 'classicuo.exe'))
        self.assertFalse(bridge.window_matches(focus, 'ExampleMage (Atlantic) - Enhanced Razor', 'ClassicUO.exe'))
        self.assertFalse(bridge.window_matches(focus, 'Notepad', 'notepad.exe'))

    def test_absolute_coordinates_round_trip_to_exact_pixel(self):
        for origin, extent in [(0, 1920), (-1920, 5760), (0, 2560)]:
            for pixel in (origin, origin + 1, origin + extent // 2, origin + extent - 1):
                value = bridge.WindowsPointer.normalize(pixel, origin, extent)
                self.assertTrue(0 <= value <= 65535)
                self.assertEqual(value * extent // 65536 + origin, pixel)

    def test_migration_adds_v2_settings_once(self):
        cfg = copy.deepcopy(DEFAULTS)
        cfg['controller_ui_version']=1
        cfg['focus'].pop('process_names')
        cfg['desktop'].pop('cursor_curve')
        self.assertTrue(bridge.migrate_controller_ui(cfg))
        self.assertEqual(cfg['focus']['process_names'], ['ClassicUO.exe'])
        self.assertEqual(cfg['desktop']['cursor_curve'], 1.6)
        self.assertIn('mouse_left', cfg['actions'])
        self.assertFalse(bridge.migrate_controller_ui(cfg))

    def test_existing_v1_config_keeps_bindings(self):
        cfg = json.loads((ROOT / 'bindings.defaults.json').read_text(encoding='utf-8'))
        before = copy.deepcopy(cfg['layers'])
        bridge.migrate_controller_ui(cfg)
        self.assertEqual(cfg['layers'], before)
        self.assertEqual(cfg['controller_ui_version'], 2)

    def test_configure_cursor_settings(self):
        cfg = copy.deepcopy(DEFAULTS)
        bridge.migrate_controller_ui(cfg)
        cfg['revision'] = 3
        changes = [{'setting': {'name': 'cursor_curve', 'value': 2.2}},
                   {'setting': {'name': 'cursor_pixels_per_second', 'value': 1800}}]
        result = bridge.configure(cfg, {'changes': changes, 'expected_revision': 3}, FakeDesktop())
        self.assertEqual(result['desktop']['cursor_curve'], 2.2)
        self.assertEqual(result['desktop']['cursor_pixels_per_second'], 1800)
        self.assertEqual(result['revision'], 4)
        with self.assertRaises(ValueError):
            bridge.configure(cfg, {'setting': {'name': 'cursor_curve', 'value': 4}}, FakeDesktop())

    def test_desktop_pointer_applies_curve(self):
        moves = []
        desktop = bridge.DesktopOutput.__new__(bridge.DesktopOutput)
        desktop.cfg = {'cursor_pixels_per_second': 1000, 'cursor_curve': 2.0, 'scroll_per_second': 10}
        desktop.windows_pointer = type('P', (), {'move': lambda self, dx, dy: moves.append((dx, dy)) or True})()
        desktop.fraction_x = desktop.fraction_y = desktop.scroll_fraction = 0.0
        desktop.pointer_notice_at = float('inf')
        for _ in range(10):
            desktop.pointer(0.5, 0.0, 0.01, False)
        self.assertEqual(sum(dx for dx, _ in moves), 25)


class GumpTests(unittest.TestCase):
    """Render every page through stubbed Razor APIs, in a temp copy so no logs are written here."""
    @classmethod
    def setUpClass(cls):
        os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
        import gump_preview
        cls.gumps = gump_preview.RecordingGumps()
        gump_preview.install_stubs(cls.gumps)
        cls.work = Path(tempfile.mkdtemp(prefix='controller_test_'))
        for name in ('razor_listener.py', 'bindings.json'):
            shutil.copy(ROOT / ('bindings.defaults.json' if name=='bindings.json' else name), cls.work / name)
        cls.module = runpy.run_path(str(cls.work / 'razor_listener.py'), run_name='controller_test')
        cls.ui = cls.module['ui']
        cls.GumpData = gump_preview.GumpData

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work, ignore_errors=True)

    def render(self, **state):
        for key, value in state.items():
            setattr(self.ui.listener if key in ('paused', 'notice', 'session') else self.ui, key, value)
        captured = []
        self.gumps.CreateGump = lambda *a: captured.append(self.GumpData()) or captured[-1]
        self.ui.draw()
        return captured[0].ops

    def test_every_page_fits_and_uses_known_buttons(self):
        for state in [dict(page='bindings', session='s'), dict(page='bindings', layer='lb'),
                      dict(page='actions', selected='north', layer='base'), dict(page='settings'),
                      dict(page='directions'), dict(confirm_exit=True), dict(confirm_exit=False, minimized=True)]:
            ops = self.render(**state)
            width, height = (300, 62) if self.ui.minimized else (self.ui.WIDTH, self.ui.HEIGHT)
            for kind, args in ops:
                if kind in ('Button', 'Html', 'Background', 'ImageTiled', 'TextEntry'):
                    self.assertTrue(0 <= args[0] < width and 0 <= args[1] < height, (state, kind, args))
            ids = [args[4] for kind, args in ops if kind == 'Button']
            self.assertTrue(ids, state)
        self.ui.minimized = False

    def test_stick_emblems_follow_roles(self):
        self.ui.draft['input']['movement_stick'], self.ui.draft['input']['mouse_stick'] = 'right', 'left'
        ops = self.render(page='bindings', minimized=False, confirm_exit=False)
        art = {args[4]: args[2] for kind, args in ops if kind == 'Button' and args[4] in (40, 41) and args[2] != 1896}
        self.assertEqual(art, {40: 5545, 41: 5549})
        self.ui.draft['input']['mouse_stick'] = 'off'
        ops = self.render()
        art = {args[4]: args[2] for kind, args in ops if kind == 'Button' and args[4] in (40, 41) and args[2] != 1896}
        self.assertEqual(art, {40: 1417, 41: 5549})

    def test_notice_message_reaches_status(self):
        listener = self.ui.listener
        listener.session, listener.last_seq = 'abc', 0
        listener.message({'type': 'notice', 'session': 'abc', 'seq': 1, 'at': 0,
                          'level': 'error', 'text': bridge.PRIVILEGE_NOTICE})
        self.assertEqual(self.ui.status, bridge.PRIVILEGE_NOTICE)
        ops = self.render(page='bindings')
        self.assertTrue(any('administrator' in str(args) for kind, args in ops if kind == 'Html'))
        listener.message({'type': 'notice', 'session': 'abc', 'seq': 2, 'at': 0, 'level': 'ok', 'text': ''})
        self.assertEqual(listener.notice, '')

    def test_profiles_page_and_correct_dpad_up_art(self):
        cfg=copy.deepcopy(DEFAULTS)
        bridge.migrate_controller_ui(cfg)
        self.module['CONFIG'].update(cfg)
        self.ui.draft=copy.deepcopy(cfg)
        ops=self.render(page='profiles',minimized=False,confirm_exit=False)
        ids={args[4] for kind,args in ops if kind=='Button'}
        self.assertTrue({70,71,72,73}.issubset(ids))
        ops=self.render(page='bindings')
        control_id=100+self.ui.CONTROLS.index('dpad_up')
        art=[args[2:4] for kind,args in ops if kind=='Button' and args[4]==control_id and args[2]!=2103]
        self.assertEqual(art,[(9900,9901)])


    def test_controller_silhouette_and_signature_keep_bindings_interactive(self):
        outline=self.module['controller_outline_rects']()
        self.assertIs(outline,self.module['controller_outline_rects']())
        self.assertTrue(100 < len(outline) < 1000)
        for x,y,width,height in outline:
            self.assertTrue(16<=x<x+width<=500 and 108<=y<y+height<=560)
        ops=self.render(page='bindings',minimized=False,confirm_exit=False)
        self.assertTrue(any(kind=='Item' and args[2:]==(0x20F6,1152) for kind,args in ops))
        self.assertTrue(any(kind=='Label' and args[2:]==(1153,'@MysticLlama') for kind,args in ops))
        buttons={args[4] for kind,args in ops if kind=='Button'}
        self.assertTrue({100+i for i in range(16)}.issubset(buttons))



if __name__ == '__main__':
    unittest.main()
