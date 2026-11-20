#!/usr/bin/env python3
"""Controller Studio CPython host. No Razor imports. python controller_bridge.py --help."""
from __future__ import annotations
import argparse
import copy
import ctypes
import json
import hashlib
import hmac
import logging
from logging.handlers import RotatingFileHandler
import math
import os
from pathlib import Path
import queue
import secrets
import socket
import threading
import time

from spell_catalog import make_spell_action
from action_catalog import native_actions
from hotkeys import normalize_hotkey, HotkeyWorker
from input_validation import mapping_issues,source_identity

LOG = logging.getLogger('controller')
VERSION = '4.0.0-beta.1'
DIRECTIONS = ('North', 'Right', 'East', 'Down', 'South', 'Left', 'West', 'Up')
DESKTOP_SETTINGS = ('cursor_pixels_per_second', 'cursor_curve')


def joystick_connected(pygame_module, joy):
    """Check current SDL instance IDs using the supported joystick API.

    Joystick.get_init alone cannot establish physical attachment, and
    get_attached is not a Joystick method in pygame/pygame-ce.
    """
    try:
        if not joy.get_init():
            return False
        identity = joy.get_instance_id()
        for index in range(pygame_module.joystick.get_count()):
            candidate = pygame_module.joystick.Joystick(index)
            if candidate.get_instance_id() == identity:
                return True
        return False
    except pygame_module.error:
        # USB/Bluetooth topology can change between count and lookup.
        return False


def radial(x, y, deadzone):
    magnitude = min(1.0, math.hypot(x, y))
    if magnitude <= deadzone:
        return 0.0, 0.0, 0.0
    scale = (magnitude - deadzone) / (1.0 - deadzone)
    angle = math.atan2(y, x)
    return math.cos(angle) * scale, math.sin(angle) * scale, scale


def cursor_curve(x, y, exponent):
    """Exponential response: fine aiming at light deflection, full speed at the rim."""
    magnitude = math.hypot(x, y)
    if magnitude <= 0 or exponent == 1:
        return x, y
    scale = min(1.0, magnitude) ** exponent / magnitude
    return x * scale, y * scale


def direction(x, y):
    # Stick up is North. RE uses Right/Down/Left/Up for diagonal directions.
    return DIRECTIONS[int(math.floor((math.atan2(x, -y) + math.pi / 8) / (math.pi / 4))) % 8]


def load_config(path):
    with open(path, encoding='utf-8') as stream:
        cfg = json.load(stream)
    if cfg['bridge']['host'] != '127.0.0.1':
        raise ValueError('Only IPv4 loopback 127.0.0.1 is allowed')
    if cfg['bridge']['mode'] not in ('socket', 'hotkey'):
        raise ValueError('bridge.mode must be socket or hotkey')
    if not 1 <= int(cfg['bridge']['port']) <= 65535:
        raise ValueError('Invalid port')
    if not 30 <= cfg['poll_hz'] <= 240:
        raise ValueError('poll_hz must be 30..240')
    for key in ('left_deadzone', 'right_deadzone'):
        if not 0 <= cfg['input'][key] < 1:
            raise ValueError('Invalid deadzone: ' + key)
    if not 0 <= cfg['input']['trigger_release'] < cfg['input']['trigger_press'] <= 1:
        raise ValueError('Trigger thresholds require release < press')
    if cfg['preset'] not in cfg['presets']:
        raise ValueError('Unknown preset')
    if not 1 <= cfg['bridge']['queue_limit'] <= 1024:
        raise ValueError('queue_limit must be 1..1024')
    if not 0 < cfg['input']['move_threshold'] <= cfg['input']['run_threshold'] <= 1:
        raise ValueError('Movement thresholds require 0 < move <= run <= 1')
    for preset in cfg['presets'].values():
        for key in ('left_stick', 'right_stick'):
            if len(preset[key]) != 2 or any(not isinstance(n, int) or n < 0 for n in preset[key]):
                raise ValueError('Stick axes must be two nonnegative integers')
        for source in preset['controls'].values():
            types = [key for key in ('button', 'hat', 'axis') if key in source]
            if len(types) != 1 or not isinstance(source[types[0]], int) or source[types[0]] < 0:
                raise ValueError('Each control needs exactly one nonnegative button/hat/axis ID')
            if 'axis' in source and source['rest'] == source['full']:
                raise ValueError('Axis rest and full cannot be equal')
            if 'hat' in source and (source['component'] not in (0, 1) or source['sign'] not in (-1, 1)):
                raise ValueError('Invalid hat component/sign')
    for layer in cfg['layers']:
        for binding in layer['bindings'].values():
            if binding['action'] not in cfg['actions']:
                raise ValueError('Unknown mapped action: ' + binding['action'])
            if binding.get('repeat_ms', 0) and binding['repeat_ms'] < 50:
                raise ValueError('repeat_ms must be zero or >= 50')
    return cfg


def save_config(path, cfg):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(cfg, indent=2) + '\n', encoding='utf-8')
    for attempt in range(5):
        try:
            os.replace(temporary, path)
            break
        except PermissionError:
            if attempt == 4: raise
            time.sleep(.005)


PROFILE_CONTROLS = ['south','east','west','north','lb','rb','lt','rt','back','start','ls','rs',
                    'dpad_up','dpad_down','dpad_left','dpad_right','p1','p2']


def single_layer(layers):
    base=next((row for row in layers if row.get('name')=='base'),None)
    if base is None:base=next((row for row in layers if not row.get('modifiers')),{'bindings':{}})
    return [{'name':'base','modifiers':[],'bindings':copy.deepcopy(base['bindings'])}]


def assignment_template(cfg, name):
    bindings={c:{'action':'unbound','repeat_ms':0} for c in PROFILE_CONTROLS}
    if name!='Blank':
        controls=cfg['presets'][cfg['preset']]['controls']
        common={'dpad_up':'drink_heal','dpad_down':'drink_refresh','dpad_right':'cycle_target','lt':'target_self','back':'cancel_target'}
        common['p1' if 'p1' in controls else 'rs']='mouse_left'
        common['p2' if 'p2' in controls else 'rt']='mouse_right'
        common.update({'south':'cast_heal','east':'cast_cure','west':'cast_greater_heal','north':'cast_energy_bolt','start':'meditate'} if name=='Caster' else
            {'south':'bandage_self','east':'attack_last','west':'primary_ability','north':'secondary_ability'})
        for control,action in common.items():
            if action in cfg['actions']:bindings[control]={'action':action,'repeat_ms':0}
    return [{'name':'base','modifiers':[],'bindings':bindings}]


def ensure_assignment_profiles(cfg):
    if 'assignment_profiles' in cfg: return False
    cfg['assignment_profiles']={'Custom':copy.deepcopy(cfg['layers'])}
    cfg['active_assignment_profile']='Custom'
    for name in ('Caster','Dexxer','Blank'):
        cfg['assignment_profiles'][name]=assignment_template(cfg,name)
    return True


def store_active_profile(cfg):
    if 'assignment_profiles' in cfg:
        cfg['assignment_profiles'][cfg.get('active_assignment_profile','Custom')]=copy.deepcopy(cfg['layers'])



def migrate_controller_ui(cfg):
    added = False
    for name, definition in native_actions().items():
        if name not in cfg['actions']:
            cfg['actions'][name] = definition
            added = True
    cfg['actions'].setdefault('mouse_left', {'type':'mouse_button','button':'left'})
    cfg['actions'].setdefault('mouse_right', {'type':'mouse_button','button':'right'})
    cfg['actions'].setdefault('unbound', {'type':'none'})
    for heading in DIRECTIONS:
        cfg['actions'].setdefault('step_'+heading.lower(), {'type':'step','direction':heading,'run':False,'cooldown_ms':150})
    version = cfg.get('controller_ui_version', 0)
    if version < 1:
        migrate_v1(cfg)
    if version < 2:
        # 2.1: process-name focus matching and a cursor response curve.
        cfg['focus'].setdefault('process_names', ['ClassicUO.exe'])
        cfg['desktop'].setdefault('cursor_curve', 1.6)
        cfg['controller_ui_version'] = 2
    profiles_added = ensure_assignment_profiles(cfg)
    cfg['desktop'].setdefault('global_cursor', True)
    if cfg.get('assignment_schema')!=4:
        cfg['layers']=single_layer(cfg['layers'])
        cfg['assignment_profiles']={name:single_layer(rows) for name,rows in cfg['assignment_profiles'].items()}
        cfg['input'].pop('shift_layer_enabled',None)
        cfg['modifier_controls']=[]
        cfg['razor'].pop('capture_weapons_on_start',None)
        cfg['assignment_schema']=4;added=True
    if 'show_gump' not in cfg['razor']:
        cfg['razor']['show_gump']=False; added=True
    return version < 2 or added or profiles_added


def migrate_v1(cfg):
    cfg['actions']['mouse_left'] = {'type':'mouse_button', 'button':'left'}
    cfg['actions']['mouse_right'] = {'type':'mouse_button', 'button':'right'}
    for layer in cfg['layers']:
        layer['bindings']['rs'] = {'action':'mouse_left', 'repeat_ms':0}
        layer['bindings']['rt'] = {'action':'mouse_right', 'repeat_ms':0}
    for index, heading in enumerate(DIRECTIONS):
        cfg['actions']['step_' + heading.lower()] = {'type':'step', 'direction':heading, 'run':False, 'cooldown_ms':150}
    cfg['actions']['unbound'] = {'type':'none'}
    cfg['controller_ui_version'] = 1


def prune_spell_actions(cfg):
    """Retain only chosen variants, including inactive profiles; don't transmit a huge catalog."""
    layers=list(cfg['layers'])
    for saved in cfg.get('assignment_profiles',{}).values(): layers.extend(saved)
    used={binding['action'] for layer in layers for binding in layer['bindings'].values()}
    for name,action in list(cfg['actions'].items()):
        if action.get('catalog_spell') and name not in used:
            del cfg['actions'][name]


def profile(cfg):
    result = copy.deepcopy({key:cfg[key] for key in ('layers','actions','input','desktop')})
    result['assignment_profiles'] = copy.deepcopy(cfg.get('assignment_profiles',{}))
    result['active_assignment_profile'] = cfg.get('active_assignment_profile','Custom')
    result['features'] = ['spell_bindings_v1']
    result['gump_enabled'] = cfg['razor'].get('show_gump',False)
    result['revision'] = cfg.get('revision', 0)
    result['available_controls'] = sorted(cfg['presets'][cfg['preset']]['controls'])
    return result


def configure(cfg, payload, desktop):
    """Validate a complete candidate before touching current settings."""
    candidate = copy.deepcopy(cfg)
    if 'changes' in payload:
        changes = payload['changes']
        if not isinstance(changes, list) or len(changes) > 80:
            raise ValueError('Invalid configuration batch')
        if payload.get('expected_revision') != cfg.get('revision', 0):
            raise ValueError('Settings changed since editing began. Cancel to reload, then edit again.')
        for change in changes:
            if not isinstance(change, dict) or set(change) not in ({'binding'}, {'setting'}, {'assignment_profile'}):
                raise ValueError('Invalid edit')
        ordered = [c for c in changes if 'assignment_profile' in c] + [c for c in changes if 'assignment_profile' not in c]
        for change in ordered:
            candidate = configure(candidate, change, desktop)
        store_active_profile(candidate)
        prune_spell_actions(candidate)
        candidate['revision'] = cfg.get('revision', 0) + 1
        return candidate
    if 'assignment_profile' in payload:
        ensure_assignment_profiles(candidate)
        name = payload['assignment_profile']
        if name not in candidate['assignment_profiles']:
            raise ValueError('Unknown assignment profile')
        store_active_profile(candidate)
        candidate['layers'] = single_layer(candidate['assignment_profiles'][name])
        candidate['active_assignment_profile'] = name
    if 'binding' in payload:
        data = payload['binding']
        if data.get('layer')!='base':raise ValueError('Extra assignment layers were removed; choose the control directly')
        layer = next((row for row in candidate['layers'] if row['name'] == data['layer']), None)
        if layer is None or data['control'] not in candidate['presets'][candidate['preset']]['controls']:
            raise ValueError('Unknown layer/control')
        action = data['action']
        if data.get('cast') is not None:
            if data.get('keys'): raise ValueError('Choose either a spell or keyboard chord')
            cast=data['cast']
            if not isinstance(cast,dict) or set(cast)-{'school','spell','target','recovery_ms'}:
                raise ValueError('Invalid spell binding')
            action,definition=make_spell_action(cast['school'],cast['spell'],cast.get('target','none'),cast.get('recovery_ms'))
            candidate['actions'][action]=definition
        if data.get('keys'):
            keys = normalize_hotkey(data['keys'])
            if not keys or len(keys) > 4:
                raise ValueError('Use a key chord such as ctrl+f1')
            for key in keys:
                desktop.key(key)
            action = 'key_' + candidate.get('active_assignment_profile','Custom') + '_' + data['layer'] + '_' + data['control']
            candidate['actions'][action] = {'type':'hotkey', 'keys':keys}
        if action not in candidate['actions']:
            raise ValueError('Unknown action')
        repeat = 220 if candidate['actions'][action]['type'] == 'step' else 0
        layer['bindings'][data['control']] = {'action':action, 'repeat_ms':repeat}
    if 'setting' in payload:
        data = payload['setting']
        limits = {'left_deadzone':(.05,.6), 'right_deadzone':(.05,.6),
                  'move_threshold':(.1,.7), 'run_threshold':(.4,1),
                  'cursor_pixels_per_second':(100,2500), 'cursor_curve':(1,3)}
        name = data['name']
        if name == 'show_gump':
            if not isinstance(data['value'], bool): raise ValueError('Expected true or false')
            candidate['razor'][name] = data['value']
            return candidate
        if name == 'global_cursor':
            if not isinstance(data['value'], bool): raise ValueError('Expected true or false')
            candidate['desktop'][name] = data['value']
            return candidate
        if name in ('movement_stick', 'mouse_stick'):
            if data['value'] not in ('left', 'right', 'off'):
                raise ValueError('Unknown stick role')
            candidate['input'][name] = data['value']
            return candidate
        if name in ('run_control', 'scroll_control'):
            if data['value'] not in ('', 'ls', 'rs', 'lb', 'rb'):
                raise ValueError('Unknown modifier')
            candidate['input'][name] = data['value']
            return candidate
        value = float(data['value'])
        if name not in limits or not math.isfinite(value) or not limits[name][0] <= value <= limits[name][1]:
            raise ValueError('Setting outside supported range')
        group = 'desktop' if name in DESKTOP_SETTINGS else 'input'
        candidate[group][name] = value
        if candidate['input']['move_threshold'] > candidate['input']['run_threshold']:
            raise ValueError('Walk threshold must be below run threshold')
    store_active_profile(candidate)
    return candidate


def effective_binding(cfg, layer, control):
    base=next((row for row in cfg['layers'] if row.get('name')=='base'),{'bindings':{}})
    return base['bindings'].get(control)


class OutputRouter:
    def __init__(self, cfg, engine, desktop):
        self.cfg, self.engine, self.desktop = cfg, engine, desktop
        self.current_control = None
        self.mouse_held = {}
        self.gump_paused = False
        self.desktop_paused = False
        self.game_allowed = True
        self.game_block_reason = ''
        self.lease_until = 0.0
        self.last_input = {}
        self.mouse_result = {}
        self.pending_mouse_releases=set();self.next_mouse_retry=0.;self.mouse_warning_at=-100.
        self.suppressed_game_buttons = set()

    @property
    def paused(self):
        return self.desktop_paused or self.gump_paused

    @paused.setter
    def paused(self, value):
        # Preserve the router API; application pause always has its own owner.
        self.gump_paused = bool(value)

    @property
    def pause_reason(self):
        return 'application' if self.desktop_paused else 'gump' if self.gump_paused else ''

    def begin_control(self, name):
        self.current_control = name

    def control(self, name, layer, down):
        row=next((row for row in self.cfg['layers'] if row['name']==layer),{'bindings':{}})
        action=(effective_binding(self.cfg,row,name) or {}).get('action','unbound')
        kind=self.cfg['actions'].get(action,{}).get('type','none')
        reason=''
        if kind=='none': reason='modifier' if name in row.get('modifiers',[]) or name in (self.cfg['input'].get('run_control'),self.cfg['input'].get('scroll_control')) else 'unassigned'
        elif self.desktop_paused: reason='application_paused'
        elif kind!='mouse_button':
            if self.gump_paused: reason='gump_paused'
            elif not self.game_allowed: reason=self.game_block_reason or 'game_focus'
            elif isinstance(self.engine,SocketServer) and not self.engine.ready.is_set(): reason='listener_offline'
        if kind!='mouse_button' and name in self.suppressed_game_buttons:reason='held_before_focus'
        if hasattr(self.engine, 'control'):
            if isinstance(self.engine,SocketServer):
                self.engine.control(name,layer,down,action=action,blocked_reason=reason)
            else: self.engine.control(name,layer,down)
        if down:
            self.last_input={'control':name,'layer':layer,'action':action,'blocked_reason':reason,'at':time.time(),'source':getattr(self,'physical_sources',{}).get(name,{})}
            LOG.info('Input %s [%s] -> %s: %s',name,layer,action,reason or 'dispatch')
        if not down:
            self.release(name)

    def send_mouse(self,button,down):
        if hasattr(self.desktop,'mouse_button'):
            accepted=self.desktop.mouse_button(button,down)
        else:
            method=self.desktop.mouse.press if down else self.desktop.mouse.release
            method(getattr(self.desktop.mouse_module.Button,button));accepted=True
        self.mouse_result={'button':button,'down':down,'accepted':bool(accepted)}
        if not accepted:
            self.last_input['blocked_reason']='mouse_rejected'
            if time.monotonic()-self.mouse_warning_at>=2:
                self.mouse_warning_at=time.monotonic()
                LOG.error('Windows rejected mouse %s %s; check privileges and active desktop',button,'down' if down else 'up')
        return bool(accepted)

    def release(self, name):
        button = self.mouse_held.pop(name, None)
        if button and button not in self.mouse_held.values():
            if not self.send_mouse(button,False):self.mouse_held[name]=button;self.pending_mouse_releases.add(name)
            else:self.pending_mouse_releases.discard(name)
        else:self.pending_mouse_releases.discard(name)

    def reset(self):
        for name in list(self.mouse_held):
            self.release(name)

    def action(self, name, value=1.0):
        definition = self.cfg['actions'].get(name, {})
        kind = definition.get('type')
        # Mouse clicks remain available while paused for navigating the Gump.
        if kind == 'mouse_button':
            if self.desktop_paused: return
            if self.current_control not in self.mouse_held:
                button = definition['button']
                if button not in self.mouse_held.values():
                    if not self.send_mouse(button,True):return
                self.mouse_held[self.current_control] = button
            self.lease_until = time.monotonic() + .8
        elif not self.paused and self.game_allowed:
            if kind == 'hotkey':
                self.desktop.cfg['hotkeys'][name] = definition['keys']
                self.desktop.action(name, value)
            elif kind != 'none':
                self.engine.action(name, value)

    def movement(self, heading, running):
        if self.pending_mouse_releases and time.monotonic()>=self.next_mouse_retry:
            self.next_mouse_retry=time.monotonic()+.1
            for name in list(self.pending_mouse_releases):self.release(name)
        self.engine.movement(None if self.paused or not self.game_allowed else heading, running)
        if self.mouse_held and time.monotonic() > self.lease_until:
            self.reset()

    def keep_mouse_alive(self):
        self.lease_until = time.monotonic() + .8

    def close(self):
        self.reset()
        self.engine.close()


PRIVILEGE_NOTICE = ('The selected UO client is running as administrator. Cursor input may be blocked. '
                    'Restart Controller Studio with matching privileges, or run UO normally.')

def process_elevated(handle):
    """True when the process token is elevated. Works for elevated targets with limited rights."""
    advapi32 = ctypes.WinDLL('advapi32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    token = ctypes.c_void_p()
    if not advapi32.OpenProcessToken(ctypes.c_void_p(handle), 0x0008, ctypes.byref(token)):
        return None
    try:
        elevation, size = ctypes.c_uint32(), ctypes.c_uint32()
        if not advapi32.GetTokenInformation(token, 20, ctypes.byref(elevation), 4, ctypes.byref(size)):
            return None
        return bool(elevation.value)
    finally:
        kernel32.CloseHandle(token)


def host_elevated():
    if os.name != 'nt':
        return False
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    return bool(process_elevated(kernel32.GetCurrentProcess()))


def window_process(hwnd):
    """Return (executable name, elevated) for a top-level window, or ('', None)."""
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.OpenProcess.restype = ctypes.c_void_p
    pid = ctypes.c_uint32()
    user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(pid))
    if not pid.value:
        return '', None
    handle = kernel32.OpenProcess(0x1000, False, pid.value)
    if not handle:
        return '', None
    try:
        buffer, size = ctypes.create_unicode_buffer(1024), ctypes.c_uint32(1024)
        name = ''
        if kernel32.QueryFullProcessImageNameW(ctypes.c_void_p(handle), 0, buffer, ctypes.byref(size)):
            name = os.path.basename(buffer.value)
        return name, process_elevated(handle)
    finally:
        kernel32.CloseHandle(ctypes.c_void_p(handle))


def window_matches(focus, title, process):
    if any(s.lower() in title.lower() for s in focus.get('exclude_titles_containing', ['Razor']) if s):
        return False
    titles = [s for s in focus.get('window_title_contains', []) if s]
    processes = [n.lower() for n in focus.get('process_names', []) if n]
    return bool(titles) and any(s.lower() in title.lower() for s in titles) and (not processes or process.lower() in processes)


class FocusGuard:
    def __init__(self, cfg):
        self.cfg = cfg
        self.title = ''
        self.process = ''
        self.elevated = None
        self.hwnd = None
        self.pid = 0
        if cfg['require_focus'] and os.name != 'nt':
            raise RuntimeError('Focus checking is Windows-only. On another OS explicitly set require_focus=false')
        if os.name == 'nt':
            self.user32 = ctypes.WinDLL('user32', use_last_error=True)
            self.user32.GetForegroundWindow.restype = ctypes.c_void_p
            self.user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]

    def allowed(self):
        if not self.cfg['require_focus']:
            return True
        hwnd = self.user32.GetForegroundWindow()
        buffer = ctypes.create_unicode_buffer(1024)
        self.user32.GetWindowTextW(hwnd, buffer, len(buffer))
        self.title = buffer.value
        pid = ctypes.c_uint32()
        self.user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(pid))
        self.pid = pid.value
        if hwnd != self.hwnd:
            # Process lookups are cached per window; titles are re-read each poll.
            self.hwnd = hwnd
            self.process, self.elevated = window_process(hwnd) if hwnd else ('', None)
        return window_matches(self.cfg, self.title, self.process) and self.pid == int(self.cfg.get('selected_pid', 0))


class SocketServer:
    """One networking thread owns all sockets; producers only use locked state/queue.

    Discrete actions are never retransmitted: an ACK loss cannot double-cast.
    Movement is a replaceable state, never a queue of individual steps.
    """
    def __init__(self, cfg):
        self.cfg = cfg
        self.stop = threading.Event()
        self.ready = threading.Event()
        self.client_pid = 0
        self.runtime = {}
        self.client_features = []
        self.last_ack = {}
        self.lock = threading.Lock()
        self.actions = queue.Queue(maxsize=cfg['queue_limit'])
        self.events = queue.Queue(maxsize=64)
        self.commands = queue.Queue(maxsize=32)
        self.motion = (None, False, time.time())
        self.thread = threading.Thread(target=self._run, name='uo-ipc', daemon=True)
        self.started = threading.Event()
        self.start_error = None
        self.thread.start()
        if not self.started.wait(3):
            raise RuntimeError('Socket server startup timed out')
        if self.start_error:
            raise RuntimeError(self.start_error)

    def movement(self, heading, running):
        with self.lock:
            self.motion = (heading, running, time.time())

    def action(self, name, value=1.0):
        if not self.ready.is_set():
            LOG.warning('Dropped %s: listener not connected', name)
            return
        try:
            self.actions.put_nowait((name, value, time.time()))
        except queue.Full:
            LOG.warning('Dropped %s: action queue full', name)

    def publish(self, message):
        try:
            self.events.put_nowait(message)
        except queue.Full:
            LOG.warning('Controller telemetry queue full')

    def control(self, name, layer, down, **details):
        if self.ready.is_set():
            self.publish(dict({'type':'control', 'control':name, 'layer':layer, 'down':down}, **details))

    def discard_actions(self):
        while True:
            try: self.actions.get_nowait()
            except queue.Empty: break

    def _clear(self):
        for pending_queue in (self.actions, self.events, self.commands):
            while True:
                try:
                    pending_queue.get_nowait()
                except queue.Empty:
                    break

    @staticmethod
    def _send(sock, msg):
        sock.sendall((json.dumps(msg, separators=(',', ':')) + '\n').encode('utf-8'))

    def _session(self, client):
        client.settimeout(0.02)
        client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        session = secrets.token_hex(16)
        self._send(client, {'type': 'hello', 'version': 1, 'session': session, 'features':['spell_bindings_v1'],
                            'auth': hmac.new(self.cfg['token'].encode('utf-8'), (session+':host').encode('ascii'), hashlib.sha256).hexdigest()})
        authenticated = False
        buffer = b''
        seq = 0
        pending = {}
        next_motion = 0.0
        began = time.monotonic()
        last_rx = began
        self._clear()
        while not self.stop.is_set():
            now = time.monotonic()
            try:
                data = client.recv(8192)
                if not data:
                    return
                buffer += data
                if len(buffer) > 65536:
                    raise ValueError('Oversized listener response')
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    response = json.loads(line)
                    if response.get('session') != session:
                        raise ValueError('Response session mismatch')
                    last_rx = now
                    if response.get('type') == 'ready':
                        if authenticated: raise ValueError('Duplicate ready message')
                        expected = hmac.new(self.cfg['token'].encode('utf-8'), (session+':listener').encode('ascii'), hashlib.sha256).hexdigest()
                        if not hmac.compare_digest(str(response.get('auth', '')), expected):
                            raise ValueError('Listener authentication failed; reinstall its connection settings')
                        self.client_features = response.get('features',[])
                        self.client_pid = int(response.get('pid', 0))
                        if self.client_pid <= 0: raise ValueError('Update the Razor listener from Controller Studio')
                        authenticated = True
                        self.ready.set()
                        LOG.info('Razor listener connected')
                        self.commands.put_nowait({'type':'sync'})
                    elif not authenticated:
                        raise ValueError('Listener is not authenticated')
                    elif response.get('type') == 'configure':
                        self.commands.put_nowait(response)
                    elif response.get('type') == 'ping':
                        self.runtime={key:response.get('runtime',{}).get(key) for key in ('pending_target','busy_ms','paused')}
                    elif response.get('type') == 'ack':
                        number = response.get('seq')
                        if number not in pending:
                            LOG.warning('Unexpected/duplicate ACK %s', number)
                        else:
                            name, sent = pending.pop(number)
                            status = response.get('status')
                            self.last_ack={'action':name,'status':status,'detail':str(response.get('detail',''))[:500]}
                            if status != 'ok':
                                LOG.warning('%s: %s (%s)', name, status, response.get('detail', ''))
                            else:
                                LOG.debug('%s ACK %.1f ms', name, (now - sent) * 1000)
            except socket.timeout:
                pass
            if not authenticated:
                if now - began > 3:
                    raise TimeoutError('Listener handshake timeout')
                continue
            if now - last_rx > 3:
                raise TimeoutError('Listener heartbeat timeout')
            for number, (name, sent) in list(pending.items()):
                if now - sent > self.cfg['ack_timeout_ms'] / 1000:
                    LOG.warning('ACK missing for %s seq=%s; disconnecting without replay', name, number)
                    raise TimeoutError('ACK timeout')
            if now >= next_motion:
                with self.lock:
                    heading, running, stamp = self.motion
                if time.time() - stamp > 0.25:
                    heading = None
                seq += 1
                self._send(client, {'type': 'movement', 'session': session, 'seq': seq,
                                    'at': time.time(), 'direction': heading, 'run': running})
                next_motion = now + self.cfg['state_interval_ms'] / 1000
            for _ in range(8):
                try:
                    event = self.events.get_nowait()
                except queue.Empty:
                    break
                seq += 1
                event.update(session=session, seq=seq, at=time.time())
                self._send(client, event)
            # Bounded work per iteration prevents command bursts starving input polling.
            for _ in range(4):
                try:
                    name, value, stamp = self.actions.get_nowait()
                except queue.Empty:
                    break
                if (time.time() - stamp) * 1000 > self.cfg['action_ttl_ms']:
                    LOG.warning('Dropped expired queued action %s', name)
                    continue
                seq += 1
                self._send(client, {'type': 'action', 'session': session, 'seq': seq,
                                    'at': stamp, 'name': name, 'value': value})
                pending[seq] = (name, now)

    def _run(self):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
                # Avoid SO_REUSEADDR on Windows: a second host must fail to bind.
                server.bind((self.cfg['host'], self.cfg['port']))
                self.bound_port = server.getsockname()[1]
                server.listen(1)
                server.settimeout(0.25)
                self.started.set()
                LOG.info('Listening on %s:%s', self.cfg['host'], self.cfg['port'])
                while not self.stop.is_set():
                    try:
                        client, _ = server.accept()
                    except socket.timeout:
                        continue
                    try:
                        with client:
                            self._session(client)
                    except Exception as exc:
                        LOG.warning('IPC session ended: %s', exc)
                    finally:
                        self.ready.clear()
                        self.client_pid = 0
                        self._clear()
        except Exception as exc:
            self.start_error = str(exc)
            LOG.exception('Socket server failed')
        finally:
            self.ready.clear()
            self.started.set()

    def close(self):
        self.stop.set()
        self.thread.join(2)


class WinMouseInput(ctypes.Structure):
    _fields_ = [('dx', ctypes.c_int32), ('dy', ctypes.c_int32),
                ('mouseData', ctypes.c_uint32), ('dwFlags', ctypes.c_uint32),
                ('time', ctypes.c_uint32), ('dwExtraInfo', ctypes.c_size_t)]


class WinKeyboardInput(ctypes.Structure):
    _fields_ = [('wVk', ctypes.c_uint16), ('wScan', ctypes.c_uint16),
                ('dwFlags', ctypes.c_uint32), ('time', ctypes.c_uint32),
                ('dwExtraInfo', ctypes.c_size_t)]


class WinHardwareInput(ctypes.Structure):
    _fields_ = [('uMsg', ctypes.c_uint32), ('wParamL', ctypes.c_uint16),
                ('wParamH', ctypes.c_uint16)]


class WinInputUnion(ctypes.Union):
    _fields_ = [('mi', WinMouseInput), ('ki', WinKeyboardInput), ('hi', WinHardwareInput)]


class WinInput(ctypes.Structure):
    _anonymous_ = ('data',)
    _fields_ = [('type', ctypes.c_uint32), ('data', WinInputUnion)]


class WinPoint(ctypes.Structure):
    _fields_ = [('x', ctypes.c_long), ('y', ctypes.c_long)]


def enable_dpi_awareness():
    """Physical-pixel coordinates keep absolute cursor positioning exact on scaled displays."""
    try:
        ctypes.WinDLL('user32').SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        try:
            ctypes.WinDLL('shcore').SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            pass


class WindowsPointer:
    """Move the cursor with absolute SendInput events, with native ABI layout.

    Absolute positioning bypasses Windows pointer acceleration ("Enhance pointer
    precision"), which otherwise shrinks the small per-frame deltas a stick produces.
    """
    MOVE, VIRTUALDESK, ABSOLUTE = 0x0001, 0x4000, 0x8000

    def __init__(self, user32=None, backend='windows_desktop'):
        self.backend = backend
        self.user32 = user32 if user32 is not None else ctypes.WinDLL('user32', use_last_error=True)
        self.user32.SendInput.argtypes = [ctypes.c_uint32, ctypes.POINTER(WinInput), ctypes.c_int]
        self.user32.SendInput.restype = ctypes.c_uint32
        self.last_warning = -100.0

    @staticmethod
    def normalize(pixel, origin, extent):
        """Smallest 0..65535 coordinate that Windows maps back onto this exact pixel."""
        return max(0, min(65535, -(-((pixel - origin) * 65536) // max(1, extent))))

    def event(self, dx, dy):
        point = WinPoint()
        if not self.user32.GetCursorPos(ctypes.byref(point)):
            return WinMouseInput(dx=int(dx), dy=int(dy), dwFlags=self.MOVE)
        left, top = self.user32.GetSystemMetrics(76), self.user32.GetSystemMetrics(77)
        width, height = self.user32.GetSystemMetrics(78), self.user32.GetSystemMetrics(79)
        x = min(max(point.x + int(dx), left), left + width - 1)
        y = min(max(point.y + int(dy), top), top + height - 1)
        return WinMouseInput(dx=self.normalize(x, left, width), dy=self.normalize(y, top, height),
                             dwFlags=self.MOVE | self.VIRTUALDESK | self.ABSOLUTE)

    def button(self,button,down):
        flags={('left',True):0x0002,('left',False):0x0004,('right',True):0x0008,('right',False):0x0010}
        event=WinInput(type=0);event.mi=WinMouseInput(dwFlags=flags[(button,down)])
        return self.user32.SendInput(1,ctypes.byref(event),ctypes.sizeof(WinInput))==1

    def move(self, dx, dy):
        if self.backend == 'windows_desktop':
            point = WinPoint()
            if not self.user32.GetCursorPos(ctypes.byref(point)):
                return False
            left, top = self.user32.GetSystemMetrics(76), self.user32.GetSystemMetrics(77)
            width, height = self.user32.GetSystemMetrics(78), self.user32.GetSystemMetrics(79)
            x = min(max(point.x + int(dx), left), left + width - 1)
            y = min(max(point.y + int(dy), top), top + height - 1)
            accepted = bool(self.user32.SetCursorPos(int(x), int(y)))
            if not accepted and time.monotonic() - self.last_warning >= 5:
                self.last_warning = time.monotonic()
                LOG.warning('Windows could not update the desktop cursor; check the active desktop and privileges')
            return accepted
        event = WinInput(type=0)
        event.mi = self.event(dx, dy)
        accepted = self.user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(WinInput)) == 1
        if not accepted and time.monotonic() - self.last_warning >= 5:
            self.last_warning = time.monotonic()
            LOG.error('Windows rejected mouse movement (error=%s). If UO is elevated, restart Controller Studio with matching privileges.',
                      getattr(ctypes, 'get_last_error', lambda: 0)())
        return accepted


class DesktopOutput:
    """pynput is imported lazily so --inspect works without a desktop session."""
    def __init__(self, cfg, keyboard_enabled=False):
        from pynput import keyboard, mouse
        self.keyboard_module = keyboard
        self.mouse_module = mouse
        self.keyboard = keyboard.Controller() if keyboard_enabled else None
        self.mouse = mouse.Controller()
        self.windows_pointer = WindowsPointer(backend=cfg.get('cursor_backend','windows_desktop')) if os.name == 'nt' else None
        self.pointer_notice_at = 0.0
        LOG.info('Mouse backend: %s', cfg.get('cursor_backend','windows_desktop') if self.windows_pointer else 'pynput')
        self.cfg = cfg
        self.held = set()
        self.hotkey_worker = None
        self.fraction_x = self.fraction_y = self.scroll_fraction = 0.0

    def mouse_button(self,button,down):
        if self.windows_pointer is not None:return self.windows_pointer.button(button,down)
        method=self.mouse.press if down else self.mouse.release
        method(getattr(self.mouse_module.Button,button));return True

    def enable_hotkey_queue(self, allowed):
        self.hotkey_worker=HotkeyWorker(self.keyboard,self.key,allowed,lambda:set(self.held),self.cfg.get('hotkey_tap_ms',60))

    def key(self, name):
        if name.startswith('numpad') and name[6:].isdigit() and 0 <= int(name[6:]) <= 9:
            if os.name != 'nt':
                raise ValueError('numpad key injection requires Windows; edit movement_hotkeys')
            return self.keyboard_module.KeyCode.from_vk(0x60 + int(name[6:]))
        if len(name) == 1:
            return name
        try:
            return getattr(self.keyboard_module.Key, name)
        except AttributeError:
            raise ValueError('Unknown pynput key: ' + name)

    def action(self, name, value=1.0):
        keys = self.cfg['hotkeys'].get(name)
        if not keys:
            LOG.warning('No hotkey for %s', name)
            return
        if self.hotkey_worker is not None:
            self.hotkey_worker.submit(keys);return
        pressed = []
        try:
            for name in keys:
                key = self.key(name)
                if key not in self.held:
                    self.keyboard.press(key)
                    pressed.append(key)
            time.sleep(max(60,self.cfg['hotkey_tap_ms']) / 1000)
        finally:
            for key in reversed(pressed):
                self.keyboard.release(key)

    def movement(self, heading, running):
        names = self.cfg['movement_hotkeys'].get(heading, []) if heading else []
        if heading and running:
            names = names + self.cfg['run_hotkey']
        desired = {self.key(name) for name in names}
        for key in self.held - desired:
            self.keyboard.release(key)
            self.held.discard(key)
        for key in desired - self.held:
            self.keyboard.press(key)
            self.held.add(key)

    def pointer(self, x, y, dt, scroll):
        if scroll:
            self.scroll_fraction += -y * self.cfg['scroll_per_second'] * dt
            ticks = math.trunc(self.scroll_fraction)
            self.scroll_fraction -= ticks
            if ticks:
                self.mouse.scroll(0, ticks)
            self.fraction_x = self.fraction_y = 0.0
        else:
            self.scroll_fraction = 0.0
            x, y = cursor_curve(x, y, self.cfg.get('cursor_curve', 1.0))
            self.fraction_x += x * self.cfg['cursor_pixels_per_second'] * dt
            self.fraction_y += y * self.cfg['cursor_pixels_per_second'] * dt
            dx, dy = math.trunc(self.fraction_x), math.trunc(self.fraction_y)
            self.fraction_x -= dx
            self.fraction_y -= dy
            if dx or dy:
                if self.windows_pointer:
                    accepted = self.windows_pointer.move(dx, dy)
                else:
                    self.mouse.move(dx, dy)
                    accepted = True
                if time.monotonic() >= self.pointer_notice_at:
                    LOG.info('Mouse stick output=(%.2f, %.2f) delta=(%d, %d) Windows cursor update accepted=%s '
                             '(not proof the game received it)', x, y, dx, dy, accepted)
                    self.pointer_notice_at = time.monotonic() + 5

    def reset(self):
        if self.hotkey_worker is not None:self.hotkey_worker.cancel()
        if self.keyboard:
            self.movement(None, False)
        self.fraction_x = self.fraction_y = self.scroll_fraction = 0.0

    def close(self):
        if self.hotkey_worker is not None:self.hotkey_worker.close()
        self.reset()


class InputMapper:
    def __init__(self, cfg, output):
        self.cfg = cfg
        self.output = output
        self.stable = {}
        self.candidate = {}
        self.changed = {}
        self.next_repeat = {}
        self.trigger_on = {}
        self.armed = False
        self.game_armed = False
        self.suppressed_game_buttons = set()
        self.unknown = set()
        self.mapping_issues={}
        self.active_controls=[]
        self.input_trace=[]

    def reset(self):
        self.stable.clear()
        self.candidate.clear()
        self.changed.clear()
        self.next_repeat.clear()
        self.trigger_on.clear()
        self.suppressed_game_buttons.clear()
        self.armed = False
        self.game_armed = False
        self.output.movement(None, False)
        if hasattr(self.output, 'reset'):
            self.output.reset()

    def source(self, joy, spec, name):
        if 'button' in spec:
            index = spec['button']
            return index < joy.get_numbuttons() and bool(joy.get_button(index)), 1.0
        if 'hat' in spec:
            index = spec['hat']
            hat = joy.get_hat(index) if index < joy.get_numhats() else (0, 0)
            return hat[spec['component']] == spec['sign'], 1.0
        axis = spec['axis']
        if axis >= joy.get_numaxes():
            return False, 0.0
        raw = joy.get_axis(axis)
        value = max(0.0, min(1.0, (raw - spec['rest']) / (spec['full'] - spec['rest'])))
        threshold = self.cfg['input']['trigger_release'] if self.trigger_on.get(name) else self.cfg['input']['trigger_press']
        down = value >= threshold
        self.trigger_on[name] = down
        return down, value

    @staticmethod
    def stick(joy, indices, signs=(1, 1)):
        values = []
        for index in indices:
            values.append(joy.get_axis(index) * signs[len(values)] if 0 <= index < joy.get_numaxes() else 0.0)
        return values

    def layer(self):
        return next((row for row in self.cfg['layers'] if row.get('name')=='base'),{'name':'base','bindings':{}})

    def poll(self, joy, preset, now, allowed, game_allowed=None):
        sources = preset['controls']
        self.mapping_issues=mapping_issues(preset)
        observed={name:self.source(joy,spec,name) for name,spec in sources.items()}
        self.active_controls=[name for name,value in observed.items() if value[0]]
        # Do not dispatch a suspect source as another button's game action.
        raw={name:((False,0.) if name in self.mapping_issues else value) for name,value in observed.items()}
        if hasattr(self.output,'last_input'):
            self.output.physical_sources=sources
        lx, ly = self.stick(joy, preset['left_stick'], preset.get('left_stick_sign', [1, 1]))
        rx, ry = self.stick(joy, preset['right_stick'], preset.get('right_stick_sign', [1, 1]))
        lx, ly, lm = radial(lx, ly, self.cfg['input']['left_deadzone'])
        rx, ry, _ = radial(rx, ry, self.cfg['input']['right_deadzone'])
        if not allowed:
            self.reset()
            return 0.0, 0.0, False
        # Movement arming is independent of cursor deflection and held buttons.
        # Seed held buttons without down edges; they must release before firing.
        if not self.armed:
            role=self.cfg['input'].get('movement_stick','left')
            magnitude=lm if role=='left' else math.hypot(rx,ry) if role=='right' else 0.
            if magnitude < self.cfg['input']['move_threshold']:
                self.armed = True
                for name,(down,value) in raw.items():
                    if down:
                        self.stable[name]=True;self.candidate[name]=True;self.changed[name]=now
                        self.suppressed_game_buttons.add(name)
                if game_allowed is not None:
                    self.game_armed = bool(game_allowed)
                    self.output.game_allowed = self.game_armed
                    self.output.game_block_reason = '' if self.game_armed else 'game_focus'
                LOG.info('Controller armed after neutral movement stick')
            self.output.movement(None, False)
            return 0.0, 0.0, False
        edges = []
        for name, (down, value) in raw.items():
            if self.candidate.get(name) != down:
                self.candidate[name] = down
                self.changed[name] = now
            if down != self.stable.get(name, False) and now - self.changed[name] >= self.cfg['input']['debounce_ms'] / 1000:
                self.stable[name] = down
                self.input_trace.append({'control':name,'down':down,'source':dict(sources[name])})
                self.input_trace=self.input_trace[-12:]
                if down:
                    edges.append(name)
                else:
                    self.next_repeat.pop(name, None)
                    if hasattr(self.output, 'control'):
                        self.output.control(name, self.layer().get('name', 'base'), False)
        layer = self.layer()
        if game_allowed is not None:
            if not game_allowed or not self.game_armed:
                self.suppressed_game_buttons.update(name for name,value in raw.items() if value[0])
            self.suppressed_game_buttons.intersection_update(name for name,value in raw.items() if value[0] or self.stable.get(name,False))
            if not game_allowed:
                self.game_armed=False
            elif not self.game_armed:
                role=self.cfg['input'].get('movement_stick','left')
                magnitude=lm if role=='left' else math.hypot(rx,ry) if role=='right' else 0.
                if magnitude<self.cfg['input']['move_threshold']:
                    self.game_armed=True
            self.output.game_allowed=bool(game_allowed and self.game_armed)
            self.output.game_block_reason='' if self.output.game_allowed else 'neutral_required' if game_allowed else 'game_focus'
        if hasattr(self.output,'suppressed_game_buttons'):self.output.suppressed_game_buttons=set(self.suppressed_game_buttons)
        for name in edges:
            if hasattr(self.output, 'control'):
                self.output.control(name, layer.get('name', 'base'), True)
        for name, (down, value) in raw.items():
            if not self.stable.get(name, False):
                continue
            binding = effective_binding(self.cfg, layer, name)
            if not binding:
                if name in edges and name not in self.cfg['modifier_controls'] and name not in self.unknown:
                    LOG.warning('Unmapped control %s in layer %s', name, layer.get('name'))
                    self.unknown.add(name)
                continue
            if name in self.suppressed_game_buttons and self.cfg['actions'].get(binding['action'],{}).get('type')!='mouse_button':
                continue
            repeat = binding.get('repeat_ms', 0) / 1000
            if name in edges or (repeat and now >= self.next_repeat.get(name, float('inf'))):
                if hasattr(self.output, 'begin_control'):
                    self.output.begin_control(name)
                self.output.action(binding['action'], value)
                self.next_repeat[name] = now + repeat if repeat else float('inf')
        if hasattr(self.output, 'keep_mouse_alive'):
            self.output.keep_mouse_alive()
        sticks = {'left': (lx, ly, lm), 'right': (rx, ry, math.hypot(rx, ry)), 'off': (0., 0., 0.)}
        mx, my, magnitude = sticks[self.cfg['input'].get('movement_stick', 'left')]
        px, py, _ = sticks[self.cfg['input'].get('mouse_stick', 'right')]
        heading = direction(mx, my) if magnitude >= self.cfg['input']['move_threshold'] else None
        run_control=self.cfg['input']['run_control']
        run_binding=effective_binding(self.cfg,layer,run_control) or {}
        force_run=self.stable.get(run_control,False) and self.cfg['actions'].get(run_binding.get('action'),{}).get('type')!='mouse_button'
        running = magnitude >= self.cfg['input']['run_threshold'] or force_run
        self.output.movement(heading, running)
        scroll_control = self.cfg['input']['scroll_control']
        scroll_binding = effective_binding(self.cfg, layer, scroll_control) or {}
        scrolling = self.stable.get(scroll_control, False) and self.cfg['actions'].get(scroll_binding.get('action'),{}).get('type') != 'mouse_button'
        return px, py, scrolling


def foreground_pid():
    if os.name != 'nt': return 0
    user32=ctypes.WinDLL('user32',use_last_error=True)
    user32.GetForegroundWindow.restype=ctypes.c_void_p
    pid=ctypes.c_uint32()
    user32.GetWindowThreadProcessId(ctypes.c_void_p(user32.GetForegroundWindow()),ctypes.byref(pid))
    return pid.value


def apply_desktop_request(cfg,request,desktop,output,mapper,engine,path,user_paused):
    reply={'id':request.get('id'),'status':'error'}
    try:
        if getattr(engine,'ready',None) is not None and engine.ready.is_set() and hasattr(engine,'client_features') and 'desktop_editor_v1' not in engine.client_features:
            raise ValueError('Install/update the Razor listener from Controller > Connection setup before changing live assignments')
        if request.get('kind')=='apply':
            candidate=configure(cfg,request['payload'],desktop)
            if candidate['input'].get('movement_stick','left')==candidate['input'].get('mouse_stick','right')!='off':
                raise ValueError('Choose different sticks for movement and cursor')
            save_config(path,candidate)
            cfg.clear();cfg.update(candidate);desktop.cfg=cfg['desktop']
        elif request.get('kind')=='recover':
            user_paused=False
        else: raise ValueError('Unknown desktop request')
        output.gump_paused=False;output.desktop_paused=user_paused
        mapper.reset();desktop.reset()
        engine.publish({'type':'reset_input'})
        engine.publish({'type':'profile','profile':profile(cfg),'paused':output.paused,'pause_reason':output.pause_reason})
        reply.update(status='ok',revision=cfg.get('revision',0))
    except Exception as exc:
        reply['detail']=str(exc);LOG.warning('Desktop request rejected: %s',exc)
    return reply,user_paused


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path(__file__).with_name('bindings.json'))
    parser.add_argument('--preset', help='Override preset name from bindings.json')
    parser.add_argument('--inspect', action='store_true', help='Print raw events; send no actions or mouse/keyboard input')
    parser.add_argument('--control', type=Path, help='Desktop application control file')
    parser.add_argument('--status', type=Path, help='Desktop application status file')
    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    if migrate_controller_ui(cfg):
        save_config(args.config, cfg)
    if args.preset:
        if args.preset not in cfg['presets']:
            parser.error('Unknown preset; choose: ' + ', '.join(cfg['presets']))
        cfg['preset'] = args.preset
    logging.basicConfig(level=logging.DEBUG if cfg['debug'] else logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    handler = RotatingFileHandler(args.config.with_name('controller_bridge.log'), maxBytes=1_000_000, backupCount=3)
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    LOG.addHandler(handler)
    # SDL must receive events while the UO window is foreground.
    os.environ['SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS'] = '1'
    os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
    if os.name == 'nt' and not args.inspect:
        enable_dpi_awareness()
    import pygame
    pygame.display.init()
    pygame.joystick.init()
    devices = {}
    active = None
    output = desktop = mapper = guard = None
    clock = pygame.time.Clock()
    preset = cfg['presets'][cfg['preset']]
    for control,detail in mapping_issues(preset).items():
        LOG.warning('Blocked physical mapping %s: %s source=%r',control,detail,preset['controls'][control])
    elevated = host_elevated()
    privilege_notice = None
    LOG.info('Controller Studio host %s (administrator=%s)', VERSION, elevated)
    LOG.info('Stick mapping: left axes=%s right axes=%s; movement=%s mouse=%s scroll modifier=%s',
             preset['left_stick'], preset['right_stick'], cfg['input'].get('movement_stick', 'left'),
             cfg['input'].get('mouse_stick', 'right'), cfg['input'].get('scroll_control', ''))
    previous_focus = None
    command_sequence = -1
    next_status = 0.0
    control_seen_at = time.monotonic()
    last_heartbeat = None
    next_control_check = 0.0
    user_paused = False
    last_desktop_request = None
    desktop_reply = {}
    last_warning = 0.0
    next_scan = 0.0
    prior = time.monotonic()

    def add(index):
        try:
            joy = pygame.joystick.Joystick(index)
            identity = joy.get_instance_id()
        except pygame.error as exc:
            LOG.warning('Device changed during discovery: %s', exc)
            return
        if identity in devices:
            return
        devices[identity] = joy
        LOG.info('Device id=%s name=%r GUID=%s axes=%s buttons=%s hats=%s', identity,
                 joy.get_name(), joy.get_guid(), joy.get_numaxes(), joy.get_numbuttons(), joy.get_numhats())

    try:
        if not args.inspect:
            guard = FocusGuard(cfg['focus'])
            desktop = DesktopOutput(cfg['desktop'], keyboard_enabled=True)
            output = SocketServer(dict(cfg['bridge'], token=cfg['token'])) if cfg['bridge']['mode'] == 'socket' else desktop
            engine = output
            output = OutputRouter(cfg, engine, desktop)
            mapper = InputMapper(cfg, output)
            if isinstance(engine,SocketServer) and hasattr(desktop,'enable_hotkey_queue'):
                desktop.enable_hotkey_queue(lambda: engine.ready.is_set() and foreground_pid()==cfg['focus'].get('selected_pid'))
        for index in range(pygame.joystick.get_count()):
            add(index)
        LOG.info('Preset %s; %s', cfg['preset'], 'inspection only' if args.inspect else cfg['bridge']['mode'])
        while True:
            now = time.monotonic()
            if args.control and now >= next_control_check:
                next_control_check = now + .05
                try:
                    control = json.loads(args.control.read_text(encoding='utf-8'))
                    if control.get('heartbeat') != last_heartbeat:
                        last_heartbeat = control.get('heartbeat')
                        control_seen_at = now
                    if control.get('stop'): break
                    request=control.get('request')
                    if request and request.get('id')!=last_desktop_request:
                        last_desktop_request=request.get('id')
                        desktop_reply,user_paused=apply_desktop_request(cfg,request,desktop,output,mapper,engine,args.config,user_paused)
                    if control.get('sequence', 0) != command_sequence:
                        command_sequence = control.get('sequence', 0)
                        user_paused = bool(control.get('paused', False))
                        output.desktop_paused = user_paused
                        mapper.reset(); desktop.reset()
                        if isinstance(engine, SocketServer):
                            engine.publish({'type':'configuration_result','status':'ok',
                                            'profile':profile(cfg),'paused':output.paused, 'pause_reason':output.pause_reason})
                except (OSError, ValueError):
                    LOG.debug('Could not read desktop control state')
                if now - control_seen_at > 6:
                    LOG.info('Desktop application heartbeat expired'); break
            if not args.inspect and isinstance(engine, SocketServer):
                for _ in range(8):
                    try:
                        command = engine.commands.get_nowait()
                    except queue.Empty:
                        break
                    if command['type'] == 'sync':
                        output.desktop_paused = user_paused
                        mapper.reset()
                        engine.publish({'type':'profile', 'profile':profile(cfg), 'paused':output.paused, 'pause_reason':output.pause_reason})
                        if privilege_notice:
                            engine.publish({'type':'notice', 'level':'error', 'text':privilege_notice})
                        continue
                    try:
                        payload = command.get('payload', {})
                        candidate = configure(cfg, payload, desktop)
                        movement_stick = candidate['input'].get('movement_stick', 'left')
                        mouse_stick = candidate['input'].get('mouse_stick', 'right')
                        if movement_stick == mouse_stick and mouse_stick != 'off':
                            raise ValueError('Choose different sticks for movement and mouse')
                        if 'changes' not in payload and ('binding' in payload or 'setting' in payload or 'assignment_profile' in payload):
                            candidate['revision'] = cfg.get('revision', 0) + 1
                        if 'binding' in payload or 'setting' in payload or 'changes' in payload or 'assignment_profile' in payload:
                            save_config(args.config, candidate)
                            cfg.clear(); cfg.update(candidate)
                            desktop.cfg = cfg['desktop']
                            mapper.reset()
                        if 'paused' in payload:
                            output.gump_paused = bool(payload['paused'])
                            LOG.info('Pause state: application=%s gump=%s',output.desktop_paused,output.gump_paused)
                            mapper.reset()
                        engine.publish({'type':'configuration_result', 'request':command.get('request'),
                                        'status':'ok', 'profile':profile(cfg), 'paused':output.paused, 'pause_reason':output.pause_reason})
                    except Exception as exc:
                        LOG.warning('Configuration rejected: %s', exc)
                        engine.publish({'type':'configuration_result', 'request':command.get('request'),
                                        'status':'error', 'detail':str(exc)})

            dt = min(0.05, now - prior)
            prior = now
            for event in pygame.event.get():
                if event.type == pygame.JOYDEVICEADDED:
                    add(event.device_index)
                elif event.type == pygame.JOYDEVICEREMOVED:
                    removed = devices.pop(event.instance_id, None)
                    if removed:
                        removed.quit()
                        LOG.warning('Controller disconnected id=%s', event.instance_id)
                if args.inspect and event.type in (pygame.JOYAXISMOTION, pygame.JOYBUTTONDOWN,
                                                   pygame.JOYBUTTONUP, pygame.JOYHATMOTION):
                    LOG.info('RAW %s', event)
                elif not args.inspect and event.type == pygame.JOYBUTTONDOWN and getattr(event, 'instance_id', None) == active:
                    mapped = {v['button'] for v in preset['controls'].values() if 'button' in v}
                    if event.button not in mapped:
                        LOG.warning('Unmapped raw button id=%s; use --inspect and edit preset', event.button)
            # Event discovery plus periodic reconciliation for drivers missing attach events.
            if now >= next_scan:
                for identity, joy in list(devices.items()):
                    if not joystick_connected(pygame, joy):
                        devices.pop(identity, None)
                        joy.quit()
                        LOG.warning('Controller detached id=%s', identity)
                for index in range(pygame.joystick.get_count()):
                    add(index)
                next_scan = now + 2
            candidates = [identity for identity, joy in devices.items()
                          if cfg['device_name_contains'].lower() in joy.get_name().lower()
                          and (not cfg.get('device_guid') or joy.get_guid() == cfg['device_guid'])]
            chosen = active if active in candidates else (candidates[0] if candidates else None)
            if chosen != active:
                active = chosen
                if mapper:
                    mapper.reset()
                    desktop.reset()
                LOG.info('Active controller: %s', active)
                if active is not None:
                    joy = devices[active]
                    limits = {'button': joy.get_numbuttons(), 'hat': joy.get_numhats(), 'axis': joy.get_numaxes()}
                    for name, source in preset['controls'].items():
                        for kind, limit in limits.items():
                            if kind in source and source[kind] >= limit:
                                LOG.warning('Preset control %s references unavailable %s ID %s', name, kind, source[kind])
                    for key in ('left_stick', 'right_stick'):
                        if any(index >= joy.get_numaxes() for index in preset[key]):
                            LOG.warning('Preset %s references unavailable axes', key)
            if not args.inspect:
                focused = guard.allowed()
                paired = not isinstance(engine, SocketServer) or (engine.ready.is_set() and guard.pid == engine.client_pid)
                game_allowed = focused and paired
                if game_allowed != previous_focus:
                    LOG.info('Game focus %s; title=%r', 'allowed' if game_allowed else 'blocked', guard.title)
                    previous_focus = game_allowed
                    mapper.game_armed = False
                    output.game_allowed = False
                    output.movement(None, False)
                    if isinstance(engine, SocketServer): engine.discard_actions()
                blocked = focused and bool(guard.elevated) and not elevated
                if blocked != bool(privilege_notice):
                    privilege_notice = PRIVILEGE_NOTICE if blocked else None
                    if blocked: LOG.warning(PRIVILEGE_NOTICE)
                    if isinstance(engine, SocketServer):
                        engine.publish({'type':'notice','level':'error' if blocked else 'ok','text':privilege_notice or ''})
                allowed = game_allowed or cfg['desktop'].get('global_cursor', True)
                if args.status and now >= next_status:
                    save_config(args.status, {'at':time.time(), 'controller':devices[active].get_name() if active in devices else '',
                        'listener':isinstance(engine, SocketServer) and engine.ready.is_set(), 'game_focus':game_allowed,
                        'paused':output.paused, 'pause_reason':output.pause_reason, 'armed':mapper.armed, 'game_armed':mapper.game_armed, 'privilege_warning':bool(privilege_notice),
                        'client_mismatch':focused and isinstance(engine, SocketServer) and engine.ready.is_set() and not paired,
                        'profile':cfg.get('active_assignment_profile','Custom'), 'desktop_reply':desktop_reply,
                        'last_input':output.last_input, 'runtime':getattr(engine,'runtime',{}), 'last_ack':getattr(engine,'last_ack',{}),
                        'hotkey_result':getattr(getattr(desktop,'hotkey_worker',None),'result',{}),
                        'mouse_result':output.mouse_result,'mapping_issues':mapper.mapping_issues,
                        'active_controls':mapper.active_controls,'input_trace':mapper.input_trace,'sources':preset['controls']})
                    next_status = now + .25
                if active is not None:
                    try:
                        x, y, scroll = mapper.poll(devices[active], preset, now, allowed and not user_paused, game_allowed)
                        if allowed and not user_paused:
                            output.keep_mouse_alive()
                            desktop.pointer(x, y, dt, scroll)
                        else:
                            desktop.reset()
                    except pygame.error as exc:
                        LOG.warning('Controller read failed: %s', exc)
                        devices.pop(active, None)
                        mapper.reset()
                        desktop.reset()
                        active = None
                else:
                    output.movement(None, False)
                    desktop.reset()
                    if now - last_warning > 10:
                        LOG.info('Waiting for a matching controller')
                        last_warning = now
            clock.tick(cfg['poll_hz'])
    except KeyboardInterrupt:
        LOG.info('Stopping')
    finally:
        if output:
            output.movement(None, False)
            output.close()
        if desktop:
            desktop.close()
        for joy in devices.values():
            joy.quit()
        pygame.quit()


if __name__ == '__main__':
    main()
