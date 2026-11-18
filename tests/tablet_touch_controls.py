"""Stateful private audio/backlight fixtures; never invoke a host control tool."""
import fcntl
import json
import os
from pathlib import Path
import sys

root = Path(os.environ['TABLET_WINDOW_TEST_ROOT'])
assert str(root).startswith('/tmp/twa.proof.')
assert Path(os.environ['XDG_RUNTIME_DIR']) == root / 'r'
name, *args = sys.argv[1:]
assert name in ('wpctl', 'brightnessctl')
with (root / (name + '.lock')).open('a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    path = root / (name + '.json')
    state = json.loads(path.read_text()) if path.exists() else {'volume': .4, 'muted': False, 'brightness': 60}
    with (root / (name + '.calls')).open('a') as log:
        log.write(' '.join(args) + '\n')
    if name == 'wpctl':
        if args == ['get-volume', '@DEFAULT_AUDIO_SINK@']:
            print('Volume: %.2f%s' % (state['volume'], ' [MUTED]' if state['muted'] else ''))
        elif args[:2] == ['set-volume', '@DEFAULT_AUDIO_SINK@']:
            state['volume'] = float(args[2])
            assert 0 <= state['volume'] <= 1
        elif args == ['set-mute', '@DEFAULT_AUDIO_SINK@', 'toggle']:
            state['muted'] = not state['muted']
        else:
            raise ValueError(args)
    else:
        assert args[0] == '--device=intel_backlight'
        if args[1:] == ['max']: print(100)
        elif args[1:] == ['get']: print(state['brightness'])
        elif args[1] == 'set':
            state['brightness'] = int(args[2].removesuffix('%'))
            assert 0 <= state['brightness'] <= 100
        else: raise ValueError(args)
    path.write_text(json.dumps(state))
