# Unattended setup (the owner runs it once per machine)

Goal: the lead starts agents and they run with no visit to their panes; only real questions come back.

## What stops agents

- **"Teach auto mode about your environment?"**: Claude offers `/auto-mode-setup` at the end of a turn until `autoMode.environment` exists or the offer is off.
- **"Do you trust this folder?"**: once per repo root in an interactive session (`-p` never shows it). Worktrees inherit their main checkout's trust; a parent folder's trust does not cover a repo inside it.
- Claude keeps folder trust in `~/.claude.json` (`projects["<repo root>"].hasTrustDialogAccepted`), Codex in `~/.codex/config.toml` (`[projects."<root>"] trust_level = "trusted"`; a `-c` override does not count). No flag or permission mode skips it.
- **The lead's own herdr commands** go through the auto-mode classifier, which refuses `agent start` and answering a dialog with `agent send-keys` until the rules below exist.

## The settings (`~/.claude/settings.json`, user scope)

An agent cannot apply these: writing its own permission settings is refused as Self-Modification, even when the owner asks. The owner runs the command below with `!`.

- `skillOverrides["auto-mode-setup"] = "off"`: no "Teach auto mode" prompt.
- `permissions.additionalDirectories = ["<trust root>"]`, with `Read(<trust root>/**)` and `Edit(<trust root>/**)`: the trust root (`FLEET_TRUST_ROOT`, default `~/code`) is a working folder.
- Narrow allow rules for the lead, `Bash(herdr <cmd>:*)`, for `agent start|prompt|send-keys|rename|list|get|read|wait`, `pane split|list|read|layout`, `tab list|create`, `workspace list|create` and `worktree create`. Narrow rules survive auto mode; broad ones such as `Bash(*)` are dropped on entering it.
- `autoMode.environment` (after `$defaults`): herdr fleets are routine; every git repo under the trust root is trusted. `autoMode.allow`: `$defaults`, plus starting agents in herdr panes, prompting them and answering their startup dialogs.
- Extend `autoMode.allow` to "Claude, Codex, Hermes (`--yolo`), Kimi (`-y`) or Cursor agents" when those run. The classifier reads `autoMode` from user settings or `--settings` only, never from a project's settings.
- **Never allowed:** `herdr pane run` and `herdr pane send-keys` (either types any command into any shell, a path around the classifier), the closing commands and `server stop`.

It backs up the file, then merges; safe to run again:

```bash
python3 - <<'EOF'
import json, os, shutil, time
p = os.path.expanduser('~/.claude/settings.json')
shutil.copy2(p, p + '.bak-' + time.strftime('%Y%m%d-%H%M%S'))
s = json.load(open(p))
def add(l, xs): l.extend(x for x in xs if x not in l)
R = os.environ.get('FLEET_TRUST_ROOT', '~/code')
s.setdefault('skillOverrides', {})['auto-mode-setup'] = 'off'
P = s.setdefault('permissions', {})
add(P.setdefault('additionalDirectories', []), [os.path.expanduser(R)])
cmds = ('agent start', 'agent prompt', 'agent send-keys', 'agent rename', 'agent list', 'agent get', 'agent read', 'agent wait',
        'pane split', 'pane list', 'pane read', 'pane layout', 'tab list', 'tab create', 'workspace list', 'workspace create', 'worktree create')
add(P.setdefault('allow', []), ['Read(' + R + '/**)', 'Edit(' + R + '/**)'] + ['Bash(herdr ' + c + ':*)' for c in cmds])
M = s.setdefault('autoMode', {})
add(M.setdefault('environment', ['$defaults']), [
    '**Agent orchestration (herdr)**: the owner runs multi-agent fleets in herdr. A lead Claude session creating panes, starting Claude '
    '(--permission-mode auto) or Codex (--approve-for-me) agents, prompting them and clearing their startup dialogs is routine and expected.',
    '**Trusted repos**: every git repo under ' + R + '.'])
add(M.setdefault('allow', []), ['$defaults',
    'On this machine, starting Claude or Codex agents in herdr panes, prompting them, and answering their startup dialogs (folder trust '
    'for repos under ' + R + ', the Codex continue-without-trusting-hooks choice) is allowed.'])
json.dump(s, open(p, 'w'), indent=2)
print('settings.json updated; backup saved alongside')
EOF
```

Check it with `claude auto-mode config`. New sessions pick it up; running ones usually do too.

## Trust a repo

`herdr-trust <repo dir>` (installed with stampede) before the first start in a repo. It resolves the main checkout's root (worktrees inherit), refuses anything outside the trust root, sets `hasTrustDialogAccepted` in `~/.claude.json` (a private temp file, then a rename) and adds the Codex table once.
Over ssh: `ssh <host> '~/.local/bin/herdr-trust <repo dir>'`. If the classifier refuses it, clear the dialog instead (below).

## Startup dialogs the lead clears

Herdr reports most of these as `idle`, not `blocked`: read the screen (`herdr agent read <name> --source visible --lines 30`) after every start. After clearing one, `herdr agent wait <name> --until idle --timeout 30000` (a stale `blocked` clears in seconds), never a sleep.

| Dialog | Keys |
|---|---|
| Claude folder trust, a repo under the trust root | `herdr agent send-keys <name> down`, read the screen to confirm "Yes, I trust this folder" is selected, then `herdr agent send-keys <name> enter` as a separate call |
| Codex "Trust this folder?" (start returns `agent_not_ready`) | `enter` accepts "Trust and continue"; the hooks dialog follows |
| Codex "Hooks need review" (after trust, and again in a fresh worktree) | `herdr agent rename <pane> <name>` if the name is missing, then `down down enter`: continue without trusting |
| Codex "Update available" (start returns `agent_not_ready`) | `esc` skips it. Never Enter: "Update now" runs npm and Codex exits |
| Kimi or Gemini folder trust | `enter` on the highlighted trust option. Gemini then asks how to sign in: stop and tell the owner |
| Claude "New MCP server found in this project" | `enter` on the default, "Continue without using this MCP server" |

- Use `herdr agent send-keys`, not `pane send-keys`: only the former is allowed.
- The lead starts agents only in the owner's own repos.
- It never answers a permission prompt for an action, never trusts a folder outside the trust root, and asks the owner about anything it does not recognise.
- A third-party clone under the trust root is trusted by these rules too: the owner's choice.
