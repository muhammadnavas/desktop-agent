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
