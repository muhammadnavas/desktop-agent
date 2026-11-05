import sys
import types

import pytest

from desktop_agent.actions import windows_uia


class FakeControl:
    def __init__(self, name, control_type, automation_id):
        self.element_info = types.SimpleNamespace(
            name=name, control_type=control_type, automation_id=automation_id
        )

    def is_visible(self):
        return True

    def is_enabled(self):
        return True


class FakeWindow:
    def __init__(self, title, controls):
        self._title = title
        self._controls = controls

    def window_text(self):
        return self._title

    def is_visible(self):
        return True

    def descendants(self):
        return self._controls


def install_fake_pywinauto(monkeypatch, windows):
    class FakeDesktop:
        def __init__(self, backend):
            assert backend == "uia"

        def windows(self):
            return windows

    monkeypatch.setitem(sys.modules, "pywinauto", types.SimpleNamespace(Desktop=FakeDesktop))
    monkeypatch.setattr(windows_uia.os, "name", "nt")


def test_inspection_returns_accessible_metadata_without_control_values(monkeypatch):
    control = FakeControl("Save", "Button", "saveButton")
    install_fake_pywinauto(monkeypatch, [FakeWindow("Untitled - Notepad", [control])])

    result = windows_uia.get_window_controls("notepad")

    assert result["available"] is True
    assert result["window_title"] == "Untitled - Notepad"
    assert result["controls"] == [{
        "name": "Save",
        "control_type": "Button",
        "automation_id": "saveButton",
        "visible": True,
        "enabled": True,
    }]
    assert "value" not in result["controls"][0]


def test_inspection_returns_empty_result_when_window_not_found(monkeypatch):
    install_fake_pywinauto(monkeypatch, [FakeWindow("Calculator", [])])

    result = windows_uia.get_window_controls("Notepad")

    assert result["available"] is False
    assert result["count"] == 0


@pytest.mark.parametrize("title", ["", "  ", "x" * 201, None])
def test_inspection_validates_window_title(monkeypatch, title):
    monkeypatch.setattr(windows_uia.os, "name", "nt")
    with pytest.raises(ValueError):
        windows_uia.get_window_controls(title)


@pytest.mark.parametrize("limit", [0, 101, True, 1.5])
def test_inspection_validates_limit(monkeypatch, limit):
    monkeypatch.setattr(windows_uia.os, "name", "nt")
    with pytest.raises(ValueError):
        windows_uia.get_window_controls("Notepad", limit=limit)
