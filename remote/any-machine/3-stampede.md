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
./install.sh
mkdir -p ~/.config/stampede && cp config.example ~/.config/stampede/config   # then edit HERDR_EVENTS_MACHINE
echo '. ~/.config/stampede/config' >> ~/.zshrc
herdr plugin link . && herdr plugin list            # only when a bot should hear events
```

- **Install:** [README, Install](../../README.md#install) and [docs/SETUP.md](../../docs/SETUP.md).
- **Settings:** every key and its default is in [config.example](../../config.example); never write a value into a script.
- **Events to a bot on this machine:** a route file, as in [events.md](../events.md).
- **Next:** [4-agents.md](4-agents.md).
