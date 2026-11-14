# Review

The setting `review.step` sets the review your brief asks for: `end` (the default: one pass at the end of what ships or reaches the owner), `each` (one per pull request or step) or `none` (no reviewer). The reviewer is `review-<scope>`, whose model comes from `roles.review` and is never the builder's. Anything touching terms, money or law is checked as it happens.

## The loop

1. The builder finishes, runs the tests its brief names, writes its report and stops.
2. The lead merges main into the lane's branch (a worktree per agent). On a real conflict: `git merge --abort`, then send the builder the conflicted files and the target commit. Then it integrates and runs the full checks.
3. The reviewer reads `briefs/_review.md` and writes `reports/review-<scope>.md` with numbered findings `R1..Rn`. Each has `file:line`, a **severity** (critical, major, minor, trivial), its **proof** (a command and its output, a failing test, the exact lines) and **pre-existing** yes or no.
   It may fix small things only in files nobody else is editing.
4. The verdict follows from the findings: **pass** when there is no new real bug (broken behaviour, a failing test or a regression; a new critical or major with proof is one), else **fail**. A critical with no proof counts as major.
5. The lead triages. Only new real bugs go into `briefs/fixes-<scope>.md`; a rejected one gets a reason. Nits, minor and trivial notes stay in the review report. Pre-existing findings never send work back: they go in the lead's final report as suggestions.
6. The builder fixes each real bug in its own commit and appends "Review fixes" to its report.
7. The reviewer rechecks only those ids, once. Stop at pass: there is no second loop for style. If a recheck still finds a real bug, the lead decides.

## The report header

A title line, then `Status: PASS` (or `FINDINGS`) and `Reviewed: <the full sha it reviewed>`, each once at the start of a line, in the first 10 lines and before any code block, quote, comment or indented line.
`stampede merge` merges only the sha a passing report names, so every new head needs a report that names it ([gates.md](gates.md)). The lead writes `Reviewed: <lane> <sha>` in `register.md` and moves it only when a new report names the new head.

## A new head

- A clean merge of main, a clean rebase, or a conflict fix that touches only the conflicted files: the reviewer confirms it from `git range-diff <old base>..<reviewed sha> <new base>..<new head>` and writes a short report naming the new sha; the checks run again.
- A message to the builder that changed no files (`git diff <reviewed sha>` is empty): the head did not move; nothing to rerun.
- Anything else reopens the review, for the changed files only.

## Variations

- **Cross-vendor pair:** Claude builds and Codex reviews (the default), or Claude reviews a Codex build.
- **Design track:** Codex writes `design-direction.md`, a Claude builder implements it, and Codex reviews the rendered pages against its own file, in one pass.
- **Peers:** a brief may name both. The builder sends `review-api "build-api: R1-R3 fixed in <sha>"` and the reviewer answers after its one recheck. The lead still merges.
- **Workflow review:** for a big candidate, and only if the owner opted in, a multi-agent review (two refuters per finding) as the independent reviewer.
