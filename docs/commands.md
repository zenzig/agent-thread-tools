# Commands

Every command is `agent-thread-tools <command>`; the plugin runs the same tools
from inside Claude Code.

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
