# -*- coding: utf-8 -*-
"""IronPython 2.7 inside Razor Enhanced. Keep bindings.json beside this script.
All game API calls run on this one script thread. No RazorEnhanced import needed.
"""
import os
import copy
import json
import hmac
import hashlib
import math
import time
import traceback
import clr
clr.AddReference("System")
from System.Diagnostics import Stopwatch, Process
from System.Collections.Generic import List
from System import Byte, Array
from System.Text import Encoding
from System.Net import IPAddress
from System.Net.Sockets import TcpClient, SocketException, SocketFlags

try:
    STRING_TYPES = (basestring,)
except NameError:
    STRING_TYPES = (str,)

SCRIPT_FOLDER = os.path.dirname(os.path.abspath(__file__))
POINTER_PATH = os.path.join(SCRIPT_FOLDER, 'controller_studio_connection.json')
CONFIG_PATH = os.path.join(SCRIPT_FOLDER, 'bindings.json')
if os.path.isfile(POINTER_PATH):
    with open(POINTER_PATH, 'r') as pointer_file:
        CONFIG_PATH = json.load(pointer_file)['config_path']
if not os.path.isfile(CONFIG_PATH):
    raise ValueError('Open Controller Studio, complete setup and install the listener again.')
with open(CONFIG_PATH, 'r') as config_file:
    CONFIG = json.load(config_file)
BRIDGE = CONFIG['bridge']
SETTINGS = CONFIG['razor']
if BRIDGE['host'] != '127.0.0.1':
    raise ValueError('Only loopback is allowed')
if BRIDGE['mode'] != 'socket':
    raise ValueError('Listener is only used with bridge.mode=socket')

VERSION = '4.0.0-beta.1'

# BEGIN EMBEDDED ACTION CATALOG
# -*- coding: utf-8 -*-
"""Native controller actions; Python 2.7 and 3 compatible."""
# Fixed native Razor hotkey handlers; no keyboard hotkey registration is needed.
BUILTIN_AGENT_ACTIONS = {
    'agent_bone_cutter_toggle': ('ProcessAgentBoneCutter','Bone Cutter Trigger ON/OFF','Bone Cutter: Toggle'),
    'agent_bone_cutter_set_blade': ('ProcessAgentBoneCutter','Bone Cutter Set Blade','Bone Cutter: Set blade'),
    'agent_auto_carver_toggle': ('ProcessAgentAutoCarver','Auto Carver Trigger ON/OFF','Auto Carver: Toggle'),
    'agent_auto_carver_set_blade': ('ProcessAgentAutoCarver','Auto Carver Set Blade','Auto Carver: Set blade'),
    'agent_auto_remount_toggle': ('ProcessAgentAutoRemount','Auto Remount Trigger ON/OFF','Auto Remount: Toggle'),
    'agent_auto_remount_set_mount': ('ProcessAgentAutoRemount','Auto Remount Set Mount','Auto Remount: Set mount'),
    'agent_graphic_filter_toggle': ('ProcessAgentGraphFilter','Graphic Filter Trigger ON/OFF','Graphic Filter: Toggle')}

def native_actions():
    actions = {}
    for command in ('all follow me','all come','all guard me','all kill','all stay','all stop'):
        actions['pet_'+command.replace(' ','_')] = {'type':'pet_command','command':command,
            'label':'Pets: '+command.title(),'category':'pets','cooldown_ms':250}
    actions['use_last_item'] = {'type':'use_last_item','label':'Use last item','category':'items'}
    actions['arm_last_weapon'] = {'type':'arm_last_weapon','label':'Arm last weapon','category':'items'}
    for operation in ('disarm','arm','toggle'):
        for hand in ('both','left','right'):
            actions[operation+'_'+hand] = {'type':'hands','operation':operation,'hand':hand,
                'label':operation.title()+' '+hand+' hand'+('s' if hand=='both' else ''),
                'category':'items','cooldown_ms':400}
    agents = ('AutoLoot','Scavenger','BandageHeal','Organizer','Restock','Dress','UnDress','BuyAgent','SellAgent','DPSMeter')
    for agent in agents:
        for operation in ('start','stop','toggle'):
            actions['agent_'+agent.lower()+'_'+operation] = {'type':'agent','agent':agent,
                'operation':operation,'label':agent+': '+operation.title(),
                'category':'agents','cooldown_ms':300}
    actions['agent_friend_add'] = {'type':'friend_target','label':'Friends: Add friend (target)','category':'agents'}
    for key, info in BUILTIN_AGENT_ACTIONS.items():
        actions[key] = {'type':'builtin_agent','builtin':key,'label':info[2],'category':'agents','cooldown_ms':300}
    return actions
# END EMBEDDED ACTION CATALOG

# BEGIN EMBEDDED SPELL CATALOG
SCHOOL_ORDER = ('Magery', 'Mysticism', 'Necromancy', 'Spellweaving', 'Bushido', 'Ninjitsu', 'Chivalry')
SPELL_METHODS = {'Bushido': 'CastBushido',
 'Chivalry': 'CastChivalry',
 'Magery': 'CastMagery',
 'Mysticism': 'CastMysticism',
 'Necromancy': 'CastNecro',
 'Ninjitsu': 'CastNinjitsu',
 'Spellweaving': 'CastSpellweaving'}
SPELL_CATALOG = {'Bushido': [{'auto_target': False,
              'circle': 0,
              'id': 401,
              'name': 'Honorable Execution',
              'recovery_ms': 500},
             {'auto_target': False, 'circle': 0, 'id': 402, 'name': 'Confidence', 'recovery_ms': 500},
             {'auto_target': False, 'circle': 0, 'id': 403, 'name': 'Evasion', 'recovery_ms': 500},
             {'auto_target': False, 'circle': 0, 'id': 404, 'name': 'Counter Attack', 'recovery_ms': 500},
             {'auto_target': False, 'circle': 0, 'id': 405, 'name': 'Lightning Strike', 'recovery_ms': 500},
             {'auto_target': False, 'circle': 0, 'id': 406, 'name': 'Momentum Strike', 'recovery_ms': 500}],
 'Chivalry': [{'auto_target': True, 'circle': 0, 'id': 201, 'name': 'Cleanse By Fire', 'recovery_ms': 1500},
              {'auto_target': True, 'circle': 0, 'id': 202, 'name': 'Close Wounds', 'recovery_ms': 1500},
              {'auto_target': False,
               'circle': 0,
               'id': 203,
               'name': 'Consecrate Weapon',
               'recovery_ms': 1500},
              {'auto_target': False, 'circle': 0, 'id': 204, 'name': 'Dispel Evil', 'recovery_ms': 1500},
              {'auto_target': False, 'circle': 0, 'id': 205, 'name': 'Divine Fury', 'recovery_ms': 1500},
              {'auto_target': False, 'circle': 0, 'id': 206, 'name': 'Enemy Of One', 'recovery_ms': 1500},
              {'auto_target': False, 'circle': 0, 'id': 207, 'name': 'Holy Light', 'recovery_ms': 1500},
              {'auto_target': False, 'circle': 0, 'id': 208, 'name': 'Noble Sacrifice', 'recovery_ms': 1500},
              {'auto_target': True, 'circle': 0, 'id': 209, 'name': 'Remove Curse', 'recovery_ms': 1500},
              {'auto_target': False, 'circle': 0, 'id': 210, 'name': 'Sacred Journey', 'recovery_ms': 1500}],
 'Magery': [{'auto_target': True, 'circle': 1, 'id': 1, 'name': 'Clumsy', 'recovery_ms': 850},
            {'auto_target': False, 'circle': 1, 'id': 2, 'name': 'Create Food', 'recovery_ms': 850},
            {'auto_target': True, 'circle': 1, 'id': 3, 'name': 'Feeblemind', 'recovery_ms': 850},
            {'auto_target': True, 'circle': 1, 'id': 4, 'name': 'Heal', 'recovery_ms': 850},
            {'auto_target': True, 'circle': 1, 'id': 5, 'name': 'Magic Arrow', 'recovery_ms': 850},
            {'auto_target': True, 'circle': 1, 'id': 6, 'name': 'Night Sight', 'recovery_ms': 850},
            {'auto_target': False, 'circle': 1, 'id': 7, 'name': 'Reactive Armor', 'recovery_ms': 850},
            {'auto_target': True, 'circle': 1, 'id': 8, 'name': 'Weaken', 'recovery_ms': 850},
            {'auto_target': True, 'circle': 2, 'id': 9, 'name': 'Agility', 'recovery_ms': 1100},
            {'auto_target': True, 'circle': 2, 'id': 10, 'name': 'Cunning', 'recovery_ms': 1100},
            {'auto_target': True, 'circle': 2, 'id': 11, 'name': 'Cure', 'recovery_ms': 1100},
            {'auto_target': True, 'circle': 2, 'id': 12, 'name': 'Harm', 'recovery_ms': 1100},
            {'auto_target': False, 'circle': 2, 'id': 13, 'name': 'Magic Trap', 'recovery_ms': 1100},
            {'auto_target': False, 'circle': 2, 'id': 14, 'name': 'Magic Untrap', 'recovery_ms': 1100},
            {'auto_target': False, 'circle': 2, 'id': 15, 'name': 'Protection', 'recovery_ms': 1100},
            {'auto_target': True, 'circle': 2, 'id': 16, 'name': 'Strength', 'recovery_ms': 1100},
            {'auto_target': True, 'circle': 3, 'id': 17, 'name': 'Bless', 'recovery_ms': 1350},
            {'auto_target': True, 'circle': 3, 'id': 18, 'name': 'Fireball', 'recovery_ms': 1350},
            {'auto_target': False, 'circle': 3, 'id': 19, 'name': 'Magic Lock', 'recovery_ms': 1350},
            {'auto_target': True, 'circle': 3, 'id': 20, 'name': 'Poison', 'recovery_ms': 1350},
            {'auto_target': False, 'circle': 3, 'id': 21, 'name': 'Telekinesis', 'recovery_ms': 1350},
            {'auto_target': False, 'circle': 3, 'id': 22, 'name': 'Teleport', 'recovery_ms': 1350},
            {'auto_target': False, 'circle': 3, 'id': 23, 'name': 'Unlock', 'recovery_ms': 1350},
            {'auto_target': False, 'circle': 3, 'id': 24, 'name': 'Wall of Stone', 'recovery_ms': 1350},
            {'auto_target': True, 'circle': 4, 'id': 25, 'name': 'Arch Cure', 'recovery_ms': 1600},
            {'auto_target': True, 'circle': 4, 'id': 26, 'name': 'Arch Protection', 'recovery_ms': 1600},
            {'auto_target': True, 'circle': 4, 'id': 27, 'name': 'Curse', 'recovery_ms': 1600},
            {'auto_target': False, 'circle': 4, 'id': 28, 'name': 'Fire Field', 'recovery_ms': 1600},
            {'auto_target': True, 'circle': 4, 'id': 29, 'name': 'Greater Heal', 'recovery_ms': 1600},
            {'auto_target': True, 'circle': 4, 'id': 30, 'name': 'Lightning', 'recovery_ms': 1600},
            {'auto_target': True, 'circle': 4, 'id': 31, 'name': 'Mana Drain', 'recovery_ms': 1600},
            {'auto_target': False, 'circle': 4, 'id': 32, 'name': 'Recall', 'recovery_ms': 1600},
            {'auto_target': False, 'circle': 5, 'id': 33, 'name': 'Blade Spirits', 'recovery_ms': 1850},
            {'auto_target': False, 'circle': 5, 'id': 34, 'name': 'Dispel Field', 'recovery_ms': 1850},
            {'auto_target': False, 'circle': 5, 'id': 35, 'name': 'Incognito', 'recovery_ms': 1850},
            {'auto_target': False, 'circle': 5, 'id': 36, 'name': 'Magic Reflection', 'recovery_ms': 1850},
            {'auto_target': True, 'circle': 5, 'id': 37, 'name': 'Mind Blast', 'recovery_ms': 1850},
            {'auto_target': True, 'circle': 5, 'id': 38, 'name': 'Paralyze', 'recovery_ms': 1850},
            {'auto_target': False, 'circle': 5, 'id': 39, 'name': 'Poison Field', 'recovery_ms': 1850},
            {'auto_target': False, 'circle': 5, 'id': 40, 'name': 'Summon Creature', 'recovery_ms': 1850},
            {'auto_target': True, 'circle': 6, 'id': 41, 'name': 'Dispel', 'recovery_ms': 2100},
            {'auto_target': True, 'circle': 6, 'id': 42, 'name': 'Energy Bolt', 'recovery_ms': 2100},
            {'auto_target': True, 'circle': 6, 'id': 43, 'name': 'Explosion', 'recovery_ms': 2100},
            {'auto_target': True, 'circle': 6, 'id': 44, 'name': 'Invisibility', 'recovery_ms': 2100},
            {'auto_target': False, 'circle': 6, 'id': 45, 'name': 'Mark', 'recovery_ms': 2100},
            {'auto_target': False, 'circle': 6, 'id': 46, 'name': 'Mass Curse', 'recovery_ms': 2100},
            {'auto_target': False, 'circle': 6, 'id': 47, 'name': 'Paralyze Field', 'recovery_ms': 2100},
            {'auto_target': False, 'circle': 6, 'id': 48, 'name': 'Reveal', 'recovery_ms': 2100},
            {'auto_target': True, 'circle': 7, 'id': 49, 'name': 'Chain Lightning', 'recovery_ms': 2350},
            {'auto_target': False, 'circle': 7, 'id': 50, 'name': 'Energy Field', 'recovery_ms': 2350},
            {'auto_target': True, 'circle': 7, 'id': 51, 'name': 'Flamestrike', 'recovery_ms': 2350},
            {'auto_target': False, 'circle': 7, 'id': 52, 'name': 'Gate Travel', 'recovery_ms': 2350},
            {'auto_target': True, 'circle': 7, 'id': 53, 'name': 'Mana Vampire', 'recovery_ms': 2350},
            {'auto_target': False, 'circle': 7, 'id': 54, 'name': 'Mass Dispel', 'recovery_ms': 2350},
            {'auto_target': True, 'circle': 7, 'id': 55, 'name': 'Meteor Swarm', 'recovery_ms': 2350},
            {'auto_target': False, 'circle': 7, 'id': 56, 'name': 'Polymorph', 'recovery_ms': 2350},
            {'auto_target': False, 'circle': 8, 'id': 57, 'name': 'Earthquake', 'recovery_ms': 2600},
            {'auto_target': False, 'circle': 8, 'id': 58, 'name': 'Energy Vortex', 'recovery_ms': 2600},
            {'auto_target': True, 'circle': 8, 'id': 59, 'name': 'Resurrection', 'recovery_ms': 2600},
            {'auto_target': False,
             'circle': 8,
             'id': 60,
             'name': 'Summon Air Elemental',
             'recovery_ms': 2600},
            {'auto_target': False, 'circle': 8, 'id': 61, 'name': 'Summon Daemon', 'recovery_ms': 2600},
            {'auto_target': False,
             'circle': 8,
             'id': 62,
             'name': 'Summon Earth Elemental',
             'recovery_ms': 2600},
            {'auto_target': False,
             'circle': 8,
             'id': 63,
             'name': 'Summon Fire Elemental',
             'recovery_ms': 2600},
            {'auto_target': False,
             'circle': 8,
             'id': 64,
             'name': 'Summon Water Elemental',
             'recovery_ms': 2600}],
 'Mysticism': [{'auto_target': True, 'circle': 1, 'id': 678, 'name': 'Nether Bolt', 'recovery_ms': 850},
               {'auto_target': False, 'circle': 1, 'id': 679, 'name': 'Healing Stone', 'recovery_ms': 850},
               {'auto_target': True, 'circle': 2, 'id': 680, 'name': 'Purge Magic', 'recovery_ms': 1100},
               {'auto_target': False, 'circle': 2, 'id': 681, 'name': 'Enchant', 'recovery_ms': 1100},
               {'auto_target': True, 'circle': 3, 'id': 682, 'name': 'Sleep', 'recovery_ms': 1350},
               {'auto_target': True, 'circle': 3, 'id': 683, 'name': 'Eagle Strike', 'recovery_ms': 1350},
               {'auto_target': False, 'circle': 4, 'id': 684, 'name': 'Animated Weapon', 'recovery_ms': 1600},
               {'auto_target': False, 'circle': 4, 'id': 685, 'name': 'Stone Form', 'recovery_ms': 1600},
               {'auto_target': False, 'circle': 5, 'id': 686, 'name': 'Spell Trigger', 'recovery_ms': 1850},
               {'auto_target': True, 'circle': 5, 'id': 687, 'name': 'Mass Sleep', 'recovery_ms': 1850},
               {'auto_target': True, 'circle': 6, 'id': 688, 'name': 'Cleansing Winds', 'recovery_ms': 2100},
               {'auto_target': True, 'circle': 6, 'id': 689, 'name': 'Bombard', 'recovery_ms': 2100},
               {'auto_target': True, 'circle': 7, 'id': 690, 'name': 'Spell Plague', 'recovery_ms': 2350},
               {'auto_target': True, 'circle': 7, 'id': 691, 'name': 'Hail Storm', 'recovery_ms': 2350},
               {'auto_target': True, 'circle': 8, 'id': 692, 'name': 'Nether Cyclone', 'recovery_ms': 2600},
               {'auto_target': False,
                'circle': 8,
                'id': 693,
                'name': 'Rising Colossus',
                'recovery_ms': 2600}],
 'Necromancy': [{'auto_target': False, 'circle': 0, 'id': 101, 'name': 'Animate Dead', 'recovery_ms': 1500},
                {'auto_target': True, 'circle': 0, 'id': 102, 'name': 'Blood Oath', 'recovery_ms': 1500},
                {'auto_target': True, 'circle': 0, 'id': 103, 'name': 'Corpse Skin', 'recovery_ms': 2500},
                {'auto_target': False, 'circle': 0, 'id': 104, 'name': 'Curse Weapon', 'recovery_ms': 1500},
                {'auto_target': True, 'circle': 0, 'id': 105, 'name': 'Evil Omen', 'recovery_ms': 1500},
                {'auto_target': False, 'circle': 0, 'id': 106, 'name': 'Horrific Beast', 'recovery_ms': 2500},
                {'auto_target': False, 'circle': 0, 'id': 107, 'name': 'Lich Form', 'recovery_ms': 4500},
                {'auto_target': True, 'circle': 0, 'id': 108, 'name': 'Mind Rot', 'recovery_ms': 2500},
                {'auto_target': True, 'circle': 0, 'id': 109, 'name': 'Pain Spike', 'recovery_ms': 1500},
                {'auto_target': True, 'circle': 0, 'id': 110, 'name': 'Poison Strike', 'recovery_ms': 2500},
                {'auto_target': True, 'circle': 0, 'id': 111, 'name': 'Strangle', 'recovery_ms': 3500},
                {'auto_target': False,
                 'circle': 0,
                 'id': 112,
                 'name': 'Summon Familiar',
                 'recovery_ms': 4500},
                {'auto_target': False,
                 'circle': 0,
                 'id': 113,
                 'name': 'Vampiric Embrace',
                 'recovery_ms': 4500},
                {'auto_target': True, 'circle': 0, 'id': 114, 'name': 'Vengeful Spirit', 'recovery_ms': 4500},
                {'auto_target': False, 'circle': 0, 'id': 115, 'name': 'Wither', 'recovery_ms': 1500},
                {'auto_target': False, 'circle': 0, 'id': 116, 'name': 'Wraith Form', 'recovery_ms': 2500},
                {'auto_target': False, 'circle': 0, 'id': 117, 'name': 'Exorcism', 'recovery_ms': 2500}],
 'Ninjitsu': [{'auto_target': False, 'circle': 0, 'id': 501, 'name': 'Focus Attack', 'recovery_ms': 500},
              {'auto_target': False, 'circle': 0, 'id': 502, 'name': 'Death Strike', 'recovery_ms': 500},
              {'auto_target': False, 'circle': 0, 'id': 503, 'name': 'Animal Form', 'recovery_ms': 500},
              {'auto_target': False, 'circle': 0, 'id': 504, 'name': 'Ki Attack', 'recovery_ms': 500},
              {'auto_target': False, 'circle': 0, 'id': 505, 'name': 'Surprise Attack', 'recovery_ms': 500},
              {'auto_target': False, 'circle': 0, 'id': 506, 'name': 'Backstab', 'recovery_ms': 500},
              {'auto_target': False, 'circle': 0, 'id': 507, 'name': 'Shadowjump', 'recovery_ms': 500},
              {'auto_target': False, 'circle': 0, 'id': 508, 'name': 'Mirror Image', 'recovery_ms': 500}],
 'Spellweaving': [{'auto_target': False,
                   'circle': 0,
                   'id': 601,
                   'name': 'Arcane Circle',
                   'recovery_ms': 1500},
                  {'auto_target': True,
                   'circle': 0,
                   'id': 602,
                   'name': 'Gift Of Renewal',
                   'recovery_ms': 3500},
                  {'auto_target': False,
                   'circle': 0,
                   'id': 603,
                   'name': 'Immolating Weapon',
                   'recovery_ms': 1500},
                  {'auto_target': False, 'circle': 0, 'id': 604, 'name': 'Attunement', 'recovery_ms': 1500},
                  {'auto_target': False, 'circle': 0, 'id': 605, 'name': 'Thunderstorm', 'recovery_ms': 2000},
                  {'auto_target': False, 'circle': 0, 'id': 606, 'name': 'Natures Fury', 'recovery_ms': 2000},
                  {'auto_target': False, 'circle': 0, 'id': 607, 'name': 'Summon Fey', 'recovery_ms': 2500},
                  {'auto_target': False, 'circle': 0, 'id': 608, 'name': 'Summon Fiend', 'recovery_ms': 2500},
                  {'auto_target': False, 'circle': 0, 'id': 609, 'name': 'Reaper Form', 'recovery_ms': 3000},
                  {'auto_target': False, 'circle': 0, 'id': 610, 'name': 'Wildfire', 'recovery_ms': 3500},
                  {'auto_target': False,
                   'circle': 0,
                   'id': 611,
                   'name': 'Essence Of Wind',
                   'recovery_ms': 3500},
                  {'auto_target': True, 'circle': 0, 'id': 612, 'name': 'Dryad Allure', 'recovery_ms': 3500},
                  {'auto_target': False,
                   'circle': 0,
                   'id': 613,
                   'name': 'Ethereal Voyage',
                   'recovery_ms': 4000},
                  {'auto_target': True, 'circle': 0, 'id': 614, 'name': 'Word Of Death', 'recovery_ms': 4000},
                  {'auto_target': True, 'circle': 0, 'id': 615, 'name': 'Gift Of Life', 'recovery_ms': 4500},
                  {'auto_target': False,
                   'circle': 0,
                   'id': 616,
                   'name': 'Arcane Empowerment',
                   'recovery_ms': 4500}]}


def get_spell(school, name):
    for spell in SPELL_CATALOG.get(school, []):
        if spell['name'] == name:
            return spell
    raise ValueError('Unknown spell or school')


def make_spell_action(school, name, target='none', recovery_ms=None):
    spell = get_spell(school, name)
    if target not in ('none', 'self', 'last'):
        raise ValueError('Choose Manual, Self or Last targeting')
    if target != 'none' and not spell['auto_target']:
        raise ValueError('This spell uses its native target/menu; choose Manual')
    recovery = spell['recovery_ms'] if recovery_ms is None else int(recovery_ms)
    if isinstance(recovery_ms, bool) or not 0 <= recovery <= 10000:
        raise ValueError('Recovery must be 0 to 10000 milliseconds')
    action = {'type':'cast', 'school':school, 'spell':spell['name'], 'target':target,
              'recovery_ms':recovery, 'cooldown_ms':250, 'target_timeout_ms':10000,
              'catalog_spell':True}
    key = 'spell_%s_%d_%s_%d' % (school, spell['id'], target, recovery)
    return key, action

# END EMBEDDED SPELL CATALOG

CLOCK = Stopwatch.StartNew()

def now():
    return CLOCK.Elapsed.TotalSeconds


def log(message, error=False):
    text = '[Controller ' + VERSION + '] ' + str(message)
    Misc.SendMessage(text, 33 if error else 68)
    try:
        with open(os.path.join(os.path.dirname(CONFIG_PATH), 'razor_listener.log'), 'a') as stream:
            stream.write(time.strftime('%Y-%m-%d %H:%M:%S ') + text + '\n')
    except Exception:
        pass


class DotNetConnection(object):
    """Native .NET TCP transport for IronPython, with explicit connect completion.

    No send/receive is attempted until EndConnect succeeds. Input processing
    polls nonblocking sockets; incomplete connects return control to the loop.
    """
    def __init__(self, host, port):
        self.client = TcpClient()
        self.connected = False
        self.started = now()
        self.flags = getattr(SocketFlags, 'None')
        self.buffer = Array.CreateInstance(Byte, 8192)
        try:
            self.pending = self.client.BeginConnect(IPAddress.Parse(host), int(port), None, None)
        except Exception:
            self.client.Close()
            raise

    def poll_connected(self):
        if self.connected:
            return True
        if not self.pending.IsCompleted:
            if now() - self.started > 2.0:
                raise IOError('TCP connection timed out; check that the controller console is running')
            return False
        self.client.EndConnect(self.pending)
        if not self.client.Connected:
            raise IOError('TCP connection was not established')
        self.client.NoDelay = True
        self.client.Client.Blocking = False
        self.connected = True
        return True

    @staticmethod
    def would_block(exc):
        return int(exc.ErrorCode) in (10035, 10036, 10037)

    def recv(self, size):
        if not self.connected:
            raise IOError('TCP connection is not ready')
        try:
            count = self.client.Client.Receive(self.buffer, 0, min(size, len(self.buffer)), self.flags)
            return Encoding.ASCII.GetString(self.buffer, 0, count)
        except SocketException as exc:
            if self.would_block(exc):
                return None
            raise

    def send(self, text):
        if not self.connected:
            raise IOError('TCP connection is not ready')
        data = Encoding.ASCII.GetBytes(text)
        try:
            return self.client.Client.Send(data, 0, len(data), self.flags)
        except SocketException as exc:
            if self.would_block(exc):
                return None
            raise

    def close(self):
        self.connected = False
        self.client.Close()


def serial(value):
    return int(value, 0) if isinstance(value, STRING_TYPES) else int(value)


def last_item_serial():
    """Read Razor's own Last Item state; do not guess from our last item action.

    RE has no public Items.UseLastItem API. World is an internal .NET type, so
    normal IronPython imports cannot access it. Resolve its read-only state via
    reflection. Fail clearly on incompatible builds rather than using a stale item.
    """
    from System import AppDomain
    from System.Reflection import BindingFlags
    world_type = None
    for assembly in AppDomain.CurrentDomain.GetAssemblies():
        world_type = assembly.GetType('Assistant.World', False)
        if world_type is not None: break
    if world_type is None: raise ValueError('Last Item is unavailable in this Razor build; use a Razor hotkey instead')
    flags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static
    prop = world_type.GetProperty('Player', flags)
    if prop is None: raise ValueError('Last Item state is unavailable in this Razor build')
    player = prop.GetValue(None, None)
    if player is None: raise ValueError('Log into a character first')
    flags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance
    prop = player.GetType().GetProperty('LastObject', flags)
    if prop is None: raise ValueError('Last Item state is unavailable in this Razor build')
    value = prop.GetValue(player, None)
    return int(value.Value)


def invoke_builtin_agent(key):
    """Call a fixed Razor handler on its UI thread, without injecting a key.

    Some Agent hotkeys have no public scripting API. Keep this compatibility
    adapter isolated and allow only the catalog's known command names.
    """
    if key not in BUILTIN_AGENT_ACTIONS: raise ValueError('Unknown built-in agent command')
    from System import AppDomain, Action, Object
    from System.Reflection import BindingFlags
    flags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static
    hotkey_type = engine_type = None
    for assembly in AppDomain.CurrentDomain.GetAssemblies():
        if hotkey_type is None: hotkey_type = assembly.GetType('RazorEnhanced.HotKey', False)
        if engine_type is None: engine_type = assembly.GetType('Assistant.Engine', False)
        if hotkey_type is not None and engine_type is not None: break
    if hotkey_type is None or engine_type is None:
        raise ValueError('Built-in agent access is unavailable in this Razor build; use a Razor hotkey instead')
    method_name, command, label = BUILTIN_AGENT_ACTIONS[key]
    method = hotkey_type.GetMethod(method_name, flags)
    if method is None: raise ValueError(label+' is unavailable in this Razor build')
    prop = engine_type.GetProperty('MainWindow', flags)
    field = engine_type.GetField('MainWindow', flags) if prop is None else None
    window = prop.GetValue(None, None) if prop is not None else field.GetValue(None) if field is not None else None
    if window is None: raise ValueError('Razor agent window is unavailable')
    errors = []
    def invoke():
        try: method.Invoke(None, Array[Object]([command]))
        except Exception as exc: errors.append(str(exc))
    if window.InvokeRequired: window.Invoke(Action(invoke))
    else: invoke()
    if errors: raise ValueError(label+': '+errors[0])


class Executor(object):
    def __init__(self):
        self.pending_target = None
        self.busy_until = 0.0
        self.cooldowns = {}
        self.equip_index = {}
        self.saved_hands = {}
        self.pending_hands = []
        self.next_hand = 0.0

    def reset(self):
        # Cancel only a cursor associated with an unfinished bridge action.
        if self.pending_target and Target.HasTarget():
            Target.Cancel()
        self.pending_target = None
        self.busy_until = 0.0
        self.cooldowns.clear()
        self.pending_hands = []
        self.next_hand = 0.0

    def aim(self, target):
        if target == 'self':
            Target.Self()
        elif target == 'last':
            if not Target.GetLast():
                raise ValueError('No last target selected')
            Target.Last()
        else:
            Target.TargetExecute(serial(target))

    def schedule_target(self, target, duration):
        if target and target != 'none':
            self.pending_target = (target, now() + duration)

    def tick_hands(self):
        if not self.pending_hands or now() < self.next_hand: return
        operation, layer, item_id = self.pending_hands.pop(0)
        try:
            if operation == 'disarm':
                current = Player.GetItemOnLayer(layer)
                if current is not None and int(current.Serial) == item_id:
                    Player.UnEquipItemByLayer(layer, False)
            else:
                item = Items.FindBySerial(item_id)
                if item is None: raise ValueError('Remembered hand item is no longer available')
                Player.EquipItem(item.Serial)
        except Exception as exc:
            self.pending_hands = []
            log('Hand action failed: '+str(exc), True)
        # Separate two-hand inventory operations without blocking the socket loop.
        self.next_hand = now() + .6

    def tick(self):
        self.tick_hands()
        if not self.pending_target:
            return
        target, deadline = self.pending_target
        if Target.HasTarget():
            try:
                self.aim(target)
            except Exception as exc:
                log('Target failed: ' + str(exc), True)
            self.pending_target = None
        elif now() >= deadline:
            log('Target cursor timed out (cast may have fizzled)', True)
            self.pending_target = None

    def find_item(self, action):
        if action.get('serial'):
            item = Items.FindBySerial(serial(action['serial']))
        else:
            item = Items.FindByID(serial(action['item_id']), int(action.get('hue', -1)), Player.Backpack.Serial, True)
        if item is None:
            raise ValueError('Required item not found in backpack')
        return item

    def cycle(self, action):
        filt = Mobiles.Filter()
        filt.Enabled = True
        filt.RangeMax = float(action.get('range', 12))
        filt.Notorieties = List[Byte]([Byte(n) for n in action.get('notorieties', [3, 4, 5, 6])])
        filt.IsGhost = 0
        mobiles = [m for m in Mobiles.ApplyFilter(filt) if m.Serial != Player.Serial]
        mobiles.sort(key=lambda m: (Player.DistanceTo(m), int(m.Serial)))
        if not mobiles:
            raise ValueError('No matching mobiles in range')
        ids = [m.Serial for m in mobiles]
        current = Target.GetLast()
        index = (ids.index(current) + 1) % len(ids) if current in ids else 0
        Target.SetLast(ids[index], False)
        Mobiles.Message(ids[index], 53, 'Controller target')

    def execute(self, name, value):
        action = CONFIG['actions'].get(name)
        if not action:
            return 'rejected', 'Unknown action name'
        kind = action['type']
        stamp = now()
        if kind == 'cancel_target':
            self.pending_target = None
            if Target.HasTarget():
                Target.Cancel()
            return 'ok', 'Target cancelled'
        if stamp < self.cooldowns.get(name, 0):
            return 'busy', 'Action cooldown'
        # Target commands can resolve a live cursor, even during recovery.
        if kind != 'target' and (self.pending_target or self.pending_hands or stamp < self.busy_until):
            return 'busy', 'Casting/item recovery in progress'
        try:
            if kind == 'cast':
                if Target.HasTarget():
                    raise ValueError('Resolve or cancel existing target first')
                target = action.get('target', 'none')
                if target == 'last' and not Target.GetLast():
                    raise ValueError('Select a last target before casting')
                school = action.get('school', 'Magery')
                methods = SPELL_METHODS
                if school not in methods:
                    raise ValueError('Unsupported spell school')
                getattr(Spells, methods[school])(action['spell'])
                self.schedule_target(target, action.get('target_timeout_ms', 4000) / 1000.0)
            elif kind == 'use_item':
                if action.get('target') and Target.HasTarget():
                    raise ValueError('Resolve or cancel existing target first')
                item = self.find_item(action)
                Items.UseItem(item.Serial)
                self.schedule_target(action.get('target'), action.get('target_timeout_ms', 1500) / 1000.0)
            elif kind == 'pet_command':
                Player.ChatSay(1153, action['command'])
            elif kind == 'use_last_item':
                # Same last-object state used by Razor's built-in Last Item hotkey.
                item_id = last_item_serial()
                if not item_id:
                    raise ValueError('Use an item once before using Last Item')
                Items.UseItem(item_id)
            elif kind == 'arm_last_weapon':
                Player.EquipLastWeapon()
            elif kind == 'hands':
                layers = ('LeftHand','RightHand') if action['hand']=='both' else (('LeftHand',) if action['hand']=='left' else ('RightHand',))
                held = [(layer,Player.GetItemOnLayer(layer)) for layer in layers]
                remove = action['operation']=='disarm' or (action['operation']=='toggle' and any(item is not None for layer,item in held))
                if remove:
                    for layer,item in held:
                        if item is not None:
                            self.saved_hands[layer] = int(item.Serial)
                            self.pending_hands.append(('disarm',layer,int(item.Serial)))
                else:
                    ids = [self.saved_hands[layer] for layer in layers if layer in self.saved_hands]
                    if not ids: raise ValueError('Disarm with Controller Studio once to remember these hands, or use Arm last weapon')
                    for item_id in ids:
                        item = Items.FindBySerial(item_id)
                        if item is None: raise ValueError('Remembered hand item is no longer available')
                        self.pending_hands.append(('arm','',item_id))
                self.tick_hands()
            elif kind == 'friend_target':
                Friend.AddFriendTarget()
            elif kind == 'builtin_agent':
                invoke_builtin_agent(action['builtin'])
            elif kind == 'agent':
                api_name = 'Dress' if action['agent']=='UnDress' else action['agent']
                api = globals().get(api_name)
                if api is None: raise ValueError(api_name+' is unavailable in this Razor version')
                methods = {'Organizer':('FStart','FStop','Status'), 'Restock':('FStart','FStop','Status'),
                    'Dress':('DressFStart','DressFStop','DressStatus'), 'UnDress':('UnDressFStart','UnDressFStop','UnDressStatus'),
                    'BuyAgent':('Enable','Disable','Status'), 'SellAgent':('Enable','Disable','Status')}
                start,stop,status = methods.get(action['agent'],('Start','Stop','Status'))
                operation = action['operation']
                stopping = operation=='stop' or (operation=='toggle' and getattr(api,status)())
                getattr(api,stop if stopping else start)()
            elif kind == 'target':
                if not Target.HasTarget():
                    raise ValueError('No active target cursor')
                self.aim(action['target'])
                self.pending_target = None
            elif kind == 'cycle_target':
                self.cycle(action)
            elif kind == 'attack_last':
                if not Target.GetLast():
                    raise ValueError('No last target selected')
                Player.Attack(Target.GetLast())
            elif kind == 'ability':
                if action['slot'] == 'primary':
                    Player.WeaponPrimarySA()
                else:
                    Player.WeaponSecondarySA()
            elif kind == 'equip_cycle':
                weapons = action['serials']
                if not weapons:
                    raise ValueError('Configure weapon serials or use Capture weapons')
                index = self.equip_index.get(name, 0) % len(weapons)
                equipped = [Player.GetItemOnLayer(layer) for layer in ('RightHand', 'LeftHand')]
                held = [int(item.Serial) for item in equipped if item is not None]
                ids = [serial(weapon) for weapon in weapons]
                for held_serial in held:
                    if held_serial in ids:
                        index = (ids.index(held_serial) + 1) % len(weapons)
                        break
                item = Items.FindBySerial(serial(weapons[index]))
                if item is None:
                    raise ValueError('Configured weapon no longer exists')
                Player.EquipItem(item.Serial)
                self.equip_index[name] = (index + 1) % len(weapons)
            elif kind == 'step':
                heading = action['direction']
                if heading not in ('North','Right','East','Down','South','Left','West','Up'):
                    raise ValueError('Invalid movement direction')
                Player.Run(heading) if action.get('run') else Player.Walk(heading)
            elif kind == 'none':
                return 'ok', 'Unbound'
            elif kind == 'skill':
                Player.UseSkill(action['skill'])
            else:
                raise ValueError('Unsupported action type ' + str(kind))
            self.busy_until = max(self.busy_until, now() + action.get('recovery_ms', 0) / 1000.0)
            self.cooldowns[name] = stamp + action.get('cooldown_ms', 200) / 1000.0
            return 'ok', 'API invoked'
        except Exception as exc:
            log(name + ': ' + str(exc), True)
            return 'error', str(exc)

    def moving_allowed(self):
        return not self.pending_target and not self.pending_hands and now() >= self.busy_until


class Listener(object):
    def __init__(self):
        self.executor = Executor()
        self.sock = None
        self.session = None
        self.rx = ''
        self.tx = ''
        self.last_seq = 0
        self.last_rx = 0.0
        self.next_ping = 0.0
        self.movement = None
        self.motion_until = 0.0
        self.next_step = 0.0
        self.retry_at = 0.0
        self.next_notice = 0.0
        self.last_error = None
        self.last_error_at = -100.0
        self.paused = False
        self.pause_reason = ''
        self.notice = ''
        self.features = []
        self.ui = None

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        self.sock = None
        self.session = None
        self.rx = self.tx = ''
        self.movement = None
        self.notice = ''
        self.features = []
        self.executor.reset()
        if self.ui:
            self.ui.synced = False
            self.ui.status = 'Host disconnected - waiting'
            self.ui.dirty = True
        self.retry_at = now() + SETTINGS['reconnect_ms'] / 1000.0

    def send(self, message):
        message['session'] = self.session
        self.tx += json.dumps(message, separators=(',', ':')) + '\n'
        if len(self.tx) > 65536:
            raise ValueError('Outgoing buffer overflow')

    def flush(self):
        if not self.tx:
            return
        sent = self.sock.send(self.tx)
        if sent is None:
            return
        if sent == 0:
            raise IOError('Socket closed on send')
        # Protocol JSON uses ASCII escapes, so bytes and characters coincide.
        self.tx = self.tx[sent:]

    def connect(self):
        self.sock = DotNetConnection(BRIDGE['host'], BRIDGE['port'])
        self.last_rx = now()
        self.last_seq = 0
        self.next_step = 0.0

    def message(self, message):
        kind = message.get('type')
        if not self.session:
            if kind != 'hello' or message.get('version') != 1 or message.get('auth') != hmac.new(CONFIG['token'].encode('utf-8'), (message.get('session','')+':host').encode('ascii'), hashlib.sha256).hexdigest():
                raise ValueError('Authentication/version failure: use matching bindings.json')
            self.session = message['session']
            self.features = message.get('features',[])
            self.send({'type': 'ready', 'pid': Process.GetCurrentProcess().Id, 'features':['desktop_editor_v1'],
                       'auth':hmac.new(CONFIG['token'].encode('utf-8'), (self.session+':listener').encode('ascii'), hashlib.sha256).hexdigest()})
            log('Connected to controller host')
            return
        if message.get('session') != self.session:
            raise ValueError('Session mismatch')
        seq = int(message['seq'])
        if seq <= self.last_seq:
            raise ValueError('Duplicate/out-of-order sequence')
        self.last_seq = seq
        age = (time.time() - float(message['at'])) * 1000.0
        if kind == 'profile' or kind == 'configuration_result':
            if message.get('status', 'ok') == 'ok':
                for key in ('layers','actions','input','desktop','revision','available_controls','assignment_profiles','active_assignment_profile'):
                    if key in message['profile']: CONFIG[key] = message['profile'][key]
                previously_paused = self.paused
                self.paused = bool(message.get('paused', False))
                self.pause_reason = message.get('pause_reason','gump' if self.paused else '')
                if self.paused and not previously_paused:
                    self.executor.reset()
                    self.movement = None
            if self.ui:
                if message.get('status','ok')=='ok' and 'gump_enabled' in message.get('profile',{}):
                    self.ui.hidden=not bool(message['profile']['gump_enabled'])
                    if self.ui.hidden: Gumps.CloseGump(self.ui.GUMP_ID)
                self.ui.receive_profile(message)
            return
        if kind == 'reset_input':
            self.executor.reset();self.movement=None;self.next_step=0.0
            return
        if kind == 'notice':
            text = message.get('text', '')
            if text and text != self.notice:
                log(text, message.get('level') == 'error')
            self.notice = text
            if self.ui:
                if text:
                    self.ui.status = text
                self.ui.dirty = True
            return
        if kind == 'control':
            if self.ui and message.get('down'):
                self.ui.last_control = message['control']
                self.ui.last_layer = message.get('layer', 'base')
                action=message.get('action')
                reason=message.get('blocked_reason','')
                if action and not self.ui.changes and self.ui.applying_request is None:
                    reasons={'modifier':'Modifier held; press its paired button.',
                             'unassigned':'Unassigned in this layer. Select the button to bind it.',
                             'application_paused':'Application paused: use Resume all input in Controller Studio.',
                             'gump_paused':'Gump paused: Apply or Cancel, then Resume.',
                             'game_focus':'Game input blocked: focus the selected UO client.',
                             'neutral_required':'Release game buttons and center the movement stick once, then press again.',
                             'listener_offline':'Listener not ready.'}
                    prefix=self.ui.LABELS.get(message['control'],message['control'])+' ['+('Normal' if self.ui.last_layer=='base' else self.ui.last_layer)+']'
                    self.ui.status=prefix+': '+(reasons.get(reason,reason) if reason else self.ui.action_label(action)+' - sent')
                if self.paused and self.ui.pick_by_press:
                    self.ui.layer = 'base'
                    self.ui.select_control(message['control'])
                    self.ui.pick_by_press = False
                    self.ui.text_entry_open = False
                self.ui.dirty = True
            return
        if kind == 'movement':
            heading = message.get('direction')
            if heading not in (None, 'North', 'Right', 'East', 'Down', 'South', 'Left', 'West', 'Up'):
                raise ValueError('Invalid direction')
            ttl = SETTINGS['movement_timeout_ms']
            self.movement = (heading, bool(message.get('run'))) if -100 <= age <= ttl else None
            self.motion_until = now() + max(0, ttl - max(0, age)) / 1000.0
        elif kind == 'action':
            if not -100 <= age <= BRIDGE['action_ttl_ms']:
                status, detail = 'expired', 'Stale command discarded'
            elif self.paused:
                status, detail = 'busy', 'Controller paused in Gump'
            else:
                status, detail = self.executor.execute(message['name'], message.get('value', 1.0))
            if self.ui:
                self.ui.status = self.ui.action_label(message['name']) + ': ' + status + (' - ' + detail if status != 'ok' else '')
                self.ui.dirty = True
            self.send({'type': 'ack', 'seq': seq, 'status': status, 'detail': detail})
        else:
            raise ValueError('Unknown message type')

    def tick(self):
        stamp = now()
        if self.sock is None:
            if stamp < self.retry_at:
                return
            try:
                self.connect()
            except Exception:
                self.retry_at = stamp + SETTINGS['reconnect_ms'] / 1000.0
                if stamp >= self.next_notice:
                    log('Waiting for Controller Studio')
                    self.next_notice = stamp + 10
                return
        try:
            if not self.sock.poll_connected():
                return
            # Bounded receive and line count; API execution stays on this thread.
            for _ in range(4):
                data = self.sock.recv(8192)
                if data is None:
                    break
                if not data:
                    raise IOError('Host disconnected')
                self.rx += data
                if len(self.rx) > 524288:
                    raise ValueError('Incoming buffer overflow')
                self.last_rx = stamp
            for _ in range(32):
                if '\n' not in self.rx:
                    break
                line, self.rx = self.rx.split('\n', 1)
                self.message(json.loads(line))
            if stamp - self.last_rx > 3:
                raise IOError('Host heartbeat timeout')
            if self.session and stamp >= self.next_ping:
                self.send({'type': 'ping','runtime':{'pending_target':bool(self.executor.pending_target),
                    'busy_ms':max(0,int((self.executor.busy_until-now())*1000)), 'paused':self.paused}})
                self.next_ping = stamp + 0.5
            self.flush()
            self.executor.tick()
            stamp = now()
            if not self.paused and self.session and self.movement and stamp < self.motion_until and stamp >= self.next_step and self.executor.moving_allowed():
                heading, running = self.movement
                if heading:
                    result = Player.Run(heading) if running else Player.Walk(heading)
                    interval = SETTINGS['run_interval_ms'] if running else SETTINGS['walk_interval_ms']
                    self.next_step = now() + interval / 1000.0
                    if result is False:
                        self.next_step = now() + SETTINGS['blocked_retry_ms'] / 1000.0
        except Exception as exc:
            detail = str(exc)
            if detail != self.last_error or now() - self.last_error_at >= 10.0:
                log('Connection/action failure: ' + detail, True)
                self.last_error = detail
                self.last_error_at = now()
            self.close()


_CONTROLLER_OUTLINE_RECTS = None


def controller_outline_rects():
    """Cached, two-pixel controller silhouette made from ordinary tiled Gump art.

    Cubic curves become connected integer strokes, then matching horizontal spans
    are merged vertically. No custom client art or per-frame curve calculation.
    """
    global _CONTROLLER_OUTLINE_RECTS
    if _CONTROLLER_OUTLINE_RECTS is not None:
        return _CONTROLLER_OUTLINE_RECTS
    paths = [
        # Outer shell, clockwise from the upper-left shoulder.
        [((74,176),(94,144),(114,120),(144,120)),
         ((144,120),(174,120),(188,140),(214,140)),
         ((214,140),(240,140),(278,140),(302,140)),
         ((302,140),(328,140),(338,120),(366,120)),
         ((366,120),(404,120),(434,172),(452,218)),
         ((452,218),(478,280),(494,382),(494,470)),
         ((494,470),(494,516),(470,548),(430,548)),
         ((430,548),(386,548),(380,510),(366,486)),
         ((366,486),(358,474),(348,470),(330,470)),
         ((330,470),(286,470),(226,470),(170,470)),
         ((170,470),(148,470),(140,492),(128,514)),
         ((128,514),(98,568),(30,558),(22,506)),
         ((22,506),(12,464),(36,246),(74,176))],
        # Shoulder inset frames the logo like the controller's central bridge.
        [((164,172),(180,188),(192,214),(214,214)),
         ((214,214),(238,214),(278,214),(302,214)),
         ((302,214),(324,214),(340,188),(354,172))]
    ]
    pixels = set()
    def stroke(a,b):
        x,y=a;ex,ey=b
        dx,dy=abs(ex-x),-abs(ey-y)
        sx,sy=1 if x<ex else -1,1 if y<ey else -1
        error=dx+dy
        while True:
            # A 2x2 stamp gives a consistent, connected edge at small scale.
            for ox in (0,1):
                for oy in (0,1): pixels.add((x+ox,y+oy))
            if x==ex and y==ey: break
            twice=2*error
            if twice>=dy: error+=dy;x+=sx
            if twice<=dx: error+=dx;y+=sy
    for path in paths:
        for a,b,c,d in path:
            length=sum(math.hypot(q[0]-r[0],q[1]-r[1]) for q,r in ((a,b),(b,c),(c,d)))
            steps=max(8,int(math.ceil(length/2.0)))
            previous=a
            for index in range(1,steps+1):
                t=float(index)/steps;u=1.0-t
                point=(int(round(u*u*u*a[0]+3*u*u*t*b[0]+3*u*t*t*c[0]+t*t*t*d[0])),
                       int(round(u*u*u*a[1]+3*u*u*t*b[1]+3*u*t*t*c[1]+t*t*t*d[1])))
                stroke(previous,point);previous=point
    rows={}
    for x,y in pixels: rows.setdefault(y,[]).append(x)
    rectangles=[];active={}
    for y in range(min(rows),max(rows)+1):
        xs=sorted(rows.get(y,[]));runs=[]
        if xs:
            start=previous=xs[0]
            for x in xs[1:]:
                if x!=previous+1: runs.append((start,previous-start+1));start=x
                previous=x
            runs.append((start,previous-start+1))
        current={}
        for run in runs:
            if run in active:
                rectangle=active[run];rectangle[3]+=1
            else:
                rectangle=[run[0],y,run[1],1];rectangles.append(rectangle)
            current[run]=rectangle
        active=current
    _CONTROLLER_OUTLINE_RECTS=tuple(tuple(rectangle) for rectangle in rectangles)
    return _CONTROLLER_OUTLINE_RECTS


class ControllerGump(object):
    """One local Gump; drafts never change gameplay until the host accepts Apply."""
    GUMP_ID = 0x4C4C4301
    VERSION = VERSION
    WIDTH, HEIGHT = 800, 660
    # Stick emblems by role: horse = movement, ankh = cursor, plain map ring = disabled.
    STICK_ART = {'Movement':(5549,60), 'Mouse':(5545,60), 'Disabled':(1417,80)}
    GOLD, SILVER, GREEN, RED, MUTED = '#E8C870', '#E6E6E6', '#7CD67C', '#FF6E6E', '#A8A8A8'
    SHORT = {'south':'B','east':'A','west':'Y','north':'X','lb':'LB','rb':'RB','lt':'LT','rt':'RT',
             'back':'Back','start':'Start','ls':'L3','rs':'R3','dpad_up':'D-pad up',
             'dpad_down':'D-pad down','dpad_left':'D-pad left','dpad_right':'D-pad right',
             'p1':'P1','p2':'P2'}
    CONTROLS = ['south','east','west','north','lb','rb','lt','rt','back','start','ls','rs',
                'dpad_up','dpad_down','dpad_left','dpad_right','p1','p2']
    LABELS = {'south':'B / bottom','east':'A / right','west':'Y / left','north':'X / top',
              'lb':'L bumper','rb':'R bumper','lt':'L trigger','rt':'R trigger',
              'back':'Back / minus','start':'Start / plus','ls':'Left stick click','rs':'Right stick click',
              'dpad_up':'D-pad up','dpad_down':'D-pad down','dpad_left':'D-pad left',
              'dpad_right':'D-pad right','p1':'Rear P1','p2':'Rear P2'}

    def __init__(self, listener):
        self.listener = listener
        self.layer, self.page, self.selected = 'base', 'bindings', 'south'
        self.action_page = 0
        self.spell_school='Magery'; self.spell_page=0; self.spell_query=''; self.spell_circle=0
        self.spell_selected=None; self.spell_target='none'; self.spell_recovery=None
        self.minimized = self.confirm_exit = self.pick_by_press = False
        self.dirty, self.running = True, True
        self.last_draw, self.next_poll = -10.0, 0.0
        self.last_control, self.last_layer = '-', 'base'
        self.status = 'Waiting for controller host'
        self.request, self.applying_request = 0, None
        self.apply_deadline = 0.0
        self.x, self.y = 60, 60
        self.text_entry_open = False
        self.changes = {}
        self.draft = copy.deepcopy(CONFIG)
        self.revision = 0
        self.available = set(self.CONTROLS[:16])
        self.synced = False

    def label(self, gd, x, y, text, hue=1152, width=280):
        Gumps.AddLabelCropped(gd,x,y,width,22,hue,str(text))

    def html(self, gd, x, y, width, text, color=None, align=None, height=20):
        """HTML text gives centered/right alignment and true colors that labels lack."""
        text = str(text).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
        body = '<BASEFONT COLOR=%s>%s</BASEFONT>' % (color or self.SILVER, text)
        if align == 'center': body = '<CENTER>' + body + '</CENTER>'
        elif align == 'right': body = '<DIV ALIGN=RIGHT>' + body + '</DIV>'
        Gumps.AddHtml(gd,x,y,width,height,body,False,False)

    def panel(self, gd, x, y, width, height, title=None):
        """Dark translucent inset with hairline edges and an optional heading."""
        Gumps.AddImageTiled(gd,x,y,width,height,2624)
        Gumps.AddAlphaRegion(gd,x,y,width,height)
        for lx,ly,lw,lh in [(x,y,width,1),(x,y+height-1,width,1),(x,y,1,height),(x+width-1,y,1,height)]:
            Gumps.AddImageTiled(gd,lx,ly,lw,lh,5058)
        if title: self.html(gd,x+10,y+6,width-20,title,self.GOLD)

    def rule(self, gd, x, y, width):
        Gumps.AddImageTiled(gd,x,y,width,1,5058)

    def tip(self, gd, text):
        try: Gumps.AddTooltip(gd,str(text))
        except Exception:
            try: Gumps.AddTooltip(gd,1114778,str(text))
            except Exception: pass

    def button(self, gd, x, y, number, text='', normal=40019, pressed=40029, tip=None):
        Gumps.AddButton(gd,x,y,normal,pressed,number,1,0)
        self.tip(gd,tip or text)
        # Captions are centered on the 126 px slate button used for all text buttons.
        if text: self.html(gd,x,y+3,126,text,self.SILVER,'center')

    def send_config(self, payload):
        if not self.listener.session:
            self.status='Host disconnected. Your draft is retained.'; self.dirty=True
            return None
        self.request += 1
        if 'paused' in payload:
            self.listener.paused=bool(payload['paused']); self.listener.movement=None
        self.listener.send({'type':'configure','request':self.request,'payload':payload})
        self.dirty=True
        return self.request

    def receive_profile(self, message):
        successful=message.get('status','ok') == 'ok'
        applying=message.get('request') == self.applying_request and self.applying_request is not None
        if successful:
            profile=message['profile']
            self.available=set(profile.get('available_controls', self.CONTROLS[:16]))
            self.synced=True
            if applying or not self.changes:
                self.draft=copy.deepcopy(CONFIG)
                self.revision=profile.get('revision',0)
            if applying:
                self.changes.clear(); self.status='Saved and applied. Resume when ready.'
            elif message['type']=='profile':
                self.status='Connected. Select any control to edit.'
                if self.changes: self.send_config({'paused':True})
        else: self.status='Error: '+message.get('detail','Configuration rejected')
        if successful and not self.changes and message.get('paused') and message.get('pause_reason')=='application':
            self.status='Application paused. Use Resume all input in Controller Studio.'
        elif successful and not applying and message['type']=='configuration_result' and not message.get('paused',False) and not self.changes:
            self.status='Resumed. Release game buttons and center the movement stick once.'
        if applying: self.applying_request=None
        self.dirty=True

    def action_label(self, name):
        action=self.draft['actions'].get(name,{})
        if action.get('type')=='cast':
            mode={'none':'Manual','self':'Self','last':'Last'}.get(action.get('target','none'),'Manual')
            return action['spell']+' ('+mode+')'
        if action.get('type')=='hotkey': return 'Keys: '+'+'.join(action['keys'])
        if action.get('label'): return action['label']
        return {'mouse_left':'Left mouse: click / drag','mouse_right':'Right mouse: click / drag',
                'unbound':'Unassigned'}.get(name,name.replace('_',' ').title())

    def layer_data(self):
        return next((r for r in self.draft['layers'] if r['name']=='base'), {'bindings':{}})

    def binding_text(self, name):
        action=self.layer_data()['bindings'].get(name,{}).get('action','unbound')
        return self.action_label(action)

    def stage_binding(self, action, keys=None):
        self.layer='base'
        data={'control':self.selected,'layer':self.layer,'action':action}
        if keys:
            parts=[p.strip().lower() for p in keys.split('+') if p.strip()]
            if not 1 <= len(parts) <= 4: raise ValueError('Enter one to four keys, for example ctrl+f1')
            data['keys']='+'.join(parts)
            action='key_'+self.draft.get('active_assignment_profile','Custom')+'_'+self.layer+'_'+self.selected
            self.draft['actions'][action]={'type':'hotkey','keys':parts}
        repeat=220 if self.draft['actions'][action].get('type')=='step' else 0
        self.layer_data()['bindings'][self.selected]={'action':action,'repeat_ms':repeat}
        self.changes[('binding',self.layer,self.selected)]={'binding':data}
        self.status='Draft: '+self.LABELS[self.selected]+' -> '+self.action_label(action)
        self.page='bindings'; self.text_entry_open=False

    def stage_setting(self, name, value):
        group='desktop' if name in ('cursor_pixels_per_second','cursor_curve') else 'input'
        self.draft[group][name]=value
        original=CONFIG[group].get(name, {'movement_stick':'left','mouse_stick':'right'}.get(name))
        if original==value: self.changes.pop(('setting',name),None)
        else: self.changes[('setting',name)]={'setting':{'name':name,'value':value}}
        self.status='Draft updated. Apply to save; Cancel to discard.'

    def select_control(self, name):
        if name not in self.available:
            self.status='Not reported separately by the current controller profile.'
            return
        self.selected=name; self.page='actions'; self.action_page=0; self.action_category='all'
        self.send_config({'paused':True})
        self.text_entry_open=True
        self.status='Choose an action for '+self.LABELS.get(name,name)

    def control_art(self, gd, name, x, y, caption='', normal=40018, pressed=40029, width=None):
        self.button(gd,x,y,100+self.CONTROLS.index(name),'',normal,pressed,
                    self.LABELS[name]+': '+self.binding_text(name)+'\nClick to assign; Apply saves changes.')
        if caption:
            if width: self.html(gd,x,y+3,width,caption,self.SILVER,'center')
            else: self.label(gd,x+8,y+2,caption,1152,110)

    def role(self, side):
        if self.draft['input'].get('movement_stick','left')==side: return 'Movement'
        if self.draft['input'].get('mouse_stick','right')==side: return 'Mouse'
        return 'Disabled'

    def stick(self, gd, cx, cy, side):
        """Stick centered on (cx, cy): role emblem, eight direction studs, caption and click."""
        role=self.role(side)
        bid=40 if side=='left' else 41
        art,size=self.STICK_ART[role]
        tip={'Movement':'Movement stick: light push walks, full push runs.',
             'Mouse':'Cursor stick: moves the Windows mouse pointer.',
             'Disabled':'Stick disabled.'}[role]+'\nClick for stick roles and sensitivity.'
        self.html(gd,cx-70,cy-80,140,side.upper()+' STICK',self.GOLD,'center')
        self.button(gd,cx-size//2,cy-size//2,bid,'',art,art,tip)
        for index in range(8):
            angle=math.pi*index/4.0
            self.button(gd,int(round(cx+50*math.sin(angle)))-9,int(round(cy-50*math.cos(angle)))-10,
                        bid,'',1896,1895,tip)
        caption={'Movement':'Movement','Mouse':'Cursor','Disabled':'Disabled'}[role]
        self.html(gd,cx-70,cy+64,140,caption,self.GREEN if role!='Disabled' else self.MUTED,'center')
        self.control_art(gd,'ls' if side=='left' else 'rs',cx-32,cy+86,
                         'L3' if side=='left' else 'R3',40018,40029,64)

    def draw_bindings(self, gd):
        # The shell uses existing gray rule art; all controls retain their IDs.
        for x,y,width,height in controller_outline_rects():
            Gumps.AddImageTiled(gd,x,y,width,height,5058)
        self.control_art(gd,'lt',48,132,'L trigger',40019,40029,126)
        self.control_art(gd,'lb',48,162,'L bumper',40019,40029,126)
        self.control_art(gd,'rt',342,132,'R trigger',40019,40029,126)
        self.control_art(gd,'rb',342,162,'R bumper',40019,40029,126)
        # MysticLlama's standard item-art signature and exact requested hues.
        Gumps.AddItem(gd,238,158,0x20F6,1152)
        Gumps.AddLabel(gd,206,188,1153,'@MysticLlama')
        self.control_art(gd,'back',215,258,'',40016,40016)
        self.button(gd,252,258,3,'',30535 if self.listener.paused else 30534,30533,
                    'Resume controller' if self.listener.paused else 'Pause controller')
        self.control_art(gd,'start',289,258,'',40017,40017)
        self.html(gd,195,286,68,'Back',self.MUTED,'center')
        self.html(gd,269,286,68,'Start',self.MUTED,'center')
        self.stick(gd,112,280,'left')
        self.html(gd,342,210,128,'BUTTONS',self.GOLD,'center')
        for name,x,y in [('north',397,240),('west',367,268),('east',427,268),('south',397,296)]:
            self.control_art(gd,name,x,y,self.SHORT[name],40014,40015,22)
        self.html(gd,168,354,100,'D-PAD',self.GOLD,'center')
        for name,x,y,art in [('dpad_up',208,382,9900),('dpad_right',234,408,9903),
                              ('dpad_down',208,434,9906),('dpad_left',182,408,9909)]:
            self.control_art(gd,name,x,y,'',art,art+1)
        self.stick(gd,338,405,'right')
        for name,x in [('p1',48),('p2',406)]:
            if name in self.available:
                self.control_art(gd,name,x,520,name.upper(),40018,40029,64)
        self.draw_binding_list(gd)

    def draw_binding_list(self, gd):
        """Every binding at a glance; each row is clickable to reassign."""
        title='BUTTON ASSIGNMENTS'
        self.panel(gd,512,108,272,452,title)
        self.rule(gd,522,130,252)
        rows=[name for name in self.CONTROLS if name in self.available]
        step=23 if len(rows)<=17 else 22
        for index,name in enumerate(rows):
            y=138+index*step
            action=self.binding_text(name)
            self.button(gd,522,y+3,100+self.CONTROLS.index(name),'',2103,2104,
                        self.LABELS[name]+': '+action+'\nClick to assign.')
            self.html(gd,540,y,84,self.SHORT[name],self.GOLD)
            self.html(gd,624,y,154,action,self.MUTED if action=='Unassigned' else self.SILVER)

    def action_names(self):
        template=self.draft.get('active_assignment_profile','Custom')
        result=[]
        category=getattr(self,'action_category','all')
        for name in sorted(self.draft['actions']):
            if category!='all' and self.draft['actions'][name].get('category','general')!=category: continue
            kind=self.draft['actions'][name].get('type')
            if kind in ('step','cast'):continue
            if name.startswith('key_') and not name.startswith('key_'+template+'_'):continue
            if template=='Caster' and kind in ('ability','equip_cycle','attack_last'):continue
            if template=='Caster' and name=='bandage_self':continue
            if template=='Dexxer' and (kind=='cast' or name=='meditate'):continue
            result.append(name)
        return result

    def stage_profile(self, name):
        profiles=self.draft.get('assignment_profiles',{})
        if name not in profiles:
            self.status='Profile not available. Restart the updated host and listener.';return
        if name==self.draft.get('active_assignment_profile','Custom'):return
        # Class changes replace binding edits in this draft, retaining stick settings.
        for key in list(self.changes):
            if key[0] in ('binding','profile'):del self.changes[key]
        self.draft['layers']=copy.deepcopy(profiles[name])
        self.draft['active_assignment_profile']=name
        self.changes[('profile',)]={'assignment_profile':name}
        self.send_config({'paused':True})
        self.status='Draft profile: '+name+'. Unused slots are blank. Apply to switch.'
        self.page='bindings'

    def draw_profiles(self, gd):
        self.label(gd,28,129,'Separate saved controller assignments',53,720)
        self.label(gd,28,161,'Choose a profile, then Apply and Resume. Each profile remembers its own edits.',1152,720)
        descriptions=[('Caster','Spells, meditation, targeting and potions. No default weapon skills or bandages.'),
                      ('Dexxer','Bandages, weapon abilities, attack and potions. No default casting or meditation.'),
                      ('Blank','Every action slot unassigned. Stick movement and cursor roles remain available.'),
                      ('Custom','Your assignments from before profiles were introduced, or your own mixed setup.')]
        for index,(name,description) in enumerate(descriptions):
            y=222+index*76
            self.button(gd,28,y,70+index,name)
            self.label(gd,160,y+2,description,1152,580)
            if name==self.draft.get('active_assignment_profile','Custom'):
                self.label(gd,160,y+28,'Selected in draft',53,570)
        self.button(gd,28,520,33,'Controller')

    def draw_actions(self, gd):
        self.panel(gd,16,108,768,452)
        self.html(gd,28,116,740,'ASSIGN  '+self.LABELS[self.selected].upper()+'   /   '+
                  'ASSIGNMENTS',self.GOLD)
        self.html(gd,28,140,740,'Current draft: '+self.binding_text(self.selected),self.GREEN)
        for index,title in enumerate(('All','General','Pets','Items / Hands','Agents')):
            self.button(gd,28+index*148,162,80+index,title)
        self.rule(gd,28,184,744)
        names=self.action_names()
        start=self.action_page*12
        current=self.layer_data()['bindings'].get(self.selected,{}).get('action','unbound')
        for index,name in enumerate(names[start:start+12]):
            x=28+(index//6)*376; y=194+(index%6)*38
            self.button(gd,x,y,2000+start+index,'',40018,40029,self.action_label(name))
            self.html(gd,x+76,y+2,290,self.action_label(name),self.GREEN if name==current else self.SILVER)
        pages=max(1,(len(names)+11)//12)
        self.button(gd,28,428,30,'',40016,40016,'Previous page')
        self.html(gd,64,430,110,'Page %d of %d'%(self.action_page+1,pages),self.MUTED,'center')
        self.button(gd,178,428,31,'',40017,40017,'Next page')
        self.button(gd,300,426,400,'Spells',tip='Choose any spell from seven spell schools')
        self.button(gd,436,426,32,'Directions',tip='Bind a single walking step')
        self.button(gd,652,426,33,'Back',tip='Return to the controller')
        self.rule(gd,28,466,744)
        self.html(gd,28,476,740,'Or send a keyboard hotkey already assigned in Razor / ClassicUO:',self.GOLD)
        Gumps.AddBackground(gd,28,502,302,31,9200)
        Gumps.AddTextEntry(gd,35,507,285,22,1152,10,'')
        self.button(gd,344,505,34,'Use keys',tip='Example: ctrl+f1. Keys are sent to the focused game window.')
        self.text_entry_open=True

    def spell_rows(self):
        query=self.spell_query.lower().replace("'",'').replace(' ','')
        aliases={'Magic Untrap':'Remove Trap','Night Sight':'Nightsight','Arch Cure':'Archcure',
                 'Arch Protection':'Archprotection','Attunement':'Attune Weapon','Shadowjump':'Shadow Jump'}
        return [spell for spell in SPELL_CATALOG[self.spell_school]
                if (not self.spell_circle or spell['circle']==self.spell_circle)
                and (not query or query in (spell['name']+' '+aliases.get(spell['name'],'')).lower().replace("'",'').replace(' ',''))]

    def stage_spell(self):
        if 'spell_bindings_v1' not in self.listener.features:
            raise ValueError('Update the desktop application before binding new spells')
        name,definition=make_spell_action(self.spell_school,self.spell_selected,self.spell_target,self.spell_recovery)
        self.draft['actions'][name]=definition
        self.layer_data()['bindings'][self.selected]={'action':name,'repeat_ms':0}
        self.changes[('binding',self.layer,self.selected)]={'binding':{
            'control':self.selected,'layer':self.layer,'action':'unbound','cast':{
            'school':self.spell_school,'spell':self.spell_selected,'target':self.spell_target,
            'recovery_ms':self.spell_recovery}}}
        self.status='Draft: '+self.LABELS[self.selected]+' -> '+self.action_label(name)+'. Apply to save.'
        self.page='bindings';self.text_entry_open=False

    def draw_spells(self, gd):
        self.panel(gd,16,108,768,452)
        self.html(gd,28,116,740,'SPELLS / '+self.LABELS[self.selected].upper()+' / '+
                  'ASSIGNMENTS',self.GOLD)
        self.html(gd,28,142,740,'Choose a school, select a spell, then Assign spell and Apply.',self.SILVER)
        for index,school in enumerate(SCHOOL_ORDER):
            x=28+(index%4)*136;y=178+(index//4)*30
            self.button(gd,x,y,410+index,'',40019,40029,'Browse '+school)
            self.html(gd,x,y+3,126,school,self.GOLD if school==self.spell_school else self.SILVER,'center')
        Gumps.AddBackground(gd,28,248,302,30,9200)
        Gumps.AddTextEntry(gd,36,253,284,22,1152,20,self.spell_query)
        self.button(gd,344,250,422,'Search',tip='Filter this school by spell name')
        self.button(gd,480,250,423,'Clear',tip='Clear the search filter')
        if self.spell_school=='Magery':
            self.html(gd,28,288,52,'Circle:',self.MUTED)
            for circle in range(9):
                x=82+circle*43
                self.button(gd,x,286,460+circle,'',40014,40015,'All circles' if circle==0 else 'Circle '+str(circle))
                self.html(gd,x,289,22,'*' if circle==0 else str(circle),self.GOLD if circle==self.spell_circle else self.SILVER,'center')
        else:
            self.html(gd,28,289,480,str(len(SPELL_CATALOG[self.spell_school]))+' spells / abilities',self.MUTED)
        self.rule(gd,28,314,744)
        rows=self.spell_rows();pages=max(1,(len(rows)+11)//12)
        self.spell_page=min(self.spell_page,pages-1)
        for index,spell in enumerate(rows[self.spell_page*12:self.spell_page*12+12]):
            x=28+(index//6)*254;y=326+(index%6)*28
            self.button(gd,x,y+2,1000+self.spell_page*12+index,'',2103,2104,'Select '+spell['name'])
            self.html(gd,x+22,y,226,spell['name'],self.GREEN if spell['name']==self.spell_selected else self.SILVER)
        if not rows: self.html(gd,28,350,490,'No matching spells. Clear the search or circle filter.',self.MUTED)
        self.html(gd,550,326,218,'CAST SETTINGS',self.GOLD)
        self.html(gd,550,352,218,self.spell_selected or 'Select a spell',self.GREEN,None,40)
        spell=get_spell(self.spell_school,self.spell_selected) if self.spell_selected else None
        for index,text in enumerate(('Manual / native','Self','Last target')):
            mode=('none','self','last')[index];y=397+index*25
            self.button(gd,550,y+2,430+index,'',2103,2104,text)
            color=self.GOLD if mode==self.spell_target else self.SILVER
            if index and (not spell or not spell['auto_target']): color=self.MUTED
            self.html(gd,572,y,198,text,color)
        self.html(gd,550,474,100,'Recovery ms',self.MUTED)
        Gumps.AddBackground(gd,650,470,116,30,9200)
        Gumps.AddTextEntry(gd,658,475,100,22,1152,21,str(self.spell_recovery if self.spell_recovery is not None else 0))
        self.button(gd,28,518,420,'',40016,40016,'Previous spells')
        self.html(gd,66,520,128,'Page %d / %d'%(self.spell_page+1,pages),self.MUTED,'center')
        self.button(gd,202,518,421,'',40017,40017,'Next spells')
        self.html(gd,246,520,240,'%d matching spells'%len(rows),self.MUTED)
        self.button(gd,508,516,440,'Assign spell')
        self.button(gd,644,516,450,'Back')
        self.text_entry_open=True

    def draw_settings(self, gd):
        self.panel(gd,16,108,768,452)
        movement=self.draft['input'].get('movement_stick','left')
        mouse=self.draft['input'].get('mouse_stick','right')
        self.html(gd,28,116,740,'STICK ROLES',self.GOLD)
        self.html(gd,28,140,740,'Movement: '+movement+' stick   |   Cursor: '+mouse+' stick',self.SILVER)
        self.button(gd,28,166,42,'Standard',tip='Left stick moves your character; right stick moves the cursor.')
        self.button(gd,164,166,43,'Swap sticks',tip='Right stick moves your character; left stick moves the cursor.')
        self.button(gd,300,166,44,'Cursor off',tip='Disable the cursor stick.')
        self.rule(gd,28,206,744)
        self.html(gd,28,214,740,'SENSITIVITY',self.GOLD)
        desktop=self.draft['desktop']
        entries=[('left_deadzone','Left deadzone','0.05 - 0.6',self.draft['input']),
                 ('right_deadzone','Right deadzone','0.05 - 0.6',self.draft['input']),
                 ('run_threshold','Run threshold','0.4 - 1.0',self.draft['input']),
                 ('cursor_pixels_per_second','Cursor speed (px/s)','100 - 2500',desktop),
                 ('cursor_curve','Cursor precision curve','1.0 linear - 3.0',desktop)]
        for index,(name,title,hint,group) in enumerate(entries):
            y=242+index*36
            self.html(gd,28,y+4,230,title,self.SILVER)
            Gumps.AddBackground(gd,262,y,110,30,9200)
            Gumps.AddTextEntry(gd,270,y+4,92,22,1152,index+1,str(group.get(name,1.0 if name=='cursor_curve' else '')))
            self.html(gd,386,y+4,200,hint,self.MUTED)
        self.button(gd,620,384,55,'Use values',tip='Stage all values. Apply saves the complete draft.')
        self.rule(gd,28,428,744)
        self.html(gd,28,436,740,'MODIFIERS',self.GOLD)
        run=self.draft['input'].get('run_control','')
        scroll=self.draft['input'].get('scroll_control','')
        self.button(gd,28,462,56,'Run modifier',tip='Hold to force running. Click to cycle.')
        self.html(gd,164,465,200,self.LABELS.get(run,'None'),self.GREEN)
        self.button(gd,400,462,57,'Scroll modifier',tip='Hold while moving the cursor stick to scroll. Click to cycle.')
        self.html(gd,536,465,220,self.LABELS.get(scroll,'None'),self.GREEN)
        self.html(gd,28,507,740,'Each controller button has one assignment. No shifted button sets.',self.MUTED)
        self.html(gd,28,536,740,'Mouse: tap to click, tap twice to double-click, hold to drag. ',self.MUTED)
        self.text_entry_open=True

    def draw_directions(self, gd):
        self.panel(gd,16,108,768,452)
        self.html(gd,28,116,740,'Assign a walking direction to '+self.LABELS[self.selected],self.GOLD)
        names=['north','northeast','east','southeast','south','southwest','west','northwest']
        for index in range(8):
            angle=math.pi*index/4.0
            x=int(round(400+150*math.sin(angle)))-25; y=int(round(330-150*math.cos(angle)))-25
            self.button(gd,x,y,300+index,'',4500+index,4500+index,'Hold to walk '+names[index])
        self.html(gd,300,322,200,'Hold to walk',self.GREEN,'center')
        self.button(gd,652,520,33,'Back',tip='Return to the controller')

    def tab(self, gd, x, number, text, active):
        self.button(gd,x,67,number,'',2103,2104,text)
        self.html(gd,x+20,67,106,text,self.GOLD if active else self.SILVER)
        self.tip(gd,'Click the small square to '+text.lower())
        if active: Gumps.AddImageTiled(gd,x+8,90,110,2,5058)

    def draw(self):
        gd=Gumps.CreateGump(True,False,True,False)
        width,height=(300,62) if self.minimized else (self.WIDTH,self.HEIGHT)
        Gumps.AddBackground(gd,0,0,width,height,9200)
        Gumps.AddImageTiled(gd,2,2,width-4,height-4,1759)
        Gumps.AddAlphaRegion(gd,2,2,width-4,height-4)
        self.text_entry_open=False
        connected=bool(self.listener.session)
        if self.minimized:
            self.html(gd,12,8,216,'Controller: '+('Paused' if self.listener.paused else 'Active'),
                      self.GOLD if self.listener.paused else self.GREEN)
            self.button(gd,234,8,4,'',4006,4007,'Maximize / restore Controller Studio')
            self.button(gd,266,8,2,'',4018,4019,'Close listener')
            self.html(gd,12,32,276,self.status,self.RED if self.listener.notice else self.SILVER)
        else:
            self.html(gd,20,12,300,'CONTROLLER STUDIO',self.GOLD)
            self.html(gd,240,12,230,'v'+self.VERSION,self.MUTED)
            self.button(gd,592,10,3,'Resume' if self.listener.paused else 'Pause',
                        tip='Resume controller' if self.listener.paused else 'Pause controller')
            self.button(gd,730,10,1,'',4015,4016,'Minimize')
            self.button(gd,764,10,2,'',4018,4019,'Close listener')
            state='Connected' if connected else 'Waiting for host'
            if connected and self.listener.paused: state='Connected - paused'
            self.html(gd,20,36,170,state,(self.GOLD if self.listener.paused else self.GREEN) if connected else self.RED)
            if self.listener.notice:
                self.html(gd,190,36,400,'Administrator mismatch: check desktop app',self.RED)
            else:
                self.html(gd,190,36,400,'Last input: '+self.LABELS.get(self.last_control,self.last_control)+' ['+('Normal' if self.last_layer=='base' else self.last_layer)+']',self.SILVER)
            on_bindings=self.page in ('bindings','actions','directions','spells') and not self.pick_by_press
            self.tab(gd,20,10,'Controller',on_bindings)
            self.tab(gd,152,12,'Sticks',self.page=='settings')
            self.tab(gd,284,13,'Press to bind',self.pick_by_press)
            self.tab(gd,416,14,'Profiles',self.page=='profiles')
            self.html(gd,680,68,100,self.draft.get('active_assignment_profile','Custom'),self.GOLD,'right')
            self.rule(gd,16,100,768)
            if self.confirm_exit:
                self.panel(gd,16,108,768,452)
                self.html(gd,16,250,768,'Stop the controller listener?',self.RED,'center')
                self.html(gd,16,280,768,'Unsaved changes will be discarded. Movement will stop.',self.SILVER,'center')
                self.button(gd,262,330,90,'Stop')
                self.button(gd,412,330,91,'Keep open')
            elif self.page=='profiles': self.draw_profiles(gd)
            elif self.page=='settings': self.draw_settings(gd)
            elif self.page=='actions': self.draw_actions(gd)
            elif self.page=='spells': self.draw_spells(gd)
            elif self.page=='directions': self.draw_directions(gd)
            else: self.draw_bindings(gd)
            self.rule(gd,16,570,768)
            error=any(word in self.status.lower() for word in ('error','blocked','unassigned',': busy',': rejected')) or (self.listener.notice and self.status==self.listener.notice)
            self.html(gd,20,578,760,self.status,self.RED if error else self.GREEN,None,40)
            edits=len(self.changes)
            self.html(gd,20,626,300,'%d unsaved edit%s'%(edits,'' if edits==1 else 's'),
                      self.GOLD if edits else self.MUTED)
            # Studio families: Cancel 241/243; Apply 238/240.
            self.button(gd,630,622,60,'',241,243,'Cancel all unsaved changes')
            self.button(gd,712,622,61,'',238,240,'Apply and save all pending changes')
        Gumps.CloseGump(self.GUMP_ID)
        Gumps.SendGump(self.GUMP_ID,Player.Serial,self.x,self.y,gd.gumpDefinition,gd.gumpStrings)
        self.dirty=False; self.last_draw=now()

    def handle(self, button, data):
        if self.applying_request is not None and button not in (1,2,4,90,91):
            self.status='Waiting for Apply confirmation...'; self.dirty=True; return
        if self.page=='settings' and button==61:
            self.handle(55,data)
        if button==1: self.minimized=not self.minimized
        elif button==2: self.confirm_exit=True; self.minimized=False
        elif button==4: self.minimized=False
        elif button==3:
            if self.changes and self.listener.paused: self.status='Apply or Cancel your draft before resuming.'
            elif self.listener.paused and self.listener.pause_reason=='application':
                self.status='Application paused. Use Resume all input in Controller Studio.'
            else: self.send_config({'paused':not self.listener.paused})
        elif button==10:
            self.layer='base';self.page='bindings';self.pick_by_press=False
            self.status='Select a controller button to assign it.'
        elif button in (12,40,41):
            self.page='settings'; self.send_config({'paused':True})
        elif button==14:
            self.page='profiles'; self.send_config({'paused':True})
        elif 80<=button<=84:
            self.action_category=('all','general','pets','items','agents')[button-80];self.action_page=0
            self.status='Agents use the active lists in Razor. Configure lists there first.' if button==84 else 'Choose an action, then Apply and Resume.'
        elif 70<=button<=73:
            self.stage_profile(['Caster','Dexxer','Blank','Custom'][button-70])
        elif button==13:
            self.send_config({'paused':True}); self.pick_by_press=True
            self.page='bindings'; self.status='Press the controller button you want to assign.'
        elif button==90:
            self.send_config({'paused':True}); self.listener.flush(); self.running=False
        elif button==91: self.confirm_exit=False
        elif 100<=button<100+len(self.CONTROLS): self.select_control(self.CONTROLS[button-100])
        elif button==30: self.action_page=max(0,self.action_page-1)
        elif button==31:
            count=len(self.action_names())
            self.action_page=min(max(0,(count-1)//12),self.action_page+1)
        elif button==400:
            if 'spell_bindings_v1' not in self.listener.features:
                self.status='Spell picker needs the rebuilt 3.1 app. Update the desktop app and restart its host.'
            else:
                self.page='spells';self.spell_page=0;self.text_entry_open=False
        elif 410<=button<417:
            self.spell_school=SCHOOL_ORDER[button-410];self.spell_page=0;self.spell_circle=0;self.spell_query=''
            self.spell_selected=None;self.spell_target='none';self.spell_recovery=None
        elif button==420: self.spell_page=max(0,self.spell_page-1)
        elif button==421: self.spell_page=min(max(0,(len(self.spell_rows())-1)//12),self.spell_page+1)
        elif button==422:
            self.spell_query=str(Gumps.GetTextByID(data,20)).strip()[:80];self.spell_page=0
        elif button==423: self.spell_query='';self.spell_page=0
        elif 460<=button<=468:
            self.spell_circle=button-460;self.spell_page=0
        elif 1000<=button<1064:
            rows=self.spell_rows();index=button-1000
            if self.page=='spells' and self.spell_page*12<=index<min(len(rows),(self.spell_page+1)*12):
                self.spell_selected=rows[index]['name'];self.spell_target='none'
                self.spell_recovery=rows[index]['recovery_ms']
        elif 430<=button<=432:
            spell=get_spell(self.spell_school,self.spell_selected) if self.spell_selected else None
            if spell and (button==430 or spell['auto_target']): self.spell_target=['none','self','last'][button-430]
            else: self.status='Choose a spell that opens a mobile target cursor for Self / Last.'
        elif button==440:
            if self.spell_selected:
                recovery=str(Gumps.GetTextByID(data,21)).strip()
                self.spell_recovery=int(recovery)
                self.stage_spell()
            else: self.status='Select a spell first.'
        elif button==450: self.page='actions'
        elif button==32: self.page='directions'
        elif button==33: self.page='bindings'
        elif button==34:
            keys=str(Gumps.GetTextByID(data,10)).strip()
            if not keys: raise ValueError('Enter a key or chord first')
            self.stage_binding('unbound',keys)
        elif 2000<=button<10000:
            names=self.action_names()
            index=button-2000
            if index<len(names): self.stage_binding(names[index])
        elif 300<=button<308:
            self.stage_binding('step_'+['north','right','east','down','south','left','west','up'][button-300])
        elif button in (42,43,44):
            movement='left' if button==42 else ('right' if button==43 else self.draft['input'].get('movement_stick','left'))
            mouse='right' if button==42 else ('left' if button==43 else 'off')
            self.stage_setting('movement_stick',movement); self.stage_setting('mouse_stick',mouse)
        elif button==55:
            names=['left_deadzone','right_deadzone','run_threshold','cursor_pixels_per_second','cursor_curve']
            values=[float(Gumps.GetTextByID(data,i+1)) for i in range(5)]
            bounds=[(.05,.6),(.05,.6),(.4,1),(100,2500),(1,3)]
            for value,(low,high) in zip(values,bounds):
                if not low<=value<=high: raise ValueError('Use deadzones .05-.6, run .4-1, speed 100-2500, curve 1-3')
            if values[2]<self.draft['input']['move_threshold']: raise ValueError('Run threshold must exceed walk threshold')
            for name,value in zip(names,values): self.stage_setting(name,value)
        elif button in (56,57):
            name='run_control' if button==56 else 'scroll_control'; choices=['','ls','rs','lb','rb']
            current=self.draft['input'].get(name,'')
            self.stage_setting(name,choices[(choices.index(current)+1)%len(choices)] if current in choices else '')
        elif button==60:
            self.changes.clear(); self.draft=copy.deepcopy(CONFIG)
            self.revision=CONFIG.get('revision',0); self.page='bindings'; self.pick_by_press=False
            self.status='Draft discarded. Saved bindings retained.'
        elif button==61:
            if not self.synced: self.status='Wait for the controller host before applying.'
            elif not self.changes: self.status='No unsaved changes.'
            else:
                self.applying_request=self.send_config({'changes':list(self.changes.values()),
                    'expected_revision':self.revision,'paused':True})
                self.apply_deadline=now()+5; self.status='Applying draft...'
                self.page='bindings'; self.pick_by_press=False
        self.dirty=True

    def tick(self):
        if getattr(self,'hidden',False):return
        if now()<self.next_poll: return
        self.next_poll=now()+.08
        if self.applying_request is not None and now()>self.apply_deadline:
            self.applying_request=None
            self.status='Apply not confirmed. Draft retained; reconnect or Cancel to reload.'; self.dirty=True
        data=Gumps.GetGumpData(self.GUMP_ID)
        if data is not None and data.hasResponse:
            data.hasResponse=False
            for attr in ('x','y'):
                value=getattr(data,attr,None)
                if isinstance(value,(int,float)) and value>=0: setattr(self,attr,int(value))
            try: self.handle(int(data.buttonid),data)
            except Exception as exc: self.status='Error: '+str(exc); self.dirty=True
            if self.running: self.draw()
        elif self.dirty and not self.text_entry_open and now()-self.last_draw>=.7:
            self.draw()


# Weapon capture setup was removed; existing native actions remain compatible.
def start_controller_ui(listener):
    # RE may resolve injected APIs through builtins or its scope fallback.
    # Testing membership in globals() silently hid the entire Gump there.
    ui = ControllerGump(listener)
    listener.ui = ui
    ui.hidden=not SETTINGS.get('show_gump',False)
    try:
        if not ui.hidden: ui.draw()
    except Exception as exc:
        log('Gump startup failed: ' + str(exc), True)
        log(traceback.format_exc(), True)
        raise
    log('Controller listener ready (' + VERSION + '). '+('Assignments are in the desktop application.' if ui.hidden else 'In-game Gump enabled.'))
    return ui


listener = Listener()
ui = start_controller_ui(listener)
log('Listener started. Stop this script to disable controller game actions.')
try:
    while Player.Connected and (ui is None or ui.running):
        listener.tick()
        if ui:
            ui.tick()
        Misc.Pause(SETTINGS['loop_pause_ms'])
finally:
    listener.close()
    if ui:
        Gumps.CloseGump(ui.GUMP_ID)
