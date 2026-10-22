# stampede brand kit

[Visual guide](guide.html) · [Markdown guide](GUIDE.md) · [Size and motion preview](preview.html) · [Download the kit](brand-kit.zip)

Open gate is the only stampede logo. The supplied geometry, outlined wordmark and 2400 ms animation are preserved. Resting ink is pure black on white and white on dark. The original amber full stop remains the dark default; a [one-ink variant](lockup-mono-dark.svg) is supplied alongside it.

## Use

- Use [mark.svg](mark.svg) alone for icons and the hero, and [lockup.svg](lockup.svg) where the name fits. Fixed light and dark SVGs are available in the guide.
- Keep one wordmark cap-height of clear space around the lockup, or half the bracket height around the standalone mark. Minimum lockup height: 20 px. Minimum standalone width: 16 px; use at least 32 px in an interface.
- Preserve proportions, geometry and colours. Do not rotate, crop, outline, distort or animate a third-party agent mark. Do not retype the outlined wordmark.
- Use the [inline SVG](lockup.inline.svg) with [logo.css](logo.css) for a theme-aware animation. Add `is-running` to play once. Reduced motion or `data-motion="off"` on the document root shows the static state.
- Drop [hero-mark/component.html](hero-mark/component.html) directly above the hero's real h1. It includes inline SVG and CSS, runs once, and uses 124 px desktop or 96 px phone width. [Demo](hero-mark/demo.html).
- Drop [cta/component.html](cta/component.html) into a page for the gold `#FFB547` Star link and the plain docs link. [Demo](cta/demo.html). The optional count uses GitHub's public API, a one-hour cache and a 3.5-second timeout. Set `data-star-count="false"` to disable all API requests. No-JS leaves a working link.
- Load [tokens.css](tokens.css) for Geist, Geist Mono and neutral theme tokens. Honour `data-theme="light"` or `data-theme="dark"` on the root, otherwise the system theme is used. The static adaptive SVG uses the system theme; choose the explicit light/dark file when the host overrides it.

## Icons and templates

The favicon is supplied as adaptive SVG, 16/32 px PNG and ICO. App icons are 180, 192 and 512 px; the separate maskable 512 px asset fits the central safe circle. The [manifest](site.webmanifest) is a starting point: set its start URL to your application's route.

[Open Graph](og-image.png) is 1200 x 630. [GitHub repository preview](github-social.png) is 1280 x 640 and below 1 MB. Both are rendered from [src/og.html](src/og.html). The guide includes a light/dark README picture snippet and three painterly compositions with real HTML UI.

Six grounds retain their native output dimensions: five at 1672 x 941 and the square grassland at 1254 x 1254. The WebP exports retain those dimensions. Prompt, reference names, provider, original hashes and delivery hashes are in [imagery/sources.json](imagery/sources.json). Keep UI separate from the painting and protect text with a strong neutral panel. No upscale was needed for these templates.

## Rebuild

The supplied SVGs are the authoritative vector sources. Python 3 rebuilds the guide and components; Node, `playwright-core` and Chrome render the raster exports. Set `CHROME_PATH` if Chrome is elsewhere. Pillow is used only for WebP format conversion and QA contact sheets.

```sh
python3 site/brand/src/compose.py
python3 site/brand/src/guide.py
node site/brand/src/render.cjs
python3 site/brand/src/package.py
python3 -m http.server 8847 --bind 127.0.0.1 --directory site
```

Open `http://127.0.0.1:8847/brand/guide.html`. The guide and preview have no external runtime dependencies. `src/package.py` repacks the PNG favicon entries into ICO and builds the asset ZIP. With `--preview-dir <folder>` it also exports the portable preview fragment. Downloads there use `.bin` transport plus original filenames to fit static-host type limits; no-JS links still download the same bytes.

Run the repository checks with `python3 -m unittest discover tests`. Browser validation covers 390 and 1440 px, light and dark, reduced motion, no-JS, root and subpath hosting, count success/cache/failure, copy controls and download links. This is local headless Chrome validation, not physical-phone testing.

## Rights

Keep [CREDITS.md](CREDITS.md) and the font notices with the kit. Third-party marks retain their owners' rights. The repository's MIT code licence does not grant rights to the stampede name or marks.
