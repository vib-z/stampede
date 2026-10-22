# Any machine, part 4: the agent CLIs

The agents do the work. Find which are installed, help the person install the rest from each vendor's page, and get each one signed in and trusting the work folder.

## Do
- List the agent CLIs installed: Claude Code (the lead), Codex, Cursor.
- For each one missing that the person wants, send them its install page; install only on their yes.
- Sign-in on a machine with no browser: send the person the CLI's headless sign-in page; they do it.
- Start each CLI once by hand in the work folder: sign in, accept folder trust, skip update prompts.
- Mark a work folder trusted only on the person's yes.
- Read every new screen; clear startup dialogs; leave anything else to the person.

## Run
```bash
claude --version; codex --version; cursor-agent --version   # which are installed
herdr-trust <work dir>                              # only after the person's yes
```

| CLI | install | sign in with no browser |
|---|---|---|
| Claude Code | [setup](https://code.claude.com/docs/en/setup) | [log in](https://code.claude.com/docs/en/authentication#log-in-to-claude-code) (paste the code shown), or [a long-lived token](https://code.claude.com/docs/en/authentication#generate-a-long-lived-token) |
| Codex CLI | [Codex CLI](https://developers.openai.com/codex/cli) | [login on headless devices](https://developers.openai.com/codex/auth) |
| Cursor Agent | [installation](https://cursor.com/docs/cli/installation) | [authentication](https://cursor.com/docs/cli/reference/authentication) |

How stampede drives each CLI: [agents-and-models.md](../../skills/herdr-fleet/references/agents-and-models.md). Startup dialogs and their fixes: [unattended-setup.md](../../skills/herdr-fleet/references/unattended-setup.md). Next: [5-watch.md](5-watch.md).
