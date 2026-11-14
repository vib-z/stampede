# Worked example: a lead, two builders and a reviewer

A feature with a server half and a UI half, on the Herdr TUI. `stampede new --file <ask.md> --name alerts` in the project workspace started the lead and made the job folder `<jobs_root>/jobs/<date>-local-alerts`. `build-api` takes its model from `roles.build`, `review-alerts` from `roles.review`; `build-ui` runs on Codex and names its own.
Each builder gets a worktree because both halves touch shared code. Ids come from Herdr's JSON, never from this page; from outside Herdr, see [tui.md](tui.md#from-outside-herdr).

## 1. Contract, briefs, register

```bash
REPO=<abs repo dir>; WT=<jobs_root>/worktrees; B=<the job folder new printed>
git -C "$REPO" fetch origin main
git -C "$REPO" worktree add "$WT/alerts" -b alerts origin/main     # the lead's integration worktree
ln -s "$REPO/node_modules" "$WT/alerts/node_modules"               # never copy an env file: the owner adds keys
```

In `$WT/alerts` the lead commits the contract (`src/lib/alerts/types.ts`, stubs, one validation test), then writes:
- `$B/_common.md`: the [ownership rules](collaboration.md#ownership-rules-paste-into-every-commonmd), the dev-server ports (api 3151, ui 3152) and project facts.
- `$B/briefs/build-api.md` and `build-ui.md` on the [hand-off template](brief.md), such as:

```markdown
# Brief: build-api
## Goal
Build the alert rules API and hourly evaluator, as the contract specifies.
## Why
You build the server half of alerts; another worker builds the UI. The lead committed the shared contract so both halves agree.
## Inputs
Read <job>/_common.md first. Worktree <jobs_root>/worktrees/alerts-api, branch alerts-api, from <contract commit>.
You own src/app/api/alerts/**, src/lib/alerts/server.ts and tests/alerts-api.test.ts. Read src/lib/alerts/types.ts.
## Constraints
Follow _common.md. Commit only to alerts-api. Do not change the contract; propose changes in your report.
## Done when
- `npx vitest run tests/alerts-api.test.ts` passes, run after the step and before the report.
## Report back
<job>/reports/build-api.md, last, under 60 lines: Status: DONE in the first 10 lines, what changed, files, unverified, decisions.
## If blocked
Write <job>/questions/build-api.md, say so in your last message and end your turn; make the reasonable call where you can.
```

- `$B/register.md`: a roster (agent, kind, model and effort, pane, worktree, port, status) and a "next step" line.

## 2. Worktrees, tab, panes, starts

```bash
for s in api ui; do
  git -C "$REPO" worktree add "$WT/alerts-$s" -b "alerts-$s" alerts
  ln -s "$REPO/node_modules" "$WT/alerts-$s/node_modules"
done
T=$(herdr tab create --workspace "$HERDR_WORKSPACE_ID" --cwd "$WT/alerts-api" --label alerts --no-focus)
TAB=$(echo "$T" | jq -r .result.tab.tab_id); PA=$(echo "$T" | jq -r .result.root_pane.pane_id)
PU=$(herdr pane split --pane "$PA" --direction right --cwd "$WT/alerts-ui" --no-focus | jq -r .result.pane.pane_id)   # after checking 80 columns each
stampede start "$B" build-api --pane "$PA" --brief "$B/briefs/build-api.md" --report reports/build-api.md
stampede start "$B" build-ui --kind codex --model gpt-6.1-sol --effort medium --pane "$PU" --brief "$B/briefs/build-ui.md" --report reports/build-ui.md
herdr-reopen-snapshot "$HERDR_WORKSPACE_ID" "$B"   # again after Codex's first turn, which reports its session id
```

- A builder moved to another CLI names its model and effort: a role's model goes only with its own kind, so `--kind codex` alone gets the CLI's default, which can be the reviewer's model.

- Read each screen before anything else (`herdr agent read build-ui --source visible --lines 40`): it shows the model too. A `BLOCKED` start or a dialog shown as `idle`: clear it ([unattended-setup.md](unattended-setup.md#startup-dialogs-the-lead-clears)), then send the printed `stampede tell` line.
- A start the classifier denies: stop and hand the owner the two `stampede start` lines, with the real pane ids, to run as `!` commands.
- Update `register.md` with panes and status.

## 3. Wait, then integrate

The lead does its own work, then ends its turn. A builder's report, turn end, question or exit adds a line to `$B/inbox.log` (`REPORT reports/build-api.md`, `TURN`, `QUESTION`, `GONE`), which wakes it.
On each `REPORT`, read the report and the diff, then merge that lane's branch:

```bash
git -C "$WT/alerts" merge --no-ff alerts-api -m "alerts: merge build-api"   # on REPORT reports/build-api.md
git -C "$WT/alerts" merge --no-ff alerts-ui -m "alerts: merge build-ui"     # on REPORT reports/build-ui.md
```

With both in, run the full checks once (type check, lint, suite, build).

## 4. Review

```bash
git -C "$REPO" worktree add --detach "$WT/alerts-review" alerts
PR=$(herdr pane split --pane "$PU" --direction down --cwd "$WT/alerts-review" --no-focus | jq -r .result.pane.pane_id)
stampede start "$B" review-alerts --pane "$PR" --brief "$B/briefs/_review.md" --report reports/review-alerts.md
herdr-reopen-snapshot "$HERDR_WORKSPACE_ID" "$B"
```

`_review.md` is on the same template: Goal, an independent review; Why, it will ship; Inputs, `_common.md`, the worktree, branch, diff (`git diff origin/main...HEAD`) and the builder briefs.
Constraints, small fixes outside the builders' files only; Done when, numbered findings `R1..Rn` with proof for correctness, security, data loss and regressions, nits listed but not sent back; Report back, the header of [review.md](review.md#the-report-header).

## 5. Fix only real bugs

For real bugs only, the lead writes `$B/briefs/fixes-api.md` and `fixes-ui.md` on the template, then:

```bash
git -C "$WT/alerts-api" merge --ff-only alerts; git -C "$WT/alerts-ui" merge --ff-only alerts
stampede tell "$B" build-api "Review fixes: read $B/briefs/fixes-api.md; one commit per finding, same checks; append 'Review fixes' to your report."
stampede tell "$B" build-ui "Review fixes: read $B/briefs/fixes-ui.md; one commit per finding, same checks; append 'Review fixes' to your report."
```

When both reports update: merge the fixes, `git -C "$WT/alerts-review" checkout --detach alerts`, point `_review.md` at those ids at the new commit, and `stampede tell "$B" review-alerts "Recheck: read $B/briefs/_review.md; append to your report."` Stop at pass.

## 6. Merge and wrap up

```bash
(cd "$WT/alerts" && git push -u origin alerts && gh pr create --draft --fill)  # in the worktree; no need to ask
stampede ask "$B" --gate --kind merge --sha <sha> --pr <n> "merge PR <n>"        # GATE <gate>
stampede gate-ok "$B" <gate> --sha <sha>                                         # once the owner said yes: APPROVED
stampede merge "$B" <n> --sha <sha> --review "$B/reports/review-alerts.md" --gate <gate>
stampede finish "$B" "PR <n> merged at <sha>"
```

- Write `Reviewed: alerts <sha>` and the final state in `register.md`; keep the builder worktrees and branches until the PR merges; refresh the reopen record.
- Leave every pane open and ask the owner last: "Close the alerts tab? Reopen with $B/reopen.sh."

Only on an explicit yes:

```bash
herdr agent prompt build-api "/exit"; herdr agent prompt review-alerts "/quit"; herdr agent prompt build-ui "/quit"
for n in build-api review-alerts build-ui; do herdr agent wait "$n" --until unknown --timeout 30000; done   # agent_not_running once each exits
herdr-reopen-snapshot "$HERDR_WORKSPACE_ID" "$B"
herdr pane close "$PR"; herdr pane close "$PU"; herdr tab close "$TAB"; git -C "$REPO" worktree remove "$WT/alerts-review"
```

The lead's tab is in the owner's project workspace, so there is no owner tag to clear and no workspace to close.
