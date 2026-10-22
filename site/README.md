# Stampede site

[The landing page](index.html) follows one ask through a team of coding agents to a finished pricing page and a reply. The silent, scroll-driven film has separate desktop and portrait compositions, light and dark themes, and a still poster for reduced motion or disabled JavaScript.

The top-right switch selects light, dark or system appearance. System is the default; an explicit choice is remembered when browser storage is available. A theme change keeps the displayed canvas until the matching pack can draw the current scroll frame. The mark, colours and posters follow the same choice. With JavaScript disabled, the page follows the system theme.

The gold **Get started** ticket appears in the intro and hand-off. It copies an install prompt for Claude Code or Codex and opens a selectable copy with confirmation. If clipboard access is refused, the prompt is selected for manual copying and the popover offers a retry. Escape or the close button dismisses it. Without JavaScript the ticket links to the README's Install section. The shine stops under reduced motion; **Star on GitHub** is a quiet outline link.

## Run locally

From the repository root:

```sh
python3 -m http.server 8855 --bind 127.0.0.1
```

Open `http://127.0.0.1:8855/site/`. Use HTTP so the player can load its frame data.

## Re-render the film

Follow [the film build instructions](../film/README.md). The [storyboard](../film/STORYBOARD.md) describes the sequence. Authored sources live in `film/`; generated frames and posters live in `site/assets/motion/`.

## Brand assets

Favicons and social images live in `site/brand/`, supplied by the brand PR. Include that directory alongside `index.html` when serving the complete site. [Agent marks](assets/logos/SOURCES.md), [Geist](assets/fonts/Geist-OFL.txt) and the [rendering library](assets/vendor/README.md) retain their own rights and licences.

For a portable preview, run `FILM_PREVIEW=/tmp/stampede-preview FILM_BRAND=site/brand node film/tools/preview.mjs`. It copies the site assets and writes a fragment for a host that supplies the HTML document wrapper.
