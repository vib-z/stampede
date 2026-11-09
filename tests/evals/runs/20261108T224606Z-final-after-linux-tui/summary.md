# Eval run 20261108T224606Z-final-after-linux-tui

Backend tui-live; Ubuntu 24.04.5 LTS aarch64; Python 3.12.3; commit a52be0972c8a; 89 s.

Product 0a1d6bef90cc, harness e6f1f21ee23a, dataset f3363bc3ac63; 10 cases selected.

Tools: herdr herdr 0.9.5, hc hc 0.1.19, moshi-hook moshi-hook version 0.4.50, jq jq-1.7, git git version 2.43.0, bash GNU bash, version 5.2.21(1)-release (aarch64-unknown-linux-gnu), python3 Python 3.12.3, claude 2.1.300 (Claude Code), codex codex-cli 0.100.0, flock flock from util-linux 2.39.3, ps ps from procps-ng 4.0.4.

| status | count |
|---|---|
| pass | 10 |
| fail | 0 |
| error | 0 |
| blocked | 0 |
| skip | 0 |
| gap | 0 |

| case | status | expected | actual |
|---|---|---|---|
| T01 | pass | stampede new on a real herdr server makes the workspace, tags it, starts the lead (a stand-in agent) with its hooks and delivers the brief pointer. | exit 0 and lead printed ok; owner tag set ok; Herdr shows the lead as claude, idle ok; hooks settings written ok; brief pointer in the inbox ok; the stand-in woke through its FileChanged hook ok; owne |
| T02 | pass | stampede start puts a stand-in worker in a new pane, named, with its brief pointer delivered, and agents.tsv and REOPEN.md record it. | start build-claude exit 0, DELIVERED ok; start build-codex exit 0, SUBMITTED ok; Herdr lists both, named, right kinds ok; in their panes ok; agents.tsv records all three ok; REOPEN.md names both worke |
| T03 | pass | stampede tell reaches the worker; the worker's reply (a tell to the lead) lands in the lead's inbox. | tell build-codex SUBMITTED (herdr-send) ok; its echo in the lead inbox ok; tell build-claude DELIVERED (inbox file) ok; the lead woke on both echoes ok |
| T04 | pass | The worker's report with Status: DONE gives one REPORT line in inbox.log. | exactly one REPORT line ok; report says Status: DONE ok; the Stop hook ran at least twice (two turns), one line ok; the Codex notify gave a TURN line ok |
| T10 | pass | A stand-in that shows Codex's prompt screen in a real pane is reported by Herdr as codex, idle at its prompt and working while it prints; stampede tell reaches it through herdr-send. Proves Herdr's de | reported as codex ok; idle or done at its prompt before ok; herdr-send SUBMITTED ok; working observed during the turn ok; idle or done again after ok; the prompt reached it (echo) ok |
| T05 | pass | ask --gate queues the gate for the bot; approve-gate from inside a pane is refused; approve-gate from outside Herdr then gate-ok passes; gate-ok at another commit is refused. | ask --gate printed GATE ok; the bot route received the gate event ok; gate-ok refused before any yes ok; approve-gate inside a pane refused, nothing recorded ok; approve-gate outside Herdr APPROVED ok |
| T06 | pass | After the workspace is closed, reopen.sh recreates it with each agent in its pane, refuses while it is open, and the job carries on. | refused while open (exit 2) ok; agents gone after the close ok; reopen.sh exit 0, REOPENED ok; all three agents back, settled ok; each in a pane of the new workspace ok; the job carries on (tell, echo |
| T07 | pass | After herdr server stop and start in the scratch home, the job's record and reopen.sh still bring it back. | server stopped ok; server running again ok; reopen.sh exit 0, REOPENED ok; all three agents back, settled ok; the job carries on (tell, echo, lead woke) ok |
| T08 | pass | finish queues one done event; the flusher delivers it once to a local stand-in route; a second finish adds nothing. | first finish FINISHED ok; one done event reached the route ok; second finish FINISHED, no new event ok; queue empty (flushed) ok; marker gone ok; finished stamp written ok |
| T09 | pass | Two checks: in a pane with no open job, a stand-in going working then idle makes Herdr's plugin event post one event to the relay queue; in an open job's pane the same turn end stays on the machine (j | turn ends in the open job were job-skipped by the relay ok; no plain turn end from a reopened workspace reached the bot while the job was open ok; after finish, the plugin event reached the route ok;  |
