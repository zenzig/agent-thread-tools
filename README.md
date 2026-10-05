<div align="center">

![Clockwork robots pull tangled threads from several coding-agent sessions into one braided cord that runs through a gauge, a filing cabinet, a bridge, and a crane onto a spool](assets/agent-thread-tools-header.png)

# agent-thread-tools

**Keep one project going across many Claude Code and OpenAI Codex sessions, without replaying old transcripts.**

Health checks · Handoffs · Automatic handoff · Token savings · Reference archive · Remote health · Recovery

<a href="#-quick-start-claude-code"><img src="https://img.shields.io/badge/Quick_start-3_commands-2F81F7?style=for-the-badge" alt="Quick start"></a>
<a href="#-why-not-just-let-claude-code-compact"><img src="https://img.shields.io/badge/Why-not_just_compact%3F-D97757?style=for-the-badge" alt="Why not just compact?"></a>
<a href="docs/README.md"><img src="https://img.shields.io/badge/Docs-project_guides-8250DF?style=for-the-badge" alt="Documentation"></a>

<img src="https://img.shields.io/badge/Claude_Code-first--class-D97757?style=flat-square&logo=claude&logoColor=white" alt="Claude Code: first-class">
<img src="https://img.shields.io/badge/OpenAI_Codex-supported-24292F?style=flat-square" alt="OpenAI Codex: supported">
<a href="https://www.npmjs.com/package/agent-thread-tools"><img src="https://img.shields.io/npm/v/agent-thread-tools.svg?style=flat-square&color=CB3837&logo=npm" alt="npm version"></a>
<a href="https://www.npmjs.com/package/agent-thread-tools"><img src="https://img.shields.io/npm/dm/agent-thread-tools.svg?style=flat-square" alt="npm downloads"></a>
<img src="https://img.shields.io/badge/node-%E2%89%A518-5FA04E?style=flat-square&logo=nodedotjs&logoColor=white" alt="Node 18 or newer">
<img src="https://img.shields.io/badge/python-3-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3">
<a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-yellow?style=flat-square" alt="License: MIT"></a>

</div>

> [!NOTE]
> **Formerly `codex-thread-tools`.** Version 2.0.0 added support for Claude Code and
> renamed the package. The old `codex-thread-tools` commands still work. To switch: `npm uninstall -g codex-thread-tools && npm install -g agent-thread-tools`.

agent-thread-tools checks how healthy your coding-agent sessions are and tells you when
a session should end. It then turns what the session learned into a short handoff file
that the next session loads automatically.

## 🧵 What's in the box

<table>
  <tr>
    <td align="center" width="33%">🩺<br><strong>Health checks</strong><br><sub>Scores every session's size, compactions, context use, and screenshots, then says continue, monitor, or hand off.</sub></td>
    <td align="center" width="33%">🌉<br><strong>Handoffs</strong><br><sub>The <code>thread-handoff</code> skill writes a short, reviewed brief that the next session loads on its own.</sub></td>
    <td align="center" width="33%">⏱️<br><strong>Automatic handoff</strong><br><sub>A plugin hook starts the handoff once a session passes 250k tokens, before compaction does.</sub></td>
  </tr>
  <tr>
    <td align="center" width="33%">💰<br><strong>Token savings</strong><br><sub><code>health savings</code> estimates the tokens each handoff saved, and the <code>thread-health</code> skill shows it in chat.</sub></td>
    <td align="center" width="33%">⚖️<br><strong>Jev checks</strong><br><sub>Optional: Jev picks a natural break for the handoff and lists anything it left out, for a fraction of a cent.</sub></td>
    <td align="center" width="33%">🗂️<br><strong>Reference archive</strong><br><sub>Handoffs, specs, and screenshots live in <code>.reference/</code>, a local git repository that is never pushed.</sub></td>
  </tr>
  <tr>
    <td align="center" width="33%">🖼️<br><strong>Screenshot archive</strong><br><sub>Copies the screenshots that still matter out of a session and verifies the copies.</sub></td>
    <td align="center" width="33%">🛰️<br><strong>Remote health</strong><br><sub>Checks sessions on another machine over SSH. Only a privacy-filtered report comes back.</sub></td>
    <td align="center" width="33%">🛟<br><strong>Recovery</strong><br><sub>Diagnoses a damaged session, strips images Claude Code cannot process, and builds a redacted recovery bundle.</sub></td>
  </tr>
</table>

## 🤔 Why not just let Claude Code compact?

Compaction keeps a session running when its context fills up. It does not carry the
project forward.

| | 🗜️ Compaction alone | 🌉 With a handoff |
| --- | --- | --- |
| **When** | ⚠️ When the context window is nearly full, often mid-task | ✅ Automatically at a threshold you set, at a natural break, or whenever you choose |
| **Token cost** | ⚠️ Every request resends the whole long conversation until it compacts | ✅ Later requests start from a small, fresh session; `health savings` shows the difference |
| **What is kept** | ⚠️ A summary the model writes for itself, usually unread | ✅ A handoff file you can read, edit, and correct |
| **After several rounds** | ⚠️ Summaries of summaries; early decisions blur | ✅ Each handoff is dated and committed, so earlier states stay readable |
| **Next session** | ⚠️ `/clear` or a new terminal starts with only `CLAUDE.md` and auto memory | ✅ Every new session also loads the latest handoff, through `CLAUDE.local.md` |
| **Screenshots** | ⚠️ Not carried into the summary | ✅ The ones that matter are copied to `.reference/` with a manifest |
| **Session file** | ⚠️ Keeps growing on disk | ✅ Health reports its size, compactions, and context use for every project |
| **Other agents** | ⚠️ The summary exists only inside that Claude session | ✅ The handoff is plain Markdown that Codex or any model can read |

> [!TIP]
> Use compaction to finish the task in front of you. Use a handoff when a piece of work
> ends, so the next session starts from a short, checked brief instead of a compressed
> transcript.

## 🚀 Quick start (Claude Code)

**As a Claude Code plugin** (needs Python 3). In any Claude Code session:

```text
/plugin marketplace add zenzig/agent-thread-tools
/plugin install agent-thread-tools@agent-thread-tools
```

That adds two skills, `/agent-thread-tools:thread-handoff` (write a handoff now) and
`/agent-thread-tools:thread-health` (this session's size, distance to the next handoff, and tokens
saved so far), and turns on [automatic handoff](#automatic-handoff).
Restart any session that was already open to load them. To use it in every project, install with
`claude plugin install agent-thread-tools@agent-thread-tools --scope user`.

**As a command-line tool** (needs Node.js 18+ and Python 3) for health reports,
archives, and recovery:

```bash
npm install -g agent-thread-tools
agent-thread-tools install-skill --agent claude   # adds /thread-handoff and /thread-health
agent-thread-tools health --agent claude          # checks every Claude Code project
```

Setting up from the desktop or mobile app? Ask Claude instead: *"Install
agent-thread-tools with `npm install -g agent-thread-tools`, then run
`agent-thread-tools install-skill --agent claude`."* Claude runs those commands on the
machine where the session runs.

The skills' names depend on how you installed them; the rest of this README uses the
plugin names:

| Installed with | Write a handoff | Check this session |
| --- | --- | --- |
| The plugin | `/agent-thread-tools:thread-handoff` | `/agent-thread-tools:thread-health` |
| `install-skill` | `/thread-handoff` | `/thread-health` |

In the slash-command menu, typing `/thread` lists both either way.

Then, whenever health says `WARN` or `DANGER`, or a piece of work is done:

<table>
  <tr>
    <td align="center" width="25%">🩺<br><strong>1. Check</strong><br><sub><code>health --agent claude</code> shows which sessions are at risk.</sub></td>
    <td align="center" width="25%">🌉<br><strong>2. Hand off</strong><br><sub>Run <code>/agent-thread-tools:thread-handoff</code> in that Claude Code session.</sub></td>
    <td align="center" width="25%">✍️<br><strong>3. Review</strong><br><sub>Read the handoff it wrote and correct anything wrong.</sub></td>
    <td align="center" width="25%">🧹<br><strong>4. Start fresh</strong><br><sub>Run <code>/clear</code>. The new session starts with the handoff loaded.</sub></td>
  </tr>
</table>

Pass `--agent claude` whenever `~/.codex/sessions` also exists on the machine; without
it, the tools read Codex sessions.

### Where it works

Run the commands yourself in any terminal, or stay inside Claude Code: type
`/agent-thread-tools:thread-handoff` or `/agent-thread-tools:thread-health`, or ask Claude to run a
command for you. That works in every Claude Code app, as long as the session runs on
a machine where the plugin or the skills are installed:

<table>
  <tr>
    <td align="center" width="25%">🖥️<br><strong>Terminal</strong><br><sub>The <code>claude</code> CLI.</sub></td>
    <td align="center" width="25%">🧩<br><strong>IDE</strong><br><sub>VS Code and JetBrains extensions.</sub></td>
    <td align="center" width="25%">💻<br><strong>Desktop app</strong><br><sub>Mac and Windows.</sub></td>
    <td align="center" width="25%">📱<br><strong>Mobile and web</strong><br><sub>Through Remote Control of a session on your machine.</sub></td>
  </tr>
</table>

![The Claude mobile app's slash-command menu, with /thread-handoff listed first](assets/thread-handoff-mobile.png)

*`/thread-handoff` (installed with `install-skill`) in the Claude mobile app, controlling
a session on a server through Remote Control.*

Cloud sessions started from claude.ai/code or the mobile app without Remote Control
run on Anthropic's machines, where the tool is not installed.

### Automatic handoff

After each turn, a hook checks the session's context size. Once it passes the
threshold (default `250k` tokens, or a share such as `60%`), Claude runs the
thread-handoff skill and tells you it's saved; you run `/clear` and continue in a small,
fresh session. It asks once per session, updates the handoff once more if you keep going, and
waits while background tasks run. This
saves tokens because every request resends the whole conversation, so rotating early
keeps every later request small. A second hook saves a redacted draft to
`.reference/handoffs/` before any compaction. See what your handoffs saved with
`/agent-thread-tools:thread-health` or `agent-thread-tools health savings --agent claude`.

**Optional: Jev.** With an OpenRouter key, [Jev](docs/claude-code.md#jev-optional),
a fast decision model, makes three checks for a fraction of a cent each: it waits past
the threshold for a natural break (work finished, nothing running; at 1.5 times the
threshold it hands off regardless), audits the finished handoff for anything a fresh
session would need, including open items from the previous handoff, and ranks what
the draft summary keeps. Set the key in a terminal,
not in chat:

```bash
agent-thread-tools jev-key set      # hidden prompt; checks the key, saves it readable only by you
agent-thread-tools jev-key status   # shows it masked: sk-or-v1…ac36
```

The plugin turns this on; set its threshold with `AGENT_THREAD_AUTO_HANDOFF_AT`.
Without the plugin, run `agent-thread-tools install-skill --agent claude
--auto-handoff --at 250k` (and `--no-auto-handoff` to remove it). Use one or the
other, not both. `AGENT_THREAD_AUTO_HANDOFF=off` skips it for a session. Hooks may not
fire in the desktop app (a reported Claude Code issue), so check before relying on it.

### Stretching your plan's usage limits

Every request resends the whole conversation, so a long session spends most of its
tokens re-reading its own history, and all of it counts against your plan's session and
weekly usage limits. Automatic handoff keeps each session in the low, cheap part of
that curve:

![Two lines show the context sent with each request over a working day. Without handoff, it climbs steadily until compaction. With automatic handoff, each session drops back to a small size whenever it reaches the threshold, and the shaded gap between the lines is the tokens no longer resent.](assets/usage-limits.svg)

In the author's own work, with every Claude Code project on one machine running
automatic handoff, long sessions used roughly 30–40% fewer tokens, leaving that much
more room under the plan's limits. Jev's audits of the handoffs and the corrections
counted in the sessions that followed showed no measurable drop in quality. Your
savings depend on how long your sessions run; `health savings` measures them on your
machine.

## 📦 What a handoff leaves behind

```text
your-project/
├── CLAUDE.md                 stable facts: architecture, conventions, commands
├── CLAUDE.local.md           points to the latest handoff; loaded every session
└── .reference/               local git repository, never pushed
    ├── INDEX.md              one line per saved document or screenshot set
    ├── handoffs/             one dated handoff per session, e.g. 2026-09-24-login-flow.md
    ├── docs/                 long pasted specs worth keeping
    └── visual-artifacts/<project>/<set>/   archived screenshots and their manifest
```

A handoff records the goal and next action, the current state, the decisions made and
why, the files involved, what was tested, and the open risks. `.reference/` and
`CLAUDE.local.md` are listed in the project's `.git/info/exclude`, so your project
repository ignores them and no tracked file changes.

## 🔐 What it runs, reads, and sends

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
See [PRIVACY.md](PRIVACY.md).

## 🚦 Reading the health report

| Status | Action | What to do |
| :---: | --- | --- |
| ![OK](https://img.shields.io/badge/OK-2DA44E?style=flat-square) | **Continue** | Nothing. The session is healthy. |
| ![WARN](https://img.shields.io/badge/WARN-D4A72C?style=flat-square) | **Monitor** | Risk is rising, for example context use above 70%. Plan a handoff at the next break. |
| ![DANGER](https://img.shields.io/badge/DANGER-CF222E?style=flat-square) | **Handoff now** | Finish the current turn, then hand off. |

Health looks at session file size, item count, compactions, context use, and screenshots
that could break a reload. Exit codes are `0` (OK), `2` (WARN), and `3` (DANGER), so
scripts can act on them. Add `--json` for machine-readable output.

```bash
agent-thread-tools health --agent claude --mode standard
agent-thread-tools health check ~/.claude/projects/<project>/<session>.jsonl
```

## 🧰 Commands

| Command | What it does | Claude Code | Codex |
| --- | --- | :---: | :---: |
| 🩺 `health` | Reports session health for all projects or for one session file | ✅ | ✅ |
| 💰 `health savings` | Estimates the tokens each handoff saved, net of its own cost | ✅ | ✅ |
| 🧩 `install-skill` | Installs the skills (`--agent claude` or `codex`); `--auto-handoff` adds the hooks without the plugin | ✅ | ✅ |
| 📝 `handoff-summary` | Drafts a redacted summary of a session to help write a handoff | ✅ | ✅ |
| 🔍 `handoff-audit` | Lists what a session said that its handoff leaves out (Jev) | ✅ | ✅ |
| 🔑 `jev-key` | Stores, checks, or removes the OpenRouter key for Jev, never showing it | ✅ | ✅ |
| 🪝 `hook` | The automatic-handoff hooks the plugin runs | ✅ | — |
| 🗂️ `reference init` / `commit` | Creates and commits the local-only `.reference/` repository | ✅ | ✅ |
| 🖼️ `visual-archive` | Copies screenshots and videos out of a session and verifies the copies | ✅ | ✅ |
| 🔖 `handoff-marker` | Records which session a handoff came from | ✅ | ✅ |
| 🧊 `session-archive` | Moves old session files into staged, verified archives, with a recovery quarantine before pruning | ✅ | ✅ |
| 🛟 `recover` | Diagnoses a damaged session, repairs it, or builds a redacted recovery bundle | ✅ | ✅ |

> [!IMPORTANT]
> Health checks and summaries only read session files. Commands that copy or delete
> files run only when you name that subcommand, verify what they copied, and need an
> extra confirmation flag before deleting local session files.

## 🤖 Codex

Install the Codex skill and check Codex sessions (`~/.codex/sessions`):

```bash
agent-thread-tools install-skill
agent-thread-tools health
```

To hand off, ask Codex in the thread:

```text
Use the installed `codex-thread-handoff` skill to create a repository-backed
handoff for a new task. Do not use Codex's native Handoff or `handoff_thread`.
If the skill is unavailable, stop and report that it must be installed.
```

📖 Background on why Codex sessions get too big to open: [The Thread That Ate Itself](https://medium.com/@atomicfalls/the-thread-that-ate-itself-what-happens-when-your-codex-session-gets-too-big-to-open-5ee559f263f3).

## 🛰️ Remote health

Check the sessions on another machine over SSH. Install the package on both machines,
then run:

```bash
agent-thread-tools health remote --host user@example-host --project /srv/project
```

The analysis runs on the remote host, and only a privacy-filtered report comes back: no
transcript text, tool output, or images cross SSH. If the command isn't found over a
non-interactive SSH session, it retries through your login shell, which covers NVM
installs. Add `--agent claude` or `--agent codex` to choose which sessions it reads.

## 📚 Documentation

Start at [Documentation](docs/README.md), or go straight to a guide:

| | Guide | Covers |
| :---: | --- | --- |
| 🟠 | [Claude Code](docs/claude-code.md) | The plugin, automatic handoff, Jev and its key, and what health measures |
| 📥 | [Installation](docs/installation.md) | `npx`, global npm, source checkout, and skill installation |
| 🩺 | [Thread health](docs/health.md) | Report modes, risk domains, remote reports, exit codes |
| 🌉 | [Handoff workflow](docs/handoff.md) | The Codex handoff skill, summaries, and markers |
| 🖼️ | [Visual archive](docs/visual-archive.md) | Keeping screenshots and videos outside session history |
| 🧊 | [Session archive](docs/session-archive.md) | Verified cold storage and pruning for old sessions |
| 🛟 | [Recovery](docs/recovery.md) | Diagnosis, repairs, and recovery bundles for damaged sessions |
| 🗜️ | [Compaction](docs/compaction.md) | How compaction differs from handoffs and archives |

## 📋 Project

<table>
  <tr><td>🏷️ <strong>Version</strong></td><td><code>2.1.0</code> · <a href="CHANGELOG.md">Changelog</a></td></tr>
  <tr><td>🐛 <strong>Issues</strong></td><td><a href="https://github.com/zenzig/agent-thread-tools/issues">Report a bug or request a feature</a></td></tr>
  <tr><td>🔒 <strong>Security</strong></td><td>Read the <a href="SECURITY.md">security policy</a> before reporting a vulnerability</td></tr>
  <tr><td>🛠️ <strong>Development</strong></td><td>See the <a href="docs/development.md">development guide</a> for tests and package checks</td></tr>
  <tr><td>⚖️ <strong>License</strong></td><td><a href="LICENSE">MIT</a></td></tr>
</table>
