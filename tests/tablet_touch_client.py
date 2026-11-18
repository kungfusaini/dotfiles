"""Fixture wire format: contacts use wl_touch; idle moves only park the cursor."""
import json
import os
from pathlib import Path
import subprocess
import sys
import signal
import time

root = Path(os.environ['TABLET_WINDOW_TEST_ROOT'])
runtime = Path(os.environ['XDG_RUNTIME_DIR'])
assert str(root).startswith('/tmp/twa.proof.') and runtime == root / 'r'
assert os.environ['HYPRLAND_INSTANCE_SIGNATURE']
(root / 'allow-test-touch').touch(mode=0o600)
ctl = os.environ['TABLET_TEST_HYPRCTL']
def command(*args):
    if args[:2] == ('dispatch', 'tablet-test-touch') and os.environ.get('TABLET_TEST_LUA') == '1':
        args = ('eval', 'assert(hl.plugin.tablet_test.touch(' + json.dumps(args[2]) + '))')
    result = subprocess.check_output([ctl, *args], text=True, timeout=5).strip()
    if result not in ('ok', ''):
        raise RuntimeError(result)
command('plugin', 'load', os.environ['TABLET_TEST_TOUCH_PLUGIN'])
pointer = subprocess.Popen([os.environ['TABLET_TEST_POINTER_ORIGINAL']], stdin=subprocess.PIPE,
                           stdout=subprocess.PIPE, text=True)
assert pointer.stdout.readline().strip() == 'READY'
signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
recorder_log = (root / 'recording.log').open('w')
recorder = subprocess.Popen([os.environ['TABLET_TEST_RECORDER'], '-o', 'eDP-1',
                             '-f', str(root / 'touch-interactions.mp4'), '-D',
                             '-F', 'scale=960:960:force_original_aspect_ratio=decrease:eval=frame,pad=960:960:(ow-iw)/2:(oh-ih)/2',
                             '-c', 'libx264', '-p', 'preset=ultrafast', '-x', 'yuv420p'],
                            stdout=recorder_log, stderr=subprocess.STDOUT, start_new_session=True)
(root / 'recording-start.json').write_text(json.dumps({'time': time.monotonic()}))
time.sleep(.3)
assert recorder.poll() is None, 'Private recording did not start'
print('READY', flush=True)
x = y = 0.0
pressed = False
trace = (root / 'touch-events.jsonl').open('a')
try:
    for line in sys.stdin:
        fields = line.split()
        if not fields:
            continue
        action = fields[0]
        if action == 'move':
            x, y = float(fields[1]) / float(fields[3]), float(fields[2]) / float(fields[4])
            if pressed:
                command('dispatch', 'tablet-test-touch', f'move {x} {y}')
            else:
                pointer.stdin.write('move ' + ' '.join(str(round(float(v))) for v in fields[1:]) + '\n'); pointer.stdin.flush()
                assert pointer.stdout.readline().strip() == 'OK'
        elif action in ('mouse-down', 'mouse-up'):
            # Existing browser-click assertions remain pointer assertions;
            # every gesture contact uses the independent wl_touch path.
            pointer.stdin.write(action.removeprefix('mouse-') + '\n'); pointer.stdin.flush()
            assert pointer.stdout.readline().strip() == 'OK'
        elif action == 'down':
            assert not pressed
            command('dispatch', 'tablet-test-touch', f'down {x} {y}')
            pressed = True
        elif action == 'up':
            assert pressed
            command('dispatch', 'tablet-test-touch', 'up')
            pressed = False
        else:
            raise ValueError(action)
        trace.write(json.dumps({'time': time.monotonic(), 'action': action, 'x': x, 'y': y}) + '\n')
        trace.flush()
        print('OK', flush=True)
finally:
    try:
        if pressed:
            command('dispatch', 'tablet-test-touch', 'up')
    finally:
        trace.close()
        pointer.terminate()
        pointer.wait(timeout=5)
        recorder.send_signal(signal.SIGINT)
        recorder.wait(timeout=15)
        recorder_log.close()
