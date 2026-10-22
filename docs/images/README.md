# Images

Every image here is 1800 px wide. Each one is rendered from an HTML source in [src/](src/) with [system.css](src/system.css). Both draw real text from a real run. Personal details (home paths, hostnames, accounts) are removed before capture.

| image | kind | how it is made |
|---|---|---|
| `fleet-build-tab.png` | real, drawn | the four panes' text from `herdr agent read`, 18 Oct 2026, home paths shown as `~`; `render.sh fleet-build-tab` |
| `events.png` | real, drawn | the lead's `watch.log` lines from the same run, report paths shortened; `render.sh events` |

**Render the drawn ones:** `bash docs/images/src/render.sh [name ...]`. It finds Chrome or Chromium (or `CHROME=<path>`), reads each source's `<meta name="render-height">`, and uses a temporary browser profile.

**Logos.** [logos/](logos/) holds the agents' and tools' official marks as SVG, for the README's "Works with" section, each credited in [logos/SOURCES.md](logos/SOURCES.md). They are vector marks, so the 1800 px rule does not apply to them.
