"""Sony priming integration contracts: never touch live Bluetooth or a real mic."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SonyHeadsetIntegrationTests(unittest.TestCase):
    def test_priming_keeps_msbc_lc3_order_and_shared_restore(self):
        source = (ROOT / "home/scripts/microphone/sony-headset-prime").read_text()
        functions = source.split('\nstate_dir="${XDG_RUNTIME_DIR:-/tmp}/sony-headset-prime"')[0]
        with tempfile.TemporaryDirectory() as directory:
            mocks = r'''
export XDG_RUNTIME_DIR="$1"
is_connected() { return 0; }
wait_for_card() { printf '99\n'; }
wait_for_stable_connection() { return 0; }
wait_for_transport_input() { printf 'synthetic-input\n'; }
controller_rejected_sco_since() { return 1; }
sleep() { :; }
wpctl() { printf '%s\n' "$*" >> "$XDG_RUNTIME_DIR/actions"; }
sony-headset-playback() { printf 'policy %s\n' "$*" >> "$XDG_RUNTIME_DIR/actions"; }
timeout() { shift; "$@"; }
pw-record() {
    # Synthetic nonzero samples only. Never open any PipeWire/microphone device.
    python3 -c 'import sys;open(sys.argv[1],"wb").write(b"X"*128+b"\1\0"*4096)' "${@: -1}"
}
prime_connection
'''
            result = subprocess.run(["bash", "-c", functions + mocks, "test", directory],
                                    text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((Path(directory) / "actions").read_text().splitlines(), [
                "policy --begin-priming", "set-profile 99 196865", "set-profile 99 196866", "policy --restore-playback",
            ])
            self.assertFalse((Path(directory) / "sony-msbc-prime.wav").exists())

    def test_busy_graph_defers_priming_without_touching_mic_or_adapter(self):
        source = (ROOT / "home/scripts/microphone/sony-headset-prime").read_text()
        functions = source.split('\nstate_dir="${XDG_RUNTIME_DIR:-/tmp}/sony-headset-prime"')[0]
        mocks = r'''
is_connected() { return 0; }
wait_for_card() { printf '99\n'; }
wait_for_stable_connection() { return 0; }
sony-headset-playback() { return 2; }
wpctl() { printf 'UNEXPECTED PROFILE CHANGE\n'; return 99; }
bluetoothctl() { printf 'UNEXPECTED BLUETOOTH CHANGE\n'; return 99; }
prime_connection
'''
        result = subprocess.run(["bash", "-c", functions + mocks], text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 3)
        self.assertNotIn("UNEXPECTED", result.stdout)

    def test_one_coordinator_and_existing_mic_policies_preserved(self):
        source = (ROOT / "home/scripts/microphone/sony-headset-prime").read_text()
        module = (ROOT / "home/modules/microphone.nix").read_text()
        audio = (ROOT / "hosts/kirax1/modules/desktop/audio.nix").read_text()
        self.assertNotIn("restore_ldac", source)
        self.assertIn('if [[ -e "$primed_marker" ]]; then\n      sony-headset-playback', source)
        self.assertIn("sonyPlaybackPolicy", module)
        self.assertIn("mic-source-disconnect-guard", module)
        self.assertIn('"bluetooth.autoswitch-to-headset-profile" = true;', audio)
        self.assertIn('"bluez5.a2dp.ldac.quality" = "hq";', audio)
        self.assertIn('"bluez5.enable-msbc" = true;', audio)
        self.assertEqual(module.count('name = "sony-headset-prime"'), 1)


if __name__ == "__main__":
    unittest.main()
