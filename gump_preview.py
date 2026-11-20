#!/usr/bin/env python3
"""Render the Controller Studio Gump to PNG files without UO or Razor running.

Uses your installed client's Gumpart.mul/Gumpidx.mul for exact art. Fonts are
approximations of the UO fonts, so check final text fit in-game.

    .controller-venv\\Scripts\\python.exe gump_preview.py [--uo-dir DIR] [--backdrop PNG]
"""
import argparse
import builtins
import html
import os
import re
import runpy
import shutil
import struct
import sys
import tempfile
import types
from pathlib import Path

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
import pygame

ROOT = Path(__file__).resolve().parent
HUES = {1152:(240, 240, 240), 53:(255, 214, 90), 68:(90, 230, 90), 33:(255, 90, 90)}


class GumpArt:
    def __init__(self, folder):
        self.index = (Path(folder) / 'Gumpidx.mul').read_bytes()
        self.data = (Path(folder) / 'Gumpart.mul').open('rb')
        self.cache = {}

    def get(self, gid):
        if gid in self.cache:
            return self.cache[gid]
        surface = None
        if 0 <= gid * 12 < len(self.index):
            offset, length, extra = struct.unpack_from('<iii', self.index, gid * 12)
            if offset >= 0 and length > 0:
                surface = self.decode(offset, length, (extra >> 16) & 0xFFFF, extra & 0xFFFF)
        self.cache[gid] = surface
        return surface

    def decode(self, offset, length, width, height):
        self.data.seek(offset)
        raw = self.data.read(length)
        surface = pygame.Surface((width, height), pygame.SRCALPHA)
        rows = struct.unpack_from('<%di' % height, raw, 0)
        for y in range(height):
            end = rows[y + 1] * 4 if y + 1 < height else length
            x = 0
            for position in range(rows[y] * 4, end, 4):
                color, run = struct.unpack_from('<HH', raw, position)
                if color:
                    rgb = (((color >> 10) & 31) * 8, ((color >> 5) & 31) * 8, (color & 31) * 8, 255)
                    pygame.draw.line(surface, rgb, (x, y), (x + run - 1, y))
                x += run
        return surface


class GumpData:
    def __init__(self):
        self.ops = []
        self.gumpDefinition = self.gumpStrings = ''


class RecordingGumps:
    """Records the subset of the Razor Enhanced Gumps API used by the listener."""
    def __init__(self):
        self.sent = None

    def __getattr__(self, name):
        if name.startswith('Add'):
            return lambda gd, *args: gd.ops.append((name[3:], args))
        raise AttributeError(name)

    def CreateGump(self, *args):
        return GumpData()

    def CloseGump(self, *args):
        pass

    def SendGump(self, gid, serial, x, y, definition, strings):
        pass

    def GetGumpData(self, gid):
        return None


def install_stubs(gumps):
    class Anything:
        def __init__(self, *a, **k): pass
        def __getattr__(self, name): return Anything()
        def __call__(self, *a, **k): return Anything()
    stopwatch = types.SimpleNamespace(StartNew=lambda: types.SimpleNamespace(
        Elapsed=types.SimpleNamespace(TotalSeconds=0.0)))
    modules = {
        'clr': types.SimpleNamespace(AddReference=lambda *a: None),
        'System': types.SimpleNamespace(Byte=int, Array=Anything()),
        'System.Diagnostics': types.SimpleNamespace(Stopwatch=stopwatch, Process=types.SimpleNamespace(GetCurrentProcess=lambda:types.SimpleNamespace(Id=1234))),
        'System.Collections.Generic': types.SimpleNamespace(List=Anything()),
        'System.Text': types.SimpleNamespace(Encoding=Anything()),
        'System.Net': types.SimpleNamespace(IPAddress=Anything()),
        'System.Net.Sockets': types.SimpleNamespace(TcpClient=Anything, SocketException=Exception,
                                                    SocketFlags=Anything()),
    }
    sys.modules.update(modules)
    builtins.basestring = str
    builtins.Gumps = gumps
    builtins.Misc = types.SimpleNamespace(SendMessage=lambda *a: None, Pause=lambda *a: None)
    builtins.Player = types.SimpleNamespace(Connected=False, Serial=1)
    for name in ('Target', 'Items', 'Mobiles', 'Spells'):
        setattr(builtins, name, Anything())


class Renderer:
    def __init__(self, art, backdrop):
        self.art = art
        self.backdrop = backdrop
        pygame.font.init()
        self.label_font = pygame.font.SysFont('tahoma', 12, bold=True)
        self.html_font = pygame.font.SysFont('tahoma', 12)

    @staticmethod
    def bounds(op):
        kind, args = op
        if kind in ('Background', 'ImageTiled', 'AlphaRegion', 'Html', 'TextEntry', 'LabelCropped'):
            return pygame.Rect(args[0], args[1], args[2], args[3])
        return pygame.Rect(args[0], args[1], 1, 1)

    def render(self, ops, size, origin=(20, 20)):
        canvas = pygame.transform.smoothscale(self.backdrop, (size[0] + origin[0] * 2, size[1] + origin[1] * 2))
        canvas = canvas.convert()
        # Checkertrans makes earlier elements under the region translucent, as ClassicUO does.
        alpha = [255] * len(ops)
        for index, op in enumerate(ops):
            if op[0] == 'AlphaRegion':
                region = self.bounds(op)
                for prior in range(index):
                    if ops[prior][0] in ('Background', 'ImageTiled') and region.colliderect(self.bounds(ops[prior])):
                        alpha[prior] = min(alpha[prior], 140)
        for op, opacity in zip(ops, alpha):
            if opacity == 255:
                self.draw(canvas, op, origin)
                continue
            layer = pygame.Surface(canvas.get_size(), pygame.SRCALPHA)
            self.draw(layer, op, origin)
            layer.fill((255, 255, 255, opacity), special_flags=pygame.BLEND_RGBA_MULT)
            canvas.blit(layer, (0, 0))
        return canvas

    def tile(self, target, gid, rect):
        image = self.art.get(gid)
        if image is None:
            return
        clip = target.get_clip()
        target.set_clip(rect)
        for y in range(rect.y, rect.bottom, image.get_height()):
            for x in range(rect.x, rect.right, image.get_width()):
                target.blit(image, (x, y))
        target.set_clip(clip)

    def background(self, target, gid, rect):
        parts = [self.art.get(gid + i) for i in range(9)]
        if any(p is None for p in parts):
            return
        tl, t, tr, l, c, r, bl, b, br = parts
        self.tile(target, gid + 4, pygame.Rect(rect.x + l.get_width(), rect.y + t.get_height(),
                                               rect.w - l.get_width() - r.get_width(), rect.h - t.get_height() - b.get_height()))
        self.tile(target, gid + 1, pygame.Rect(rect.x + tl.get_width(), rect.y, rect.w - tl.get_width() - tr.get_width(), t.get_height()))
        self.tile(target, gid + 7, pygame.Rect(rect.x + bl.get_width(), rect.bottom - b.get_height(), rect.w - bl.get_width() - br.get_width(), b.get_height()))
        self.tile(target, gid + 3, pygame.Rect(rect.x, rect.y + tl.get_height(), l.get_width(), rect.h - tl.get_height() - bl.get_height()))
        self.tile(target, gid + 5, pygame.Rect(rect.right - r.get_width(), rect.y + tr.get_height(), r.get_width(), rect.h - tr.get_height() - br.get_height()))
        target.blit(tl, rect.topleft)
        target.blit(tr, (rect.right - tr.get_width(), rect.y))
        target.blit(bl, (rect.x, rect.bottom - bl.get_height()))
        target.blit(br, (rect.right - br.get_width(), rect.bottom - br.get_height()))

    def text(self, target, font, text, color, rect, align=None):
        words, lines, line = text.split(' '), [], ''
        for word in words:
            trial = (line + ' ' + word).strip()
            if font.size(trial)[0] > rect.w and line:
                lines.append(line)
                line = word
            else:
                line = trial
        lines.append(line)
        clip = target.get_clip()
        target.set_clip(rect)
        for number, content in enumerate(lines):
            image = font.render(content, True, color)
            x = rect.x + {'center': (rect.w - image.get_width()) // 2,
                          'right': rect.w - image.get_width()}.get(align, 0)
            target.blit(image, (x, rect.y + number * 16))
        target.set_clip(clip)

    def draw(self, target, op, origin):
        kind, args = op
        ox, oy = origin
        if kind == 'Background':
            x, y, w, h, gid = args
            self.background(target, gid, pygame.Rect(x + ox, y + oy, w, h))
        elif kind == 'ImageTiled':
            x, y, w, h, gid = args
            self.tile(target, gid, pygame.Rect(x + ox, y + oy, w, h))
        elif kind in ('Button', 'Image'):
            image = self.art.get(args[2])
            if image is not None:
                target.blit(image, (args[0] + ox, args[1] + oy))
        elif kind == 'LabelCropped':
            x, y, w, h, hue, text = args
            self.text(target, self.label_font, text, HUES.get(hue, (220, 220, 220)), pygame.Rect(x + ox, y + oy, w, h))
        elif kind == 'Html':
            x, y, w, h, body = args[:5]
            color = re.search(r'COLOR=#([0-9A-Fa-f]{6})', body)
            rgb = tuple(int(color.group(1)[i:i + 2], 16) for i in (0, 2, 4)) if color else (230, 230, 230)
            align = 'center' if '<CENTER>' in body else ('right' if 'ALIGN=RIGHT' in body else None)
            self.text(target, self.html_font, html.unescape(re.sub(r'<[^>]+>', '', body)), rgb,
                      pygame.Rect(x + ox, y + oy, w, h), align)
        elif kind == 'TextEntry':
            x, y, w, h, hue, _, text = args
            self.text(target, self.label_font, text, HUES.get(hue, (230, 230, 230)), pygame.Rect(x + ox, y + oy, w, h))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--uo-dir', help='UO data folder containing Gumpart.mul (auto-detected)')
    parser.add_argument('--backdrop', help='Optional game screenshot shown through translucent areas')
    parser.add_argument('--out', default=str(ROOT / 'gump_preview'))
    args = parser.parse_args()
    pygame.display.init()
    pygame.display.set_mode((1, 1), pygame.HIDDEN)
    candidates = [args.uo_dir] if args.uo_dir else [
        r'C:\Program Files (x86)\Ultima Online', r'C:\Program Files (x86)\Ultima Online Classic',
        r'C:\Program Files (x86)\Electronic Arts\Ultima Online Classic', r'C:\Program Files\Ultima Online Classic']
    folder = next((c for c in candidates if (Path(c) / 'Gumpidx.mul').is_file()), None)
    if folder is None:
        parser.error('Gumpart.mul/Gumpidx.mul not found; pass --uo-dir with your UO data folder')
    art = GumpArt(folder)
    if args.backdrop:
        backdrop = pygame.image.load(args.backdrop).convert()
    else:
        backdrop = pygame.Surface((64, 64))
        backdrop.fill((38, 44, 40))
    gumps = RecordingGumps()
    install_stubs(gumps)
    # Run a copy so the listener's log file is not written into this folder.
    work = Path(tempfile.mkdtemp(prefix='gump_preview_'))
    shutil.copy(ROOT / 'razor_listener.py', work / 'razor_listener.py')
    import json
    from controller_bridge import migrate_controller_ui, save_config
    cfg=json.loads((ROOT / 'bindings.defaults.json').read_text(encoding='utf-8'))
    migrate_controller_ui(cfg)
    cfg['layers']=cfg['assignment_profiles']['Caster']
    cfg['active_assignment_profile']='Caster'
    save_config(work/'bindings.json',cfg)
    module = runpy.run_path(str(work / 'razor_listener.py'), run_name='gump_preview')
    ui = module['ui']
    ui.listener.session = 'preview'
    ui.synced = True
    ui.last_control = 'dpad_left'
    ui.status = 'Connected. Select any control to edit.'
    renderer = Renderer(art, backdrop)
    out = Path(args.out)
    out.mkdir(exist_ok=True)

    def snapshot(name, **state):
        for key, value in state.items():
            target = ui.listener if key in ('paused', 'notice') else ui
            setattr(target, key, value)
        captured = []
        original = gumps.CreateGump
        gumps.CreateGump = lambda *a: captured.append(GumpData()) or captured[-1]
        try:
            ui.draw()
        finally:
            gumps.CreateGump = original
        size = (300, 62) if ui.minimized else (ui.WIDTH, ui.HEIGHT)
        pygame.image.save(renderer.render(captured[0].ops, size), str(out / (name + '.png')))
        print('wrote', out / (name + '.png'))

    snapshot('1_bindings', page='bindings')
    snapshot('2_bindings_lb_layer', layer='lb')
    snapshot('3_actions', layer='base', page='actions', selected='north')
    snapshot('4_sticks', page='settings')
    snapshot('5_directions', page='directions')
    notice = ('UO is running as administrator but the controller host is not. Windows may '
              'blocks the cursor and mouse clicks.')
    snapshot('6_privilege_notice', page='bindings', notice=notice, status=notice)
    snapshot('8_profiles',page='profiles',notice='',minimized=False)
    snapshot('9_spells_magery',page='spells',notice='',minimized=False)
    snapshot('7_minimized', notice='', minimized=True, status='Connected. Select any control to edit.')
    shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    main()
