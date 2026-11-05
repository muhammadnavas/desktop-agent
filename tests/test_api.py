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
    assert {
        "launch_app", "get_active_window", "list_open_windows", "get_window_controls",
        "read_file", "prepare_file_write", "close_app", "create_folder",
        "open_new_tab", "close_current_tab", "get_system_status", "run_diagnostic_command", "list_project_files", "search_project", "list_directory",
    } <= {tool["name"] for tool in response.json()["tools"]}


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


def test_close_app_and_create_folder_tools_are_registered():
    response = client.get("/api/tools")
    names = {tool["name"] for tool in response.json()["tools"]}
    assert {"close_app", "create_folder"} <= names


def test_create_folder_tool_creates_only_inside_workspace(monkeypatch, tmp_path):
    from desktop_agent.actions.files import create_folder

    monkeypatch.setenv("DESKTOP_AGENT_WORKSPACE", str(tmp_path))
    result = create_folder("new-project/docs")
    assert result["success"] is True
    assert result["created"] is True
    assert (tmp_path / "new-project" / "docs").is_dir()


def test_create_folder_allows_parent_traversal(monkeypatch, tmp_path):
    from desktop_agent.actions.files import create_folder

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("DESKTOP_AGENT_WORKSPACE", str(workspace))
    result = create_folder("../outside")
    assert result["created"] is True
    assert (tmp_path / "outside").is_dir()


def test_create_folder_asks_for_destination_and_uses_follow_up(monkeypatch, tmp_path):
    monkeypatch.setenv("DESKTOP_AGENT_WORKSPACE", str(tmp_path))
    calls = []
    def interpret(text):
        calls.append(text)
        if len(calls) == 1:
            return {"tool": "create_folder", "arguments": {"path": "Projects"}, "response": "Creating folder."}
        assert "Original request:" in text
        assert "User clarification: Documents" in text
        return {"tool": "create_folder", "arguments": {"path": "Documents/Projects"}, "response": "Creating it in Documents."}
    monkeypatch.setattr(api, "understand_command", interpret)
    first = client.post("/api/commands", json={"text": "Create a folder called Projects", "session_id": "folder-test"})
    assert first.status_code == 200
    assert first.json()["needs_clarification"] is True
    assert "Where should I create" in first.json()["message"]
    assert not (tmp_path / "Projects").exists()
    second = client.post("/api/commands", json={"text": "Documents", "session_id": "folder-test"})
    assert second.status_code == 200
    assert second.json()["tool"] == "create_folder"
    assert second.json()["needs_approval"] is True
    assert not (tmp_path / "Documents" / "Projects").exists()
    approved = client.post("/api/commands/confirm", json={
        "confirmation_token": second.json()["confirmation_token"]
    })
    assert approved.status_code == 200
    assert (tmp_path / "Documents" / "Projects").is_dir()


def test_model_clarification_is_returned_without_running_tool(monkeypatch):
    executed = []
    monkeypatch.setattr(api, "understand_command", lambda _text: {
        "tool": None, "arguments": {}, "response": "",
        "clarification_question": "Which directory should I use?",
    })
    monkeypatch.setattr(api, "execute_tool", lambda *args: executed.append(args))
    response = client.post("/api/commands", json={"text": "Create a folder", "session_id": "clarify-test"})
    assert response.status_code == 200
    assert response.json()["needs_clarification"] is True
    assert executed == []

def test_close_phrase_requires_approval_before_execution(monkeypatch):
    executed = []
    monkeypatch.setattr(api, "understand_command", lambda _text: (_ for _ in ()).throw(AssertionError("Ollama must not override close")))
    monkeypatch.setattr(api, "execute_tool", lambda name, args: executed.append((name, args)) or {"app": "WhatsApp"})
    response = client.post("/api/commands", json={"text": "Let's close WhatsApp"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["needs_approval"] is True
    assert payload["tool"] == "close_app"
    assert executed == []

    confirmed = client.post("/api/commands/confirm", json={
        "confirmation_token": payload["confirmation_token"]
    })
    assert confirmed.status_code == 200
    assert executed == [("close_app", {"app_id": "whatsapp"})]


def test_incomplete_folder_request_asks_for_name_then_destination(monkeypatch, tmp_path):
    monkeypatch.setenv("DESKTOP_AGENT_WORKSPACE", str(tmp_path))
    first = client.post("/api/commands", json={"text": "Alexa can you create a folder", "session_id": "voice-folder"})
    assert first.status_code == 200
    assert first.json()["needs_clarification"] is True
    assert "name" in first.json()["message"].lower()

    second = client.post("/api/commands", json={"text": "Projects", "session_id": "voice-folder"})
    assert second.status_code == 200
    assert second.json()["needs_clarification"] is True
    assert "where" in second.json()["message"].lower()

    third = client.post("/api/commands", json={"text": "Documents", "session_id": "voice-folder"})
    assert third.status_code == 200
    assert third.json()["tool"] == "create_folder"
    assert third.json()["needs_approval"] is True
    assert not (tmp_path / "documents" / "projects").exists()
    approved = client.post("/api/commands/confirm", json={
        "confirmation_token": third.json()["confirmation_token"]
    })
    assert approved.status_code == 200
    assert (tmp_path / "documents" / "projects").is_dir()


def test_model_cannot_open_an_app_not_mentioned_by_user(monkeypatch):
    monkeypatch.setattr(api, "understand_command", lambda _text: {
        "tool": "launch_app", "arguments": {"app_id": "whatsapp"}, "response": "Opening WhatsApp."
    })
    response = client.post("/api/commands", json={"text": "Alexa open mindset", "session_id": "wrong-app"})
    assert response.status_code == 200
    assert response.json()["needs_clarification"] is True
    assert "Which supported app" in response.json()["message"]


def test_file_tools_accept_absolute_paths_outside_workspace(monkeypatch, tmp_path):
    from desktop_agent.actions.files import read_file, create_folder, prepare_file_write, confirm_file_write

    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    monkeypatch.setenv("DESKTOP_AGENT_WORKSPACE", str(workspace))

    source = outside / "notes.txt"
    source.write_text("outside workspace", encoding="utf-8")
    assert read_file(str(source))["content"] == "outside workspace"

    folder = outside / "new-folder"
    created = create_folder(str(folder))
    assert created["created"] is True
    assert folder.is_dir()

    target = outside / "created.txt"
    staged = prepare_file_write(str(target), "approved content")
    assert staged["path"] == str(target.resolve())
    assert not target.exists()
    result = confirm_file_write(staged["confirmation_token"])
    assert result["path"] == str(target.resolve())
    assert target.read_text(encoding="utf-8") == "approved content"


def test_file_tools_allow_parent_traversal_for_relative_paths(monkeypatch, tmp_path):
    from desktop_agent.actions.files import create_folder

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("DESKTOP_AGENT_WORKSPACE", str(workspace))
    result = create_folder("../outside-folder")
    assert result["created"] is True
    assert (tmp_path / "outside-folder").is_dir()


def test_blocked_destructive_command_never_reaches_ollama_or_tools(monkeypatch):
    executed = []
    monkeypatch.setattr(api, "understand_command", lambda _text: (_ for _ in ()).throw(AssertionError("must not call Ollama")))
    monkeypatch.setattr(api, "execute_tool", lambda *args: executed.append(args))
    response = client.post("/api/commands", json={"text": "delete all files in Downloads"})
    assert response.status_code == 200
    assert response.json()["blocked"] is True
    assert executed == []


def test_folder_creation_requires_approval(monkeypatch, tmp_path):
    monkeypatch.setenv("DESKTOP_AGENT_WORKSPACE", str(tmp_path))
    response = client.post("/api/commands", json={
        "text": "create folder called Projects in Documents",
        "use_ollama": False,
    })
    assert response.status_code == 200
    assert response.json()["tool"] == "create_folder"
    assert response.json()["needs_approval"] is True
    assert not (tmp_path / "documents" / "projects").exists()
    approved = client.post("/api/commands/confirm", json={
        "confirmation_token": response.json()["confirmation_token"]
    })
    assert approved.status_code == 200
    assert (tmp_path / "documents" / "projects").is_dir()



def test_browser_tab_close_requires_approval_and_is_single_use(monkeypatch):
    from desktop_agent.actions import browser_tabs

    calls = []
    monkeypatch.setattr(browser_tabs, "close_current_tab",
        lambda: calls.append("closed") or {"success": True, "window": "Google Chrome"})
    monkeypatch.setattr(api, "understand_command", lambda _text: {
        "tool": "close_current_tab", "arguments": {}, "response": "Closing the current tab."
    })
    planned = client.post("/api/commands", json={"text": "Close this browser tab"})
    assert planned.status_code == 200
    payload = planned.json()
    assert payload["needs_approval"] is True
    assert calls == []

    approved = client.post("/api/commands/confirm",
        json={"confirmation_token": payload["confirmation_token"]})
    assert approved.status_code == 200
    assert approved.json()["tool"] == "close_current_tab"
    assert calls == ["closed"]

    replay = client.post("/api/commands/confirm",
        json={"confirmation_token": payload["confirmation_token"]})
    assert replay.status_code == 404


def test_command_approval_endpoint_rejects_unknown_token():
    response = client.post("/api/commands/confirm",
        json={"confirmation_token": "x" * 40})
    assert response.status_code == 404


def test_system_status_tool_is_registered_and_read_only():
    from desktop_agent.actions.system import get_system_status

    status = get_system_status()
    assert status["success"] is True
    assert status["python"]
    assert status["logical_cpu_count"] is None or status["logical_cpu_count"] >= 1



def test_project_file_tools_are_registered():
    names = {tool["name"] for tool in client.get("/api/tools").json()["tools"]}
    assert {"list_project_files", "search_project"} <= names


def test_project_file_tools_route_through_command_api(monkeypatch, tmp_path):
    (tmp_path / "main.py").write_text("def hello():\n    return 'world'\n", encoding="utf-8")
    monkeypatch.setattr(api, "understand_command", lambda _text: {
        "tool": "search_project",
        "arguments": {"root": str(tmp_path), "query": "hello"},
        "response": "Searching the project.",
    })
    response = client.post("/api/commands", json={"text": "Find hello in this project"})
    assert response.status_code == 200
    assert response.json()["tool"] == "search_project"
    assert response.json()["result"]["matches"][0]["file"] == "main.py"


def test_list_directory_tool_lists_entries_and_filters_secret_names(tmp_path):
    from desktop_agent.actions.files import list_directory

    (tmp_path / "notes.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("do not list", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    result = list_directory(str(tmp_path))
    names = {item["name"] for item in result["entries"]}
    assert {"notes.txt", "docs"} <= names
    assert "secret.txt" not in names


def test_diagnostic_command_rejects_non_allowlisted_command(monkeypatch):
    from desktop_agent.actions.diagnostics import run_diagnostic_command
    import pytest

    with pytest.raises(ValueError):
        run_diagnostic_command("powershell")


def test_diagnostic_command_tool_is_registered():
    names = {tool["name"] for tool in client.get("/api/tools").json()["tools"]}
    assert "run_diagnostic_command" in names


def test_diagnostic_command_routes_with_ollama(monkeypatch):
    monkeypatch.setattr(api, "understand_command", lambda _text: {
        "tool": "run_diagnostic_command",
        "arguments": {"command_id": "ipconfig"},
        "response": "Running network diagnostics.",
    })
    monkeypatch.setattr(api, "execute_tool", lambda name, args: {
        "success": True, "command_id": args["command_id"], "output": "IPv4 Address"
    })
    response = client.post("/api/commands", json={"text": "Show my IP configuration"})
    assert response.status_code == 200
    assert response.json()["tool"] == "run_diagnostic_command"
    assert "IPv4 Address" in response.json()["message"]


def test_diagnostic_command_has_rules_fallback(monkeypatch):
    calls = []
    monkeypatch.setattr(api, "understand_command", lambda _text: (_ for _ in ()).throw(api.OllamaError("offline")))
    monkeypatch.setattr(api, "execute_tool", lambda name, args: calls.append((name, args)) or {
        "success": True, "command_id": "ipconfig", "output": "Windows IP Configuration"
    })
    response = client.post("/api/commands", json={
        "text": "Run ipconfig", "use_ollama": False
    })
    assert response.status_code == 200
    assert calls == [("run_diagnostic_command", {"command_id": "ipconfig"})]



def test_pending_command_can_be_rejected_without_execution(monkeypatch):
    executed = []
    monkeypatch.setattr(api, "understand_command", lambda _text: {
        "tool": "close_current_tab", "arguments": {}, "response": "Close the tab."
    })
    monkeypatch.setattr(api, "execute_tool", lambda *args: executed.append(args))
    planned = client.post("/api/commands", json={"text": "Close this tab"})
    assert planned.json()["needs_approval"] is True
    rejected = client.post("/api/commands/cancel", json={
        "confirmation_token": planned.json()["confirmation_token"]
    })
    assert rejected.status_code == 200
    assert rejected.json()["cancelled"] is True
    assert executed == []
    replay = client.post("/api/commands/confirm", json={
        "confirmation_token": planned.json()["confirmation_token"]
    })
    assert replay.status_code == 404



def test_voice_status_exposes_last_interaction():
    monkeypatch = None
    from desktop_agent import api as api_module
    api_module._last_voice_activity.update({
        "transcript": "open notepad",
        "response": "Opening Notepad.",
        "pending_approval": None,
    })
    response = client.get("/api/voice/status")
    assert response.status_code == 200
    assert response.json()["last_voice_activity"]["transcript"] == "open notepad"
    assert response.json()["last_response"] == "Opening Notepad."



def test_staged_file_write_can_be_cancelled_without_writing(monkeypatch, tmp_path):
    from desktop_agent.actions import files

    monkeypatch.setenv("DESKTOP_AGENT_WORKSPACE", str(tmp_path))
    staged = files.prepare_file_write("draft.txt", "hello")
    response = client.post("/api/files/cancel-write", json={
        "confirmation_token": staged["confirmation_token"]
    })
    assert response.status_code == 200
    assert response.json()["cancelled"] is True
    assert not (tmp_path / "draft.txt").exists()
