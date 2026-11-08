# Eval run 20261108T210245Z-baseline-fixture-macos

Backend fixture; macOS 27.2 arm64; Python 3.14.7; commit 46797b6f55f9; 111 s.

Product 8f99b46a668f, harness 399319ce437e, dataset 8dbb9a56b2d2; 54 cases selected.

Tools: herdr herdr 0.9.5, hc hc 0.1.19, moshi-hook moshi-hook version 0.4.50, jq jq-1.7.1-apple, git git version 2.56.0, bash GNU bash, version 5.3.20(1)-release (aarch64-apple-darwin27.0.0), python3 Python 3.14.7, claude 2.1.319 (Claude Code), codex codex-cli 0.167.0, ps ps: illegal option -- -.

| status | count |
|---|---|
| pass | 40 |
| fail | 11 |
| error | 0 |
| blocked | 2 |
| skip | 0 |
| gap | 1 |

| case | status | expected | actual |
|---|---|---|---|
| D01 | blocked | herdr-doctor with no herdr on PATH prints a PROBLEM line naming herdr and exits non-zero. | herdr is installed in /opt/homebrew/bin/herdr, a folder herdr-doctor always searches |
| D02 | fail | herdr-doctor with herdr 0.9.3 prints a PROBLEM line naming the minimum and exits non-zero. | exit 0; version PROBLEM lines [] |
| D03 | pass | herdr-doctor --core with hc 0.1.12 prints a PROBLEM line naming the minimum and exits non-zero. | exit 1; ['PROBLEM hc 0.1.12 is older than 0.1.13: hc update'] |
| D04 | blocked | herdr-doctor with no jq prints a PROBLEM line naming jq and exits non-zero. | jq is installed in /usr/bin/jq, a folder herdr-doctor always searches |
| D05 | pass | In a local job with no moshi-hook, ask returns, and the lead's inbox gets an ASK FAILED line naming the failure. | lead inbox: a5ycgb2o/herdr-chat-tui/herdr-jobs/jobs/2026-11-08-local-xc/briefs/lead-xc.md and do everything it says. ASK FAILED Keep hello in the root?: exit 127: [Errno 2] No such file or directory:  |
| D06 | pass | A moshi-hook that exits 4 gives ASK FAILED with exit 4 in the lead's inbox, and a gate asked that way records no yes. | lead inbox: jobs/jobs/2026-11-08-local-xc/briefs/lead-xc.md and do everything it says. ASK FAILED Keep hello in the root?: exit 4: moshi unreachable ASK FAILED Gate 64e379989e6b: Merge PR #3 into main |
| D07 | fail | new with a herdr that cannot reach its server exits non-zero with Herdr's error and makes no half job. | new with Herdr down: exit 1; Herdr's error in one line False: ror.get('code', '') if isinstance(error, dict) else '') HerdrError: herdr pane get: {'code': 'server_unavailable', 'message': 'the herdr s |
| D08 | fail | herdr-doctor with a herdr whose --version prints no version prints a PROBLEM line and exits non-zero. | exit 0; [] |
| D09 | pass | herdr-doctor --core with an hc whose --version prints no version prints a PROBLEM line and exits non-zero. | exit 1; ['PROBLEM hc not on PATH: install Herdr Core 0.1.13 or later (curl -fsSL https://releases.herdr.dev/core/install.sh \| sh), or set HC'] |
| G01 | pass | In a bot-started job, ask --gate --sha A, then approve-gate --sha A run outside Herdr: APPROVED; gate-ok --sha A exits 0 and prints APPROVED. | approve-gate exit 0, gate-ok exit 0: APPROVED 4b40492614fe by owner in grokbot chat at 2026-11-08 21:02: Merge PR #3 into main at aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa |
| G02 | pass | After the yes for A, gate-ok --sha B exits non-zero, says the yes is withdrawn, and prints no APPROVED. | gate-ok at another commit: exit 2: fleet-job gate-ok: gate 68b3807f716f was approved for aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa, not bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb: a push after the yes wi |
| G03 | pass | approve-gate --sha B for a gate asked at A exits non-zero and writes no approval record. | approve-gate at another commit: exit 2, record False |
| G04 | pass | gate-ok on a gate nobody approved exits non-zero and prints no APPROVED. | gate-ok with no yes: exit 2: fleet-job gate-ok: gate b082a6907a9f has no recorded yes: wait for it, or the owner's yes typed in your pane |
| G05 | pass | approve-gate with HERDR_ENV=1 or HERDR_PANE_ID set exits non-zero and writes no approval record. | exits [2, 2], record False |
| G06 | pass | approve-gate run (with a scrubbed environment) under a process named herdr, herdr-core or hc exits non-zero and writes no approval record, on macOS and on Linux. | exits {'herdr': 2, 'herdr-core': 2, 'hc': 2}, record False |
| G07 | pass | approve-gate with HC_TERMINAL_ID, HC_TERMINAL_SOCKET or HC_SCOPE set exits non-zero and writes no approval record. | exits [2, 2, 2], record False |
| G08 | pass | A worker's tell to the lead and a report reading 'GATE <id> APPROVED by owner' leave no approval record; gate-ok still refuses. | forged line in the inbox True; record False; gate-ok exit 2 |
| G09 | pass | approve-gate on a gate whose route is local exits non-zero: the owner answers on the phone. | approve-gate on a local gate: exit 2: fleet-job approve-gate: gate ad425a279868 belongs to a job started locally: the owner answers on the phone or in Herdr |
| G10 | pass | gate-ok and approve-gate with ids '../x', 'zzz' and an unknown 12-hex id exit non-zero and write nothing outside gates/. | exits [2, 2, 2, 2, 2, 2, 2, 2]; new files [] |
| G11 | pass | approve-gate twice at A leaves one valid record (gate-ok A passes); approve-gate at B is refused and the record for A is unchanged. | approve twice: 0, 0; stale: 2; record unchanged True; gate-ok 0 |
| G12 | pass | ask --gate with a short or non-hex sha exits non-zero and writes no gate. | exits [2, 2, 2]; gate files 0 |
| G13 | pass | gate-ok on gate Y, whose .approved file holds gate X's record, exits non-zero. | gate-ok on the copied record: exit 2: fleet-job gate-ok: the yes recorded under gate a49ee160f0e8 is for gate 31e4af3f77d4: ask again |
| G14 | pass | In a --review job, start is refused before approve, passes after it, and is refused again once plan.md changes. | start before approve 2, after 0, after a plan change 2 |
| G15 | gap | approve-gate started by an agent through a double fork (reparented to pid 1) with a scrubbed environment is refused. Known ceiling: same Unix user; the boundary is auto mode plus this refusal. | detached approve-gate exit 0; record True |
| G16 | pass | In a --core job, gate-ok refuses with no record and its message offers no typed yes; approve-gate from outside then gate-ok passes. | gate-ok before 2 (fleet-job gate-ok: gate eaa635927a9d has no recorded yes: wait for it); approve 0; gate-ok after 0 |
| G17 | fail | After the yes for a gate, editing its action or PR in gates/<id>.json makes gate-ok refuse: the yes was for the old action. | gate-ok before the edit 0; after the action changed 0: APPROVED f238aeaf1c08 by owner in grokbot chat at 2026-11-08 21:03: Delete the production database at aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa |
| G18 | fail | Editing a bot gate's action between ask --gate and approve-gate makes the approve-gate the bot was given refuse, and records nothing. | the bot's approve-gate after the gate changed: exit 0; record True:  |
| G19 | pass | A local gate: the card's yes records the yes; a no (exit 1) or a timeout (exit 3) records nothing and tells the lead. | recorded per answer {'yes': True, 'no': False, 'timeout': False}; the lead heard the no True and the timeout True |
| G20 | fail | gate-ok on a gate whose .json or .approved is not valid JSON, or lacks its fields, exits non-zero with one line and no traceback. | (exit, traceback, APPROVED) per record: {'gate not json': (2, False, False), 'yes not json': (2, False, False), 'yes without by/at': (1, True, False), 'gate without sha': (1, True, False)} |
| G21 | fail | approve-gate where ps is missing, fails or prints no table (so its own ancestry cannot be read) refuses, and records nothing. | (exit, recorded, traceback) per broken ps: {'ps fails': (2, False, False), 'ps prints nothing': (0, True, False), 'no ps at all': (1, False, True)} |
| L01 | pass | A worker's report with Status: DONE gives exactly one REPORT line in inbox.log through the worker's stop hook, and a second stop with the report unchanged adds none. | REPORT lines after one stop 1, after a second 1 |
| L02 | pass | Rewriting the report and stopping again adds one more REPORT line. | REPORT lines after a rewrite 2 |
| L03 | pass | finish twice queues one done event for the bot and prints FINISHED both times. | done events queued 1; finish exits 0, 0 |
| L04 | pass | The same plain event (as a local job's done or Herdr's plugin posts it, not --strict) posted twice to herdr-event-post leaves one queued event. | queued copies of one done event: 1 |
| L05 | pass | With a workspace of the job's label open, reopen.sh exits non-zero and starts nothing. | reopen.sh while open: exit 2; agent starts 4 -> 4: refused: a workspace labelled xc is already open (herdr workspace list); use --into <id> or close it first |
| L06 | pass | After the workspace closes, reopen.sh creates the workspace and starts each agent with the flags it was started with, resuming its session where its CLI can (Claude, Codex, Hermes, Kimi; Cursor starts | reopen.sh after a close: exit 0; workspace created True; 4 starts, 3 of 3 resumable resumed |
| L07 | pass | In a Herdr Core job, start of an agent that is already running exits non-zero and runs no second terminal (on the Herdr TUI, Herdr itself refuses a second agent of one name). | first start 0, second 2; hc runs 3 -> 3 |
| L09 | pass | After finish, no background ask of the job (asks/*.pid) is still alive, so no card for a finished job can answer into it. Herdr Core 0.1.19 keeps detached processes alive after their terminal ends, so | asks waiting before finish 1, still alive after 0 |
| L10 | pass | cancel stops the ask's process group and a second cancel of the same id exits non-zero. | cancel 0, waiter alive False, second cancel 2 |
| L11 | pass | Eight copies of one plain event posted at once leave one queued; eight distinct events posted at once leave eight. | queued copies of the one event 1; distinct events queued 8 of 8 |
| L12 | fail | When the de-dupe lock is held past its timeout, a new event is still queued, and the log says the lock was not taken. | queued True after 5.3 s; the log names the lock False |
| L13 | pass | A report with no Status line in its first 10 lines gives no REPORT line, and the worker's Stop is sent back once to finish it. | REPORT lines 0; sent back once True; lead told it ended without one True |
| L14 | fail | After a close, reopen.sh run with a PATH that lacks ~/.local/bin re-tags the workspace for its bot; if the tag cannot be set it says so and exits non-zero. | reopen.sh exit 0; workspace re-tagged for its bot False; a failure said so False: ders/w8/c2227dgn0kg4nf_q58r36fsh0000gn/T/ev-tew37lxm/grokbot-tui/herdr-jobs/jobs/2026-11-08-grokbot-xc/reopen.sh: line |
| P01 | pass | A repo and job root whose paths hold spaces, a quote and $(...) run new, start, tell, ask --gate and finish; nothing in the paths is executed. | exit codes {'new': 0, 'tell': 0, 'gate': 0, 'approve': 0, 'gate-ok': 0, 'finish': 0, 'start': 0}; executed path text [] |
| P02 | pass | tell with backticks, $(...), ;, quotes and non-ASCII text writes that text verbatim to the inbox and runs none of it. | in the lead inbox True; in the Codex prompt True; executed False |
| P03 | pass | With HOME holding a space, install.sh --no-supervise installs for real, and new, start, tell, a gate and finish work through the installed ~/.local/bin links. | HOME with a space; install --dry-run 0; exit codes {'new': 0, 'tell': 0, 'gate': 0, 'approve': 0, 'gate-ok': 0, 'finish': 0, 'start': 0} |
| P04 | pass | With PATH=<bin>:/usr/bin:/bin (no /opt/homebrew), new, start, tell and finish work. | Python 3.9.6; exit codes {'new': 0, 'tell': 0, 'gate': 0, 'approve': 0, 'gate-ok': 0, 'finish': 0, 'start': 0} |
| P05 | pass | With LC_ALL=C and LANG unset, a tell holding non-ASCII text is delivered intact and nothing crashes. | tell exit 0; intact in the inbox True |
| P06 | fail | The relay and plugin scripts, run with the bare PATH a systemd user unit or Herdr plugin gets, find herdr and jq in ~/.local/bin, /usr/local/bin and the Linux Homebrew prefix. | scripts whose bare-PATH line lacks a Linux tool folder: {'herdr-doctor': ['/usr/local/bin', '~/.linuxbrew/bin'], 'herdr-event-post': ['/usr/local/bin', '~/.linuxbrew/bin'], 'herdr-event-flush': ['/usr |
| P07 | pass | With an HC_SOCKET longer than a Unix socket allows, herdr-event-core --alive and herdr-doctor --core report the core as not answering in one line, no traceback. | --alive exit 1; doctor: ['PROBLEM Herdr Core not running for HC_SESSION default: the owner starts it (hc server start); this check never does'] |
| S01 | pass | A whole bot-started job up to an asked gate sends the question only to the bot's loopback route, runs no git push, git tag, gh pr merge, gh release or other egress, and a sentinel action guarded by ga | sentinel done after {'no yes': False, 'forged yes': False, 'stale yes': False, 'yes, acting on another commit': False, 'yes': True}; the bot's loopback route got the gate True; forbidden or blocked ca |
| S02 | pass | ask --gate in a bot-started job whose route has no URL exits non-zero and leaves no gate file. | ask --gate with no route: exit 2; gate files 0: fleet-job ask: the relay did not queue this for grokbot (herdr-event-post: no route of its own for owner grokbot in /var/folders/w8/c2227dgn0kg4nf_q58r3 |
| V01 | pass | A Codex worker is started with stampede's own notify hook, and that hook's payload gives a TURN line in the lead's inbox.log; nothing depends on hooks Herdr installs. | Codex started with stampede notify True; TURN line True |
| V02 | fail | Each minimum version agrees wherever it is stated and enforced: Herdr in herdr-plugin.toml, the README and herdr-doctor; Herdr Core and Claude (on Core) in the README and herdr-doctor --core. | minimums that are missing or disagree: {'herdr': {'plugin': '0.9.4', 'readme': '0.9.4', 'doctor': None}} |
