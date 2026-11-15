# Configure

This page lists every setting, its default and where to change it. Each has a default, so you need to set none.

stampede reads each setting from these layers. The last one that sets it wins:

1. the defaults, in [defaults.toml](../skills/herdr-fleet/scripts/stampede/defaults.toml), the list of every key;
2. yours: `~/.config/stampede/config.toml` (`$XDG_CONFIG_HOME/stampede/config.toml` when that is set);
3. the project's: `.stampede.toml` at the repo root, which a repo can commit;
4. the environment: the variable names stampede has always read, which still work;
5. the command's own flags (`--lead`, `--lead-model`, `--lead-effort`, `--max-helpers`, and `start`'s `--kind`, `--model`, `--effort`), then `--set key=value` (repeatable, on `new` and `start`; the value is read as TOML, and a bare word is a string).

[config.example](../config.example) holds every key with its default. Copy it to `~/.config/stampede/config.toml` and keep only what you change:

```bash
mkdir -p ~/.config/stampede && cp config.example ~/.config/stampede/config.toml
stampede config show                     # every setting and the layer that set it; exit 1 when the config has problems
stampede config show --json              # {values, sources, files, environment, problems}
stampede config show --job <job>         # what that job saved at new
stampede new --file ask.md --set helpers.max=6 --set lead.kind=codex
```

**What a job remembers.** `stampede new` saves what it resolved, with the layer of each value, in `<job>/settings.json`, and every later command of that job reads it there. Anything not set then follows your current config. A later command's own `--set` still wins for that command, and `<job>/max-helpers` for its job.

**User-only settings.** `jobs_root`, `trust_root`, `ask.command`, `lead.forbid` and every `gates.` key run a command, widen what is trusted or lower a rule. `backend` is your own choice. So stampede reads these only from your file, the environment or a flag. In a repo's `.stampede.toml` each is skipped, with a problem line. They are never saved in `settings.json`, which the job's agents can write.

`lead.forbid` matches exact model names. A job's gates are fixed at `stampede new`, in the owner-side record ([Safety](SAFETY.md)). The rest follow your live config at every command.

**Problems.** stampede skips an unknown key, a value of the wrong type or not one of the key's choices, and a file that does not parse. `stampede config show` names each in one line. `stampede new` refuses to start a job while there is one (exit 2); no other command fails on them.

## Every key, with its default

| key | default | environment | what it does |
|---|---|---|---|
| `backend` | `tui` | | where `stampede new` runs a job given no `--core`, `--pane` or `--workspace`: `tui` (the Herdr TUI; outside a Herdr pane `new` refuses), `core` (Herdr Core), or `auto` if you ask for it (the TUI inside a Herdr pane, Core anywhere else). `stampede config set backend <tui\|core\|auto>` writes it to your file. User only: a repo's `.stampede.toml` cannot put a job on Herdr Core |
| `jobs_root` | `~/code/herdr-jobs` | `FLEET_JOBS_ROOT` | every job folder, on every backend, is `<root>/jobs/<date>-<owner or local>-<slug>`, never in a repo (user only) |
| `trust_root` | `~/code` | `FLEET_TRUST_ROOT` | a Core job's repo must sit under it (user only). `herdr-trust` and `herdr-doctor` read only `FLEET_TRUST_ROOT`: if you move the root, export that too |
| `lead.kind` | `claude` | `FLEET_LEAD_KIND` | the lead's CLI when `stampede new` has no `--lead`: `claude` or `codex`, on the Herdr TUI and on Herdr Core. `--fork` takes `claude` only |
| `lead.forbid` | `[]` | `FLEET_LEAD_FORBID` (comma-separated) | models that may not lead a job. Before it makes anything, `stampede new` refuses a lead whose model is on the list, from `--lead-model`, a setting or the default, in one line naming the model and `lead.forbid` (user only). Workers are not checked |
| `lead.claude.model`, `lead.claude.effort` | Claude Opus 5.5 (its id is in config.example), `xhigh` | `FLEET_LEAD_MODEL`, `FLEET_LEAD_EFFORT` | a Claude lead's model and effort |
| `lead.codex.model`, `lead.codex.effort` | GPT-6 Astra (its id is in config.example), `ultra` | `FLEET_LEAD_MODEL`, `FLEET_LEAD_EFFORT` | a Codex lead's model and effort. `FLEET_LEAD_MODEL` and `FLEET_LEAD_EFFORT` set a pair: a `gpt-...` model sets the Codex pair, any other (or none) the Claude pair. `new --lead-model` and `--lead-effort` set the pair of the lead's own CLI |
| `roles.<role>.kind`, `.model`, `.effort` | `build`, `default`: Claude Opus 5.5 `medium`; `research`: Claude Opus 5.5 `xhigh`; `copy`: Claude Opus 5.5 `high`; `test`: Claude Sonnet 5.5 `medium`; `review`, `qa`, `design`: Codex GPT-6 Astra `ultra` (the ids are in config.example) | | what `stampede start <job> <role>-<scope>` gives a helper that names no `--kind`, `--model` or `--effort`. The role is the name up to its first `-`; any other role takes `roles.default`. A flag always wins. A role's model and effort go only with its own kind, so `--kind codex` on a Claude role leaves the model to Codex. Add a role of your own as `[roles.<name>]`. Not for a program after `--` |
| `review.step` | `end` | | the review step the lead's brief asks for, with its reviewer from `roles.review`: `end` (one pass at the end, by another model than the builder's), `each` (one per pull request or step) or `none` (no review step: the brief says you switched it off). Nothing enforces it |
| `ask.command` | `moshi-hook ask --require-remote --source herdr-fleet --timeout 24h` | `FLEET_ASK_CMD` | what `stampede ask` runs, for a question or a gate, in a job started here (a bot's job asks its bot). The options and the question are added at the end (user only) |
| `brief.sections` | the seven headings of the [hand-off template](../skills/herdr-fleet/references/brief.md) | | the sections every worker's brief must fill |
| `helpers.max` | `12` | `STAMPEDE_MAX_HELPERS` | a Core job: how many helpers may work at once in the lead's tree, at any depth; a start over it is queued (`--max-helpers` or `<job>/max-helpers` per job) |
| `helpers.layout` | `grid` | | a Core job: how the labels split a tab's terminals: `grid` (2 right of 1, 3 below 2, 4 below 1), `columns` (each right of the one before) or `rows` (each below the one before) |
| `helpers.tab_panes` | `4` | `STAMPEDE_TAB_PANES` | a Core job: live terminals per layout tab label (`main`, `main-2`, ...) before a helper goes to the next |
| `timeouts.wait` | `3600` | | seconds `stampede wait` waits before exit 3 (`--timeout` per call) |
| `timeouts.hc_call` | `60` | | seconds one `hc` call may take on top of what the command itself waits for |
| `timeouts.leave` | `15` | | seconds an idle agent has to leave after `/exit` or `/quit` at `stampede close` |
| `timeouts.hold_settle` | `5` | | seconds a `--relay` terminal must have been at rest before its turn count can start a hold |
| `gates.merge` | `true` | | `stampede merge` needs a gate approved at the reviewed commit; `false` merges a passing review without one, logged (user only) |
| `gates.push_default_branch` | `true` | | the `pre-push` hook (git's check before a push) stops a job's agent pushing to the default branch without a gate; `false` lets it, logged (user only) |
| `gates.deploy`, `gates.publish`, `gates.send`, `gates.spend` | `true` | | the lead asks before a deploy, publishing, sending or any spend; `false` tells it that one needs no yes (user only) |
| `gates.close` | `true` | | the lead asks before closing a helper's terminals; a whole job never closes from inside it (user only) |
| `merge.method` | `squash` | | how `stampede merge` merges: `squash`, `merge` or `rebase` |

## Environment only, with defaults

Other programs read these, so they stay environment variables. Export them in your shell profile, or in the shell file `~/.config/stampede/config` (`$XDG_CONFIG_HOME/stampede/config` when that is set), sourced from your profile. The relay scripts read that file themselves, so the hooks and the timers see it with no line in your profile.
- They read only its plain lines, `NAME=value` or `export NAME=value`: the value bare or quoted, with `$HOME` or a leading `~/` at most. They run nothing in it, so a value worked out by a command belongs in your shell profile. `herdr-doctor --relay` names the lines they skip.
- A file over 4 KB or 100 lines is not read at all, and `herdr-doctor --relay` says so.
- A value the environment already holds wins over the file. The Herdr plugin event is the exception: it sources the file as shell, and there the file's value wins.
- `stampede config show` lists them with their current values. A Core job passes them, and the environment names above, to every terminal it starts.

| variable | default | what it does |
|---|---|---|
| `FLEET_WATCH_INTERVAL` | `30` | seconds between `fleet-watch.sh` passes (a bot outside Herdr) |
| `FLEET_WATCH_PASSES` | `0` | stop the watch after this many passes; 0 runs until stopped |
| `FLEET_WATCH_NOTIFY` | `1` | `0` turns off the watch's phone push. A `--core --relay` job's follower pushes stalls and ended terminals to the phone (`moshi-hook notify`) only when it is `1`; unset, it does not |
| `HERDR_EVENTS_MACHINE` | short hostname (`hostname -s`, else the name before the first dot) | the machine label sent with every event |
| `HERDR_EVENTS_HOME` | `~/.herdr-events` | the event queue and dead letters |
| `HERDR_EVENTS_ROUTES_DIR` | `$HERDR_EVENTS_DIR/routes` | one file per route, `URL=` and `KEY=` |
| `HERDR_EVENTS_STALE_MINUTES` | `30` | the watchdog's sweep of a Core job's lead, and a `--core --relay` job's follower: minutes a working terminal's screen may stay unchanged, with no status or turn change, before one `stale` (the TUI watchdog's fixed 30) |
| `HERDR_EVENTS_DIR` | `~/.config/herdr-events` | owner tags (`owners/`), job markers (`jobs/`), handed panes' marks (`handed/`), and the routes when `HERDR_EVENTS_ROUTES_DIR` is unset |
| `HERDR_EVENTS_FLUSH_LOG` | `~/.herdr-events/flush.log` | the flusher's log |
| `HERDR_EVENTS_FALLBACK_ROUTE` | unset | a route's name, a file in the routes folder: an owner with no route file of its own goes there instead of `default`, and a Codex turn with no Herdr pane and no Core terminal (the Codex desktop app) is sent there as source `codex-desktop`, with no workspace or owner, instead of skipped. Any other value is ignored (logged), and events go as when it is unset. A question or a gate never uses it |
| `HERDR_EVENTS_LAUNCHD` | `local` | macOS: the label prefix of the two launchd jobs `herdr-doctor` checks, `<prefix>.herdr-event-watchdog` and `<prefix>.herdr-events-flush` |
| `HERDR_DOCTOR_EXTRA` | unset | an absolute path to an executable of your own that `herdr-doctor` runs last, never through a shell, with empty stdin. Its first 64 KB print with control bytes removed (cut at a line end, with a line that says so). Each line that starts `PROBLEM` counts toward exit 1, all of them. A missing or failing one, or one not done in 30 seconds (it and its process group are ended), is one `warn` |
| `HERDR_EVENTS_OWNER` | unset | set per command by a bot, never in a config file: at `stampede new`, the bot that started the job (else the workspace's owner tag), so its gates go back to it |
| `HC` | `hc` | the Herdr Core binary, 0.1.13 or later |
| `HC_SESSION` | `default` | Herdr Core's own: which core; each name is a separate core with its own terminals and state. A Core job keeps the one it was made with (`<job>/endpoint`) and passes it to every terminal; a command from a shell set to another is refused |
| `HC_SOCKET` | Core's default path for the session | Herdr Core's own: that core's socket; passed on like `HC_SESSION`. Set to the default socket's own path, it is the default core |
| `STAMPEDE_APP_SPACE` | `0` | `1`: every `stampede new --core --relay` job labels its lead and workers for the Herdr app, as `--app-space` does ([core-relay.md](../skills/herdr-fleet/references/core-relay.md#in-the-herdr-app)); a Core job always carries the app's labels |
| `STAMPEDE_NO_UPDATE_CHECK` | `0` | `1` turns off the daily check for a newer release ([Updating](SETUP.md#update)) |
| `STAMPEDE_UPDATE_URL` | `https://api.github.com/repos/vib-z/stampede/releases/latest` | where the check reads the latest release; the tests point it at a local file |
