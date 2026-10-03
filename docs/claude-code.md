# Claude Code

`agent-thread-tools` reads Claude Code sessions as well as Codex sessions. Each
session file is checked on its own: Codex records carry a `payload`, and Claude
Code records are translated into the same shape before analysis.

## Where sessions live

Claude Code writes one JSONL file per session to
`~/.claude/projects/<project-dir>/<session-id>.jsonl`, where `<project-dir>` is the
project path with separators replaced by `-`. Next to it, a folder named
`<session-id>/` holds subagent transcripts, tool results, and workflow files. Files
in that folder are not counted as separate sessions when a root is scanned.

## Health

```bash
agent-thread-tools health --agent claude
agent-thread-tools health check ~/.claude/projects/<project-dir>/<session-id>.jsonl
```

Without `--agent`, the tools use `~/.codex/sessions` when it exists and
`~/.claude/projects` otherwise.

What is measured for Claude Code:

| Metric | Source |
| --- | --- |
| Project and session | `cwd` and `sessionId` on each record |
| Turns | a user prompt opens a turn; `turn_duration` or an `end_turn` reply closes it; an interrupt aborts it; an API error message is an error |
| Compactions | `compact_boundary` records and the compact summary that follows |
| Context use | the latest reply's input, cache, and output tokens against the context window |
| Visuals | pasted and tool-result images, which Claude Code embeds as base64 |

The context window is 200,000 tokens unless a reply or compaction in the session
exceeds it, in which case 1,000,000 is assumed. Set `CLAUDE_CONTEXT_WINDOW` to fix it.

## Handoff skill

```bash
agent-thread-tools install-skill --agent claude
```

This installs `~/.claude/skills/thread-handoff`. `/thread-handoff` then appears in
the slash-command menu of every Claude Code app (terminal, IDE, desktop, and mobile
through Remote Control) when the session runs on that machine. See
[Installation](installation.md#claude-code) to install from inside an app.

Running `/thread-handoff` in a session:

1. runs the health check and redacted summary on the current session;
2. archives screenshots that still matter and saves large reference text;
3. writes a dated handoff and puts stable facts into `CLAUDE.md`;
4. points `CLAUDE.local.md` at the latest handoff, so the next session loads it;
5. commits the handoff in `.reference/` and records a handoff marker.

Handoffs, screenshots, and reference docs go in the project's `.reference/`
folder. The skill sets it up automatically: it is its own local git repository,
listed (with `CLAUDE.local.md`) in the project's `.git/info/exclude` so the project
repository ignores both without any tracked file changing, and each handoff is committed there. Nothing in
it is pushed. You can run the same steps yourself:

```bash
agent-thread-tools reference init                    # create .reference/ and hide it
agent-thread-tools reference commit -m "Add spec"    # commit everything in it
```

Then run `/clear` or start a new session: it starts from `CLAUDE.md`, the handoff,
and auto memory instead of the old transcript.

Health then links the two sessions. The session that was handed off shows as
retired, and a later session that loaded the handoff through `CLAUDE.local.md`
shows as its replacement ("Replacement active").

Handoff markers are kept in `~/.codex/thread-tools/handoff-markers.jsonl` when
`~/.codex` exists, so one file covers both agents, and in
`~/.claude/thread-tools/handoff-markers.jsonl` otherwise. Set
`AGENT_THREAD_HANDOFF_MARKER_FILE` to use another file.

## Plugin

agent-thread-tools is also a Claude Code plugin. The repository is its own
marketplace:

```text
/plugin marketplace add zenzig/agent-thread-tools
/plugin install agent-thread-tools@agent-thread-tools
```

The plugin brings the `/thread-handoff` skill and the two automatic-handoff hooks
below, and runs the Python tools bundled with it, so the npm package is optional
(install it for `health`, archives, and recovery from a terminal). It needs Python 3
on the machine where Claude Code runs. Set the threshold with
`AGENT_THREAD_AUTO_HANDOFF_AT` (default `250k`), for example in the `env` section of
`~/.claude/settings.json`; `AGENT_THREAD_AUTO_HANDOFF=off` turns the hooks off.
Plugins from your own marketplaces don't update automatically unless you turn that on
in `/plugin`, under Marketplaces.

If you used `install-skill` before, remove the copied skill
(`rm -r ~/.claude/skills/thread-handoff`) and run
`agent-thread-tools install-skill --agent claude --no-auto-handoff`, so the skill and
hooks aren't installed twice. Cloud sessions started on claude.ai/code don't load
plugins.

## Automatic handoff

```bash
agent-thread-tools install-skill --agent claude --auto-handoff --at 250k
```

Without the plugin, this adds two hooks to `~/.claude/settings.json`, next to any hooks you already
have (a backup is saved as `settings.json.agent-thread-tools.bak`):

- `Stop` runs `agent-thread-tools hook claude-stop --at 250k` after each turn. It
  reads the context size of the latest reply from the end of the session file
  (Claude Code writes a reply to the file just after the hook runs, so this is the
  size as of the previous reply). While background tasks are still running, it
  waits and asks after they finish, so the handoff records the finished result. The
  first time a finished turn is past the threshold, it asks Claude to run
  `/thread-handoff` and to tell you to run `/clear`. It asks once per session
  (recorded in `~/.claude/thread-tools/auto-handoff/`), never interrupts a turn that
  is still working, and never repeats itself in a loop.
- `PreCompact` runs `agent-thread-tools hook claude-precompact` before any
  compaction. If the project has a `.reference/` folder, it saves a redacted draft
  handoff there first.

`--at` takes a token count (`150k`, `150000`, `1m`) or a share of the context window
(`60%`). Remove the hooks with `--no-auto-handoff`, or skip them for one session by
starting Claude Code with `AGENT_THREAD_AUTO_HANDOFF=off`. Sessions started after
the change pick up the hooks; restart a running session to use them.

The hooks run where the session runs. There have been reports of Claude Code hooks
not firing in the desktop app, so check that it works there before relying on it.

## Archive and recovery

Old sessions can move to external storage with `session-archive --agent claude`.
Each session's folder (subagents, tool results, workflows) travels with it, the
project's `memory/` folder is never touched, and sessions open in Claude Code are
skipped. See [Session archive](session-archive.md#claude-code-sessions).

`recover` reads Claude Code sessions too. `diagnose` also reports tool calls
without results and API errors about images, and `strip-images` removes images
that Claude Code cannot process. See [Recovery](recovery.md).

Commands that write refuse to touch a session that is open in Claude Code. The
tool reads the open sessions from `~/.claude/sessions/`, where Claude Code
records each running session.
