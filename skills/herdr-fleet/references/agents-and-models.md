# Agents and models

How to pick the agent, model and effort for each lane. The flags and quirks of each CLI are in [clis.md](clis.md).

## Roles are settings

- `stampede start <job> <role>-<scope>` takes its kind, model and effort from the setting `roles.<role>` (the role is the name up to its first `-`), else `roles.default`. A flag given wins. A role's model and effort go only with its own kind.
- `stampede config show` prints the current choice for every role and the layer that set it; `--set roles.build.effort=high` changes one for a command.
- **Effort, by default:** the lead at `xhigh` on either CLI and every worker at `medium`.
- The roles: `build` (implementation against the spec), `research` (with the browser), `review` and `qa` (another vendor than build), `design` (direction and design review), `copy` (docs and copy), `test` (tests and quick mechanical edits), `default` (any other).
- **The lead:** `stampede new --lead claude|codex` (the setting `lead.kind`), `--lead-model` and `--lead-effort` (the settings `lead.<its CLI>.model` and `.effort`).
- `FLEET_LEAD_MODEL` and `FLEET_LEAD_EFFORT` set them as a pair, only for the CLI the model belongs to: a `gpt-...` model sets a Codex lead, any other a Claude lead. A restarted lead keeps its CLI and model. `--fork` takes a Claude lead.
- The owner can enforce the lead list with `lead.allow` and cap workers with `workers.forbid` and `workers.max_effort` ([Configure](../../../docs/CONFIGURE.md)).

## Thinker and doer

The default shape; the owner can change it per job.

- **The lead thinks:** extra high effort. It plans once and writes a tight spec per task: what to build, which files, what done looks like, which tests to run.
- **Workers do:** medium effort, reviewers and researchers too. Builders follow the spec and do not redesign it.
- **Tests** run after each builder step (a cheap check the brief names); the lead runs the full checks once after integration.
- **Review:** one pass on a different model than the builder, which does not share the builder's blind spots ([review.md](review.md)).
- **Proof frames** only for UI changes the owner will look at.

## Pick for the task

Every worker here runs at `medium`, the default; only the lead row names an effort.

| Task | Pick | Fallback |
|---|---|---|
| Lead, planning, briefs | Claude `claude-opus-5-5` or `claude-fable-5-2` at `xhigh`; Codex `gpt-6.2-sol` or `gpt-6.2-astra` at `xhigh` with `--lead codex` | another of these four |
| Plan review (only if the owner asks, or the plan is high risk) | Codex `gpt-6.2-sol` for a Claude plan or Claude `claude-opus-5-5` for a Codex plan | choose a different model from the planner's |
| Architecture, hard trade-offs | Claude `claude-opus-5-5`, with a Codex `gpt-6.2-sol` second opinion | Codex `gpt-6.2-sol` |
| Implementation against the spec | Claude `claude-opus-5-5`; `claude-sonnet-5-5` for coding the spec fully covers; Codex `gpt-6.2-sol` for a parallel slice | the other vendor |
| Independent review, QA | Codex `gpt-6.2-astra` | Claude `claude-opus-5-5` if the builder used Codex |
| Research with the browser | Claude `claude-opus-5-5` (BrowserOS Neo, MCP tools) | Codex `gpt-6.2-sol` with `--search` (no Neo) |
| Design direction, design review | Codex `gpt-6.2-astra` | Claude `claude-opus-5-5` |
| Images, layered HTML images | Codex `gpt-6.2-sol` | Claude `claude-opus-5-5` |
| Docs and copy | Claude `claude-opus-5-5` | Codex `gpt-6.2-sol` |
| Quick mechanical edits | Claude `claude-sonnet-5-5` or Codex `gpt-6.2-sol` | the other of those two |

- Use Claude `claude-sonnet-5-5` or Codex `gpt-6.2-sol` for fully specified bulk work.
- Codex is the second vendor: the end review, design direction, a parallel slice. Hermes, Kimi and Cursor run when the plan or the owner names them ([clis.md](clis.md#other-kinds)).
- A plan may give each lane a `fallback` column; it wins over the table.

## Fallback

- Never substitute a model the owner named: when it is unavailable or at capacity, say so and wait or ask.
- Any other lane moves to its fallback on a usage limit, or on "at capacity" again after one retry. A Claude usage limit covers every Claude model, so Claude lanes fall back to Codex.
- To move a lane: exit the agent, start the fallback in the same pane under the same name (on another CLI, with its `--model` and `--effort`: a role's model goes only with its own kind), and prompt it with its brief plus one line: it takes over from the stopped agent, whose work is on disk (`git status`) and in any partial report.
- A lead falls back the same way: `stampede start <job> <lead> --kind claude|codex --pane <its pane> --brief <job>/briefs/<lead>.md` (the Herdr TUI only).
- Note the switch in `register.md` and in the report.
