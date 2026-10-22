# Phone clients: other people's apps for Herdr on a phone

You can watch and steer Herdr from a phone with apps other people build. They sit beside any stampede remote; stampede links them and ships none of them.

## Do
- Pick one app to see panes and answer agents from the phone.
- Read its own install guide and license before you install it.
- Keep one remote for stampede's events; the app is for looking and answering.
- Give an app no more access than its guide asks for.

## Run
| app | what it is | license |
|---|---|---|
| [herdr-web-ui](https://github.com/devswha/herdr-web-ui/blob/97a48035fb4c975c982952f8825b8eae36be3a4b/README.md) | chat and a terminal per pane, approvals as cards, push alerts, a phone web app | MIT |
| [Collie](https://github.com/AltanS/collie/blob/afed99bc8d5f9ca29a12561f975ca0e72c5733a3/README.md) | a phone web app over Tailscale, with a push when an agent blocks | MIT |
| [Heeler](https://github.com/ZingerLittleBee/Heeler/blob/92ba5dac6ca83c6972e18fd6227bbde49eabe3bf/README.md) | a native iOS console with encrypted pushes and Live Activities | Apache-2.0 |
| [herdr-remote](https://github.com/dcolinmorgan/herdr-remote/blob/6843636df54386781de122211d8a8d354fac2dbd/README.md) by dcolinmorgan | menu bar, phone and Telegram, with one-tap approvals | AGPL-3.0 or commercial; link only |
| [Moshi](https://getmoshi.app/docs/herdr) | a phone terminal over SSH or Mosh, with an Inbox for agents' questions | see its site |

- Each link points at the commit that was read on 18 Oct 2026; check the app's current page before installing.
- Moshi with stampede, step by step: [moshi.md](moshi.md). The rules every remote follows: [README.md](README.md).
