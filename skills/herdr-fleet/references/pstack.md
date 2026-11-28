# pstack inside a fleet

pstack is a set of working rules for a coding agent: data shape first, a contract commit, a todo list with a reason for each skip, and proof on the real surface.
It is on by default for coding jobs (the setting `dev.pstack`), and optional: a job runs without it.

- **When it applies.** `stampede new` looks for pstack where the lead's CLI loads it from ([Setup](../../../docs/SETUP.md#pstack)). When it finds it, your brief says so and names the command that loads it.
  - On Claude that is `/pstack:poteto-mode` or `/poteto-mode`; on Codex, `$pstack:poteto-mode` or `$poteto-mode`.
  - A brief with no such sentence means pstack is switched off or not installed, and nothing here applies.
- **Whose it is.** pstack is Lauren Tan's ([cursor/plugins](https://github.com/cursor/plugins/tree/main/pstack), MIT, commit `9e278fe`).
  - stampede recommends the port [michael-denyer/pstack-claude](https://github.com/michael-denyer/pstack-claude) (MIT, the plugin `pstack@pstack-claude`). These rules were read against 0.9.112 at commit `22b5e13` and checked again at 0.9.159, commit `b15f9d8`.
  - The mirror [backnotprop/pstack](https://github.com/backnotprop/pstack) (MIT, commit `10a2937`) holds the same skills as plain folders.

pstack's playbooks assume one session with built-in subagents, so in a fleet these rules win wherever pstack says otherwise.

0. **Coding jobs only.** You decide from the ask. Use pstack's playbooks for coding work (features, fixes, refactors, reviews) and leave them alone on any other job (research, writing, ops).
1. **Fan-out runs as panes.** Every pstack step that spawns agents (how explorers, architect and arena runners, design panels, interrogate, swarm, comment-sicko, thermos reviewers) runs as a Herdr pane on another model, or is skipped with a one-line reason in `todo.md`. Never as a hidden built-in Agent or Task subagent ([SKILL.md, Hard rules](../SKILL.md#hard-rules)).
2. **The fleet's roles win.** Each pane's app, model and effort come from its role ([agents-and-models.md](agents-and-models.md)), not pstack's role models (`sonnet` for feature work, `opus`, `fable`) or a `pstack-models.md` sheet.
3. **Herdr ownership wins.** The Feature playbook's "own worktree per delegate" and "commit liberally" give way to [collaboration.md](collaboration.md): only the lead commits to shared branches and in a shared worktree; a worker in a worktree of its own commits only to its branch.
4. **The architect sketch becomes the contract commit.** Turn pstack architect's sketch (types, signatures, module structure) into the lead's contract: the types, stubs and one failing test ([SKILL.md, The lead](../SKILL.md#the-lead), item 4). Commit it once, before any worker starts.
5. **The todo list is a file.** Keep pstack's todo list as `todo.md` in the job folder, not in the task tools. It survives a restart and `reopen.sh`, the owner and any bot that started the job can read it, and it needs no setup. Do not set `CLAUDE_CODE_ENABLE_TODO_TOOLS=1` for it: that changes every lead's start and keeps the list inside one session.
