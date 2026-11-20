"""Application storage, installation, calibration and Windows helpers (no GUI imports)."""
from __future__ import annotations
import copy
import ctypes
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time

from controller_bridge import migrate_controller_ui, save_config, window_process
from input_validation import mapping_issues

APP_NAME = 'Mystic Llama Controller Studio'
CONTROLS = [
 ('south','BOTTOM face button'), ('east','RIGHT face button'),
 ('west','LEFT face button'), ('north','TOP face button'),
 ('lb','LEFT bumper'), ('rb','RIGHT bumper'), ('lt','LEFT trigger'), ('rt','RIGHT trigger'),
 ('back','Minus / Select / Back'), ('start','Plus / Start / Options'),
 ('ls','LEFT stick click'), ('rs','RIGHT stick click'),
 ('dpad_up','D-pad UP'), ('dpad_down','D-pad DOWN'), ('dpad_left','D-pad LEFT'), ('dpad_right','D-pad RIGHT')]


def resource(name):
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent)) / name


def data_directory(override=None):
    if override: return Path(override).resolve()
    return Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local' / 'share')) / 'MysticLlama' / 'ControllerStudio'


def initialize(directory):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / 'bindings.json'
    if not path.exists():
        cfg = json.loads(resource('bindings.defaults.json').read_text(encoding='utf-8'))
        cfg['token'] = secrets.token_hex(32)
        migrate_controller_ui(cfg)
        save_config(path, cfg)
    else:
        cfg = json.loads(path.read_text(encoding='utf-8'))
        if cfg.get('assignment_schema')!=4:
            backup=directory/'bindings.before-4.0.json'
            if not backup.exists():shutil.copy2(path,backup)
        if not cfg.get('token'): cfg['token'] = secrets.token_hex(32)
        migrate_controller_ui(cfg)
        save_config(path, cfg)
    return path


def install_listener(directory, destination):
    """Install only into the explicitly selected dedicated script subfolder."""
    folder = Path(destination) / 'MysticLlamaController'
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / 'razor_listener.py'
    if target.exists(): shutil.copy2(target, folder / 'razor_listener.previous.py')
    temporary = folder / 'razor_listener.new'
    shutil.copyfile(resource('razor_listener.py'), temporary)
    os.replace(temporary, target)
    save_config(folder / 'controller_studio_connection.json', {'config_path':str((directory/'bindings.json').resolve())})
    return target


def detect_source(before, current, axis_only=False, prefer_axis=False):
    axes = [(i, value-before['axes'][i]) for i,value in enumerate(current['axes'])
            if abs(value-before['axes'][i]) >= .6]
    buttons = [i for i,value in enumerate(current['buttons']) if value and not before['buttons'][i]]
    hats = [(i,c,value[c]) for i,value in enumerate(current['hats']) for c in (0,1)
            if value[c] and value[c] != before['hats'][i][c]]
    if not axis_only and len(buttons)+len(hats)>1:return None
    if axes and (axis_only or prefer_axis and not buttons and not hats):
        index,delta=max(axes,key=lambda pair:abs(pair[1]))
        return {'axis':index,'rest':round(before['axes'][index],4),'full':1.0 if delta>0 else -1.0}
    if not axis_only:
        if buttons: return {'button':buttons[0]}
        if hats:
            index,component,sign=hats[0]
            return {'hat':index,'component':component,'sign':sign}
    return None


def source_identity(source):
    if 'button' in source: return ('button',source['button'])
    if 'hat' in source: return ('hat',source['hat'],source['component'],source['sign'])
    return ('axis',source['axis'],1 if source['full']>source['rest'] else -1)


def apply_calibration(cfg, name, guid, learned):
    cfg=copy.deepcopy(cfg)
    sticks={};signs={};controls={}
    for key,value in learned.items():
        if key in ('left_x','left_y','right_x','right_y'): continue
        controls[key]=value
    axes=[learned[key]['axis'] for key in ('left_x','left_y','right_x','right_y')]
    if len(set(axes))!=4: raise ValueError('Each stick direction must use a different axis. Retry calibration.')
    for side in ('left','right'):
        values=[learned[side+'_'+axis] for axis in ('x','y')]
        sticks[side+'_stick']=[s['axis'] for s in values]
        signs[side+'_stick_sign']=[1 if s['full']>s['rest'] else -1 for s in values]
    preset=dict(sticks,**signs,controls=controls)
    issues=mapping_issues(preset)
    if issues:raise ValueError('; '.join(name+': '+reason for name,reason in issues.items()))
    cfg['presets']['learned_controller']=preset
    cfg.update(preset='learned_controller',device_name_contains=name,device_guid=guid)
    cfg['setup_complete']=True
    return cfg


def apply_button_calibration(cfg,name,guid,learned):
    candidate=copy.deepcopy(cfg)
    if cfg.get('device_guid') and guid!=cfg['device_guid']:
        raise ValueError('Choose your saved controller. Use full controller setup for a different device.')
    preset=copy.deepcopy(cfg['presets'][cfg['preset']]);preset['controls'].update(learned)
    issues=mapping_issues(preset)
    if issues:raise ValueError('; '.join(control+': '+reason for control,reason in issues.items()))
    candidate['presets']['learned_controller']=preset
    candidate.update(preset='learned_controller',device_name_contains=name,device_guid=guid,setup_complete=True)
    return candidate


def list_game_windows():
    if os.name!='nt': return []
    user=ctypes.WinDLL('user32',use_last_error=True)
    callback=ctypes.WINFUNCTYPE(ctypes.c_bool,ctypes.c_void_p,ctypes.c_void_p)
    result=[]
    def visit(hwnd,_):
        if user.IsWindowVisible(ctypes.c_void_p(hwnd)):
            buffer=ctypes.create_unicode_buffer(1024)
            user.GetWindowTextW(ctypes.c_void_p(hwnd),buffer,len(buffer))
            title=buffer.value
            if title and 'razor' not in title.lower():
                process,elevated=window_process(hwnd)
                if 'classicuo' in process.lower() or 'ultima' in title.lower():
                    pid=ctypes.c_uint32()
                    user.GetWindowThreadProcessId(ctypes.c_void_p(hwnd),ctypes.byref(pid))
                    result.append({'title':title,'process':process,'pid':pid.value,'elevated':elevated})
        return True
    user.EnumWindows(callback(visit),None)
    return result


def launch_arguments(*arguments):
    return ([sys.executable] if getattr(sys,'frozen',False) else [sys.executable,str(resource('app.py'))]) + list(arguments)


def elevate(directory):
    if os.name!='nt': raise RuntimeError('Elevation is available only on Windows.')
    command=launch_arguments('--data-dir',str(directory))
    shell=ctypes.WinDLL('shell32',use_last_error=True)
    shell.ShellExecuteW.argtypes=[ctypes.c_void_p,ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_int]
    shell.ShellExecuteW.restype=ctypes.c_void_p
    code=shell.ShellExecuteW(None,'runas',command[0],subprocess.list2cmdline(command[1:]),str(resource('').resolve()),1)
    if not code or code<=32: raise RuntimeError('Windows did not approve the administrator restart.')


def diagnostics(directory):
    """Useful support text without tokens, character names, paths or weapon serials."""
    from controller_bridge import VERSION, host_elevated
    cfg=json.loads((directory/'bindings.json').read_text(encoding='utf-8'))
    status={}
    try: status=json.loads((directory/'host_status.json').read_text(encoding='utf-8'))
    except (OSError,ValueError): pass
    for key in ('controller','error'): status.pop(key,None)
    # Keep free-form native/OS error text in local logs, not copied diagnostics.
    for key in ('last_ack','hotkey_result','desktop_reply'):
        if key in status: status[key]={name:status[key][name] for name in ('status','revision') if name in status[key]}
    if 'last_input' in status:
        last=status['last_input'];status['last_input']={key:last[key] for key in ('control','layer','blocked_reason') if key in last}
        status['last_input']['action_type']=cfg['actions'].get(last.get('action'),{}).get('type','unknown')
    return json.dumps({'version':VERSION,'platform':sys.platform,'administrator':host_elevated(),
        'preset':cfg['preset'],'controller_configured':bool(cfg.get('setup_complete')),
        'global_cursor':cfg['desktop'].get('global_cursor'), 'status':status},indent=2)
