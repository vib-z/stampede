# Worked example: a lead, two builders and a reviewer

A feature with a server half and a UI half. The lead is `lead-alerts`, started with its hooks by `fleet-job new --file <ask.md> --name alerts` in the project workspace, which made the job folder `$REPO/.herdr-alerts`. `build-api` is Claude Opus 5.5 at xhigh, `build-ui` is Codex `gpt-6.1-sol` at xhigh, and `review-alerts` is Claude Fable 5.1 at max. Each builder gets its own worktree because both halves touch shared code. Run everything from the lead's pane. IDs come from JSON responses, never from these examples. External callers (over ssh): see "Where are you?" in SKILL.md and put literal ids where this example uses `$HERDR_WORKSPACE_ID`.

## 1. Contract, briefs, register (lead)

```bash
REPO=<abs repo dir>
WT=$REPO/.claude/worktrees
B=$REPO/.herdr-alerts
git -C "$REPO" fetch origin main
git -C "$REPO" worktree add "$WT/alerts" -b claude/alerts origin/main     # the lead's integration worktree
ln -s "$REPO/node_modules" "$WT/alerts/node_modules"   # never copy .env.local or any env file: the owner adds keys
mkdir -p "$B/reports"
echo ".herdr-alerts/" >> "$(git -C "$REPO" rev-parse --git-common-dir)/info/exclude"
```

In `$WT/alerts`, the lead writes the contract (`src/lib/alerts/types.ts`, stub files, one validation test) and commits it. Then it writes:
- `$B/_common.md`: the ownership rules from [collaboration.md](collaboration.md), the dev-server ports (api 3151, ui 3152) and project facts.
- `$B/build-api.md` and `$B/build-ui.md`, on the [hand-off template](brief.md), shaped like this:

```markdown
# Brief: build-api
## Goal
Build the alert rules API and hourly evaluator, as specified in the contract.
## Why
You build the server half of the alerts feature; a separate worker builds the UI. Your lead committed the shared contract so both halves agree.
## Inputs
Read /abs/path/.herdr-alerts/_common.md first.
Worktree: /abs/path/.claude/worktrees/alerts-api, branch alerts/api, starting commit <contract commit>.
You own, under that worktree: src/app/api/alerts/**, src/lib/alerts/server.ts, tests/alerts-api.test.ts.
Read its src/lib/alerts/types.ts contract.
## Constraints
Follow _common.md. Commit only to alerts/api. Do not change the contract; propose changes in your report.
## Done when
- `npx vitest run tests/alerts-api.test.ts` passes and the API and hourly evaluator match the contract.
## Report back
Write /abs/path/.herdr-alerts/reports/build-api.md last, under 60 lines: Status: DONE in the first 10 lines, what changed, files touched, unverified and decisions.
## If blocked
Your lead decides: write /abs/path/.herdr-alerts/questions/build-api.md, say so in your last message and end your turn. Make the reasonable call where you can and record it.
```

- `$B/register.md`: a roster table (agent, kind, model and effort, pane, worktree, port, status) and a "next step" line.

## 2. Worktrees, tab and panes (lead)

```bash
for s in api ui; do
  git -C "$REPO" worktree add "$WT/alerts-$s" -b "alerts/$s" claude/alerts
  ln -s "$REPO/node_modules" "$WT/alerts-$s/node_modules"   # no env file copied
done
T=$(herdr tab create --workspace "$HERDR_WORKSPACE_ID" --cwd "$WT/alerts-api" --label alerts --no-focus) # external caller: literal id, e.g. --workspace w1
TAB=$(echo "$T" | jq -r .result.tab.tab_id)
PA=$(echo "$T" | jq -r .result.root_pane.pane_id)
herdr pane layout --pane "$PA" | jq --arg p "$PA" '.result.layout.panes[] | select(.pane_id==$p) | .rect'   # this pane's own size (.area is the tab); split right only if both halves keep 80 columns
PU=$(herdr pane split --pane "$PA" --direction right --cwd "$WT/alerts-ui" --no-focus | jq -r .result.pane.pane_id)
herdr pane rename "$PA" build-api
herdr pane rename "$PU" build-ui
```

## 3. Start and brief the builders

```bash
# each: auto mode, the job's hooks, --add-dir "$B" for Codex, the reopen record, then the brief pointer
fleet-job start "$B" build-api --kind claude --pane "$PA" --brief "$B/build-api.md" --model claude-opus-5-5 --effort xhigh --report reports/build-api.md
fleet-job start "$B" build-ui --kind codex --pane "$PU" --brief "$B/build-ui.md" --model gpt-6.1-sol --effort xhigh --report reports/build-ui.md
herdr-reopen-snapshot "$HERDR_WORKSPACE_ID" "$B"   # REOPEN.md and reopen.sh in $B; Codex reports its session id after its first turn, so refresh later too
```

- If a start prints `BLOCKED`, read the screen, clear the startup dialog yourself ([unattended-setup.md](unattended-setup.md)), then send the `fleet-job tell` line it printed. If a start is denied by the classifier, stop and hand the owner those two `fleet-job start` lines, expanded with the real pane ids, to run as `!` commands.
- If Codex shows "Trust this folder?" (a folder it has never opened), send `herdr agent send-keys build-ui enter`. When it then shows "Hooks need review", run `herdr agent rename "$PU" build-ui` if the name is missing, then `herdr agent send-keys build-ui down down enter` (continue without trusting), then `herdr agent wait build-ui --until idle --timeout 30000`. If Codex first shows "Update available", send `herdr agent send-keys build-ui esc` (Enter would update it). Read every pane's screen once before its first prompt: some dialogs show as `idle`.
- Check the real model on each screen with `herdr agent read <name> --source visible --lines 40`. Claude prints the model and effort, and Codex prints it in its status line.
- Update `register.md` with panes and status.

## 4. Wait for the hooks

The lead does its own work (docs, gates, the next brief), then ends its turn. A builder's finished report, turn end, question or exit adds a line to `$B/inbox.log` (`REPORT reports/build-api.md`, `TURN`, `QUESTION`, `GONE`), and that line wakes the lead. No Monitor, no `herdr agent wait`, no polling; `fleet-watch.sh` is only for a bot outside Herdr.

## 5. Integrate (lead)

On `REPORT .../build-api.md`, read the report and the diff, then merge:

```bash
git -C "$WT/alerts" merge --no-ff alerts/api -m "alerts: merge build-api"
```

Do the same for `build-ui`. Then run the full gates once in `$WT/alerts` (type check, lint, whole suite, build).

## 6. Independent review

```bash
git -C "$REPO" worktree add --detach "$WT/alerts-review" claude/alerts
PR=$(herdr pane split --pane "$PU" --direction down --cwd "$WT/alerts-review" --no-focus | jq -r .result.pane.pane_id)
herdr pane rename "$PR" review-alerts
fleet-job start "$B" review-alerts --kind claude --pane "$PR" --brief "$B/_review.md" --model claude-fable-5-1 --effort max --report reports/review-alerts.md
herdr-reopen-snapshot "$HERDR_WORKSPACE_ID" "$B"
```

`_review.md` uses the [hand-off template](brief.md):
- Goal: independently review the alerts feature; Why: you did not build it and it will ship.
- Inputs: read `_common.md` first, then the absolute worktree path, branch, starting commit, diff (`git diff origin/main...HEAD`) and builder briefs.
- Constraints: small fixes outside the builders' files only; report everything else, under the ownership rules.
- Done when: check correctness, security, data loss, then style, with proof for numbered findings `R1..Rn`.
- Report back: the absolute report path, under 60 lines, `Status: PASS` or `Status: FINDINGS` in the first 10 lines, files touched, unverified and decisions.
- If blocked: write the lead's question file, say so and end your turn; make and record reasonable calls.

For a cross-vendor second pass in a plain pane, add `herdr pane run <pane> "codex review --base origin/main"`.

## 7. Fix round

The lead triages the review into `$B/fixes-api.md` and `$B/fixes-ui.md` on the [hand-off template](brief.md), referencing unchanged sections from the original briefs. It fast-forwards each builder to the integration branch and prompts them:

```bash
git -C "$WT/alerts-api" merge --ff-only claude/alerts
git -C "$WT/alerts-ui" merge --ff-only claude/alerts
herdr agent prompt build-api "Review round 1: read $B/fixes-api.md and fix each finding, one commit per finding, same checks. Append 'Review fixes, round 1' to your report."
herdr agent prompt build-ui "Review round 1: read $B/fixes-ui.md and fix each finding, one commit per finding, same checks. Append 'Review fixes, round 1' to your report."
```

When both reports update, the lead:
1. merges the fixes;
2. moves the review worktree with `git -C "$WT/alerts-review" checkout --detach claude/alerts`;
3. updates `_review.md` on the same template to recheck only R1-R5 at the integration commit, then sends `herdr agent prompt review-alerts "Round 2: read $B/_review.md; append to your report."`

Stop at "ship". After two rounds the lead decides.

## 8. Wrap up

- Push `claude/alerts` and open a draft PR (no need to ask). Write `Reviewed: alerts <sha>` in the register. Ask the owner before the merge, and on a yes run `gh pr merge <n> --squash --match-head-commit <sha>`.
- Keep the builder worktrees and branches until the PR merges.
- Write the register's final state (commits, what was verified, what is left for the owner) and refresh the reopen record: `herdr-reopen-snapshot "$HERDR_WORKSPACE_ID" "$B"`.
- Leave every pane and tab open. End with a short summary and one question to the owner in the lead pane (AskUserQuestion; external callers: in their own chat): "Close the alerts tab? Reopen with $B/reopen.sh."

Only after the owner's explicit yes (17 Oct 2026 rule), and as the last step:

```bash
herdr agent prompt build-api "/exit"
herdr agent prompt review-alerts "/exit"
herdr agent prompt build-ui "/quit"
for n in build-api review-alerts build-ui; do herdr agent wait "$n" --until unknown --timeout 30000; done   # each ends with agent_not_running once exited
herdr-reopen-snapshot "$HERDR_WORKSPACE_ID" "$B"   # keeps the exited agents' sessions from the earlier snapshots
herdr pane close "$PR"; herdr pane close "$PU"; herdr tab close "$TAB"   # only what the fleet created; the lead's tab stays
git -C "$REPO" worktree remove "$WT/alerts-review"
```

The lead's tab lives in the owner's project workspace, so there is no owner tag to clear and no workspace to close. A fleet that created its own workspace clears its tag (`herdr-events-owner <ws> --clear`) and then runs `herdr workspace close <ws>` instead of the pane and tab closes.
