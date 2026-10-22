# stampede site

[The landing page](index.html) is one page. A header carries the stampede lockup, a GitHub link and a theme toggle. The hero holds the Open gate mark, the promise and one gold Get started button. Then the silent, scroll-driven film, and a short footer. The film has separate desktop and portrait compositions, light and dark themes, and a still poster for reduced motion or disabled JavaScript.

## Theme

Two states, light and dark. The page follows the system by default. The header toggle sets an explicit choice and remembers it when browser storage is available. The film, the mark and the posters follow the same choice mid-scroll: the displayed frame stays on screen until the matching pack can draw it. A host page can force a theme by setting `data-theme` to `light` or `dark` on the html element before the page script runs. Without JavaScript the page follows the system and the toggle stays hidden.

## Get started

Clicking copies the install prompt to the clipboard and the button reads Copied for two seconds. If the clipboard is refused, a panel opens with the prompt selected as text, with a Copy retry and a Close button; Escape closes it. Without JavaScript the button links to the README's Install section.

## Motion

The Open gate mark plays the brand's 2400 ms run on load: the cells charge in and stomp into place, scan at 12 fps, the middle one waits in amber, the left one finishes in green, the right one turns red as a blocked cell, and all settle to one ink. The cells carry no outline. It runs again on hover or tap, and when Get started copies; while idle, one cell winks every eight seconds. The page follows the run's grammar: the words rise after the cells land, on the same 100 ms beats and easing, and Copied lands with the same squash. The gold button carries a slow shine, and a light runs its rim on hover and keyboard focus. The header hides on scroll down and returns on scroll up. Reduced motion stops all of it and shows the film's poster. The film player (`assets/motion.js`, `assets/motion.css`, `assets/motion/`) is unchanged.

## Run locally

From the repository root:

```sh
python3 -m http.server 8855 --bind 127.0.0.1
```

Open `http://127.0.0.1:8855/site/`. Use HTTP so the player can load its frame data.

## Re-render the film

Follow [the film build instructions](../film/README.md). The [storyboard](../film/STORYBOARD.md) describes the sequence. Authored sources live in `film/`; generated frames and posters live in `site/assets/motion/`.

## Brand assets

Favicons and social images live in `site/brand/`, supplied by the brand kit. Include that directory alongside `index.html` when serving the complete site. The hero mark's run comes from the kit's [hero mark styles](assets/hero-mark/hero-mark.css). [Agent marks](assets/logos/SOURCES.md), [Geist](assets/fonts/Geist-OFL.txt) and the [rendering library](assets/vendor/README.md) retain their own rights and licences.

## References and credits

These ideas were rebuilt here in plain CSS and JavaScript. No source code from them is included.

- [Aceternity UI](https://ui.aceternity.com): Spotlight for the hero light, Hover Border Gradient and Moving Border for the light that runs the rim of Get started, and Floating Navbar for the header that hides on scroll down. The free components are published on ui.aceternity.com; Pro items are covered by the [Aceternity licence](https://ui.aceternity.com/licence), which forbids redistributing their source.
- [Cult UI Pro](https://pro.cult-ui.com) border beam button and [KokonutUI Pro](https://kokonutui.pro) copy button, looked at for the button's rim light and its Copied state; both are paid licences that forbid redistribution, so only the idea was used.
- [Linear](https://linear.app): the calm composition, the type scale and the pill controls. No code or assets.
- The GitHub mark belongs to GitHub and links to the repository under GitHub's logo guidelines.

For a portable preview, run `FILM_PREVIEW=/tmp/stampede-preview FILM_BRAND=site/brand node film/tools/preview.mjs`. It copies the site assets and writes a fragment for a host that supplies the HTML document wrapper.
