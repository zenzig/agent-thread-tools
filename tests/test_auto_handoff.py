from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from agent_thread_tools import auto_handoff
from agent_thread_tools.auto_handoff import latest_context_tokens, parse_threshold, stop_decision

ROOT = Path(__file__).resolve().parents[1]


def reply(context: int, **fields: object) -> dict[str, object]:
    return {
        "type": "assistant",
        "sessionId": "s1",
        "cwd": "/work/project",
        "timestamp": "2026-09-30T10:00:00.000Z",
        "message": {
            "role": "assistant",
            "model": "claude-opus-5-5",
            "content": [{"type": "text", "text": "Done."}],
            "usage": {
                "input_tokens": 10,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": context - 15,
                "output_tokens": 5,
            },
        },
        **fields,
    }


def write(path: Path, records: list[dict[str, object]]) -> Path:
    path.write_text("".join(json.dumps(item) + "\n" for item in records), encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv(auto_handoff.DISABLE_ENV, raising=False)
    monkeypatch.delenv("CLAUDE_CONTEXT_WINDOW", raising=False)
    return home


def event(transcript: Path, **fields: object) -> dict[str, object]:
    return {"session_id": "s1", "transcript_path": str(transcript), "stop_hook_active": False, **fields}


def test_thresholds_parse() -> None:
    assert parse_threshold("150k") == (150_000, None)
    assert parse_threshold("1m") == (1_000_000, None)
    assert parse_threshold("90000") == (90_000, None)
    assert parse_threshold("60%") == (None, 0.6)
    with pytest.raises(ValueError):
        parse_threshold("lots")


def test_latest_context_skips_subagent_and_synthetic_replies(tmp_path: Path) -> None:
    synthetic = reply(999)
    synthetic["message"]["model"] = "<synthetic>"
    transcript = write(
        tmp_path / "s1.jsonl",
        [reply(120_000), reply(500_000, isSidechain=True), synthetic, {"type": "system"}],
    )
    assert latest_context_tokens(transcript) == 120_000


def test_below_threshold_lets_the_turn_end(tmp_path: Path) -> None:
    transcript = write(tmp_path / "s1.jsonl", [reply(100_000)])
    assert stop_decision(event(transcript), "150k") is None


def test_past_threshold_asks_for_a_handoff_once(tmp_path: Path) -> None:
    transcript = write(tmp_path / "s1.jsonl", [reply(160_000)])
    decision = stop_decision(event(transcript), "150k")
    assert decision is not None
    assert decision["decision"] == "block"
    assert "/thread-handoff" in decision["reason"] and "/clear" in decision["reason"]
    assert stop_decision(event(transcript), "150k") is None


def test_percent_threshold_uses_the_context_window(tmp_path: Path) -> None:
    transcript = write(tmp_path / "s1.jsonl", [reply(130_000)])
    assert stop_decision(event(transcript), "60%") is not None  # 60% of 200k


@pytest.mark.parametrize(
    "fields",
    [
        {"stop_hook_active": True},
        {"stop_reason": "max_tokens"},
        {"session_id": ""},
        {"background_tasks": [{"id": "bspliwozb", "status": "running"}]},
    ],
)
def test_loops_unfinished_turns_and_bad_events_are_left_alone(tmp_path: Path, fields) -> None:
    transcript = write(tmp_path / "s1.jsonl", [reply(900_000)])
    assert stop_decision(event(transcript, **fields), "150k") is None


def test_environment_switch_turns_it_off(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(auto_handoff.DISABLE_ENV, "off")
    transcript = write(tmp_path / "s1.jsonl", [reply(900_000)])
    assert stop_decision(event(transcript), "150k") is None


def run_hook(args: list[str], payload: object, home: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "tools" / "agent-thread-hook.py"), *args],
        input=payload if isinstance(payload, str) else json.dumps(payload),
        text=True,
        capture_output=True,
        env={**os.environ, "HOME": str(home)},
        check=False,
    )


def test_stop_hook_command_prints_the_decision(tmp_path: Path, isolated_home: Path) -> None:
    transcript = write(tmp_path / "s1.jsonl", [reply(200_000)])
    result = run_hook(["claude-stop", "--at", "150k"], event(transcript), isolated_home)
    assert result.returncode == 0
    assert json.loads(result.stdout)["decision"] == "block"


def test_hook_command_never_fails_on_bad_input(isolated_home: Path) -> None:
    result = run_hook(["claude-stop"], "not json", isolated_home)
    assert result.returncode == 0 and result.stdout == ""


def test_precompact_saves_a_draft_only_where_reference_exists(tmp_path: Path, isolated_home: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    transcript = write(
        tmp_path / "s1.jsonl",
        [
            {
                "type": "user",
                "sessionId": "s1",
                "cwd": str(project),
                "timestamp": "2026-09-30T10:00:00.000Z",
                "message": {"role": "user", "content": "Build the login page"},
            },
            reply(50_000),
        ],
    )
    payload = {"transcript_path": str(transcript), "cwd": str(project), "trigger": "auto"}
    run_hook(["claude-precompact"], payload, isolated_home)
    assert not (project / ".reference").exists()

    (project / ".reference").mkdir()
    run_hook(["claude-precompact"], payload, isolated_home)
    [draft] = list((project / ".reference" / "handoffs").glob("*-before-compaction-draft.md"))
    assert "Draft saved before compaction" in draft.read_text(encoding="utf-8")


def run_install(home: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", str(ROOT / "bin" / "agent-thread-tools.js"), "install-skill", "--agent", "claude", *args],
        text=True,
        capture_output=True,
        env={**os.environ, "HOME": str(home)},
        check=False,
    )


def test_installer_adds_and_removes_hooks_without_touching_other_settings(isolated_home: Path) -> None:
    settings = isolated_home / ".claude" / "settings.json"
    settings.parent.mkdir()
    other = {"matcher": "", "hooks": [{"type": "command", "command": "notify-me"}]}
    settings.write_text(json.dumps({"model": "opus", "hooks": {"Stop": [other]}}), encoding="utf-8")

    assert run_install(isolated_home, "--auto-handoff", "--at", "120k").returncode == 0
    assert run_install(isolated_home, "--auto-handoff", "--at", "120k").returncode == 0  # idempotent
    data = json.loads(settings.read_text(encoding="utf-8"))
    commands = [hook["command"] for group in data["hooks"]["Stop"] for hook in group["hooks"]]
    assert commands == ["notify-me", "agent-thread-tools hook claude-stop --at 120k"]
    assert data["hooks"]["PreCompact"][0]["hooks"][0]["command"] == "agent-thread-tools hook claude-precompact"
    assert data["model"] == "opus"
    assert (isolated_home / ".claude" / "skills" / "thread-handoff" / "SKILL.md").is_file()

    assert run_install(isolated_home, "--no-auto-handoff").returncode == 0
    data = json.loads(settings.read_text(encoding="utf-8"))
    assert data["hooks"] == {"Stop": [other]}


def test_installer_refuses_a_bad_threshold_and_unreadable_settings(isolated_home: Path) -> None:
    settings = isolated_home / ".claude" / "settings.json"
    settings.parent.mkdir()
    settings.write_text("{not json", encoding="utf-8")
    assert run_install(isolated_home, "--auto-handoff", "--at", "lots").returncode == 1
    assert run_install(isolated_home, "--auto-handoff").returncode == 1
    assert settings.read_text(encoding="utf-8") == "{not json"


def test_waits_for_background_work_then_asks(tmp_path: Path) -> None:
    transcript = write(tmp_path / "s1.jsonl", [reply(400_000)])
    running = event(transcript, background_tasks=[{"id": "gate", "status": "running"}])
    assert stop_decision(running, "300k") is None
    assert stop_decision(event(transcript, background_tasks=[]), "300k") is not None
