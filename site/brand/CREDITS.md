# Sources and rights

Updated 22 October 2026.

## stampede

Open gate is the supplied stampede identity: three cells in brackets, the outlined wordmark and its original 2400 ms run. The import changes only `#211b13` to `#000000` and `#f3ede2` to `#ffffff`. Geometry, timing and running colours are preserved; the default dark full stop remains amber. [Import record](src/import-record.json).

The repository's MIT licence covers code, not rights to the stampede name or marks. Use the supplied assets to identify or link to stampede. Do not imply endorsement, alter the identity, use it as your own product name or put it on merchandise without permission. These identity rules do not change any third party's rights.

## Fonts

- Geist and Geist Mono: Vercel, [Geist project](https://github.com/vercel/geist-font), SIL Open Font License 1.1. [Geist notice](fonts/Geist-OFL.txt), [Geist Mono notice](fonts/GeistMono-OFL.txt). Latin variable fonts are self-hosted. The supplied font files were retained from the existing site and brand source.
- Wordmark outlines: JetBrains Mono ExtraBold 2.304, JetBrains Mono Project Authors, [release 2.304](https://github.com/JetBrains/JetBrainsMono/releases/tag/v2.304), [SIL Open Font License 1.1](fonts/JetBrainsMono-OFL.txt). No replacement wordmark font is introduced.

## Agent marks

The five SVGs are byte-for-byte copies of the supplied site assets. They identify compatible tools; they do not imply endorsement. The stampede MIT code licence grants no rights to these trademarks. Keep the original colours and proportions.

| Asset | Owner | Source and supplied date |
| --- | --- | --- |
| [Claude](agents/claude.svg) | Anthropic | [Supplied agent artwork](https://herdr.dev/assets/agent-icons/claude.svg), 16 October 2026 |
| [Codex](agents/codex.svg) | OpenAI | [Supplied agent artwork](https://herdr.dev/assets/agent-icons/codex.svg), 16 October 2026 |
| [Cursor](agents/cursor.svg) | Anysphere | [Supplied agent artwork](https://herdr.dev/assets/agent-icons/cursor.svg), 16 October 2026 |
| [Grok Bot](agents/grokbot.svg) | xAI | [Official bot page](https://x.ai/bot), supplied 21 October 2026 |
| [Tailscale](agents/tailscale.svg) | Tailscale | [Official site](https://tailscale.com), supplied 21 October 2026 |

## Scenery

Six purpose-made images were generated through Codex's built-in GPT Image on 22 October 2026, from the supplied painterly genre references. The approved valley is the shared style reference for mountains, lake, planet surface, outer world and grassland. The guide uses native-dimension WebP exports; its panels and text are actual HTML, never baked into a ground.

[The source record](imagery/sources.json) contains every prompt, reference filename, date, native dimensions and SHA-256 hashes. The built-in tool exposes neither model version nor seed; neither is invented. Generated images are not described as CC0 museum works. Original PNG masters are retained with the production handoff; the approved valley PNG is also included in this kit. Reference images are not redistributed.

## Design and implementation references

[Linear's brand guide](https://linear.app/brand) is the primary reference for calm layout, precise type and quiet motion. [Vercel's design system](https://vercel.com/geist) informs the reference structure. No third-party page source, photography, screenshots or design-system implementation is copied into this kit.

The star and arrow icons, CTA component, guide and templates are authored for stampede. The count uses GitHub's [public repository API](https://docs.github.com/en/rest/repos/repos#get-a-repository). It makes no authenticated requests and disappears if the data cannot be loaded.
