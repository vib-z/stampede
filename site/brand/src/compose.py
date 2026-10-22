"""Compose preview pages from the shared assets, without runtime dependencies."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
inline=(ROOT/'lockup.inline.svg').read_text()
actions=(ROOT/'cta/actions.html').read_text().replace('data-star-count="true"','data-star-count="false"')
starcss=(ROOT/'cta/star.css').read_text()
starjs=(ROOT/'cta/star.js').read_text()
component='<style>\n'+starcss+'</style>\n'+(ROOT/'cta/actions.html').read_text()+'\n<script>\n'+starjs+'</script>\n'
(ROOT/'cta/component.html').write_text(component)
head='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>stampede / Brand</title><link rel="icon" href="favicon.svg" type="image/svg+xml"><link rel="stylesheet" href="tokens.css"><link rel="stylesheet" href="preview.css"><link rel="stylesheet" href="logo.css"><link rel="stylesheet" href="cta/star.css"></head><body>'''
header='''<div class="page"><header><a href="preview.html" aria-label="stampede brand"><img class="brand logo-on-light" src="lockup-light.svg" alt="stampede"><img class="brand logo-on-dark" src="lockup-dark.svg" alt="stampede"></a><nav><a href="guide.html">Brand guide</a><a href="https://github.com/vib-z/stampede#readme">Docs</a></nav></header>'''
intro='''<main><section class="intro"><div class="eyebrow">stampede / Identity 0.1</div><h1>One ask. A team that<br>reports back.</h1><p>The stampede identity, in every detail.</p></section><div class="hero-stage"><div class="stage" data-surface="light"><img src="lockup-light.svg" alt="Black Open gate mark and wordmark"></div><div class="stage" data-surface="dark"><img src="lockup-dark.svg" alt="White Open gate mark and wordmark"></div></div>'''
icons='<section class="section"><div class="section-head"><h2>Small, with presence.</h2><p>Every pixel has a place.</p></div><div class="icon-grid">'
for theme in ['light','dark']:
    for size in [16,32,64,128]:
        name=f'src/favicon-{theme}.svg' if size<48 else f'mark-{theme}.svg'
        icons+=f'<figure class="icon-cell" data-surface="{theme}"><div class="icon-holder"><img src="{name}" width="{size}" height="{size}" alt="{theme} Open gate at {size} pixels"></div><figcaption>{size} px / {theme}</figcaption></figure>'
icons+='</div></section>'
motion='<section class="section"><div class="section-head"><h2>Make an entrance.</h2><button type="button" class="replay" data-replay>Replay</button></div><div class="motion-stage">'+inline+'</div></section>'
cta='<section class="section"><div class="section-head"><h2>A little gold. One action.</h2><p>Help the herd grow.</p></div><div class="cta-grid">'+''.join('<div class="cta-cell" data-surface="'+t+'">'+actions+'</div>' for t in ['light','dark'])+'</div></section>'
large='<section class="section"><div class="section-head"><h2>Room for the whole team.</h2><p>The full mark at 512 px.</p></div><div class="large-icons">'+''.join(f'<figure data-surface="{t}"><img class="native512" src="mark-{t}.svg" width="512" height="512" alt="{t} Open gate at 512 pixels"><figcaption>512 px / {t}</figcaption></figure>' for t in ['light','dark'])+'</div></section>'
social='<section class="section"><div class="section-head"><h2>Ready to share.</h2><p>1200 x 630</p></div><img class="social" src="og-image.png" width="1200" height="630" alt="Open gate logo with One ask. A team that reports back."><div class="download-row"><a href="mark.svg" download>Mark SVG</a><a href="lockup.svg" download>Lockup SVG</a><a href="og-image.png" download>Social card PNG</a><a href="guide.html">Open the brand guide</a></div></section>'
footer='''</main><footer><span>stampede</span><span>One ask. A team that reports back.</span></footer></div><script src="preview.js"></script></body></html>'''
(ROOT/'preview.html').write_text(head+header+intro+icons+motion+cta+large+social+footer)
(ROOT/'cta/demo.html').write_text('''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>stampede / Star on GitHub</title><link rel="stylesheet" href="../tokens.css"><style>body{min-height:100vh;display:grid;place-items:center;padding:24px}main{max-width:540px}h1{font-size:40px;letter-spacing:-.04em;font-weight:500;line-height:1.15}p{color:var(--muted);margin-bottom:32px}</style></head><body><main><h1>Help the herd grow.</h1><p>One ask. A team that reports back.</p>'''+component+'</main></body></html>')
(ROOT/'src/og.html').write_text('''<!doctype html><html lang="en"><head><meta charset="utf-8"><link rel="stylesheet" href="../tokens.css"><style>body{width:1200px;height:630px;background:#000;color:#fff;padding:64px 64px;position:relative;overflow:hidden}.lockup{width:235px}h1{font-size:68px;font-weight:500;line-height:1.05;letter-spacing:-.05em;position:absolute;bottom:112px;left:64px;margin:0}.hero-symbol{position:absolute;width:380px;height:168px;right:64px;top:252px}footer{position:absolute;bottom:64px;font-size:15px;color:#a3a3a3}</style></head><body><img class="lockup" src="../lockup-dark.svg" alt="stampede"><h1>One ask.<br>A team that<br>reports back.</h1><img class="hero-symbol" src="../mark-dark.svg" alt="Three agents inside brackets"><footer>github.com/vib-z/stampede</footer></body></html>''')
print('Composed preview, self-contained CTA, demo and social-card source.')
