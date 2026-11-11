# Eval run 20261111T042415Z-after-core-macos

Backend core-live; macOS 27.2 arm64; Python 3.14.7; commit ec55d6a08999 (dirty); 175 s.

Product 07be6e60e6cd, harness 1ea870ab3a38, dataset c12007c19294; 17 cases selected.

Tools: herdr herdr 0.9.5, hc hc 0.1.20, moshi-hook moshi-hook version 0.4.53, jq jq-1.7.1-apple, git git version 2.56.0, bash GNU bash, version 5.3.20(1)-release (aarch64-apple-darwin27.0.0), python3 Python 3.14.7, claude 2.1.322 (Claude Code), codex codex-cli 0.167.0, ps ps: illegal option -- -.

| status | count |
|---|---|
| pass | 16 |
| fail | 0 |
| error | 0 |
| blocked | 0 |
| skip | 1 |
| gap | 0 |

| case | status | expected | actual |
|---|---|---|---|
| C01 | pass | stampede new --core in a scratch HC_SESSION writes the job record, starts the lead (a stand-in agent speaking OSC 7501) and the follower relay-<key>, and delivers the brief pointer. | new --core made .herdr-ev1 (key hc-b21e32730c05) on HC_SESSION=ev75f5f5: record (backend, endpoint, owner, marker, tag), follower relay-b21e32730c05 at t1 and lead at t2 live with the job's labels and |
| C02 | pass | stampede start in a --core job (start takes the job's backend) starts a stand-in worker in a Core terminal with the job's labels, and agents.tsv and core.json record it. | stampede start (no --core flag: the job's backend) put worker-a (claude) at t3 and worker-b (codex) at t4 in Core terminals with the job's labels; agents.tsv and core.json record them; a second start  |
| C03 | pass | tell reaches the worker through hc send only when it is idle; the worker's reply lands in the lead's inbox. | tell reached the idle Codex worker with hc send --if idle, was refused while it worked (FAILED, working, nothing typed), went in once its turn was done, and the worker's reply (fleet-job tell lead) la |
| C13 | pass | While a person has typed an unsent draft into a worker through hc attach, stampede tell waits; when the person clears the draft the tell goes in alone and prints SUBMITTED, and the person's text is ne | with a person's unsent draft in the worker's terminal (typed through hc attach), stampede tell waited (6 s in all, still waiting at 5 s, nothing typed meanwhile); once the person cleared the draft it  |
| C04 | pass | The worker's report gives exactly one REPORT line, made by the worker's Stop hook (a stand-in that runs its --settings hooks as Claude does); a second turn with the report unchanged adds none; the fol | one REPORT line from the worker's Stop hook (run by the stand-in from its --settings, 3 Stop runs), none added by a second turn; the follower posted turns [1, 2, 3] once each (3 relay lines, kept home |
| C05 | pass | A yes typed into the lead terminal records nothing; approve-gate under hc exec is refused; approve-gate from a plain shell outside Core then gate-ok passes; another commit is refused. | gate 1085d5434e1f queued for evalbot; a typed yes recorded nothing (gate-ok: no recorded yes, no typed yes offered); approve-gate refused under hc exec and inside the lead terminal (exit 2); from a sh |
| C10 | pass | HC_SESSION=<scratch> hc server restart (from a shell with a changed environment) keeps the job's terminals; the follower reconnects and adds no duplicate line for events it already reported. | hc server restart kept the job's 4 terminals (same addresses and pids); the follower reconnected and wrote no duplicate line; a worker started after it did not get the restart shell's variable (its en |
| C11 | pass | Killing only the lead terminal leaves every worker terminal (started --no-parent) running; reopen.sh then restarts the lead only. | killing the lead left worker-a, worker-b, worker-d running (same pids); reopen.sh restarted the lead only (t6), acknowledged through its wake hook, exit 0 |
| C06 | pass | After the lead and a worker terminal are killed, reopen.sh restarts exactly the missing ones once, and a second reopen.sh starts nothing. | the follower reported GONE worker-a killed; reopen.sh restarted exactly the lead and worker-a, each with --resume <its session>, and left worker-b, worker-d and the follower alone; a second reopen.sh  |
| C07 | pass | finish queues one done event, the follower relay-<key> exits by itself, and no stampede process of the job is left. | finish from the lead queued one done event for evalbot, the follower relay-b21e32730c05 exited 0 by itself, the marker is gone, no herdr-event-core or fleet_job.py process of the job is left (the stan |
| C08 | pass | A setsid child of a killed worker terminal is still alive on hc 0.1.19 (it was not before); stampede's own detached helpers (a background ask) are ended by finish, not left behind. | the setsid child of the killed worker outlived its terminal; finish ended the background ask (pid 83998) |
| C12 | skip | On Linux with no polkit, a Core terminal reports its first status within 5 s; on macOS this case is skip. | macOS: the 25 s polkit wait was a Linux terminal start (Core 0.1.17); nothing to measure here |
| C14 | pass | stampede new --core --lead codex starts a Codex lead (a stand-in) in a Core terminal without its daemon, its brief pointer as its first prompt; a line for the lead in its inbox is typed into its termi | new --core --lead codex started lead-ev3 at t13 as Codex without its daemon, its brief pointer as its first prompt and its own session in agents.tsv after its first turn; an answer for it and the foll |
| C16 | pass | A job started with new --core --app-space labels its lead and workers herdr.space=stampede-<key> and herdr.tab=<agent> on the real core, and its follower not at all; a job started without the flag car | new --core --app-space labelled lead-ev4 and worker-k herdr.space=stampede-f5df82e33325 and herdr.tab=<its name> on the real core, and the follower not at all; the 8 terminals of the job started witho |
| C15 | pass | With keep on for a worker's terminal (as the Herdr app sets it), killing the worker's process by signal makes Core put a shell at the same address; the follower writes one GONE line that names the she | with keep on, kill -9 of worker-k's process made Core put a shell at t17 (reason signaled); the follower wrote one GONE line naming the shell and one dead event for the bot (last state working), nothi |
| V03 | pass | hc schema on this machine has every method, parameter, error kind, result field and event type stampede uses, each as in the committed snapshot (tests/fixtures/hc-schema-0.1.20.json); on a core older  | hc schema 0.1.20 on this machine holds the 13 commands stampede uses (each method, parameter, error kind and result field) and the 12 event types, as the snapshot of 0.1.20 does |
| C09 | pass | Nothing the run did reached the machine's own core: every hc call named the scratch session, the scratch config and sockets lived under the scratch folder, and the default core was only observed witho | 306 hc calls, every one with HC_SESSION=ev75f5f5; config, state and socket under the scratch folder; the default core only observed by its socket (alive before True, after True), never an hc command;  |
