from desktop_agent import startup


def test_startup_configures_background_server(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    captured = {}
    monkeypatch.setattr(startup.uvicorn, "run", lambda *args, **kwargs: captured.update(kwargs))

    startup.main()

    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 8765
    assert captured["log_config"] is None
    assert (tmp_path / "DesktopAgent" / "logs" / "agent.log").exists()
