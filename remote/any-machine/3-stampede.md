# Any machine, part 3: stampede

stampede is three skills and a command, plus a Herdr plugin for events. Install it on this machine, then give it the few settings that differ here.

## Do
- Ask the person before installing.
- Install stampede the way its README says.
- Copy the example settings, then change only what differs on this machine.
- Name the machine, so events say where they came from (`HERDR_EVENTS_MACHINE`).
- If a bot on this machine should hear events, give it a route.
- Leave every other setting at its default.

## Run
```bash
git clone https://github.com/vib-z/stampede.git ~/stampede && cd ~/stampede
./install.sh --dry-run                              # read what it would do
./install.sh                                        # on Linux this also starts the event timers
mkdir -p ~/.config/stampede && echo 'export HERDR_EVENTS_MACHINE=<this machine>' >> ~/.config/stampede/config
echo '. ~/.config/stampede/config' >> ~/.zshrc       # bash: ~/.bashrc; the relay and its timers read it too
herdr plugin link . && herdr plugin list            # only when a bot should hear events
```

- **Install:** [README, Install](../../README.md#install) and [docs/SETUP.md](../../docs/SETUP.md).
- **Settings:** every key and its default is in [config.example](../../config.example) (keys go in `~/.config/stampede/config.toml`, the environment-only variables in the shell file above); `stampede config show` prints them all. Never write a value into a script.
- **Events to a bot on this machine:** a route file, as in [events.md](../events.md).
- **Next:** [4-agents.md](4-agents.md).
