# Any machine, part 6: verify

Prove the machine is ready before the first real job, and tell the person in plain words what works and what does not.

## Do
- Check Herdr runs and answers.
- Check stampede's health check passes, and read every line it prints.
- Check at least one agent CLI is usable.
- If a remote listens, send it one test event and confirm it arrived.
- Report: what works, what is missing, and the one next step.

## Run
```bash
herdr --version && herdr status
herdr-doctor --relay                                        # exit 0: go on; exit 1: report the PROBLEM lines
claude --version                                    # the lead's CLI
stampede --help                                     # usage: fleet-job ... {new,start,tell,ask,cancel,approve,hook,_ask}
herdr-event-post source=test state=done pane=<pane id>                                    # only when a remote listens
```

```text
This machine is ready for stampede: Herdr <version>, agents <list>, health check clean. Ask me for a job.
```

Anything failed: the fix is in [README, Troubleshoot](../../README.md#troubleshoot) and [docs/SETUP.md](../../docs/SETUP.md#setup-problems). Setup B is done; the job flow is the same as on any machine ([README](../../README.md#how-it-works)).
