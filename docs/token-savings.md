# Token Savings and Usage Limits

Every request resends the whole conversation, so a long session spends most of its
tokens re-reading its own history, and all of it counts against your plan's session and
weekly usage limits. Automatic handoff keeps each session in the low, cheap part of
that curve:

![Two lines show the context sent with each request over a working day. Without handoff, it climbs steadily until compaction. With automatic handoff, each session drops back to a small size whenever it reaches the threshold, and the shaded gap between the lines is the tokens no longer resent.](../assets/usage-limits.svg)

In the author's own work, with every Claude Code project on one machine running
automatic handoff, long sessions used roughly 30–40% fewer tokens, leaving that much
more room under the plan's limits. Jev's audits of the handoffs and the corrections
counted in the sessions that followed showed no measurable drop in quality. Your
savings depend on how long your sessions run; `health savings` measures them on your
machine.

## How savings are measured

`agent-thread-tools health savings --agent claude` (or `/agent-thread-tools:thread-health`
in a session) estimates what each recorded handoff saved. For every request in the
session after a handoff, it compares the context actually sent with what the old
session would have sent, carrying its final size forward until it would have
compacted, and subtracts the handoff's own cost. It reports raw tokens and a
cost-weighted figure in which cached input counts for less than fresh input. With an
OpenRouter key it also counts prompts after each handoff that correct something the
session should have known. [Thread health](health.md#handoff-savings) has the details.

## How the threshold is chosen

The default threshold, `auto`, is 300k tokens on a 1M-context model and half the
window on a smaller one (100k of 200k), well before Claude Code would compact. Set
`AGENT_THREAD_AUTO_HANDOFF_AT` to change it; [Claude Code](claude-code.md#automatic-handoff)
covers the hooks.
