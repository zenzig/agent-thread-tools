---
name: thread-health
description: Check this Claude Code session's health with agent-thread-tools - context size, distance to the next automatic handoff, compactions - plus what this project's handoffs have saved. Use when the user asks about session health, context size, when the next handoff is due, or how much handoffs have saved.
---

# Thread Health (Claude Code)

Report on this session and this project. Run the tools that ship with this skill:
`python3 "${CLAUDE_PLUGIN_ROOT}/tools/agent-thread-<command>.py" <arguments>`. If that
file does not exist, use the installed `agent-thread-tools <command>` instead.

1. Find this session's file: `ls ~/.claude/projects/*/${CLAUDE_SESSION_ID}.jsonl`.
2. Session health: `python3 "${CLAUDE_PLUGIN_ROOT}/tools/agent-thread-health.py" check <session-file>`.
   Exit `2` is WARN and `3` is DANGER; both are results, not failures.
3. Context and the next handoff: quote the `Context:` line from step 2 exactly; do not
   recompute it. The auto-handoff threshold is `echo "${AGENT_THREAD_AUTO_HANDOFF_AT:-250k}"`;
   with an OpenRouter key the handoff comes at the first natural break past it, and at
   1.5 times it regardless.
4. Savings: `python3 "${CLAUDE_PLUGIN_ROOT}/tools/agent-thread-health.py" savings --agent claude --project "$(pwd)"`.

Reply in a few lines, not raw output: the session's status and why, its context
(for example "142k of 1M; next handoff after 300k"), compactions if any, and the
project's net tokens saved, handoff count, and possible corrections. Mention a
WARN or DANGER reason in plain words. Do not run a handoff unless the user asks.
