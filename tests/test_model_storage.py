from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from macro_recorder_plus.model import Macro, MacroEvent
from macro_recorder_plus.storage import load_macro, save_macro


class MacroModelStorageTests(unittest.TestCase):
    def test_macro_round_trip(self) -> None:
        macro = Macro(
            name="demo",
            events=[
                MacroEvent(time=0.0, device="keyboard", action="press", key="a"),
                MacroEvent(time=0.1, device="keyboard", action="release", key="a"),
                MacroEvent(time=0.2, device="mouse", action="press", button="Button.left", x=10, y=20),
            ],
        )

        with tempfile.TemporaryDirectory() as directory:
            path = save_macro(macro, Path(directory) / "demo")
            loaded = load_macro(path)

        self.assertEqual(path.suffix, ".mrplus")
        self.assertEqual(loaded.name, "demo")
        self.assertEqual(len(loaded.events), 3)
        self.assertEqual(loaded.events[2].button, "Button.left")
        self.assertAlmostEqual(loaded.duration, 0.2)

    def test_macro_from_dict_sorts_events(self) -> None:
        macro = Macro.from_dict(
            {
                "version": 1,
                "name": "sorted",
                "events": [
                    {"time": 2.0, "device": "keyboard", "action": "release", "key": "b"},
                    {"time": 1.0, "device": "keyboard", "action": "press", "key": "b"},
                ],
            }
        )

        self.assertEqual([event.time for event in macro.events], [1.0, 2.0])

    def test_rejects_unsupported_schema_version(self) -> None:
        with self.assertRaises(ValueError):
            Macro.from_dict({"version": 999, "events": []})

    def test_saved_macro_is_json_object(self) -> None:
        macro = Macro(name="empty")
        with tempfile.TemporaryDirectory() as directory:
            path = save_macro(macro, Path(directory) / "empty.mrplus")
            data = json.loads(path.read_text(encoding="utf-8"))

        self.assertIsInstance(data, dict)
        self.assertEqual(data["version"], 1)


if __name__ == "__main__":
    unittest.main()
