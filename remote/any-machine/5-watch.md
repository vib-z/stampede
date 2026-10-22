# Any machine, part 5: watching from elsewhere

The fleet runs on this machine; the person watches and answers from a phone or a laptop. Offer the ways below and set up the one they choose.

## Do
- Ask how the person wants to watch: a terminal, a phone app, or a bot's messages.
- A terminal: they reach this machine over SSH and attach to Herdr there.
- A laptop with Herdr: it can attach to this machine as a thin client.
- A phone: one of the apps other people build for Herdr, or Moshi.
- A bot on this machine: events reach it through its webhook; it never polls.
- Give the person only the access the chosen way needs.

## Run
```bash
herdr machine add <ssh-target>                      # from a laptop with Herdr: save the cloud machine once
ssh <host>                                          # then run herdr there; it attaches like tmux
herdr --remote <host>                               # from a laptop with Herdr: a thin local client
herdr --machine <label> <command>                   # from a laptop: one command on a saved SSH machine (herdr machine --help)
moshi-hook doctor                                   # if the person chose Moshi
```

- **Herdr remotely:** [working remotely](https://herdr.dev/docs/how-to-work/) explains SSH versus `--remote`.
- **Phone apps:** herdr-web-ui, Collie, Heeler, herdr-remote by dcolinmorgan, and Moshi: [phone-clients.md](../phone-clients.md); Moshi with stampede: [moshi.md](../moshi.md).
- **A private network** for SSH, if the machine is not public: [Tailscale](../grokbot/tailscale.md).
- **Events for a bot:** [events.md](../events.md).
- **Next:** [6-verify.md](6-verify.md).
