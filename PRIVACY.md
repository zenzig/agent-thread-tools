# Privacy

agent-thread-tools runs on your machine. It has no server and collects no telemetry,
analytics, or usage data. Its author receives nothing from it.

## What it reads and writes

It reads Claude Code and Codex session files on your machine
(`~/.claude/projects`, `~/.codex/sessions`) to measure their size and to draft
handoffs. It writes handoffs and screenshots you choose to keep into your project's
`.reference/` folder, a local git repository it never pushes, and small state files
under `~/.claude/thread-tools/` and `~/.codex/thread-tools/`. [What runs, reads, and sends](#what-runs-reads-and-sends)
lists every file and when it is written.

## Data sent to third parties

None by default. If you store an OpenRouter API key (`agent-thread-tools jev-key set`)
or set `OPENROUTER_API_KEY`, the tools send short, redacted excerpts of your sessions
to OpenRouter's decision endpoint (`https://openrouter.ai/api/alpha/decisions`), where
TypeSafe's Jev model answers yes/no questions about them. [What runs, reads, and sends](#what-runs-reads-and-sends) lists
exactly which excerpts. Keys, tokens, and similar secrets are redacted before sending. That
data is handled under [OpenRouter's privacy policy](https://openrouter.ai/privacy) and
billed to your OpenRouter account.

To stop it, run `agent-thread-tools jev-key remove` or set `AGENT_THREAD_JEV=off`.

`health remote` connects over SSH to a host you name; only a privacy-filtered health
report comes back.

## Your key

Your OpenRouter key is stored in `~/.config/agent-thread-tools/openrouter-key`,
readable only by your account, and is sent only to OpenRouter.

## Contact

Report a problem at https://github.com/zenzig/agent-thread-tools/issues. For a
security issue, follow [SECURITY.md](SECURITY.md).

## What runs, reads, and sends

Everything runs on your machine, from readable Python and JavaScript in this
repository. There is no telemetry, and nothing leaves the machine unless you turn on
Jev.

| Part | When it runs | What it reads | What it writes |
| --- | --- | --- | --- |
| `Stop` hook | After each Claude Code turn (plugin, or `install-skill --auto-handoff`) | The end of the current session's transcript, for its context size | `~/.claude/thread-tools/auto-handoff/`: one state file per session and a decisions log |
| `PreCompact` hook | Before a compaction | The session's transcript | A redacted draft handoff in the project's `.reference/handoffs/`, only if that folder exists |
| Handoff skill | When you or the hook run it | The session's transcript and the project's git state | The handoff, `CLAUDE.md`, `CLAUDE.local.md`, `.reference/` (a local git repository, never pushed), the project's `.git/info/exclude`, and a handoff marker in `~/.claude/thread-tools/` or `~/.codex/thread-tools/` |
| Health skill and `health` | When you run them | Session files under `~/.claude/projects` or `~/.codex/sessions` | Nothing |

**Jev (optional, off without a key).** Only when you've stored an OpenRouter key
(`agent-thread-tools jev-key set`) or set `OPENROUTER_API_KEY` do the tools send text to
OpenRouter's decision endpoint, `https://openrouter.ai/api/alpha/decisions`, using that
key. Secrets such as keys and tokens are redacted first. What is sent:

- **Hand-off timing** (`Stop` hook, past the threshold): the last 3,000 characters of
  Claude's latest reply.
- **Handoff audit** (handoff skill): the handoff, plus each of your prompts and
  Claude's messages from the session, and the open items of the previous handoff, up to
  1,500 characters each.
- **Draft summary** (`handoff-summary`, `PreCompact` hook): the session's messages, up
  to 500 characters each.
- **Context corrections** (`health savings`): your prompts in sessions after a
  handoff, up to 1,500 characters each.

OpenRouter's [privacy policy](https://openrouter.ai/privacy) covers that data. Remove
the key with `agent-thread-tools jev-key remove`, or set `AGENT_THREAD_JEV=off`. The
only other network use is `health remote`, which runs over SSH to a host you name.
