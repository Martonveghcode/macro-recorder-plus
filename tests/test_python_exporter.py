from __future__ import annotations

from macro_recorder_plus.exporters.python_exporter import PythonExporter
from macro_recorder_plus.models.actions import ActionType, MacroAction
from macro_recorder_plus.models.macro import MacroDocument


def test_python_export_contains_cli_options_and_macro_data(tmp_path):
    document = MacroDocument(
        name="export",
        actions=[MacroAction(type=ActionType.TYPE_SECRET, params={"environment_variable": "WEBSITE_PASSWORD"})],
    )

    path = PythonExporter().export(document, tmp_path / "exported.py")
    text = path.read_text(encoding="utf-8")

    assert "--dry-run" in text
    assert "--start-action" in text
    assert "<f10>" in text
    assert "WEBSITE_PASSWORD" in text
    assert "set_dpi_awareness" in text
