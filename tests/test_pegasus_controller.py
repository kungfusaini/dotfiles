"""Keep the Pro Controller confirm/back correction local to Pegasus."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PegasusControllerTests(unittest.TestCase):
    def test_only_confirm_back_changed(self):
        lines = (ROOT / "home/config/pegasus/sdl_controllers.txt").read_text().splitlines()
        mappings = [line for line in lines if line and not line.startswith("#")]
        self.assertEqual(len(mappings), 1)
        guid, name, *fields = mappings[0].split(",")
        self.assertEqual(guid, "0500d71f7e0500000920000000006803")
        actual = dict(field.split(":", 1) for field in fields if field)
        expected = dict(field.split(":", 1) for field in (
            "a:b1,b:b0,back:b4,dpdown:h0.4,dpleft:h0.8,dpright:h0.2,dpup:h0.1,"
            "guide:b5,leftshoulder:b9,leftstick:b7,lefttrigger:a4,leftx:a0,lefty:a1,"
            "rightshoulder:b10,rightstick:b8,righttrigger:a5,rightx:a2,righty:a3,"
            "start:b6,x:b2,y:b3,misc1:b11,crc:1fd7,platform:Linux"
        ).split(","))
        self.assertEqual(actual, expected)

    def test_deployed_only_as_pegasus_native_mapping(self):
        module = (ROOT / "home/modules/pegasus.nix").read_text()
        self.assertIn(
            '"pegasus-frontend/sdl_controllers.txt".source = ../config/pegasus/sdl_controllers.txt;',
            module,
        )
        self.assertNotIn("SDL_GAMECONTROLLERCONFIG", module)


if __name__ == "__main__":
    unittest.main()
