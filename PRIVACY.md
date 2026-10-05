# Privacy

agent-thread-tools runs on your machine. It has no server and collects no telemetry,
analytics, or usage data. Its author receives nothing from it.

## What it reads and writes

It reads Claude Code and Codex session files on your machine
(`~/.claude/projects`, `~/.codex/sessions`) to measure their size and to draft
handoffs. It writes handoffs and screenshots you choose to keep into your project's
`.reference/` folder, a local git repository it never pushes, and small state files
under `~/.claude/thread-tools/` and `~/.codex/thread-tools/`. The
[README](README.md#-what-it-runs-reads-and-sends) lists every file and when it is
written.

## Data sent to third parties

None by default. If you store an OpenRouter API key (`agent-thread-tools jev-key set`)
or set `OPENROUTER_API_KEY`, the tools send short, redacted excerpts of your sessions
to OpenRouter's decision endpoint (`https://openrouter.ai/api/alpha/decisions`), where
TypeSafe's Jev model answers yes/no questions about them. The README lists exactly
which excerpts. Keys, tokens, and similar secrets are redacted before sending. That
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
