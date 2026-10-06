# Compaction

Claude Code and Codex both compact long conversations so a session can keep
going when its context fills up. That is useful, but it does not mean a single
session should be treated as the only place your project memory lives.

## Claude Code

Claude Code compacts automatically when the context window is nearly full, and
when you run `/compact`. It replaces the earlier conversation with a summary the
model writes, then continues. The session file keeps the full history; compaction
adds records to it rather than removing any.

Each compaction writes two records to the session JSONL:

- a `system` record with `"subtype": "compact_boundary"`, whose
  `compactMetadata` records what triggered it (for example `auto`, or `manual`
  for `/compact`) and the token
  counts before and after (`preTokens`, `postTokens`)
- a `user` record with `"isCompactSummary": true` that holds the summary text

Health counts the summary as an installed compaction and the boundary as a
compaction event. A `preTokens` value above 200,000 tells health that the
session uses a 1,000,000-token context window.

The summary is plain text inside the session file. You rarely see it, it is not
reviewed, and after several compactions it summarizes earlier summaries. It also
stays inside that one session: `/clear` or a new session starts without it.

## Codex

Codex can keep long conversations alive with several compaction systems.

| Path | What it means |
| --- | --- |
| Local compaction | Codex creates a smaller replacement history locally and persists it into the session JSONL. |
| Remote compaction | Codex asks the remote compaction system to produce a smaller context window. |
| Remote compaction v2 / standalone compaction | A newer flow carries forward state with an opaque compaction output item from `/responses/compact`. |
| Server-side compaction | The Responses API can compact during normal response generation when configured with `context_management` and `compact_threshold`. |

In a local Codex session file, the strongest sign that compaction succeeded is a
JSONL record like:

```json
{
  "type": "compacted",
  "payload": {
    "replacement_history": []
  }
}
```

The important part is `payload.replacement_history`. That is the replacement
history Codex can use when rebuilding the live conversation. A `compacted`
record without a valid `replacement_history` is weaker and may be legacy or
malformed.

Remote compaction has a lifecycle:

1. A compaction request starts.
2. The request completes or fails.
3. The compacted result is installed as the live replacement history.

Step 2 by itself is not enough. A request can complete without becoming the
actual live conversation state. The important boundary is when the replacement
history is installed.

Server-side and standalone compaction can emit opaque encrypted compaction
items. Those items carry prior state forward with fewer tokens, but they are
intentionally not human-readable. They help Codex, but they are not durable
project notes for you.

## What Compaction Does Not Solve

Compaction reduces the context the model needs to see on later turns. It does
not solve every session failure mode, for either agent.

A session can still become unhealthy because:

- the session JSONL keeps growing on disk
- response and item counts can still approach API or app limits
- the summary or opaque compaction state preserves model-facing context without
  producing reviewed, human-readable project notes
- repeated compactions summarize earlier summaries, so early decisions blur
- failed compaction can leave a session unable to continue cleanly
- Codex only: legacy or malformed compacted records may not reconstruct well
- the agent may still struggle to load a very large session file

That is why this repo uses health checks, handoffs, and archive tools together.
A handoff written at a point you choose, then loaded into a fresh session, carries
the project forward in a form you can read and correct.

## Compaction compared with a handoff

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
