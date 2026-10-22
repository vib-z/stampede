# Stampede site

[The landing page](index.html) follows one ask through a team of coding agents to a finished pricing page and a reply. The silent, scroll-driven film has separate desktop and portrait compositions, light and dark themes, and a still poster for reduced motion or disabled JavaScript.

The header switch selects light, dark or system appearance. System is the default; an explicit choice is remembered when browser storage is available. A theme change keeps the displayed canvas until the matching pack can draw the current scroll frame. The mark, colours and posters follow the same choice. With JavaScript disabled, the page follows the system theme.

The wordmark-only header keeps navigation and the theme switch together. One Open gate mark sits above the hero headline, **One ask. A team that reports back.** The headline explains the outcome; the header carries the name. The hero and header scroll away before the film pins, leaving every frame clear. The footer carries the full lockup, the brand line, GitHub, Docs, Brand, the MIT licence and v0.1.0.

The metallic gold **Get started** pill appears in the hero and hand-off. It copies the install prompt and crossfades to **Copied** with a check for two seconds, with a small instruction to paste into Claude Code or Codex. Success keeps the page clear. **See prompt** opens a selectable copy; clipboard refusal opens it automatically, selects the text and offers a retry. Escape or the close button dismisses it. Without JavaScript the pill links to the README's Install section. The shine and crossfade stop under reduced motion; **Star on GitHub** is a quiet outline pill of the same height.

The header wordmark reuses the supplied outlined paths from `brand/lockup-light.svg`, without the gate, as approved for this layout. The footer uses the complete supplied lockup. The film, its player, the saved theme behaviour, the install prompt, and the social images and icons are unchanged.

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
