"""Validate physical sources, independently of game bindings."""
def source_identity(source):
    if 'button' in source:return ('button',source['button'])
    if 'hat' in source:return ('hat',source['hat'],source['component'],source['sign'])
    return ('axis',source['axis'],1 if source['full']>source['rest'] else -1)

def mapping_issues(preset):
    issues={};groups={};stick_axes=set(preset['left_stick']+preset['right_stick'])
    for name,source in preset['controls'].items():
        groups.setdefault(source_identity(source),[]).append(name)
        if 'axis' in source:
            if name not in ('lt','rt'):
                issues[name]='A button was learned as an analog axis. Recheck this control.'
            elif source['axis'] in stick_axes:
                issues[name]='This trigger shares a cursor/movement axis. Recheck bumpers and triggers.'
    for names in groups.values():
        if len(names)>1:
            for name in names:issues[name]='Physical input is shared by '+', '.join(names)+'. Recheck these controls.'
    return issues
