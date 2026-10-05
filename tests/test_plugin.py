from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def test_plugin_manifest_matches_the_package() -> None:
    plugin = load(".claude-plugin/plugin.json")
    package = load("package.json")
    assert plugin["name"] == "agent-thread-tools"
    assert plugin["version"] == package["version"] == (ROOT / "VERSION").read_text().strip()
    # Claude Code loads every skill in skills/, so it must hold only the Claude Code skill.
    assert "skills" not in plugin
    assert sorted(path.name for path in (ROOT / "skills").iterdir()) == ["thread-handoff", "thread-health"]


def test_marketplace_lists_the_plugin_from_this_repository() -> None:
    marketplace = load(".claude-plugin/marketplace.json")
    [entry] = marketplace["plugins"]
    assert entry["name"] == load(".claude-plugin/plugin.json")["name"]
    assert entry["source"] == "./"


def test_plugin_hooks_run_bundled_scripts() -> None:
    hooks = load("hooks/hooks.json")["hooks"]
    assert set(hooks) == {"Stop", "PreCompact"}
    for groups in hooks.values():
        for group in groups:
            for hook in group["hooks"]:
                assert hook["command"].startswith('python3 "${CLAUDE_PLUGIN_ROOT}/tools/')
                script = hook["command"].split("${CLAUDE_PLUGIN_ROOT}/")[1].split('"')[0]
                assert (ROOT / script).is_file()


def test_skill_runs_its_bundled_tools() -> None:
    skill = (ROOT / "skills" / "thread-handoff" / "SKILL.md").read_text(encoding="utf-8")
    assert 'python3 "${CLAUDE_PLUGIN_ROOT}/tools/agent-thread-<command>.py"' in skill


def test_install_skill_points_the_copy_at_the_package(tmp_path: Path) -> None:
    (tmp_path / ".claude").mkdir()
    result = subprocess.run(
        ["node", str(ROOT / "cli" / "agent-thread-tools.js"), "install-skill", "--agent", "claude"],
        env={**os.environ, "HOME": str(tmp_path)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    installed = (tmp_path / ".claude" / "skills" / "thread-handoff" / "SKILL.md").read_text(encoding="utf-8")
    assert "${CLAUDE_PLUGIN_ROOT}" not in installed
    assert f'python3 "{ROOT}/tools/agent-thread-<command>.py"' in installed


def test_stop_hook_reads_the_threshold_from_the_environment(tmp_path: Path) -> None:
    transcript = tmp_path / "s1.jsonl"
    usage = {"input_tokens": 10, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 5000, "output_tokens": 5}
    transcript.write_text(
        json.dumps({"type": "assistant", "message": {"model": "claude-opus-5-5", "usage": usage}}) + "\n",
        encoding="utf-8",
    )
    event = json.dumps({"session_id": "s1", "transcript_path": str(transcript), "stop_hook_active": False})

    def run(threshold: str) -> str:
        home = tmp_path / f"home-{threshold}"
        home.mkdir()
        return subprocess.run(
            ["python3", str(ROOT / "tools" / "agent-thread-hook.py"), "claude-stop"],
            input=event,
            env={**os.environ, "HOME": str(home), "AGENT_THREAD_AUTO_HANDOFF_AT": threshold},
            capture_output=True,
            text=True,
            check=False,
        ).stdout

    assert '"block"' in run("4k")
    assert run("10k") == ""
