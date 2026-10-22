# Hero film

A silent, deterministic 14-second composition: 420 frames at 30 fps, with independent 1920x1080 desktop and 1080x1920 portrait cuts. See the [storyboard](STORYBOARD.md). `world.js` composes SVG poses; `brand/` holds generated materials and outlined type; `runtime/` supplies the animation runtime.

## Build the web frames

Use Node 26, Python 3.14, Google Chrome and the WebP tools (`cwebp`). Run from the repository root:

```sh
npm ci --prefix film
python3 -m venv film/.venv
film/.venv/bin/pip install -r film/requirements.txt
node film/tools/materials.mjs
film/.venv/bin/python film/tools/shapes.py
node film/tools/pack.mjs
```

The build writes all four aspect/theme variants to `site/assets/motion/`. Serve the repository with `python3 -m http.server 8855 --bind 127.0.0.1`, then open `http://127.0.0.1:8855/site/`. To inspect the composition directly, open `http://127.0.0.1:8855/film/?cut=desktop&theme=light`.

## Render a video

Install FFmpeg, keep the local server running, then run:

```sh
node film/tools/motionmaxxing/render.mjs 'http://127.0.0.1:8855/film/?cut=desktop&theme=light' /tmp/stampede-desktop.mp4 --width 1920 --height 1080 --fps 30 --duration 14
node film/tools/motionmaxxing/render.mjs 'http://127.0.0.1:8855/film/?cut=phone&theme=light' /tmp/stampede-phone.mp4 --width 1080 --height 1920 --fps 30 --duration 14
```

Use `theme=dark` for the dark versions. Keep video masters outside Git. The renderer's `--help` lists still export and encoding controls. Browser checks are available through `npm run qa --prefix film` while the server runs; captures go in ignored `film/renders/`.

## Sources and licences

Original composition, materials and web player use the repository MIT licence. Third-party code and marks retain their own rights:

- [motionmaxxing](https://github.com/Tejashmakwana/motionmaxxing/tree/8c8ec0f2a6f6c9a0da15cd24f7b1298ab298368c), Tejash Makwana, Apache 2.0: runtime, render and inspection tools; licences accompany the copied files.
- [GSAP 3.13.0](../site/assets/vendor/README.md), GreenSock / Webflow, standard licence; [Geist](../site/assets/fonts/Geist-OFL.txt), Vercel, SIL OFL; [agent marks](../site/assets/logos/SOURCES.md), their respective trademark owners. These supplied assets are pinned at repository commit `1a1d5e8d7b54ac54fc7b40314cfbab700ebf5fe9`.
- [Playwright 1.64.0](https://github.com/microsoft/playwright/tree/606ecd8b34bac100db32561b6278ffd76e5eb3cd), Microsoft, Apache 2.0; [FontTools 4.67.0](https://github.com/fonttools/fonttools/tree/16f88cb09446ab617a1a788e48ae12e0f0ec5217), FontTools contributors, MIT; [Brotli 1.2.0](https://github.com/google/brotli/tree/028fb5a23661f123017c060daa546b55cf4bde29), Google, MIT: local build dependencies.
- [libwebp 1.6.0](https://chromium.googlesource.com/webm/libwebp/+/4fa21912338357f89e4fd51cf2368325b59e9bd9), WebP project authors, BSD 3-Clause; [FFmpeg 9.0.2](https://github.com/FFmpeg/FFmpeg/tree/946fcce07b6dcd0331c8cc609192aeff5e1924f8), FFmpeg contributors, licence depends on build configuration: local encoding tools, binaries not included.
