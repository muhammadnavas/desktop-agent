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
        "notepad", "calculator", "explorer", "vscode", "whatsapp"
    }


def test_command_uses_rules_when_ollama_is_unavailable(monkeypatch):
    def unavailable(_text):
        raise api.OllamaError("offline")

    monkeypatch.setattr(api, "understand_command", unavailable)
    monkeypatch.setattr(api, "execute_tool", lambda _name, arguments: {"status": "launched", "app": arguments["app_id"]})

    response = client.post("/api/commands", json={"text": "Open Notepad"})

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["source"] == "rules_fallback"
    assert response.json()["result"]["app"] == "notepad"


def test_command_opens_whatsapp_with_rules_fallback(monkeypatch):
    def unavailable(_text):
        raise api.OllamaError("offline")

    monkeypatch.setattr(api, "understand_command", unavailable)
    monkeypatch.setattr(api, "execute_tool", lambda _name, arguments: {"status": "launched", "app": arguments["app_id"]})
    response = client.post("/api/commands", json={"text": "Open WhatsApp"})
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["result"]["app"] == "whatsapp"


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
        lambda _text: {"tool": "launch_app", "arguments": {"app_id": "powershell"}, "response": "Opening"},
    )
    response = client.post("/api/commands", json={"text": "open something"})
    assert response.status_code == 400


def test_voice_upload_rejects_payload_over_20mb():
    response = client.post(
        "/api/voice/transcribe",
        files={"audio": ("large.webm", b"x" * (20 * 1024 * 1024 + 1), "audio/webm")},
    )
    assert response.status_code == 413


def test_sensitive_desktop_task_is_blocked():
    response = client.post("/api/tasks/plan", json={"text": "Please delete these files"})
    assert response.status_code == 403


def test_task_plan_requires_approval_and_is_single_use(monkeypatch):
    monkeypatch.setattr(
        api,
        "capture_screenshot",
        lambda: {"image": "data:image/png;base64,ZmFrZQ==", "width": 1200, "height": 800},
    )
    monkeypatch.setattr(
        api,
        "plan_desktop_task",
        lambda *_args: {
            "summary": "Open a page",
            "steps": [{"action": "click", "x": 100, "y": 100}],
        },
    )
    monkeypatch.setattr(api, "execute_steps", lambda *_args: [{"step": "1", "status": "completed"}])

    plan = client.post("/api/tasks/plan", json={"text": "Open the visible browser tab"})
    assert plan.status_code == 200
    payload = plan.json()
    assert payload["requires_confirmation"] is True
    assert payload["screenshot"]["width"] == 1200

    approved = client.post(
        "/api/tasks/confirm",
        json={"confirmation_token": payload["confirmation_token"]},
    )
    assert approved.status_code == 200
    assert approved.json()["success"] is True

    replay = client.post(
        "/api/tasks/confirm",
        json={"confirmation_token": payload["confirmation_token"]},
    )
    assert replay.status_code == 404


def test_code_autometa_starts_fixed_workflow_without_ollama(monkeypatch):
    monkeypatch.setattr(
        api,
        "start_code_autometa_workflow",
        lambda: {
            "message": "Workflow started",
            "workflow": "code_autometa",
        },
    )

    def should_not_call_ollama(_text):
        raise AssertionError("The explicit workflow phrase must bypass Ollama")

    monkeypatch.setattr(api, "understand_command", should_not_call_ollama)
    response = client.post("/api/commands", json={"text": "code autometa"})

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["source"] == "workflow"
    assert response.json()["result"]["workflow"] == "code_autometa"


def test_diagnostics_endpoint_reports_optional_dependencies(monkeypatch):
    monkeypatch.setattr(api, "ollama_status", lambda: {
        "connected": False,
        "model_available": False,
        "error": "offline",
    })

    response = client.get("/api/diagnostics")

    assert response.status_code == 200
    payload = response.json()
    assert "voice" in payload
    assert "memory" in payload
    assert "desktop" in payload
    assert payload["voice"]["install_command"] in {
        None, "pip install -e .[voice]"
    }


def test_voice_status_is_actionable_when_listener_has_not_started():
    monkeypatch_listener = api._wake_listener
    try:
        api._wake_listener = None
        response = client.get("/api/voice/status")
        assert response.status_code == 200
        assert response.json()["state"] == "not_started"
        assert response.json()["available"] is False
    finally:
        api._wake_listener = monkeypatch_listener


def test_tools_endpoint_lists_registered_windows_tools():
    response = client.get("/api/tools")
    assert response.status_code == 200
    assert {tool["name"] for tool in response.json()["tools"]} == {
        "launch_app", "get_active_window", "list_open_windows", "get_window_controls", "read_file", "prepare_file_write"
    }


def test_memory_api_create_list_delete(monkeypatch):
    import mongomock
    from desktop_agent import memory

    mongo_client = mongomock.MongoClient()
    monkeypatch.setattr(memory, "_client", mongo_client)
    created = client.post(
        "/api/memories",
        json={"content": "Preferred project model is Qwen", "category": "preference"},
    )
    assert created.status_code == 200
    memory_id = created.json()["memory"]["id"]
    assert isinstance(memory_id, str)

    listed = client.get("/api/memories?q=Qwen")
    assert listed.status_code == 200
    assert listed.json()["memories"][0]["id"] == memory_id

    deleted = client.delete(f"/api/memories/{memory_id}")
    assert deleted.status_code == 200
    assert client.delete(f"/api/memories/{memory_id}").status_code == 404


def test_skills_api_lists_and_reads_builtin_skill():
    listed = client.get("/api/skills")
    assert listed.status_code == 200
    assert "desktop_task" in {item["id"] for item in listed.json()["skills"]}

    detail = client.get("/api/skills/desktop_task")
    assert detail.status_code == 200
    assert "explicit approval" in detail.json()["instructions"]


def test_unknown_skill_returns_404():
    assert client.get("/api/skills/not-a-real-skill").status_code == 404


def test_command_routes_to_active_window_tool(monkeypatch):
    monkeypatch.setattr(
        api,
        "understand_command",
        lambda _text: {"tool": "get_active_window", "arguments": {}, "response": "Checking active window."},
    )
    monkeypatch.setattr(
        api,
        "execute_tool",
        lambda name, arguments: {"available": True, "title": "VS Code", "handle": 123}
        if name == "get_active_window" and arguments == {} else {},
    )

    response = client.post("/api/commands", json={"text": "What window is active?"})

    assert response.status_code == 200
    assert response.json()["tool"] == "get_active_window"
    assert response.json()["result"]["title"] == "VS Code"


def test_command_uses_rule_fallback_for_open_windows(monkeypatch):
    monkeypatch.setattr(api, "understand_command", lambda _text: (_ for _ in ()).throw(api.OllamaError("offline")))
    monkeypatch.setattr(
        api,
        "execute_tool",
        lambda name, arguments: {"windows": [{"title": "Notepad"}], "count": 1, "limit": 30},
    )

    response = client.post("/api/commands", json={"text": "List all open windows"})

    assert response.status_code == 200
    assert response.json()["tool"] == "list_open_windows"
    assert response.json()["result"]["count"] == 1


def test_ui_button_click_requires_confirmation_and_is_single_use(monkeypatch):
    from desktop_agent.actions import windows_uia

    monkeypatch.setattr(windows_uia, "inspect_button_target", lambda window, button: {
        "available": True, "window_title": window, "button_name": button,
        "control_type": "Button", "enabled": True, "action": "click",
    })
    clicked = []
    monkeypatch.setattr(windows_uia, "click_button",
        lambda window, button: clicked.append((window, button)) or {"success": True})
    plan = client.post("/api/ui-actions/plan-click",
        json={"window_title": "Notepad", "button_name": "Save"})
    assert plan.status_code == 200
    payload = plan.json()
    assert payload["requires_confirmation"] is True
    assert payload["target"]["button_name"] == "Save"
    assert clicked == []
    approved = client.post("/api/ui-actions/confirm-click",
        json={"confirmation_token": payload["confirmation_token"]})
    assert approved.status_code == 200
    assert clicked == [("Notepad", "Save")]
    replay = client.post("/api/ui-actions/confirm-click",
        json={"confirmation_token": payload["confirmation_token"]})
    assert replay.status_code == 404


def test_ui_button_click_plan_rejects_unavailable_target(monkeypatch):
    from desktop_agent.actions import windows_uia
    monkeypatch.setattr(windows_uia, "inspect_button_target",
        lambda *_args: (_ for _ in ()).throw(ValueError("No unique button")))
    response = client.post("/api/ui-actions/plan-click",
        json={"window_title": "Notepad", "button_name": "Save"})
    assert response.status_code == 400


def test_file_write_confirmation_endpoint_commits_only_after_approval(monkeypatch, tmp_path):
    from desktop_agent.actions import files as file_actions

    monkeypatch.setenv("DESKTOP_AGENT_WORKSPACE", str(tmp_path))
    staged = file_actions.prepare_file_write("docs/hello.txt", "Hello from Alexa")
    target = tmp_path / "docs" / "hello.txt"
    assert not target.exists()
    response = client.post("/api/files/confirm-write",
        json={"confirmation_token": staged["confirmation_token"]})
    assert response.status_code == 200
    assert target.read_text(encoding="utf-8") == "Hello from Alexa"
    replay = client.post("/api/files/confirm-write",
        json={"confirmation_token": staged["confirmation_token"]})
    assert replay.status_code == 404


def test_file_write_requires_valid_confirmation_token():
    response = client.post("/api/files/confirm-write",
        json={"confirmation_token": "x" * 40})
    assert response.status_code == 404


def test_file_tools_are_registered():
    response = client.get("/api/tools")
    names = {tool["name"] for tool in response.json()["tools"]}
    assert {"read_file", "prepare_file_write"} <= names


def test_file_management_skill_is_available():
    response = client.get("/api/skills/file_management")
    assert response.status_code == 200
    assert "prepare_file_write" in response.json()["instructions"]


def test_natural_language_file_read_routes_to_registered_tool(monkeypatch, tmp_path):
    from desktop_agent.actions import files as file_actions

    monkeypatch.setenv("DESKTOP_AGENT_WORKSPACE", str(tmp_path))
    (tmp_path / "README.md").write_text("project notes", encoding="utf-8")
    monkeypatch.setattr(api, "understand_command", lambda _text: {
        "tool": "read_file", "arguments": {"path": "README.md"}, "response": "Reading it."
    })
    response = client.post("/api/commands", json={"text": "Read README.md"})
    assert response.status_code == 200
    assert response.json()["tool"] == "read_file"
    assert response.json()["result"]["content"] == "project notes"


def test_natural_language_file_write_only_stages_change(monkeypatch, tmp_path):
    monkeypatch.setenv("DESKTOP_AGENT_WORKSPACE", str(tmp_path))
    monkeypatch.setattr(api, "understand_command", lambda _text: {
        "tool": "prepare_file_write",
        "arguments": {"path": "notes.txt", "content": "new content"},
        "response": "The file has been created.",
    })
    response = client.post("/api/commands", json={"text": "Create notes.txt"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["tool"] == "prepare_file_write"
    assert "Nothing has been written yet" in payload["message"]
    assert not (tmp_path / "notes.txt").exists()
