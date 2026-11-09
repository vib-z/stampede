# Eval run 20261108T223920Z-final-before-linux-install

Backend linux-install; Ubuntu 24.04.5 LTS aarch64; Python 3.12.3; commit d7a1237e161e; 132 s.

Product 8f99b46a668f, harness e6f1f21ee23a, dataset f3363bc3ac63; 6 cases selected.

Tools: herdr herdr 0.9.5, hc hc 0.1.19, moshi-hook moshi-hook version 0.4.50, jq jq-1.7, git git version 2.43.0, bash GNU bash, version 5.2.21(1)-release (aarch64-unknown-linux-gnu), python3 Python 3.12.3, claude 2.1.300 (Claude Code), codex codex-cli 0.100.0, flock flock from util-linux 2.39.3, ps ps from procps-ng 4.0.4.

| status | count |
|---|---|
| pass | 5 |
| fail | 1 |
| error | 0 |
| blocked | 0 |
| skip | 0 |
| gap | 0 |

| case | status | expected | actual |
|---|---|---|---|
| I01 | pass | herdr 0.9.5, hc 0.1.19 and moshi-hook 0.4.50 install from their release URLs into the container user's ~/.local/bin, each checked by sha256, with no root and no global change. | herdr herdr 0.9.5 digest ok; hc hc 0.1.19 digest ok; moshi-hook moshi-hook version 0.4.50 digest ok; uid 1001, all in ~/.local/bin |
| I02 | pass | install.sh links the skills and commands, starts the event timers (the flock loop when systemctl --user does not answer), and a second run changes nothing. | first run: 15 command links, skills linked for .claude and .codex, started the event loop (no systemctl --user); second run: nothing changed |
| I05 | pass | herdr plugin install (or link) of this checkout on a real Linux herdr accepts the plugin (platforms include linux) and its event hook runs on an agent status change. | link exit 0, listed enabled True, agent start exit 0, 3 hook runs logged (succeeded), state file written: idle, relay log reached |
| I03 | pass | herdr-doctor and herdr-doctor --relay against a real herdr server print no PROBLEM line; herdr-doctor --core against a real hc in a scratch session prints no PROBLEM line for Core. | plain: exit 0, 23 ok, 0 PROBLEM; relay: exit 0, 23 ok, 0 PROBLEM; core: exit 0, 24 ok, 0 PROBLEM |
| I04 | fail | python3 -m unittest discover tests passes in the container. | exit 1; Ran 430 tests in 122.418s; FAILED (failures=4, errors=9, skipped=12, expected failures=7); failed: test_a_gate_goes_to_the_outbox_and_the_front_door_records_the_quoted_yes (test_fleet_job.Fron |
| I06 | pass | The real moshi-hook 0.4.50 for Linux, unpaired, makes stampede ask fail loudly (ASK FAILED, exit 4 or its own code) and never approves a gate. | moshi-hook ask unpaired: exit 4 (moshi-hook: can't ask on your phone: Moshi daemon not running. Start it with 'moshi-hook service install' (persistent) o); stampede ask -> inbox ASK FAILED Which colou |
