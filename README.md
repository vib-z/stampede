<h1 align="center">stampede</h1>

<p align="center">stampede lets a team of AI agents do one big task on your computer, while you watch and decide.</p>

<p align="center">
  <a href="https://github.com/vib-z/stampede/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/vib-z/stampede/actions/workflows/ci.yml/badge.svg"></a>
  <a href="CHANGELOG.md"><img alt="Version 0.2.5" src="https://img.shields.io/badge/version-0.2.5-black"></a>
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-black"></a>
</p>

<p align="center"><img src="assets/demo.gif" alt="Demo: a task texted to Grok Bot reaches a Mac over Tailscale, a Claude Code lead works on it in Herdr with a Codex and a Cursor worker beside it, the bot asks before merging, then reports back." width="640"></p>

<p align="center"><sub>An animated mock-up of one job, 27 Oct 2026.</sub></p>

## What it is

You give stampede one big task, written in your own words.
One AI agent (a program that writes and runs code for you), called the lead, plans the work and does it.
It works on your computer inside [Herdr](https://herdr.dev), an app that shows each agent in its own pane (a box in the Herdr window), so you can watch.
The lead brings in more agents only when that helps.
It comes back to you only with real questions, and to ask before anything risky.

## What you need

- A Mac or a Linux computer.
- [Herdr](https://herdr.dev/docs/install/) 0.9.4 or later.
- [Claude Code](https://code.claude.com/docs/en/setup), signed in: it leads the job by default.
- Python 3.9 or later.
- git, jq and curl, three small tools for the terminal.
- Optional: [Codex](https://developers.openai.com/codex/cli), to work beside the lead or to [lead a job](docs/GUIDE.md#use-one-job-start-to-finish) with `--lead codex`.

Also optional: a [phone bot](docs/GUIDE.md#front-doors) that starts jobs, [Herdr Core](docs/CORE.md), a second way to run jobs, and [pstack](docs/GUIDE.md#works-well-with), rules for coding jobs.
The versions we tested: [docs/SETUP.md](docs/SETUP.md#what-you-need).

## Install

Open a terminal (the app where you type commands) and run these lines one at a time:

```bash
git clone https://github.com/vib-z/stampede.git ~/stampede
~/stampede/install.sh
export PATH="$HOME/.local/bin:$PATH"   # add this line to your shell profile too
stampede --version                     # 0.2.5
stampede doctor
```

The first line copies stampede to your computer, and `install.sh` sets up its commands.
The `export` line lets your terminal find them. To keep it, add it to your shell profile, a settings file your terminal reads when it opens: `~/.zshrc` on a Mac, `~/.bashrc` on Linux.
Run `stampede doctor` while Herdr is open. Each line says `ok`, or names a problem and how to fix it.
The full install, other ways to install, and updating: [docs/SETUP.md](docs/SETUP.md).

## Your first job

1. Once per computer, run `stampede setup` to save [your preferences](docs/SETUP.md#your-preferences). Then do the [one-time settings](docs/SETUP.md#unattended-agents), so the lead can start agents.
2. Your project must be a folder inside `~/code` that uses git, a tool that keeps the history of your files. Once per project, run `herdr-trust ~/code/my-app` with its folder.
3. Write what you want in a file outside the project, such as `~/ask.md`:

   ```text
   Add a page that says hello, with a test.
   Have a second agent check the work.
   ```
4. Open Herdr: type `herdr` in a terminal. In its pane, go to your project with `cd ~/code/my-app`.
5. Start the job:

   ```bash
   stampede new --file ~/ask.md
   ```

   The last line it prints names the lead and the job's folder.
6. A new tab named `lead` appears in Herdr, with the lead agent in it. Click it to watch. The lead writes a plan, then starts work. Each extra agent it brings in gets a pane of its own.
7. If the lead needs you, a question appears in its tab. Pick or type your answer there. With [Moshi](remote/moshi.md), a phone app, set up, its questions reach your phone too.
8. At the end, the lead writes a short report in its tab. Then it asks whether to close the job. By default, nothing closes until you say yes.

The same job, command by command: [the guide](docs/GUIDE.md#use-one-job-start-to-finish). If something goes wrong: [docs/TROUBLESHOOT.md](docs/TROUBLESHOOT.md).

## How it keeps you safe

- You give your yes before each of these: a merge (adding the work to your project's main code), a push (an upload) straight to the main branch,
  a deploy (putting it live), publishing, sending messages, spending money, and closing tabs or panes.
- A merge takes only the exact version of the code that a reviewer passed.
- Agents never close anything the job did not start.
- By default, agents do small steps without asking you each time. Their agent program's own safety checks stay on.
- Without asking, agents may save their work on a side branch (a separate copy of your code) and open a draft pull request (a proposed change, not yet accepted).

Every rule, and who records your yes: [docs/SAFETY.md](docs/SAFETY.md).

## Read more

- [The guide](docs/GUIDE.md): how a job flows, what stampede works with, one job command by command, and every way to start one.
- [Setup](docs/SETUP.md): the full install, updating, the one-time settings and uninstalling.
- [Herdr Core](docs/CORE.md): how to run a job on Herdr Core, a second way to run jobs, without Herdr's tabs and panes. Jobs use it only when you ask.
- [Safety](docs/SAFETY.md): every step that needs your yes, and what the code holds.
- [Configure](docs/CONFIGURE.md): every setting and its default, such as effort (how hard an agent thinks): extra high for the lead, medium for the others, and how to change both.
- [Troubleshoot](docs/TROUBLESHOOT.md): each message you may see, its fix, and the FAQ.
- [Reference](docs/REFERENCE.md): every command and script with its exit codes, how the code is laid out, every doc, and the credits.
- [Status and roadmap](docs/STATUS.md): what works, how it was tested, and what comes next.
- [For an agent](USING.md): the one page an agent reads before it runs a job.
- [Changelog](CHANGELOG.md): what each version shipped.
- [Contributing](CONTRIBUTING.md): how to help, and how to run the tests.
- [License](LICENSE): MIT.
