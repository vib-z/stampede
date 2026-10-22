# Any machine, part 1: know the machine

Before installing anything, learn what the machine is, so every later step picks the right installer.

## Do
- Find the operating system, its version and the processor type.
- Check it is macOS; Linux is untried (tell the person); anything else, stop and tell them.
- Find the shell, the home folder and whether a user bin folder is on PATH.
- Check the basic tools are present; list the missing ones.
- Ask the person before installing missing tools with the system's own package manager.
- Note whether the machine sleeps or shuts down when idle; agents need it on.

## Run
```bash
uname -s; uname -m                                  # Linux or Darwin; x86_64 or arm64
cat /etc/os-release 2>/dev/null || sw_vers          # the release
echo "$SHELL"; echo "$PATH" | tr ':' '\n' | grep -n "$HOME"
for t in bash python3 jq git curl; do printf '%s: %s\n' "$t" "$(command -v "$t" || echo MISSING)"; done
python3 --version; bash --version | head -1
```

- **Tools stampede needs:** bash, Python 3, jq, git and curl. The tested versions are in the [README](../../README.md#install).
- **A user bin folder:** stampede links its commands into `~/.local/bin`; make sure it is on PATH for non-interactive shells too.
- **Next:** [2-herdr.md](2-herdr.md).
