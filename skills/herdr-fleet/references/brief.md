# Hand-off brief

Write for an agent that has seen nothing else: not the ask, the plan or your lead's chat. Give it everything it needs to act on its own. A brief with a missing or empty section is not ready; `fleet-job start` refuses it.

## Goal
<The outcome in one or two sentences, not the steps.>

## Why
<Who this is for, what came before, decisions already made and their reasons: the context you need to make good calls.>

## Inputs
<Absolute paths to read first, links, worktree, branch, starting commit and the files you own.>

## Constraints
<Rules and anti-goals: what not to change, scope to stay out of, commands to avoid; use the ownership rules in collaboration.md or your job's _common.md.>

## Done when
<A checklist you can verify yourself: commands that pass, files that exist and behaviour to show.>

## Report back
<Your report's absolute path and shape: Status: DONE (a review: PASS or FINDINGS) in the first 10 lines; what changed, files touched, not verified and decisions, under 60 lines.>

## If blocked
<Your lead decides: write the question to <job>/questions/<agent>.md (a Claude worker can use its question card, which does that), say so in your last message and end your turn; make the reasonable call where you can and record it.>

A follow-up task to a running worker (such as `fixes-<scope>.md`) carries the same sections, and may say "as in <brief>" for a section that has not changed.
