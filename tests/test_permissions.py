from desktop_agent.permissions import classify_command_text, classify_tool


def test_low_risk_tools_are_automatic():
    for name in ("launch_app", "read_file", "list_directory", "list_project_files", "search_project", "get_active_window", "list_open_windows", "open_new_tab", "get_system_status"):
        assert classify_tool(name).level == "safe"


def test_closing_apps_and_file_writes_need_approval():
    assert classify_tool("close_app").level == "approval"
    assert classify_tool("close_current_tab").level == "approval"
    assert classify_tool("create_folder").level == "approval"
    assert classify_tool("prepare_file_write").level == "approval"


def test_unknown_tools_are_blocked():
    assert classify_tool("run_shell_command").level == "blocked"


def test_destructive_and_sensitive_requests_are_blocked():
    for command in (
        "delete all files in Downloads",
        "format drive D",
        "disable antivirus",
        "show api key",
        "make a payment",
    ):
        assert classify_command_text(command).level == "blocked"


def test_harmless_requests_continue_to_intent_routing():
    assert classify_command_text("Find Python files in my D drive").level == "continue"
