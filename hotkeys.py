"""Validated shortcut names and cancellable injection, independent of the input loop."""
import queue
import threading
import time

ALIASES={'control':'ctrl','escape':'esc','return':'enter','pgup':'page_up','pgdown':'page_down',
         'pageup':'page_up','pagedown':'page_down','del':'delete','ins':'insert','backspace':'backspace','meta':'cmd','win':'cmd'}
MODIFIERS={'ctrl','ctrl_l','ctrl_r','alt','alt_l','alt_r','shift','shift_l','shift_r','cmd','cmd_l','cmd_r'}
NAMED={'esc','enter','tab','space','backspace','delete','insert','home','end','page_up','page_down','up','down','left','right','caps_lock','pause','print_screen','scroll_lock','num_lock'}

def normalize_hotkey(text):
    if ',' in text: raise ValueError('Record one combination, not a sequence of combinations')
    parts=[ALIASES.get(p.strip().lower(),p.strip().lower()) for p in text.split('+')]
    if not 1<=len(parts)<=4 or any(not p for p in parts): raise ValueError('Choose a key, optionally with Ctrl, Alt or Shift')
    if len(set(parts))!=len(parts): raise ValueError('A key cannot occur twice')
    for p in parts:
        if not (p in MODIFIERS or p in NAMED or len(p)==1 or p.startswith('f') and p[1:].isdigit() and 1<=int(p[1:])<=24 or p.startswith('numpad') and p[6:].isdigit() and 0<=int(p[6:])<=9):
            raise ValueError('Unsupported shortcut key: '+p)
    if all(p in MODIFIERS for p in parts): raise ValueError('Press a regular key along with the modifier, for example Ctrl+F1')
    return [p for p in parts if p in MODIFIERS]+[p for p in parts if p not in MODIFIERS]

class HotkeyWorker:
    def __init__(self,keyboard,key,allowed,held=lambda:set(),tap_ms=60):
        self.keyboard,self.key,self.allowed,self.held=keyboard,key,allowed,held
        self.tap=max(.06,min(.25,float(tap_ms)/1000))
        self.queue=queue.Queue(8);self.stop=threading.Event();self.lock=threading.Lock();self.generation=0
        self.result={};self.thread=threading.Thread(target=self.run,name='uo-hotkeys',daemon=True);self.thread.start()
    def submit(self,keys):
        keys=normalize_hotkey('+'.join(keys))
        with self.lock: generation=self.generation
        try:self.queue.put_nowait((keys,generation,time.monotonic()))
        except queue.Full: self.result={'status':'error','detail':'Shortcut queue full'}
    def cancel(self):
        with self.lock:self.generation+=1
    def valid(self,generation):
        with self.lock: current=self.generation
        return not self.stop.is_set() and generation==current and self.allowed()
    def wait(self,seconds,generation):
        until=time.monotonic()+seconds
        while time.monotonic()<until:
            if not self.valid(generation):return False
            self.stop.wait(min(.01,max(0,until-time.monotonic())))
        return self.valid(generation)
    def run(self):
        while not self.stop.is_set():
            try:keys,generation,stamp=self.queue.get(timeout=.05)
            except queue.Empty:continue
            pressed=[];completed=False
            try:
                if time.monotonic()-stamp>.3 or not self.valid(generation):
                    self.result={'status':'blocked','detail':'Shortcut cancelled or selected game lost focus'};continue
                for name in keys:
                    if not self.valid(generation):break
                    key=self.key(name)
                    if key not in self.held():self.keyboard.press(key);pressed.append(key)
                    if name in MODIFIERS and not self.wait(.02,generation):break
                else:
                    if self.wait(self.tap,generation):
                        self.result={'status':'sent','detail':'+'.join(keys)+' sent to Windows; Razor action is not confirmed'};completed=True
            except Exception as exc:self.result={'status':'error','detail':str(exc)}
            finally:
                if not completed:self.result={'status':'blocked','detail':'Shortcut cancelled, expired or selected game lost focus'}
                for key in reversed(pressed):
                    try:self.keyboard.release(key)
                    except Exception:pass
    def close(self):
        self.cancel();self.stop.set();self.thread.join(timeout=1)
