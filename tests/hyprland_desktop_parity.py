"""Independent full merged-config parity audit.

Inputs are Nix-evaluated baseline JSON and the generated Lua captured with
hyprland_desktop_capture.lua. Store hashes alone are normalized, not commands,
versions, binding order, flag values, regexes or settings.
"""
import argparse
import collections
import json
from pathlib import Path
import re


def normalize(value):
    if isinstance(value, str):
        return re.sub(r'/nix/store/[a-z0-9]{32}-', '/nix/store/HASH-', value)
    if isinstance(value, dict):
        return {key:normalize(item) for key,item in value.items()}
    if isinstance(value, list):
        return [normalize(item) for item in value]
    return value


def flatten(value, prefix=''):
    result = {}
    for key,item in value.items():
        name = prefix + key
        if isinstance(item, dict):
            result.update(flatten(item, name + '.'))
        else:
            result[name] = item
    return result


def audit(baseline, capture):
    s = baseline['settings']
    calls = collections.defaultdict(list)
    for entry in capture:
        calls[entry['name']].append(entry['args'])
    expected_calls = {'bind','config','monitor','device','env','exec_cmd','window_rule','layer_rule','curve','animation','gesture'}
    assert set(calls) == expected_calls, ('unexpected/missing native call', set(calls)^expected_calls)
    def same(label, expected, actual):
        if normalize(expected) != normalize(actual):
            raise AssertionError(label + '\nEXPECTED ' + json.dumps(normalize(expected),sort_keys=True,ensure_ascii=False) + '\nACTUAL   ' + json.dumps(normalize(actual),sort_keys=True,ensure_ascii=False))
    def expand(text):
        return re.sub(r'\$[A-Za-z]\w*', lambda m:s.get(m[0],m[0]), text)
    seen = set()
    expected_binds = []
    for group in ('bind','bindel','bindl','bindm','bindr'):
        seen.add(group)
        for entry in s[group]:
            parts = expand(entry).split(',',3)
            modifiers,key,operation = (p.strip() for p in parts[:3])
            argument = parts[3].strip() if len(parts) == 4 else ''
            keys = ' + '.join([*modifiers.split(), key])
            simple = {'killactive':'window.close','togglegroup':'group.toggle','fullscreen':'window.fullscreen','togglefloating':'window.float','movewindow':'window.drag','resizewindow':'window.resize'}
            args = []
            if operation == 'exec': op,args = 'exec_cmd',[argument]
            elif operation in simple:
                op = simple[operation]
                if operation == 'togglefloating': args = [{'action':'toggle'}]
            elif operation == 'workspace': op,args = 'focus',[{'workspace':int(argument) if argument.isdecimal() else argument}]
            elif operation == 'movetoworkspace': op,args = 'window.move',[{'workspace':int(argument) if argument.isdecimal() else argument}]
            elif operation == 'movefocus': op,args = 'focus',[{'direction':{'l':'left','r':'right','u':'up','d':'down'}[argument]}]
            elif operation == 'changegroupactive': op = 'group.next' if argument == 'f' else 'group.prev'
            elif operation == 'lockactivegroup': op,args = 'group.lock_active',[{'action':argument}]
            elif operation == 'layoutmsg': op,args = 'layout',[argument]
            elif operation == 'togglespecialworkspace': op,args = 'workspace.toggle_special',[argument]
            else: raise AssertionError('Unaudited binding operation: '+operation)
            flags = {'bindr':{'release':True},'bindm':{'mouse':True},'bindel':{'repeating':True,'locked':True},'bindl':{'locked':True}}.get(group,{})
            expected_binds.append([keys, {'operation':'dsp.'+op,'args':args}, flags])
    actual_binds = []
    for entry in calls['bind']:
        keys, action, *options = entry
        options = options[0] if options else {}
        if action['args'] == {}: action['args'] = []
        if action['operation'] in ('dsp.window.drag','dsp.window.resize') and not action['args']:
            options = {**options,'mouse':True}
        actual_binds.append([keys,action,options])
    same('bindings including flags and order',expected_binds,actual_binds)
    seen.update(k for k in s if k.startswith('$'))
    seen.update(('monitor','env','exec-once','windowrule','layerrule','plugin'))
    expected_config = flatten({k:v for k,v in s.items() if k not in seen})
    actual_config = flatten(calls['config'][0][0])
    # Lua's gradient is structured; compare exact stop colors and angle.
    gradient = expected_config.pop('general.col.active_border').split()
    actual_colors = actual_config.pop('general.col.active_border.colors')
    actual_angle = actual_config.pop('general.col.active_border.angle')
    same('active gradient', [gradient[:-1],int(gradient[-1][:-3])], [actual_colors,actual_angle])
    same('all explicit config values', expected_config, actual_config)
    # This plugin is disabled in both implementations. Its old namespace was
    # inert, not an active feature. Unknown plugin changes must stop the audit.
    same('documented inert plugin tuning', {'touch_gestures':{'sensitivity':4.0,'long_press_delay':400,'resize_on_border_long_press':True,'edge_margin':10}},s['plugin'])
    same('environment without DBus imports', [[*entry.split(',',1),False] for entry in s['env']],calls['env'])
    same('startup commands and ordering', list(map(expand,s['exec-once'])),[entry[0] for entry in calls['exec_cmd']])
    same('monitor rules', [{'output':p[0].strip(),'mode':p[1].strip(),'position':p[2].strip(),'scale':float(p[3])} for p in [entry.split(',') for entry in s['monitor']]],[entry[0] for entry in calls['monitor']])
    def rule(text):
        spec = {'match':{}}
        for item in text.split(','):
            key,value = item.strip().split(' ',1)
            if key.startswith('match:'):
                spec['match'][key[6:]] = {'true':True,'false':False}.get(value,value)
            else:
                spec[key] = {'on':True,'off':False}.get(value,value)
        return spec
    same('window rules and priority',list(map(rule,s['windowrule'])),[entry[0] for entry in calls['window_rule']])
    same('layer rules',list(map(rule,s['layerrule'])),[entry[0] for entry in calls['layer_rule']])
    extra = baseline['extraConfig']
    device_block = re.search(r'device\s*\{([^}]+)\}',extra)[1]
    device = {}
    for key,value in re.findall(r'([\w_]+)\s*=\s*([^\n]+)',device_block):
        value = value.strip()
        device[key] = float(value) if key == 'sensitivity' else int(value) if key == 'scroll_button' else value
    same('TrackPoint device overrides',[device],[entry[0] for entry in calls['device']])
    curves = []
    for text in re.findall(r'^\s*bezier\s*=\s*(.+)$',extra,re.M):
        name,*values = map(str.strip,text.split(',')); values = list(map(float,values))
        curves.append([name,{'type':'bezier','points':[values[:2],values[2:]]}])
    same('all curves',curves,calls['curve'])
    animations = []
    for text in re.findall(r'^\s*animation\s*=\s*(.+)$',extra,re.M):
        leaf,enabled,speed,bezier,*style = map(str.strip,text.split(','))
        animations.append({'leaf':leaf,'enabled':bool(int(enabled)),'speed':float(speed),'bezier':bezier,**({'style':style[0]} if style else {})})
    same('all animation values',animations,[entry[0] for entry in calls['animation']])
    gestures = re.findall(r'^\s*gesture\s*=\s*(.+)$',extra,re.M)
    same('native trackpad gesture', ['3, horizontal, workspace'],gestures)
    same('native trackpad gesture spec',[{'fingers':3,'direction':'horizontal','action':'workspace'}],[entry[0] for entry in calls['gesture']])
    # Account for every executable (non-comment) extraConfig line.
    for line in extra.splitlines():
        text = line.strip()
        assert not text or text.startswith(('#','device','name =','sensitivity =','accel_profile =','scroll_method =','scroll_button =','}','bezier =','animation =','gesture =')), ('unaccounted extraConfig',text)
    return {'bindings':len(expected_binds),'window_rules':len(s['windowrule']),'startup_commands':len(s['exec-once']),'config_values':len(expected_config)+1,'curves':len(curves),'animations':len(animations)}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline');parser.add_argument('capture')
    parser.add_argument('--transition')
    args=parser.parse_args()
    baseline=json.loads(Path(args.baseline).read_text())
    if args.transition:
        executable_lines=lambda text: [normalize(line.strip()) for line in text.splitlines() if line.strip() and not line.lstrip().startswith('#')]
        assert executable_lines(baseline['config'])==executable_lines(Path(args.transition).read_text()), 'Frozen transition config lost baseline content'
    print(json.dumps(audit(baseline,json.loads(Path(args.capture).read_text())),indent=2))
