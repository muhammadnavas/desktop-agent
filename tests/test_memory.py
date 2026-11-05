import mongomock
import pytest

from desktop_agent import memory


@pytest.fixture
def mongo_memory(monkeypatch):
    client = mongomock.MongoClient()
    monkeypatch.setattr(memory, "_client", client)
    monkeypatch.setattr(memory, "MONGO_DATABASE", "test_desktop_agent")
    monkeypatch.setattr(memory, "MONGO_COLLECTION", "memories")
    yield client
    client.close()


def test_remember_and_search_memory(mongo_memory):
    saved = memory.remember("My preferred editor is VS Code", "preference")
    assert len(saved["id"]) == 24
    assert memory.list_memories("VS Code")[0]["content"] == "My preferred editor is VS Code"


def test_memory_context_includes_category(mongo_memory):
    memory.remember("Use local Ollama", "project")
    assert "[project] Use local Ollama" in memory.memory_context()


def test_delete_memory(mongo_memory):
    saved = memory.remember("Temporary fact")
    assert memory.delete_memory(saved["id"]) is True
    assert memory.delete_memory(saved["id"]) is False


def test_delete_rejects_invalid_object_id(mongo_memory):
    assert memory.delete_memory("not-an-object-id") is False


def test_memory_rejects_empty_content(mongo_memory):
    with pytest.raises(ValueError):
        memory.remember("   ")
