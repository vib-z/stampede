# Agents and models

How to pick the agent, model and effort for each lane. The flags and quirks of each CLI are in [clis.md](clis.md).

## Roles are settings

- `stampede start <job> <role>-<scope>` takes its kind, model and effort from the setting `roles.<role>` (the role is the name up to its first `-`), else `roles.default`. A flag given wins. A role's model and effort go only with its own kind.
- `stampede config show` prints the current choice for every role and the layer that set it; `--set roles.build.effort=high` changes one for a command.
- The roles: `build` (implementation against the spec), `research` (with the browser), `review` and `qa` (another vendor than build), `design` (direction and design review), `copy` (docs and copy), `test` (tests and quick mechanical edits), `default` (any other).
- **The lead:** `stampede new --lead claude|codex` (the setting `lead.kind`), `--lead-model` and `--lead-effort` (the settings `lead.<its CLI>.model` and `.effort`).
- `FLEET_LEAD_MODEL` and `FLEET_LEAD_EFFORT` set them as a pair, only for the CLI the model belongs to: a `gpt-...` model sets a Codex lead, any other a Claude lead. A restarted lead keeps its CLI and model. `--fork` takes a Claude lead.
- The owner can override any choice, the effort or the review shape per job.

## Thinker and doer

The default shape; the owner can change it per job.

- **The lead thinks:** high effort. It plans once and writes a tight spec per task: what to build, which files, what done looks like, which tests to run.
- **Builders do:** medium effort. They follow the spec and do not redesign it. Raise a builder to high or xhigh only for a hard task the lead flags in the plan.
- **Tests** run after each builder step (a cheap check the brief names); the lead runs the full checks once after integration.
- **Review:** one pass on a different model than the builder, which does not share the builder's blind spots ([review.md](review.md)).
- **Proof frames** only for UI changes the owner will look at.

## Pick for the task

| Task | Pick | Fallback |
|---|---|---|
| Lead, planning, briefs | Claude `claude-opus-5-5` xhigh, or Codex `gpt-6-astra` ultra with `--lead codex` | the other of those two |
| Plan review (only if the owner asks, or the plan is high risk) | another vendor than the planner's; the planner then hardens the plan | Codex `gpt-6.1-sol` xhigh or Cursor, never the planner's model |
| Architecture, hard trade-offs | Claude `claude-fable-5-1` max, with a Codex `gpt-6-astra` ultra second opinion | Codex `gpt-6-astra` ultra alone |
| Implementation against the spec | Claude `claude-opus-5-5` medium; `claude-sonnet-5-5` medium for heavy coding the spec fully covers; Codex `gpt-6.1-sol` medium for a parallel slice | the other vendor at medium |
| Independent review, QA | Codex `gpt-6-astra` ultra; Claude `claude-fable-5-1` max when Codex built the work | the other vendor's reviewer, never the builder's model |
| Research with the browser | Claude `claude-opus-5-5` xhigh (BrowserOS Neo, MCP tools) | Codex `gpt-6.1-sol` xhigh with `--search` (no Neo) |
| Design direction, design review | Codex `gpt-6-astra` ultra writes or reviews; a Claude builder implements | Claude `claude-fable-5-1` max |
| Images, layered HTML images | Codex; Grok only sparingly, for videos and the odd photo | none: wait or ask |
| Docs and copy | Claude `claude-opus-5-5` high | Codex `gpt-6.1-sol` high |
| Quick mechanical edits | the lead itself if under 10 minutes, else Claude `claude-sonnet-5-5` or Codex `gpt-6.1-sol` medium | the other of those two |

- Cheap models (`claude-sonnet-5-5`, `claude-haiku-5-5`, `gpt-6.1-sol` medium, `gpt-6-luna`) take fully specified bulk work. A slice that needs judgement is not theirs.
- Codex is the second vendor: the end review, design direction, a parallel slice. Hermes, Kimi and Cursor run when the plan or the owner names them ([clis.md](clis.md#other-kinds)).
- A plan may give each lane a `fallback` column; it wins over the table.

## Fallback

- Never substitute a model the owner named: when it is unavailable or at capacity, say so and wait or ask.
- Any other lane moves to its fallback on a usage limit, or on "at capacity" again after one retry. A Claude usage limit covers every Claude model, so Claude lanes fall back to Codex.
- To move a lane: exit the agent, start the fallback in the same pane under the same name, and prompt it with its brief plus one line: it takes over from the stopped agent, whose work is on disk (`git status`) and in any partial report.
- A lead falls back the same way: `stampede start <job> <lead> --kind claude|codex --pane <its pane> --brief <job>/briefs/<lead>.md` (the Herdr TUI only).
- Note the switch in `register.md` and in the report.
