import pytest

from desktop_agent import memory


def test_remember_and_search_memory(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "DB_PATH", tmp_path / "memory.sqlite3")
    saved = memory.remember("My preferred editor is VS Code", "preference")
    assert saved["id"] > 0
    assert memory.list_memories("VS Code")[0]["content"] == "My preferred editor is VS Code"


def test_memory_context_includes_category(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "DB_PATH", tmp_path / "memory.sqlite3")
    memory.remember("Use local Ollama", "project")
    assert "[project] Use local Ollama" in memory.memory_context()


def test_delete_memory(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "DB_PATH", tmp_path / "memory.sqlite3")
    saved = memory.remember("Temporary fact")
    assert memory.delete_memory(saved["id"]) is True
    assert memory.delete_memory(saved["id"]) is False


def test_memory_rejects_empty_content(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "DB_PATH", tmp_path / "memory.sqlite3")
    with pytest.raises(ValueError):
        memory.remember("   ")
