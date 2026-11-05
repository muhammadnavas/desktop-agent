import pytest

from desktop_agent.actions import files


def test_read_file_reads_utf8_text_inside_workspace(monkeypatch, tmp_path):
    monkeypatch.setenv("DESKTOP_AGENT_WORKSPACE", str(tmp_path))
    (tmp_path / "README.md").write_text("Hello", encoding="utf-8")

    result = files.read_file("README.md")

    assert result["content"] == "Hello"
    assert result["path"] == "README.md"


@pytest.mark.parametrize("path", ["../outside.txt", "/etc/passwd", "", "folder/../../escape"])
def test_file_operations_reject_paths_outside_workspace(monkeypatch, tmp_path, path):
    monkeypatch.setenv("DESKTOP_AGENT_WORKSPACE", str(tmp_path))
    with pytest.raises(ValueError, match="relative path|outside"):
        files.read_file(path)


def test_file_operations_reject_symlink_escape(monkeypatch, tmp_path):
    outside = tmp_path.parent / "outside-secret.txt"
    outside.write_text("secret", encoding="utf-8")
    link = tmp_path / "escape.txt"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation is not available in this environment")
    monkeypatch.setenv("DESKTOP_AGENT_WORKSPACE", str(tmp_path))
    with pytest.raises(ValueError, match="outside"):
        files.read_file("escape.txt")


def test_write_is_staged_until_one_time_confirmation(monkeypatch, tmp_path):
    monkeypatch.setenv("DESKTOP_AGENT_WORKSPACE", str(tmp_path))
    staged = files.prepare_file_write("notes/todo.txt", "First task")
    target = tmp_path / "notes" / "todo.txt"

    assert staged["requires_confirmation"] is True
    assert not target.exists()

    result = files.confirm_file_write(staged["confirmation_token"])
    assert result["success"] is True
    assert target.read_text(encoding="utf-8") == "First task"
    with pytest.raises(KeyError):
        files.confirm_file_write(staged["confirmation_token"])


def test_write_preview_reports_existing_file_overwrite(monkeypatch, tmp_path):
    monkeypatch.setenv("DESKTOP_AGENT_WORKSPACE", str(tmp_path))
    target = tmp_path / "notes.txt"
    target.write_text("old", encoding="utf-8")

    staged = files.prepare_file_write("notes.txt", "new")

    assert staged["overwrites_existing"] is True
    assert target.read_text(encoding="utf-8") == "old"
    files.confirm_file_write(staged["confirmation_token"])
    assert target.read_text(encoding="utf-8") == "new"


def test_read_rejects_binary_or_invalid_utf8(monkeypatch, tmp_path):
    monkeypatch.setenv("DESKTOP_AGENT_WORKSPACE", str(tmp_path))
    (tmp_path / "binary.bin").write_bytes(b"\\xff\\xfe")
    with pytest.raises(ValueError, match="UTF-8"):
        files.read_file("binary.bin")


def test_write_rejects_content_over_one_mb(monkeypatch, tmp_path):
    monkeypatch.setenv("DESKTOP_AGENT_WORKSPACE", str(tmp_path))
    with pytest.raises(ValueError, match="1 MB"):
        files.prepare_file_write("large.txt", "x" * (1_000_001))


def test_expired_write_token_cannot_write(monkeypatch, tmp_path):
    monkeypatch.setenv("DESKTOP_AGENT_WORKSPACE", str(tmp_path))
    staged = files.prepare_file_write("expired.txt", "no")
    files._pending_writes[staged["confirmation_token"]]["created_at"] -= 121
    with pytest.raises(TimeoutError):
        files.confirm_file_write(staged["confirmation_token"])
    assert not (tmp_path / "expired.txt").exists()
