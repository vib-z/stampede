# Codex as the remote

You talk to Codex on your own computer from the ChatGPT phone app. The Codex session runs on the machine, so it needs no SSH: it is the front desk: it writes your ask to a file, creates a workspace for the job and hands the job to its lead in that workspace's root pane (`stampede new --file <ask.md> --pane <id>`, since Codex runs outside Herdr) and stops; it passes your answers on to that lead.

## Do
- Connect the machine to ChatGPT once, from the ChatGPT desktop app.
- On the phone, open Codex and pick the connected machine.
- Type the ask; Codex reads stampede's entry file and starts the job.
- Approve Codex's commands from the phone when it asks.
- Ask for status whenever you like. Codex passes on only your plan approval and your ordinary answers; every gate (merge, push to main, deploy, publish, send, spend, close) is your own tap on the lead's card, which Moshi puts on your phone.
- For pushes from every pane, pair Moshi too.

## Run
```text
Read the stampede SKILL.md and start this job: <the ask>
What is the stampede job doing?               # Codex reads <job dir>/plan.md and the reports
Tell the lead: <your answer or change>         # Codex runs: stampede tell <job dir> lead "..."
Approve the plan                               # review jobs only; Codex runs: stampede approve <job dir> --by "Codex"
```

- **Needs:** the ChatGPT desktop app on a Mac or Windows PC, the same account on both devices, remote access approved, the machine awake and online. Setup: [Codex on mobile](https://developers.openai.com/codex/remote).
- **Linux:** connecting a computer is not offered there; use Grok Bot or Moshi instead.
- **Cloud tasks** run in OpenAI's cloud and cannot reach your Herdr. Use the connected machine.
- **Events:** a Codex session cannot be woken by another agent, so the lead's questions and gates reach you through Moshi.
- The rules every remote follows: [README.md](README.md).
