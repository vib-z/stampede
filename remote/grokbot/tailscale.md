# Grok Bot, part 1: Tailscale

The bot's computer and your machine join one private network, so the bot can reach the machine from anywhere without opening a port to the internet.

## Do
- Install Tailscale on your machine and on the bot's computer.
- Sign both into the same tailnet.
- Keep your machine awake and plugged in while jobs run.
- Check that each side sees the other.
- If SSH times out later, check Tailscale first.

## Run
```bash
tailscale up                    # on each side; the first run prints a sign-in link
tailscale status                # both machines listed, the other one online
tailscale ping <machine>        # a pong means the tunnel passes traffic
tailscale ip -4 <machine>       # the address for ssh.md, if MagicDNS is off
```

- **Install:** [tailscale.com/kb/1017/install](https://tailscale.com/kb/1017/install).
- **Optional:** [Tailscale SSH](https://tailscale.com/kb/1193/tailscale-ssh) lets the tailnet handle SSH keys instead of [ssh.md](ssh.md).
- **Awake (macOS):** System Settings, Energy, prevent automatic sleeping when the display is off.
- **Quietly dead tunnel:** `tailscale status` can say Running while nothing passes. `tailscale ping` tells the truth.
- **Never** run `tailscale down` on the machine over SSH: it cuts your own connection.
