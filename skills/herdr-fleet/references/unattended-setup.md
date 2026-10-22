# Unattended setup (the owner runs it once per machine)

Goal: the lead starts agents and they run with no visit to each pane. Only genuine questions come back.

## What used to stop agents, and why

- **"Teach auto mode about your environment?"**: Claude Code offers `/auto-mode-setup` at the end of a turn in
  each session until `autoMode.environment` exists or the offer is turned off.
- **"Do you trust this folder?"**: shown once per repo root in interactive sessions (`-p` never shows it).
  Git worktrees inherit trust from their main checkout; a parent folder's trust does NOT cover a repo inside it
  (`~/code` was trusted, a repo inside it still asked). Stored as `projects["<repo root>"].hasTrustDialogAccepted`
  in `~/.claude.json`. No flag or permission mode skips it, `bypassPermissions` included. Codex keeps the same per
  repo in `~/.codex/config.toml` (`[projects."<root>"] trust_level = "trusted"`; a `-c` override does not count).
  Since 2026-10-16 the owner allows fleet setup to write both: `~/.local/bin/herdr-trust <repo dir>` (below).
- **The lead's own herdr commands** went through the auto-mode classifier, which refused `agent start` and
  answering a trust dialog with `agent send-keys`.

## The settings (in `~/.claude/settings.json`, user scope)

An agent cannot apply these: writing its own permission settings is refused as Self-Modification, even when
the owner explicitly asks (2026-10-11). The owner runs the command in this section with `!`, which runs it as them.

- `skillOverrides["auto-mode-setup"] = "off"`: no "Teach auto mode" prompt in any pane.
- `permissions.additionalDirectories = ["<trust root>"]` plus `Read(<trust root>/**)` and
  `Edit(<trust root>/**)`: the whole trust root (`FLEET_TRUST_ROOT`, default `~/code`) is a working folder.
- Narrow allow rules for the lead: `Bash(herdr <cmd>:*)` for `agent start|prompt|send-keys|rename|list|get|
  read|wait`, `pane split|list|read|layout`, `tab list|create`, `workspace list|create`, `worktree create`.
  Narrow rules survive auto mode; broad ones such as `Bash(*)` are dropped on entering it.
- `autoMode.environment` (kept after `$defaults`): herdr fleets are routine here; every git repo under `~/code`
  is trusted. `autoMode.allow`: `$defaults` plus "starting Claude or Codex agents in herdr panes, prompting them,
  and answering their startup dialogs is allowed". The classifier reads `autoMode` from user settings or
  `--settings` only, never from a project's `.claude/settings.json`. On 2026-10-14 the classifier passed Claude and
  Codex starts but denied Hermes with `--yolo` and Kimi with `-y`; the owner has since approved both flags, so extend
  the allow sentence to "starting Claude, Codex, Hermes (`--yolo`), Kimi (`-y`) or Cursor agents in herdr panes".

**Deliberately not allowed:** `herdr pane run` and `herdr pane send-keys`. Either can type any command into
any shell, an unrestricted path around the classifier. Closing commands and `server stop` stay unallowed too.

The one-liner the owner ran on 2026-10-11 (backs up, then merges; safe to re-run):

```bash
python3 -c "import json,os,shutil,time;p=os.path.expanduser('~/.claude/settings.json');shutil.copy2(p,p+'.bak-'+time.strftime('%Y%m%d-%H%M%S'));s=json.load(open(p));A=lambda l,xs:[l.append(x) for x in xs if x not in l];s.setdefault('skillOverrides',{})['auto-mode-setup']='off';P=s.setdefault('permissions',{});R=os.environ.get('FLEET_TRUST_ROOT','~/code');A(P.setdefault('additionalDirectories',[]),[os.path.expanduser(R)]);A(P.setdefault('allow',[]),['Read('+R+'/**)','Edit('+R+'/**)']+['Bash(herdr '+c+':*)' for c in ('agent start','agent prompt','agent send-keys','agent rename','agent list','agent get','agent read','agent wait','pane split','pane list','pane read','pane layout','tab list','tab create','workspace list','workspace create','worktree create')]);M=s.setdefault('autoMode',{});A(M.setdefault('environment',['\$defaults']),['**Agent orchestration (herdr)**: the owner runs multi-agent fleets in herdr. A lead Claude session creating panes, starting Claude (--permission-mode auto) or Codex (--approve-for-me) agents, prompting them and clearing their startup dialogs is routine and expected.','**Trusted repos**: every git repo under '+R+'.']);A(M.setdefault('allow',[]),['\$defaults','On this machine, starting Claude or Codex agents in herdr panes, prompting them, and answering their startup dialogs (folder trust for repos under '+R+', the Codex continue-without-trusting-hooks choice) is allowed.']);json.dump(s,open(p,'w'),indent=2);print('settings.json updated; backup saved alongside')"
```

Check the result with `claude auto-mode config`. New sessions pick the settings up; running ones usually do too.

## What the lead does with it

- Starts agents itself, in the owner's own repos only.
- Pre-trusts the repo before the first start: `~/.local/bin/herdr-trust <repo dir>` (grokbot-herdr/scripts). It
  resolves the main checkout's root (worktrees inherit), refuses anything outside `~/code`, sets
  `hasTrustDialogAccepted` in `~/.claude.json` (private temp file, then rename) and appends the Codex table once.
  Over ssh: `ssh <host> '~/.local/bin/herdr-trust <repo dir>'`. If the classifier refuses it, clear the
  dialog as below instead.
- Clears **startup** dialogs itself, and nothing else:
  - folder trust for a repo under `~/code`: `herdr agent send-keys <name> down`, confirm "Yes, I trust this folder" is selected (`agent read`), then `herdr agent send-keys <name> enter` separately; then `herdr agent wait <name> --until idle --timeout 30000`;
  - Codex "Trust this folder?" (a folder Codex has never opened; the start returns `agent_not_ready`): `herdr agent
    send-keys <name> enter` accepts the highlighted "Trust and continue". The hooks dialog follows.
  - Codex "Update available" (start returns `agent_not_ready`): `herdr agent send-keys <name> esc` skips it. The
    highlighted default, "Update now", runs npm, so never Enter.
  - Codex "Hooks need review": `herdr agent send-keys <name> down down enter` (continue WITHOUT trusting). Herdr
    reports this one as `idle`, so read the screen rather than waiting for `blocked`.
  - Kimi and Gemini "Trust this folder?" (also reported `idle`): `herdr agent send-keys <name> enter` on the
    highlighted trust option. Gemini then asks how to sign in if it has no login: stop there and tell the owner.
  - Claude "New MCP server found in this project": `herdr agent send-keys <name> enter` on the default,
    "Continue without using this MCP server".
- Live test 2026-10-11 (Sonnet 5.5 + Codex gpt-6.1-sol in a fresh folder under `~/code`): no trust dialog (a
  non-repo folder inherits trust from trusted `~/code`; only a git repo root asks), no "Teach auto mode", one MCP
  dialog cleared by the lead, Codex started clean. No owner visit was needed.
- Never answers a permission prompt for an action, never trusts a folder outside `~/code`, and asks the owner
  about anything it does not recognise. A third-party clone under `~/code` (for example a local copy of an open-source tool) is
  still trusted by these rules; the owner chose that on 2026-10-11.
