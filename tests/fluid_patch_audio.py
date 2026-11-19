"""Run with private-x11-run; validates actual ACE Fluid Synth patch audio.

Arguments: jalv/jackd bin directory, FluidR3 SF2 path, Ardour LV2 directory,
JACK client library, optional Ardour GUI binary (tests the actual session).
No physical devices. The runner retains audio/results under /tmp/work.
"""
import array
import ctypes as C
import importlib.util
import json
import math
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import time

assert os.environ.get('HOME') == '/tmp/work/home', 'Use private-x11-run'
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('setup', ROOT / 'home/scripts/laptop-instrument-setup.py')
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)
TOOLS, FONT, LV2_DIR, JACK_LIB = map(Path, sys.argv[1:5])
ARDOUR = Path(sys.argv[5]) if len(sys.argv) > 5 else None
WORK = Path('/tmp/work')
state = WORK / 'state1'
state.mkdir()
(state / 'state.ttl').write_bytes(setup.fluid_state(FONT))
log = (WORK / 'jack.log').open('w')
server = subprocess.Popen([str(TOOLS/'jackd'), '--no-realtime', '-d', 'dummy', '-r', '48000', '-p', '256'], stdout=log, stderr=subprocess.STDOUT)
host = None
client = None
j = C.CDLL(str(JACK_LIB))

def declare(name, result, args):
    fn = getattr(j, name)
    fn.restype, fn.argtypes = result, args
    return fn

ptr, uint, charp = C.c_void_p, C.c_uint, C.c_char_p
open_client = declare('jack_client_open', ptr, [charp, C.c_int, ptr])
close_client = declare('jack_client_close', C.c_int, [ptr])
register = declare('jack_port_register', ptr, [ptr, charp, charp, C.c_ulong, C.c_ulong])
get_buffer = declare('jack_port_get_buffer', ptr, [ptr, uint])
port_name = declare('jack_port_name', charp, [ptr])
connect = declare('jack_connect', C.c_int, [ptr, charp, charp])
activate = declare('jack_activate', C.c_int, [ptr])
deactivate = declare('jack_deactivate', C.c_int, [ptr])
clear = declare('jack_midi_clear_buffer', None, [ptr])
write = declare('jack_midi_event_write', C.c_int, [ptr, uint, ptr, C.c_size_t])
get_ports = declare('jack_get_ports', C.POINTER(charp), [ptr, charp, charp, C.c_ulong])
free = declare('jack_free', None, [ptr])
CALLBACK = C.CFUNCTYPE(C.c_int, uint, ptr)
set_callback = declare('jack_set_process_callback', C.c_int, [ptr, CALLBACK, ptr])
commands = queue.SimpleQueue()
chunks = []
recording = False

try:
    time.sleep(1)
    assert server.poll() is None, (WORK/'jack.log').read_text()
    env = os.environ.copy()
    env['LV2_PATH'] = str(LV2_DIR)
    hostlog = (WORK/'host.log').open('w')
    if ARDOUR:
        setup.create_session(WORK, ROOT / 'home/config/ardour/musical-sketch.template', FONT)
        config = Path(os.environ['XDG_CONFIG_HOME']) / 'ardour9'
        config.mkdir(parents=True)
        (config / '.a9').touch()
        (config / 'ui_config').write_text('<Ardour><UI><Option name="check-announcements" value="0"/></UI></Ardour>')
        (config / 'instant.xml').write_text('<instant><no-memory-warning/></instant>')
        (config / 'config').write_text('<Ardour><Config/></Ardour>')
        setup.configure_ardour(config.parent)
        cmd = [str(ARDOUR), '-a', '-n', '-P', '-c', 'fluid-test', str(WORK/'Laptop Instrument')]
        midi_port = b'fluid-test:Sketch Piano/midi_in 1'
        audio_port = b'fluid-test:Sketch Piano/audio_out 1'
    else:
        cmd = [str(TOOLS/'jalv'), '-i', '-n', 'fluid-test', '-l', str(state), '-c', 'rev_enable=0', '-c', 'cho_enable=0', 'urn:ardour:a-fluidsynth']
        midi_port, audio_port = b'fluid-test:control', b'fluid-test:outL'
    host = subprocess.Popen(cmd, env=env, stdout=hostlog, stderr=subprocess.STDOUT)
    for _ in range(30):
        client = open_client(b'patch-recorder', 1, None)
        if client:
            break
        time.sleep(.1)
    assert client, 'No private JACK client'
    midi = register(client, b'notes', b'8 bit raw midi', 2, 0)
    audio = register(client, b'audio', b'32 bit float mono audio', 1, 0)

    @CALLBACK
    def process(nframes, unused):
        global recording
        mbuf = get_buffer(midi, nframes)
        clear(mbuf)
        while not commands.empty():
            message = commands.get_nowait()
            if message == 'begin':
                chunks.clear()
                recording = True
            elif message == 'end':
                recording = False
            else:
                raw = C.create_string_buffer(message)
                write(mbuf, 0, raw, len(message))
        if recording:
            chunks.append(C.string_at(get_buffer(audio, nframes), nframes * 4))
        return 0

    assert set_callback(client, process, None) == 0
    assert activate(client) == 0
    names = []
    for _ in range(300):
        ports = get_ports(client, b'fluid-test:.*', None, 0)
        names = []
        if ports:
            i = 0
            while ports[i]:
                names.append(ports[i].decode())
                i += 1
            free(ports)
        if midi_port.decode() in names and audio_port.decode() in names:
            break
        if host.poll() is not None:
            raise RuntimeError((WORK/'host.log').read_text())
        time.sleep(.1)
    print('Private plugin ports:', names, flush=True)
    if midi_port.decode() not in names:
        if shutil.which('xdotool'):
            subprocess.run(['xdotool', 'search', '--onlyvisible', '--name', '.', 'getwindowname', '%@'])
        if shutil.which('xwd') and shutil.which('magick'):
            subprocess.run(['xwd', '-root', '-silent', '-out', str(WORK/'failure.xwd')])
            subprocess.run(['magick', str(WORK/'failure.xwd'), str(WORK/'failure.png')])
        raise RuntimeError('Plugin MIDI port missing; inspect retained host.log and GUI artifacts')
    assert connect(client, port_name(midi), midi_port) == 0
    assert connect(client, audio_port, port_name(audio)) == 0
    time.sleep(1)
    summary = []
    signals = []
    cases = [(0, 'piano', 0), (24, 'nylon-guitar', 0), (80, 'square-lead', 0)]
    if ARDOUR:
        # Keep program changes on channel1, but send the next note on channel2.
        # Forced capture must map it to the same square patch, not channel2's
        # default piano. This checks real live-input remapping, not just XML.
        cases.append((80, 'channel-two-square', 1))
    for program, name, channel in cases:
        commands.put(bytes([0xB0, 120, 0]))
        time.sleep(.1)
        commands.put('begin')
        commands.put(bytes([0xC0, program]))
        commands.put(bytes([0x90 | channel, 60, 90]))
        time.sleep(.8)
        commands.put('end')
        time.sleep(.05)
        commands.put(bytes([0x80 | channel, 60, 0]))
        data = b''.join(chunks)
        (WORK/(name+'.f32')).write_bytes(data)
        samples = array.array('f')
        samples.frombytes(data)
        peak = max(map(abs, samples), default=0)
        rms = math.sqrt(sum(x*x for x in samples)/max(1, len(samples)))
        summary.append({'program':program, 'name':name, 'samples':len(samples), 'peak':peak, 'rms':rms})
        assert peak > .005 and rms > .001, 'Silent or unloaded soundfont: '+name
        signals.append(samples)
    # Same MIDI pitch/velocity, contrasting GM programs. Compare steady audio
    # without relying on event generation, labels, or successful host exit.
    differences = []
    for a, b in [(signals[0], signals[1]), (signals[0], signals[2]), (signals[1], signals[2])]:
        n = min(len(a), len(b))
        diff = math.sqrt(sum((a[i]-b[i])**2 for i in range(n))/n)
        scale = max(math.sqrt(sum(a[i]**2 for i in range(n))/n), math.sqrt(sum(b[i]**2 for i in range(n))/n))
        differences.append(diff/scale)
    assert all(d > .3 for d in differences), 'Programs did not produce distinct audio'
    if ARDOUR:
        assert abs(summary[3]['rms'] / summary[2]['rms'] - 1) < .15, 'Channel2 live notes did not use the forced channel1 patch'
    result = {'host':'Ardour session' if ARDOUR else 'jalv', 'audio':summary, 'pairwise_normalized_difference':differences, 'passed':True}
    (WORK/'results.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2), flush=True)
finally:
    if client:
        deactivate(client)
        close_client(client)
    if host and host.poll() is None:
        host.terminate()
        host.wait(timeout=5)
    if server.poll() is None:
        server.terminate()
        server.wait(timeout=5)
    log.close()
