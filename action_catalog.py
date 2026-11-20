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
