# Claude as the remote

You talk to a Claude Code session on your machine from the Claude app or claude.ai/code, through Claude Code's Remote Control. The session runs on the machine, so it needs no SSH: it is the front desk: it writes your ask to a file, hands the job to its lead in Herdr (`stampede new --file`) and stops. The lead asks you everything; with Remote Control on for every session, the lead's row shows in the Claude app too.

## Do
- Start one Claude Code session with Remote Control, in a Herdr pane of its own.
- Open it from the phone and type the ask.
- The session reads stampede's entry file and starts the job; the lead plans and goes unless you ask to see the plan first.
- Ask it for status whenever you like; it reads the job, it does not guess.
- It passes on only your plan approval and your ordinary answers, word for word. Every gate (merge, push to main, deploy, publish, send, spend, close) is your own tap on the lead's card, never relayed.
- For pushes while you are away, pair Moshi too.

## Run
```bash
claude --remote-control "stampede"           # in a Herdr pane on the machine; or /remote-control inside a session
```
```text
Read the stampede SKILL.md and start this job: <the ask>
What is the stampede job doing?               # the session reads <job dir>/plan.md and the reports
Tell the lead: <your answer or change>         # the session runs: stampede tell <job dir> lead "..."
Approve the plan                               # review jobs only; the session runs: stampede approve <job dir> --by "Claude app"
```

- **Needs:** a Claude plan that includes Remote Control, signed in on the machine. Setup and limits: [Remote Control](https://code.claude.com/docs/en/remote-control).
- **Events:** the session lives inside Herdr and needs no webhook; the lead's own questions reach you in the Claude app and through Moshi.
- **Keep the machine awake;** the session reconnects when the machine comes back.
- The rules every remote follows: [README.md](README.md).

## Plan here, then fork the lead
Talk the job through with Claude first, in the Claude desktop app or any Claude Code chat on the machine. Once the plan is agreed, say "start it with stampede, forked from this chat". The chat writes the ask with the agreed plan, makes a workspace for the job and starts the lead as a fork of itself:

```bash
P=$(herdr workspace create --cwd <repo> --label <job> --no-focus | jq -r .result.root_pane.pane_id)
stampede new --file <ask.md> --pane "$P" --fork "$CLAUDE_CODE_SESSION_ID"
```

- The lead runs `claude --resume <id> --fork-session` with the lead's hooks, so it starts with the whole conversation, and writes the agreed plan into `plan.md` instead of planning again. Your chat is left as it was.
- **The ask file stays the source of truth.** The fork carries the chat's saved transcript, and a saved transcript can miss some of the chat's messages (seen in the Claude desktop app on 28 Oct 2026: tool calls and results were all there, some plain replies were not). Put the agreed plan and every fact the lead must not miss in the ask.
- Claude Code sets `CLAUDE_CODE_SESSION_ID` in every session; the chat's folder can differ from the repo.
- The fork carries the chat's whole context into the lead, so fork a focused planning chat, not a long one.
- `reopen.sh` resumes the lead's own session, never the planning chat.
- **On Herdr Core:** no workspace; the chat runs `stampede new --core --file <ask.md> --cwd <repo> --fork "$CLAUDE_CODE_SESSION_ID"` ([core.md](../skills/herdr-fleet/references/core.md)).
