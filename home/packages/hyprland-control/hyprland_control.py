"""Native Lua IPC for this repository's audited desktop operations.

Not a hyprctl replacement or a Hyprlang interpreter. Unknown operations and
legacy exec-prefix strings are rejected; queries remain upstream hyprctl.
"""
import argparse
import json
import math
import os
from pathlib import Path
import re
import subprocess


def literal(value):
    if value is None:
        return 'nil'
    if type(value) is bool:
        return 'true' if value else 'false'
    if isinstance(value, str):
        return '"' + ''.join('\\' + c if c in '\\"' else ('\\%03d' % ord(c) if ord(c) < 32 or ord(c) == 127 else c) for c in value) + '"'
    if type(value) in (int, float) and math.isfinite(value):
        return repr(value)
    if isinstance(value, dict):
        return '{' + ','.join('[' + literal(k) + ']=' + literal(v) for k, v in value.items()) + '}'
    if isinstance(value, (list, tuple)):
        return '{' + ','.join(map(literal, value)) + '}'
    raise ValueError('Unsupported Lua value')


def call(name, *args):
    if not re.fullmatch(r'[a-z_]+(?:\.[a-z_]+)*', name):
        raise ValueError('Unsupported native API name')
    return 'hl.' + name + '(' + ','.join(map(literal, args)) + ')'


def dispatch_args(operation, argument=''):
    """Adapt ONLY the existing internal operation vocabulary, not shell syntax."""
    arg = str(argument)
    simple = {'killactive': 'window.close', 'togglegroup': 'group.toggle',
              'cyclenext': 'window.cycle_next', 'exit': 'exit'}
    if operation in simple and not arg:
        expr = call('dsp.' + simple[operation])
    elif operation in ('workspace', 'focuswindow', 'focusmonitor'):
        expr = call('dsp.focus', {dict(workspace='workspace', focuswindow='window', focusmonitor='monitor')[operation]: arg})
    elif operation in ('movetoworkspace', 'movetoworkspacesilent'):
        target, separator, window = arg.rpartition(',')
        spec = {'workspace': target if separator else arg, 'follow': not operation.endswith('silent')}
        if separator:
            spec['window'] = window
        expr = call('dsp.window.move', spec)
    elif operation == 'moveworkspacetomonitor':
        workspace, monitor = arg.rsplit(' ', 1)
        expr = call('dsp.workspace.move', {'workspace': workspace, 'monitor': monitor})
    elif operation in ('setfloating', 'settiled', 'togglefloating'):
        expr = call('dsp.window.float', {'action': {'setfloating':'on','settiled':'off','togglefloating':'toggle'}[operation], **({'window':arg} if arg else {})})
    elif operation == 'closewindow':
        expr = call('dsp.window.close', {'window': arg})
    elif operation == 'layoutmsg':
        expr = call('dsp.layout', arg)
    elif operation == 'lockactivegroup':
        expr = call('dsp.group.lock_active', {'action': {'enable':'on','disable':'off','toggle':'toggle'}[arg]})
    elif operation == 'changegroupactive' and arg in ('f', 'b'):
        expr = call('dsp.group.next' if arg == 'f' else 'dsp.group.prev')
    elif operation == 'moveintogroup':
        expr = call('dsp.window.move', {'into_group': {'l':'left','r':'right','u':'up','d':'down'}[arg]})
    elif operation == 'tagwindow':
        tag, window = arg.split(' ', 1)
        expr = call('dsp.window.tag', {'tag':tag, 'window':window})
    elif operation == 'setprop':
        window, prop, value = arg.split(' ', 2)
        expr = call('dsp.window.set_prop', {'window':window, 'prop':prop, 'value':value})
    elif operation in ('resizewindowpixel', 'movewindowpixel'):
        size, window = arg.rsplit(',', 1)
        exact = size.startswith('exact ')
        x, y = size.removeprefix('exact ').split(' ', 1)
        if not re.fullmatch(r'-?\d+', x) or not re.fullmatch(r'-?\d+', y):
            raise ValueError('Expected integer pixel coordinates')
        expr = call('dsp.window.resize' if operation.startswith('resize') else 'dsp.window.move',
                    {'window':window, 'x':int(x), 'y':int(y), 'relative':not exact})
    elif operation == 'fullscreenstate':
        internal, client = map(int, arg.split())
        # Legacy toggles the PAIR only when both requested channels match.
        # Native action=toggle instead toggles each channel independently.
        # Resolve keep-current and choose set/unset in one compositor callback.
        expr = ('function() local w=hl.get_active_window();if not w then return {ok=true} end;'
                + 'local i=' + ('w.fullscreen' if internal == -1 else str(max(0,min(2,internal)))) + ';'
                + 'local c=' + ('w.fullscreen_client' if client == -1 else str(max(0,min(2,client)))) + ';'
                + 'return hl.dispatch(hl.dsp.window.fullscreen_state({window=w,internal=i,client=c,'
                  'action=(w.fullscreen==i and w.fullscreen_client==c) and "unset" or "set"})) end')
    elif operation == 'fullscreen':
        expr = call('dsp.window.fullscreen', {'mode':'maximized' if arg == '1' else 'fullscreen'})
    elif operation == 'dpms':
        action, _, monitor = arg.partition(' ')
        expr = call('dsp.dpms', {'action':action, **({'monitor':monitor} if monitor else {})})
    elif operation == 'exec' and not arg.lstrip().startswith('['):
        expr = call('dsp.exec_cmd', arg)
    else:
        raise ValueError('Operation needs an explicit native migration: ' + operation)
    return ['dispatch', expr]


def exec_args(command, rules=None):
    return ['dispatch', call('dsp.exec_cmd', command, rules or {})]


def desktop_exec_args(executable, command, rules=None):
    if uses_lua(executable):
        return exec_args(command, rules)
    prefix = '; '.join(key + ' ' + ('on' if value is True else 'off' if value is False else str(value)) for key, value in (rules or {}).items())
    return ['dispatch', 'exec', ('[' + prefix + '] ' if prefix else '') + command]


def setting_args(key, value):
    if not uses_lua():
        return ['keyword', key, str(value)]
    if key == 'input:follow_mouse' and type(value) is int and value in range(4):
        spec = {'input': {'follow_mouse':value}}
    elif key == 'gestures:workspace_swipe_touch' and type(value) is int and value in (0, 1):
        spec = {'gestures': {'workspace_swipe_touch':bool(value)}}
    else:
        raise ValueError('Unaudited runtime setting')
    return ['eval', call('config', spec)]


def rule_args(name, spec=None):
    """Disable, clear, then install one reusable named rule in one callback.

    Callers serialize rule ownership as before. Each caller always supplies the
    same match-property keys; changing match-key sets is intentionally unsupported.
    None only disables a previously configured rule, retaining bounded storage.
    """
    base = {'name':name, 'enabled':False}
    code = 'local r=' + call('window_rule', base) + ';'
    if spec is not None:
        code += 'assert(type(r.clear_effects)=="function","Missing bounded rule API");r:clear_effects();'
        code += call('window_rule', {**spec, 'name':name, 'enabled':True})
    return ['eval', code]


def uses_lua(executable='hyprctl'):
    # Read-only negotiation against the actual targeted compositor, not a file
    # extension guess (activation and a session restart are separate events).
    mode = os.environ.get('HYPRLAND_CONTROL_TEST_BACKEND')
    if mode in ('lua', 'legacy'):
        return mode == 'lua'
    result = subprocess.run([executable, 'eval', 'do end'], capture_output=True, text=True, timeout=3)
    if result.returncode == 0 and result.stdout.strip() == 'ok':
        return True
    if result.stdout.strip() == 'eval is only supported with the lua config manager':
        return False
    raise RuntimeError('Could not identify the targeted compositor backend')


def desktop_args(executable, arguments):
    """Explicit transport boundary for owned applications' internal operations."""
    if arguments and arguments[0] == 'dispatch' and len(arguments) >= 2:
        if arguments[1].startswith('hl.dsp.'):
            return list(arguments)
        if arguments[1] == 'exec' and len(arguments) == 3 and isinstance(arguments[2], dict):
            return desktop_exec_args(executable, **arguments[2])
        if not uses_lua(executable):
            return list(arguments)
        name, *rest = arguments[1:]
        if rest[:1] == ['--']:
            rest = rest[1:]
        return dispatch_args(name, ' '.join(rest))
    return list(arguments)


def desktop_argv(argv):
    return [argv[0], *desktop_args(argv[0], argv[1:])]


def config_path():
    root = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'hypr'
    return root / ('hyprland.lua' if uses_lua() else 'hyprland.conf')


def guarded_layer(namespace):
    """Read the actual compositor rule contract, never parse Lua as text."""
    if not uses_lua():
        path = config_path()
        pattern = r'(?m)^\s*layerrule\s*=\s*match:namespace\s+\^' + re.escape(namespace) + r'\$\s*,\s*no_anim\s+on\s*$'
        return path.is_file() and re.search(pattern, path.read_text()) is not None
    result = subprocess.run(['hyprctl','repl','return desktop_policy and desktop_policy.no_animation[' + literal(namespace) + '] == true'],
                            capture_output=True, text=True, timeout=3)
    return result.returncode == 0 and result.stdout.strip() == 'true'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='operation', required=True)
    for name in ('workspace','focusmonitor','focuswindow'):
        sub.add_parser(name).add_argument('value')
    p = sub.add_parser('moveworkspacetomonitor'); p.add_argument('workspace'); p.add_argument('monitor')
    p = sub.add_parser('monitor'); p.add_argument('spec', nargs='?', help='Native monitor specification as JSON')
    p.add_argument('--output'); p.add_argument('--mode'); p.add_argument('--position'); p.add_argument('--scale', type=float)
    p.add_argument('--transform', type=int); p.add_argument('--mirror')
    p.add_argument('--disabled', action='store_true'); p.add_argument('--reset', action='store_true')
    p = sub.add_parser('rule'); p.add_argument('name'); p.add_argument('spec', nargs='?', help='Native rule specification as JSON; absent disables')
    p = sub.add_parser('dispatch'); p.add_argument('name'); p.add_argument('value', nargs='?', default='')
    args = parser.parse_args()
    requests = None
    if args.operation == 'monitor':
        spec = json.loads(args.spec) if args.spec else {key:value for key,value in vars(args).items() if key not in ('operation','spec') and value is not None and value is not False}
        if uses_lua():
            request = ['eval', call('monitor', spec)]
        elif spec.get('disabled'):
            request = ['keyword', 'monitor', spec['output'] + ',disable']
        else:
            value = ','.join(str(spec[key]) for key in ('output','mode','position','scale'))
            for key in ('transform','mirror'):
                if key in spec:
                    value += ',' + key + ',' + str(spec[key])
            request = ['keyword', 'monitor', value]
    elif args.operation == 'rule':
        spec = json.loads(args.spec) if args.spec else None
        if uses_lua():
            request = rule_args(args.name, spec)
        else:
            prefix = 'windowrule[' + args.name + ']:'
            requests = [['keyword',prefix+'enable','0']]
            if spec is not None:
                for key,value in spec.get('match',{}).items():
                    if key not in ('class','title') or not isinstance(value,str):
                        raise ValueError('Unaudited legacy match property')
                    requests.append(['keyword',prefix+'match:'+key,value])
                for key,value in spec.items():
                    if key == 'match': continue
                    if key not in ('float','center','size','workspace','no_initial_focus','suppress_event'):
                        raise ValueError('Unaudited legacy rule effect')
                    requests.append(['keyword',prefix+key,'on' if value is True else 'off' if value is False else str(value)])
                requests.append(['keyword',prefix+'enable','1'])
    elif args.operation == 'moveworkspacetomonitor':
        request = desktop_args('hyprctl', ['dispatch', args.operation, args.workspace + ' ' + args.monitor])
    elif args.operation == 'dispatch':
        request = desktop_args('hyprctl', ['dispatch', args.name, args.value])
    else:
        request = desktop_args('hyprctl', ['dispatch', args.operation, args.value])
    for item in requests if requests is not None else [request]:
        result = subprocess.run(['hyprctl', *item], capture_output=True, text=True, timeout=5)
        if result.returncode or result.stdout.strip() != 'ok':
            raise SystemExit(result.stderr.strip() or result.stdout.strip() or 'Desktop request failed')
    print('ok')


if __name__ == '__main__':
    main()
