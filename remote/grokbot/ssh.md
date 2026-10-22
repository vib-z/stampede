# Grok Bot, part 2: SSH

The bot logs into your machine with a key, never a password, and every command runs there. Nothing about Herdr runs on the bot's own computer.

## Do
- Turn on remote login on your machine.
- Make a key on the bot's computer; add its public half to your machine.
- Give the machine a short alias in the bot's SSH config.
- Test one command that cannot hang.
- Never put a password, key or token in a prompt, a brief or the repo.

## Run
```bash
ssh-keygen -t ed25519 -f <key file> -N ''                    # on the bot's computer
cat <key file>.pub                                            # append to ~/.ssh/authorized_keys on the machine
printf 'Host <host>\n  HostName <machine>\n  User <user>\n  IdentityFile <key file>\n' >> ~/.ssh/config
ssh -o BatchMode=yes -o ConnectTimeout=10 <host> 'herdr --version'
```

- **Remote login (macOS):** System Settings, General, Sharing, Remote Login. **Linux:** run `sshd`.
- **`<machine>`:** the MagicDNS name from `tailscale status`, or the address from `tailscale ip -4`.
- **PATH:** a non-interactive SSH shell may miss `~/.local/bin`. If a command is not found, prefix `export PATH=$HOME/.local/bin:/opt/homebrew/bin:$PATH;`.
- **BatchMode** makes SSH fail fast instead of waiting at a password prompt the bot cannot answer.
- **Times out:** check [tailscale.md](tailscale.md), retry once, then tell the owner. Usually the machine is asleep or offline.
