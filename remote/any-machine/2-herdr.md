# Any machine, part 2: Herdr

Herdr holds every agent in a named pane and keeps them running when nobody is attached. Install it with its own guide, which is written for agents.

## Do
- Read Herdr's agent guide first, and follow its install section for this OS.
- Ask the person before running the installer.
- Check the version once it is installed.
- Learn how a Herdr server keeps running with nobody attached, and how someone attaches from elsewhere.
- If you run inside a Herdr pane already, never start Herdr again from it.
- Never start or stop a Herdr server someone else is using.
- Start the Herdr server from a clean shell: every pane inherits its environment, so no secret may be in it.

## Run
```bash
curl -fsSL https://herdr.dev/agent-guide.md         # read it; install exactly as its Install section says
herdr --version                                     # after the install
herdr status                                        # the runtime summary
```

- **Herdr's guides:** [agent guide](https://herdr.dev/agent-guide.md), [install](https://herdr.dev/docs/install/), [working remotely](https://herdr.dev/docs/how-to-work/), [what survives a detach or restart](https://herdr.dev/docs/session-state/), [CLI reference](https://herdr.dev/docs/cli-reference/).
- **Over SSH:** bare `herdr` opens its screen; an agent always gives a subcommand.
- **Version:** stampede is tested with the version in the [README](../../README.md#install); the installed binary's `--help` wins over any doc.
- **Herdr Core instead:** install it with `curl -fsSL https://releases.herdr.dev/core/install.sh | sh`, start its core, then check `hc --version`; jobs then use `stampede new --core` ([core.md](../../skills/herdr-fleet/references/core.md)).
- **Next:** [3-stampede.md](3-stampede.md).
