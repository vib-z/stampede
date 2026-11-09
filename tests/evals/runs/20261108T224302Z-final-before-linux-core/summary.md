# Eval run 20261108T224302Z-final-before-linux-core

Backend core-live; Ubuntu 24.04.5 LTS aarch64; Python 3.12.3; commit d7a1237e161e; 49 s.

Product 8f99b46a668f, harness e6f1f21ee23a, dataset f3363bc3ac63; 12 cases selected.

Tools: herdr herdr 0.9.5, hc hc 0.1.19, moshi-hook moshi-hook version 0.4.50, jq jq-1.7, git git version 2.43.0, bash GNU bash, version 5.2.21(1)-release (aarch64-unknown-linux-gnu), python3 Python 3.12.3, claude 2.1.300 (Claude Code), codex codex-cli 0.100.0, flock flock from util-linux 2.39.3, ps ps from procps-ng 4.0.4.

| status | count |
|---|---|
| pass | 11 |
| fail | 1 |
| error | 0 |
| blocked | 0 |
| skip | 0 |
| gap | 0 |

| case | status | expected | actual |
|---|---|---|---|
| C01 | pass | stampede new --core in a scratch HC_SESSION writes the job record, starts the lead (a stand-in agent speaking OSC 7501) and the follower relay-<key>, and delivers the brief pointer. | new --core made .herdr-ev1 (key hc-53ebe274236f) on HC_SESSION=ev90adae: record (backend, endpoint, owner, marker, tag), follower relay-53ebe274236f at t1 and lead at t2 live with the job's labels and |
| C02 | pass | stampede start in a --core job (start takes the job's backend) starts a stand-in worker in a Core terminal with the job's labels, and agents.tsv and core.json record it. | stampede start (no --core flag: the job's backend) put worker-a (claude) at t3 and worker-b (codex) at t4 in Core terminals with the job's labels; agents.tsv and core.json record them; a second start  |
| C03 | pass | tell reaches the worker through hc send only when it is idle; the worker's reply lands in the lead's inbox. | tell reached the idle Codex worker with hc send --if idle, was refused while it worked (FAILED, working, nothing typed), went in once its turn was done, and the worker's reply (fleet-job tell lead) la |
| C04 | pass | The worker's report gives exactly one REPORT line, made by the worker's Stop hook (a stand-in that runs its --settings hooks as Claude does); a second turn with the report unchanged adds none; the fol | one REPORT line from the worker's Stop hook (run by the stand-in from its --settings, 3 Stop runs), none added by a second turn; the follower posted turns [1, 2, 3] once each (3 relay lines, kept home |
| C05 | pass | A yes typed into the lead terminal records nothing; approve-gate under hc exec is refused; approve-gate from a plain shell outside Core then gate-ok passes; another commit is refused. | gate 0c8b6f3da2b3 queued for evalbot; a typed yes recorded nothing (gate-ok: no recorded yes, no typed yes offered); approve-gate refused under hc exec and inside the lead terminal (exit 2); from a sh |
| C10 | pass | HC_SESSION=<scratch> hc server restart (from a shell with a changed environment) keeps the job's terminals; the follower reconnects and adds no duplicate line for events it already reported. | hc server restart kept the job's 4 terminals (same addresses and pids); the follower reconnected and wrote no duplicate line; a worker started after it did not get the restart shell's variable (its en |
| C11 | pass | Killing only the lead terminal leaves every worker terminal (started --no-parent) running; reopen.sh then restarts the lead only. | killing the lead left worker-a, worker-b, worker-d running (same pids); reopen.sh restarted the lead only (t6), acknowledged through its wake hook, exit 0 |
| C06 | pass | After the lead and a worker terminal are killed, reopen.sh restarts exactly the missing ones once, and a second reopen.sh starts nothing. | the follower reported GONE worker-a killed; reopen.sh restarted exactly the lead and worker-a, each with --resume <its session>, and left worker-b, worker-d and the follower alone; a second reopen.sh  |
| C07 | pass | finish queues one done event, the follower relay-<key> exits by itself, and no stampede process of the job is left. | finish from the lead queued one done event for evalbot, the follower relay-53ebe274236f exited 0 by itself, the marker is gone, no herdr-event-core or fleet_job.py process of the job is left (the stan |
| C08 | fail | A setsid child of a killed worker terminal is still alive on hc 0.1.19 (it was not before); stampede's own detached helpers (a background ask) are ended by finish, not left behind. | finish left the background ask alive (pid 37270, its card still waiting); after the lead terminal's kill it was still alive: on 0.1.19 a detached helper outlives its terminal, so finish must end it |
| C12 | pass | On Linux with no polkit, a Core terminal reports its first status within 5 s; on macOS this case is skip. | a Core terminal reported its first status (idle) 0.1 s after hc run; polkit present: False |
| C09 | pass | Nothing the run did reached the machine's own core: every hc call named the scratch session, the scratch config and sockets lived under the scratch folder, and the default core was only observed witho | 182 hc calls, every one with HC_SESSION=ev90adae; config, state and socket under the scratch folder; the default core only observed by its socket (alive before False, after False), never an hc command |
