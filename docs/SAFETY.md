# Safety

This page says what never happens without your yes, who records that yes, and what the code itself enforces.
A gate is a step that needs your yes. Other words: [the guide](GUIDE.md#words-on-this-page).

## What needs your yes

Your own yes, every time, before:

- a merge to main, or a push to main or another shared branch;
- a deploy, or publishing;
- sending email or messages;
- resubmitting a sitemap;
- any spend;
- closing panes, tabs, a workspace or a Core job (`stampede close`).

Pushing the job's own work branch and opening a draft PR need no ask.
The one list, and what never counts as a yes: [gates.md](../skills/herdr-fleet/references/gates.md).

## Who asks you

`stampede new` writes down which bot started the job, in `<job>/owner`. It takes the name from `HERDR_EVENTS_OWNER`, else from the workspace's owner tag.
The lead asks each gate with `stampede ask <job> --gate [--kind merge|push_default_branch] --sha <commit> [--pr <n>] "<the exact action>"`. A gate for anything but those two kinds has no kind.

Who asks you depends on how the job started:

- **By a bot:** a `gate` event goes to that bot ([remote/events.md](../remote/events.md)). The bot asks you in chat. On your yes, it runs the approve line the event hands it, as written, over SSH: `stampede approve-gate <job> <gate> --sha <commit> --digest <d> --by "owner in <bot> chat"`. That records your yes in `<job>/gates/`.
- **On your own computer:** your phone records your tap the same way, through `FLEET_ASK_CMD` (Moshi). Or you answer the lead's own question card.
- **By a front door** (`--front-door`, on the Herdr TUI or on Herdr Core): the gate is a post in `<job>/outbox/`. The front door shows you the exact action. On your yes in its chat, it runs the post's approve line as written: `stampede approve-gate <job> <gate> --sha <commit> --digest <d> --by "owner in <chat>: '<your words>'"`.
  If you already gave a clear order there for that exact action, it counts, quoted. Anything vaguer goes back to you.

## Which yes counts

- **The lead acts on** one of these two:
  - your yes typed in its pane for that exact action. Only a Claude lead on the Herdr TUI takes this, and never for a merge or a push to the default branch;
  - a recorded yes for one gate at one commit. `stampede gate-ok <job> <gate> --sha <the commit it acts on>` prints `APPROVED` only when the record names that gate and that commit.
- **`approve-gate` refuses** inside Herdr, for a job started locally, and for another commit. An agent's own say-so never counts. Nor does a plan, a brief or a yes passed on in a message.
- **A yes covers the gate exactly as you were asked it.** The record holds a digest (a fingerprint) of the gate's action, PR, commit and route. If the gate changes after your yes, `gate-ok` refuses.
  The bot's `approve` command carries the same digest (`--digest`), so a gate that changed between the question and your yes gets no yes.
- **`stampede finish` cancels** every question of the job still waiting on your phone.
- **A Codex lead counts only the recorded yes.** stampede types its inbox into its pane, marked as from stampede, so text there proves nothing.
- **On Herdr Core only the recorded yes counts.** A yes typed into the lead, an answer to its own question card, and any message never count, because on Core another program can type into any terminal (`hc send`, `hc keys`).
  To a typed yes the lead replies: "A typed yes does not count on Core; answer in the chat or on the phone that started this job." Your tap on a phone card and a bot's `approve-gate` are recorded, so they count.
- **`approve-gate` refuses inside Herdr Core too:** in a Core terminal (`HC_TERMINAL_ID`, `HC_TERMINAL_SOCKET` or `HC_SCOPE` set) and under a `herdr-core` or `hc` process, so `hc exec` cannot run it. A bot runs it over plain ssh.
  Core's own `blocked` state is never a gate.

## Three gates the code holds

- **Merge.** The lead merges only with `stampede merge <job> <pr> --sha <sha> --review <report> --gate <id>`.
  - Whatever the settings, the review report's header must say exactly `Status: PASS` and `Reviewed: <sha>` ([Troubleshoot](TROUBLESHOOT.md) has its format). The PR must be open, with that sha as its head.
  - With `gates.merge` on, the gate must be one asked with `--kind merge` for that PR, and approved at that sha.
  - Every new head, a rebase too, needs a review report that names it.
  - Then it marks a draft ready and runs `gh pr merge <pr> --squash --match-head-commit <sha>` (`merge.method`). So a push after the review or the yes means a new review and a new ask.
- **Push to the default branch** (the repo's main line, such as `main`).
  - `stampede new` installs a `pre-push` hook (marked `# stampede-hook`) in the repo's own hooks folder. It does so only when there is no `pre-push` and `core.hooksPath` is unset. A repo with a hook of its own gets no push gate from a hook, and `new` says so.
  - A push from your own shell outside a job (neither `STAMPEDE_JOB_KEY` nor `HERDR_WORKSPACE_ID` set) is never touched.
  - A job's agent pushing to the default branch needs a gate asked with `--kind push_default_branch` and approved at the pushed commit.
  - The default branch is the one `stampede new` found for each remote (its HEAD), else `refs/remotes/<remote>/HEAD`, else `main` and `master`.
  - Only `stampede prepush`'s own refusal (exit 9) stops a push. A missing, old or failing stampede lets the push through, with one warning line.
- **Close.** A whole job never closes from one of its own terminals. `stampede close` never ends a terminal that carries another job's key. It skips that terminal, its branch of the tree and the terminals above it (`SKIPPED ...`), and exits 1.

These guard against a forgetful agent, not a hostile one. An agent runs as your user, so it could edit the record, or skip a hook with `git push --no-verify`.

## Switching a gate off

Every gate is on by default (`[gates]` in [Configure](CONFIGURE.md)). You may switch one off, and stampede logs it.

- For one job: `stampede new --file <ask.md> --no-gate merge` (repeatable, the same as `--set gates.merge=false`).
- For every job: your own `config.toml`. A repo's `.stampede.toml` can never switch a gate off.

`stampede new` records the job's gates, and each remote's default branch, outside the job folder, in `$HERDR_EVENTS_DIR/gates/<job key>.json`.
`stampede merge`, the hook, the lead's brief and `finish` read them there. A job with no record has every gate on.
Each gate that is off shows in:

- a line `<UTC time> OFF <name> (<layer>)` in `<job>/gates.log`;
- the lead's brief;
- `stampede config show --job <job>`;
- `stampede finish`, which prints `gates off: <names>` and sends it with the done event.

Two rules have no switch: never close what the job did not create, and merge only the reviewed commit.

## Always true

- **Auto mode by default, never no-checks mode.** Claude `--permission-mode auto`, Codex `--approve-for-me`, Cursor `--auto-review`, Hermes its default (a dangerous command asks), Kimi `-y` (a risky action asks).
  `stampede start --yolo-in <worktree>` runs a worker in its CLI's no-checks mode, but only when its pane's shell sits in its own linked git worktree (a second working copy of the repo). Never the lead.
- **Plan approval** (only when you asked to see the plan) lets the lead work inside the job's own folder and branch. It is not a gate, and covers no merge or spend.
- **Nothing closes by itself,** unless you switch on `finish.auto_close` ([Configure](CONFIGURE.md#every-key-with-its-default)). The last step is always the question whether to close. No answer is a no.
- **Never touched:** panes, tabs and workspaces the lead did not create; the pane you have focused; credentials and `.env` files.
