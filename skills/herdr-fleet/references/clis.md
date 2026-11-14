# The agent CLIs

What `stampede start` passes each CLI, and each one's quirks. Which model to pick: [agents-and-models.md](agents-and-models.md). The installed binary is the authority: `<cli> --help`.

## Permission flags

| CLI | Auto mode (`stampede start` adds it) | Plan mode | Never |
|---|---|---|---|
| Claude | `--permission-mode auto` | `--permission-mode plan` | `--dangerously-skip-permissions`, `bypassPermissions` |
| Codex | `--approve-for-me` | shift+tab once after start | `--yolo` |
| Cursor | `--auto-review --trust` (asks when unsure: a worker on its own branch, not a lead) | `--plan` | `--yolo`, `--force` |
| Hermes | its default (asks before a dangerous command) | | `--yolo` |
| Kimi | `-y` (routine edits and commands run; risky actions, questions and plans ask) | `--plan` | `--auto` (never asks) |

- No-checks mode only for a worker in its own git worktree: `stampede start --yolo-in <worktree>`, never the lead. Its brief still forbids pushing a shared branch, merging, spending and publishing: a worktree walls off files, not the network or the owner's logins.
- Skip-permission flags only when the owner asks for them.

## Claude (`--kind claude`)

- Models `claude-opus-5-5`, `claude-fable-5-1`, `claude-sonnet-5-5`, `claude-haiku-5-5` (aliases `opus`, `fable`, `sonnet`, `haiku`); effort `low`, `medium`, `high`, `xhigh`, `max`.
- `-n <name>` sets the session name in `/resume`, the title and peer messaging: `stampede start` uses the agent's name.
- Keep the whole fleet in auto mode: peer messages between sessions in different modes wait for the owner.
- One-shot, outside the fleet: `claude -p --model claude-sonnet-5-5 --output-format json "<prompt>"`, for an isolated answer only.
- A raw `herdr agent start` with the first prompt as a positional argument often returns `timeout` while the agent works, and leaves it unnamed: check with `herdr pane read`, then `herdr agent rename <pane> <name>`. On macOS a start line over about 1 KB is rejected: send long text with `agent prompt`, which pastes.

## Codex (`--kind codex`)

- Models `gpt-6.1-sol` (workhorse), `gpt-6-astra` (frontier), `gpt-6-luna` (fast, effort up to `max`), `gpt-6-sol` (previous). Effort: `-c 'model_reasoning_effort="<level>"'`, `low` to `ultra`.
- A bare `codex` may run with full access and no approvals, by the owner's own config: always start it through `stampede start`.
- `--approve-for-me` keeps writes inside the cwd's sandbox (`/tmp` too); each other folder needs an `--add-dir` (`stampede start` adds the job folder). Dropping the flag means full access: only on the owner's OK.
- `--search` turns on web search. Quit with `/quit`, never `/exit`; never `ctrl+c` an empty idle prompt (it quits).
- Codex can sit in `unknown` after it answers: the report file is the signal, never a state.
- One-offs from the lead: `codex exec -m gpt-6.1-sol "<prompt>"`, `codex review --base main` (or `--commit <sha>`, `--uncommitted`).
- **A Codex lead** runs like a Codex worker, with the network on (Herdr's socket, `git push`, `gh`) and two more writable roots: `<jobs_root>/worktrees` and the repo's git folder, which also lets it write `.git/hooks` and `.git/config`.
  Rarer writes, such as the relay queue behind `stampede ask`, still go through Codex's approval review. Its notify hook forwards its turn ends to the relay and writes no `TURN`.
  It has no file hook: a deliverer types its inbox into its pane ([tui.md](tui.md#what-wakes-you), log `<job>/hooks/deliver.log`), so only the recorded yes counts ([gates.md](gates.md)).
  Quit it with `herdr-send <lead> /quit`: `stampede tell` text is marked as from fleet-job, so a slash command there is only chat.

## Other kinds

Run one when the plan or the owner names it. The owner's prerequisites, never done for them: Cursor needs the macOS login keychain unlocked; Kimi `kimi login`; Gemini a Google sign-in.

| Kind | Start flags | Notes |
|---|---|---|
| `hermes` | `--reasoning <level>` (`none` to `ultra`); `-m` overrides `~/.hermes/config.yaml`; `--yolo` only with `--yolo-in` | `/exit`; session id after the first turn. No `STALL?` cover. Herdr 0.9.5 does not detect Hermes 0.22.5, so a handed start ends `FAILED` (end it with `/exit`). |
| `kimi` | `-y`; `-m <model>`; no effort flag | `/exit`; its trust dialog shows `idle`; it stays `working` after an error turn. |
| `gemini` | `--approval-mode auto_edit` | Optional. Its sign-in picker shows `idle`, and keys there press "Sign in with Google": close the pane you made. Updates itself through npm. |
| `cursor` | `--model <model>` (`--force` only if `cursor-agent --help` lists it) | With the keychain locked it exits at once and the start returns `timeout`. Check its flags with `cursor-agent --help` first. |
| `grok` | | Not a herdr agent. |

On Herdr Core, Cursor, Hermes and Kimi run as a program (`stampede start <job> <name> -- <cli> ...`, [core.md](core.md#start-a-helper)); only a `--core --relay` job hands them to a TUI pane ([core-relay.md](core-relay.md#hand-an-agent-to-a-tui-pane)).

## Resume

- The session id: `herdr agent get <name> | jq -r .result.agent.agent_session.value`. Claude has it at start; Codex, Hermes and Kimi after their first turn: record it in the register then.
- Each CLI prints its resume command on exit: `claude --resume <id>`, `codex resume <id>`, `hermes --resume <id>`, `kimi -S <id>`.
- `reopen.sh` resumes them all ([tui.md](tui.md#reopen-record)).

## zsh and herdr flags

- zsh does not word-split `$ARGS`: write flags literally, or use an array (`args=(--model opus --effort medium)`, `"${args[@]}"`). Model and effort are separate flags.
- Keep Codex's `-c` value in single quotes. `echo ====` fails in zsh: use `printf`.
- `herdr agent prompt` takes no `--` and no `--no-focus` (those are `agent start`'s and `pane split`'s).
- `agent prompt <name> "..." --wait --timeout <ms>` matches idle, done or blocked; `--until <state>` needs `--wait`. `--wait` does not track turns: `agent get` first.
