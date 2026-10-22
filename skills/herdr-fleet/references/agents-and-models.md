# Agents and models

## Why the routing table looks like that

- **Opus 5.5 at xhigh** is the owner's standard builder (since the first fleet, 2026-09-30). It uses tools well and finishes a 25 to 45 minute slice without drifting.
- **Fable 5.1 at max** is the owner's standard independent reviewer. "Ultra" in the owner's words means max, the Claude CLI's top level. It is slower and dearer, which is worth it where a missed bug costs more than tokens. A reviewer on a different model from the builder does not share the builder's blind spots.
- **Codex is the second vendor.** Use it for second opinions, design direction (it wrote one site's design direction and later reviewed the built pages against it) and a parallel builder slice (two database slices in one fleet). `gpt-6-astra` at `ultra` is the frontier setting the owner picked for builders and reviews. `gpt-6.1-sol` at `xhigh` is the config default and the workhorse.
- **Sonnet 5.5, Haiku 5.5, `gpt-6.1-sol` medium and `gpt-6-luna`** are for cheap, fully specified bulk work. If a slice needs judgement, it is not a Sonnet slice. Exception (2026-10): Sonnet 5.5 may take heavy coding once a cross-model-reviewed, hardened plan specifies it fully.
- **Effort follows ambiguity, not size.** A big mechanical change runs at medium. A small subtle one runs at xhigh.
- If a model the owner named is unavailable or at capacity, say so and wait or ask. Do not quietly swap it. A lane whose model the owner did not name moves to its fallback after a usage limit or a second "at capacity" (the Fallback column in SKILL.md, or the plan's `fallback` column).

| CLI | Auto mode (use) | Plan mode | Never |
|---|---|---|---|
| Claude | `--permission-mode auto` | `--permission-mode plan` | `--dangerously-skip-permissions` |
| Codex | `--approve-for-me` | shift+tab once after start | `--yolo` |
| Cursor | `--auto-review --trust` (asks about anything unsure: a worker on its own branch, not a lead) | `--plan` | `--yolo`, `--force` |

Yolo, case by case: a worker in its own git worktree may run without checks (`fleet-job start --yolo-in <worktree>`); never the lead, and its brief still forbids pushing to a shared branch, merging, spending and publishing, since a worktree walls off files, not the network or your logins.

## Claude Code (`--kind claude`)

- Models: `claude-opus-5-5`, `claude-fable-5-1`, `claude-sonnet-5-5`, `claude-haiku-5-5` (aliases `opus`, `fable`, `sonnet`, `haiku`).
- Effort: `low`, `medium`, `high`, `xhigh`, `max`.
- Permission modes: `auto` is the fleet standard. `plan` suits a read-only planner. Fleet convention: no `bypassPermissions` in a fleet. The owner's policy allows skip-permission flags when he asks for them.
- `-n <name>` sets the session name shown in `/resume`, the terminal title and Claude peer messaging. Use the herdr agent name.

Interactive in a pane, the fleet default:

```bash
fleet-job start "$B" build-api --kind claude --pane "$P" --brief "$B/build-api.md" --model claude-opus-5-5 --effort xhigh \
  --report reports/build-api.md   # adds --permission-mode auto, -n build-api, the job's hooks and the reopen record; sends the brief pointer
```

Shortcut, for a raw `herdr agent start` outside a fleet job only (`fleet-job start` takes `--brief` instead): put the first prompt last, as a positional argument after the native flags, and the agent starts working at once. The start then often returns `timeout` while the agent is in fact working, and the name is not attached. Check `herdr pane read "$P" --source visible --lines 20`, then `herdr agent rename "$P" build-api`. On macOS `agent start` rejects a command longer than the terminal's line-input limit (about 1 KB), so keep that prompt to one short line or send it with `agent prompt`, which pastes.

Smoke-tested 2026-10-14 with herdr 0.9.4 and Claude Code 2.1.300: the start line above, one prompt, `working` then `done`, and `/exit` clears the name within a few seconds.

Resume a session in the same pane (after a hang or a restart). The id comes from `herdr agent get <name> | jq -r .result.agent.agent_session.value` (set at start for Claude; Codex, Hermes and Kimi report theirs after the first turn, so record it in the register then):

```bash
herdr agent start build-api --kind claude --pane "$P" --timeout 90000 -- \
  --resume <session-id> --model claude-opus-5-5 --effort xhigh --permission-mode auto
```

A reviewer can take over a finished builder's pane, which keeps the tab small:

```bash
herdr agent prompt build-api "/exit"
herdr agent wait build-api --until unknown --timeout 30000   # ends with agent_not_running once it exits and the name clears
fleet-job start "$B" review-api --kind claude --pane "$P" --brief "$B/review-api.md" --model claude-fable-5-1 --effort max \
  --report reports/review-api.md   # hooked like any start; sends the brief pointer
```

One-shot, no herdr state: `claude -p --model claude-sonnet-5-5 --output-format json "<prompt>"`. Use it for an isolated answer (a persona test, a classification), not for fleet members.

## Codex (`--kind codex`)

- Models (from `~/.codex/models_cache.json`): `gpt-6.1-sol` (latest workhorse, the config default), `gpt-6-astra` (frontier), `gpt-6-luna` (fast), `gpt-6-sol` (previous generation).
- Effort is set with `-c 'model_reasoning_effort="<level>"'`: `low`, `medium`, `high`, `xhigh`, `max`, `ultra`. `gpt-6-luna` tops out at `max`.
- The owner's `~/.codex/config.toml` sets `model = "gpt-6.1-sol"`, `model_reasoning_effort = "xhigh"`, `approval_policy = "never"` and `sandbox_mode = "danger-full-access"`. A bare `codex` therefore runs with full access and no approvals.

Interactive in a pane:

```bash
fleet-job start "$B" build-db --kind codex --pane "$P" --brief "$B/build-db.md" --model gpt-6-astra --effort ultra \
  --report reports/build-db.md   # adds --approve-for-me, --add-dir "$B", the notify hook and the reopen record; sends the brief pointer
```

- `--approve-for-me` routes approvals to automatic review inside the workspace-write sandbox, so writes stay in the worktree. One fleet's Codex builder ran tests, type checks and a local Postgres this way. Network access inside that sandbox was not checked. Dropping the flag means the config's full access. By fleet convention do that only with the owner's OK (the owner's policy allows it when the owner asks).
- The workspace-write sandbox refuses writes outside the cwd (checked 2026-10-16 with `codex sandbox`: a write to a sibling folder under `$HOME` was denied, and allowed once that folder was a writable root; `/tmp` is always writable). When the briefs or reports folder is not under the agent's cwd, add `--add-dir <abs dir>` (one per folder) to the start line.
- `--search` turns on live web search.
- A positional first prompt after the flags works as it does for Claude.
- Quit with `/quit`.

Non-interactive, useful from the lead or in a plain pane via `herdr pane run`:
- `codex exec -m gpt-6.1-sol "<prompt>"` runs one task and exits.
- `codex review --base main` (or `--commit <sha>`, `--uncommitted`) runs a quick cross-vendor code review.

Codex gotchas (details in [failure-modes.md](failure-modes.md)):
- A folder Codex has never opened asks "Trust this folder?" first (the start returns `agent_not_ready`, status `blocked`; Enter accepts "Trust and continue"), then "Hooks need review" (reported `idle`; `down down enter` continues without trusting). A fresh worktree asks the hooks question again. Smoke-tested 2026-10-14 with Codex 0.162.1: after both, one prompt went `working` then `done`, and `/quit` clears the name.
- When a newer Codex is out it shows "Update available" at start: the start returns `agent_not_ready`, status `blocked`, and the highlighted default is "Update now" (runs npm). `herdr agent send-keys <name> esc` skips it for this launch, then `agent wait <name> --until idle --timeout 30000` (checked 2026-10-16, Codex 0.162.1 with 0.163.0 out). Enter updates Codex and it exits with "Please restart Codex".
- `ctrl+c` on an empty idle Codex prompt quits Codex. Prompt with `herdr-send`, which sends `ctrl+c` only to clear typed leftovers.
- Codex can sit in `unknown` after it answers (with herdr 0.9.4 and Codex 0.162 it reported `done`), so do not wait on a state; use the report file.
- "Selected model is at capacity" ends a turn with no work done. Read the screen, then send the prompt again.

## Other kinds on this Mac (smoke test, 2026-10-14)

`herdr agent start --kind` lists 24 kinds; these are the ones installed here, each tried with a start, a one-line prompt that writes a file, and an exit. The routing table stays Claude and Codex as the defaults; the owner approved Hermes, Kimi and Cursor Agent as fleet kinds too (2026-10-14), with their unattended flags below. Use another kind when the plan or the owner names it. Owner prerequisites: Cursor Agent needs the macOS login keychain unlocked; Kimi needs `kimi login`; Gemini needs a Google sign-in (Kimi and Gemini are optional). Never do these for the owner.

| Kind | Start (after `herdr agent start <name> --kind <kind> --pane "$P" --timeout 90000 --`) | Status and exit | Notes |
|---|---|---|---|
| `hermes` (0.21.5) | `--yolo --reasoning <level>`; the model comes from `~/.hermes/config.yaml`, `-m` overrides it | idle, working, done; session id after the first turn. `/exit` | `--yolo` is the approved unattended flag (it skips dangerous-command prompts). A caller's safety check may ask for approval the first time; that approval is sanctioned. Smoke-tested without `--yolo` (still wrote files in its cwd). No `STALL?` cover (its sessions live in `~/.hermes/state.db`). Hooks: herdr v5, Moshi current. |
| `kimi` (2.1.1) | `-y` (approved unattended flag; a caller's safety check may ask for approval the first time) | Trust dialog reported `idle`; Enter trusts. Stayed `working` after an error turn. `/exit` | Optional. Prerequisite (owner): `kimi login`; the smoke test hit "stored token rejected, re-login required". Hooks: herdr v7, Moshi current. |
| `gemini` (0.62.0) | `--approval-mode auto_edit` | Trust dialog, then a sign-in picker, both reported `idle`. ctrl+c, esc and ctrl+d do not leave the picker, and `/quit` sent there is Enter on "Sign in with Google"; only closing the pane ended it | Optional. Prerequisite (owner): Google sign-in. Self-updates on start through npm. No `gemini` entry in `herdr integration status`; Moshi hooks current. |
| `cursor` (`cursor-agent` 2026.10.01) | `--model <model>` (and `--force` to run commands without asking, if the installed `cursor-agent --help` lists it; not yet verified, the help itself needs the keychain) | Expected idle, working, done like the others; exit with `/quit` or ctrl+d (not yet verified live). While the login keychain is locked the CLI exits at once, so `agent start` waits out its timeout and returns `timeout` | Supported fleet kind. Prerequisite (owner): unlock the macOS login keychain (`security unlock-keychain` in the owner's own session). Verify flags with `cursor-agent --help` on first use and update this row. Hooks: herdr v1, Moshi current. |
| `grok` | not installed (`~/.grok` holds hooks only) | | Not usable as a herdr agent on this Mac. |

Every CLI prints its resume command on exit (`claude --resume <id>`, `codex resume <id>`, `hermes --resume <id>`, `kimi -r <id>`); the register should hold the id before then.

## Writing start commands in zsh

- zsh does not word-split `$ARGS`, so `-- $ARGS` passes one argument. Write the flags literally, or use an array: `args=(--model claude-opus-5-5 --effort xhigh); ... -- "${args[@]}"`.
- Keep the Codex `-c` value in single quotes so the inner double quotes reach TOML.
- `echo ====` fails in zsh (`=` expansion). Use `printf`.
- `herdr agent prompt` takes no `--` separator and no `--no-focus`; those belong to `agent start` and `pane split`. A wrong flag fails with "unknown option".
- `agent prompt <name> "..." --wait --timeout <ms>` is the normal form (it matches idle, done or blocked by default). Add `--until <state>` only when you need one specific state; without `--wait` it is rejected ("--until requires --wait"). `--wait` does not track turns, so `agent get` first and read the screen before any resend.
