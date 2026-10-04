from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
KEY = "sk-or-v1-0123456789abcdef0123456789abcdef"


def run(home: Path, *args: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
    env = {key: value for key, value in os.environ.items() if key not in {"OPENROUTER_API_KEY", "AGENT_THREAD_JEV_KEY_FILE"}}
    return subprocess.run(
        [sys.executable, str(ROOT / "tools" / "agent-thread-jev-key.py"), *args],
        input=stdin, text=True, capture_output=True, env={**env, "HOME": str(home)}, check=False,
    )


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions")
def test_set_stores_the_key_privately_and_never_prints_it(tmp_path: Path) -> None:
    result = run(tmp_path, "set", "--stdin", "--no-verify", stdin=KEY + "\n")
    assert result.returncode == 0, result.stderr
    assert KEY not in result.stdout and "sk-or-v1…cdef" in result.stdout
    stored = tmp_path / ".config" / "agent-thread-tools" / "openrouter-key"
    assert stored.read_text() == KEY
    assert stat.S_IMODE(stored.stat().st_mode) == 0o600
    assert stat.S_IMODE(stored.parent.stat().st_mode) == 0o700
    status = run(tmp_path, "status")
    assert "sk-or-v1…cdef" in status.stdout and KEY not in status.stdout


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions")
def test_a_key_file_others_can_read_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_thread_tools import jev

    run(tmp_path, "set", "--stdin", "--no-verify", stdin=KEY)
    stored = tmp_path / ".config" / "agent-thread-tools" / "openrouter-key"
    stored.chmod(0o644)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert jev.api_key() == ""
    status = run(tmp_path, "status")
    assert status.returncode == 1 and "chmod 600" in status.stdout


def test_bad_input_and_no_terminal_are_rejected(tmp_path: Path) -> None:
    assert run(tmp_path, "set", "--stdin", "--no-verify", stdin="\n").returncode == 1
    no_tty = run(tmp_path, "set", "--no-verify")
    assert no_tty.returncode != 0 and "--stdin" in (no_tty.stdout + no_tty.stderr)
    assert not (tmp_path / ".config" / "agent-thread-tools" / "openrouter-key").exists()


def test_remove_deletes_the_stored_key(tmp_path: Path) -> None:
    run(tmp_path, "set", "--stdin", "--no-verify", stdin=KEY)
    assert "Removed" in run(tmp_path, "remove").stdout
    assert "none" in run(tmp_path, "status").stdout
