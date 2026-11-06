from desktop_agent.parser import parse_open_website_command


def test_parse_common_website_aliases():
    assert parse_open_website_command("Alexa, open YouTube") == "https://www.youtube.com"
    assert parse_open_website_command("visit GitHub") == "https://github.com"
    assert parse_open_website_command("go to ChatGPT") == "https://chatgpt.com"


def test_parse_explicit_http_and_domain_urls():
    assert parse_open_website_command("open https://example.com/docs") == "https://example.com/docs"
    assert parse_open_website_command("visit www.example.com") == "https://www.example.com"


def test_reject_unsafe_or_ambiguous_website_requests():
    assert parse_open_website_command("open calculator") is None
    assert parse_open_website_command("open javascript:alert(1)") is None
    assert parse_open_website_command("open file:///C:/Windows") is None
    assert parse_open_website_command("open https://user:pass@example.com") is None


def test_open_website_routes_without_ollama(monkeypatch):
    from fastapi.testclient import TestClient
    from desktop_agent import api

    calls = []
    monkeypatch.setattr(api, "execute_tool", lambda name, args: calls.append((name, args)) or {
        "success": True, "url": args["url"], "message": "Opened website."
    })
    response = TestClient(api.app).post("/api/commands", json={
        "text": "Alexa, open YouTube",
        "use_ollama": False,
        "session_id": "website-test",
    })
    assert response.status_code == 200
    assert response.json()["tool"] == "open_website"
    assert calls == [("open_website", {"url": "https://www.youtube.com"})]
