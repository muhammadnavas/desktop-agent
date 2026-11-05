from fastapi.testclient import TestClient

from desktop_agent import api


client = TestClient(api.app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["name"] == "Desktop Agent"


def test_apps_endpoint_returns_allowlist():
    response = client.get("/api/apps")
    assert response.status_code == 200
    assert {app["id"] for app in response.json()["apps"]} == {
        "notepad", "calculator", "explorer", "vscode"
    }


def test_command_uses_rules_when_ollama_is_unavailable(monkeypatch):
    def unavailable(_text):
        raise api.OllamaError("offline")

    monkeypatch.setattr(api, "understand_command", unavailable)
    monkeypatch.setattr(api, "launch_app", lambda app_id: {"status": "launched", "app": app_id})

    response = client.post("/api/commands", json={"text": "Open Notepad"})

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["source"] == "rules_fallback"
    assert response.json()["result"]["app"] == "notepad"


def test_command_rejects_unsupported_rule_command(monkeypatch):
    def unavailable(_text):
        raise api.OllamaError("offline")

    monkeypatch.setattr(api, "understand_command", unavailable)
    response = client.post("/api/commands", json={"text": "delete my files"})
    assert response.status_code == 422


def test_command_rejects_unknown_model_app(monkeypatch):
    monkeypatch.setattr(
        api,
        "understand_command",
        lambda _text: {"action": "launch_app", "app_id": "powershell", "response": "Opening"},
    )
    response = client.post("/api/commands", json={"text": "open something"})
    assert response.status_code == 422


def test_voice_upload_rejects_payload_over_20mb():
    response = client.post(
        "/api/voice/transcribe",
        files={"audio": ("large.webm", b"x" * (20 * 1024 * 1024 + 1), "audio/webm")},
    )
    assert response.status_code == 413
