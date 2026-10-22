"""Build the HTML guide and Markdown twin from one set of rules."""
from pathlib import Path
from html import escape, unescape
from html.parser import HTMLParser
ROOT=Path(__file__).resolve().parents[1]

class Tables(HTMLParser):
    """Keep textual tables in the Markdown twin as well as the visual guide."""
    def __init__(self):
        super().__init__(); self.tables=[]; self.rows=None; self.row=None; self.cell=None
    def handle_starttag(self, tag, attrs):
        if tag=='table': self.rows=[]
        elif tag=='tr' and self.rows is not None: self.row=[]
        elif tag in ('th','td') and self.row is not None: self.cell=''
    def handle_data(self, value):
        if self.cell is not None: self.cell+=value
    def handle_endtag(self, tag):
        if tag in ('th','td') and self.cell is not None: self.row.append(self.cell); self.cell=None
        elif tag=='tr' and self.row is not None: self.rows.append(self.row); self.row=None
        elif tag=='table' and self.rows is not None: self.tables.append(self.rows); self.rows=None
ACTIONS=(ROOT/'cta/actions.html').read_text().replace('data-star-count="true"','data-star-count="false"')
INLINE=(ROOT/'lockup.inline.svg').read_text()
HERO=(ROOT/'hero-mark/component.html').read_text()
sections=[]
def section(id,title,paragraphs,visual=''):
    sections.append((id,title,paragraphs,visual))
def pair(a,b):
    return '<div class="rules-grid"><div class="rule"><strong>Do</strong><p>'+a+'</p></div><div class="rule"><strong>Avoid</strong><p>'+b+'</p></div></div>'
def table(head,rows):
    return '<div class="table-scroll"><table><thead><tr>'+''.join('<th>'+x+'</th>' for x in head)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+x+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table></div>'
def logos(mark=False):
    name='mark' if mark else 'lockup'
    return '<div class="specimen logo-pair">'+''.join(f'<div class="logo-panel {"mark-only" if mark else ""}" data-surface="{t}"><img src="{name}-{t}.svg" alt="Open gate {name} on {t}"><small>{"Ink on paper" if t=="light" else "White with the original amber full stop" if not mark else "White on near-black"}</small></div>' for t in ['dark','light'])+'</div>'
section('identity','One name. One identity.',[
    'stampede is always lowercase, even in headings and at the start of a sentence. The name stays plain. The drawn wordmark keeps its full stop.',
    'One ask. A team that reports back.',
    'Open gate is the only logo: three agent cells, two brackets and the original outlined wordmark. Use the full lockup where space allows, and the mark for icons and the hero. Keep the supplied geometry.'
],logos()+logos(True))
section('logo','Give the mark room.',[
    'Clear space is one wordmark cap-height on all four sides: 0.76 times the lockup height. For the standalone mark, reserve half the bracket height around it.',
    'The lockup is at least 20 px tall, about 153 px wide. The standalone mark is at least 16 px wide; use 32 px or more in interface layouts. Do not add the wordmark to a favicon.',
    'On dark, the original amber full stop is the default. A white full stop is supplied for applications that require one ink. It is the same artwork, not a second identity.'
],'<div class="specimen clearspace"><div><img class="logo-on-light" src="lockup-light.svg" alt="Open gate lockup with clear space"><img class="logo-on-dark" src="lockup-dark.svg" alt="Open gate lockup with clear space"></div><p>One cap-height of clear space on every side.</p></div>'+table(['Form','Minimum','Use'],[['Lockup','20 px high','Headers, README, credits'],['Mark','16 px wide','Favicon; 32 px or more in UI'],['Hero mark','96 px phone / 124 px desktop','Centred above the title']])+pair('Use the supplied mark, at its natural proportions, on a quiet neutral ground.','Stretch, rotate, crop, outline, add effects, redraw the cells or replace the wordmark.')+'<div class="specimen logo-pair"><div class="logo-panel" data-surface="dark"><img src="lockup-dark.svg" alt="Default lockup with amber full stop"><small>Default / amber full stop</small></div><div class="logo-panel" data-surface="dark"><img src="lockup-mono-dark.svg" alt="One-ink lockup with white full stop"><small>One-ink use / white full stop</small></div></div>')
light=[('Ground','#FFFFFF'),('Ink','#0A0A0A'),('Text secondary','#333333'),('Text muted','#666666'),('Text quiet','#757575'),('Surface 1','#FAFAFA'),('Surface 2','#F5F5F5'),('Surface 3','#EEEEEE'),('Hairline','#E5E5E5'),('Border','#CCCCCC'),('Control edge','#767676')]
dark=[('Ground','#0A0A0A'),('Ink','#F5F5F5'),('Text secondary','#D4D4D4'),('Text muted','#A3A3A3'),('Text quiet','#8A8A8A'),('Surface 1','#111111'),('Surface 2','#171717'),('Surface 3','#1F1F1F'),('Hairline','#262626'),('Border','#383838'),('Control edge','#767676')]
def swatches(items):
    return '<div class="tokens">'+''.join(f'<button class="token" data-copy="{v}" aria-label="Copy {n} {v}"><span class="swatch" style="background:{v}"></span><strong>{n}</strong><code>{v}</code></button>' for n,v in items)+'</div>'
section('colour','Quiet by default.',[
    'Dark ground is #0A0A0A with #F5F5F5 text. Light ground is #FFFFFF with #0A0A0A text. Every interface grey is neutral. The logo ink itself stays pure black or white.',
    'Amber #FFB547 belongs to the Star on GitHub button and the original full stop. It does not become a page wash, a heading colour or a general highlight.',
    'The original animation keeps its waiting amber and success green. Third-party marks keep their own colours. Soft natural colour belongs to the painterly scenery. Use a written label for every product status.',
    'Normal text needs at least 4.5:1 contrast; large text and essential control boundaries need 3:1. Use the control-edge token for an input boundary, not the decorative hairline.'
],'<h3>Dark</h3>'+swatches(dark)+'<h3>Light</h3>'+swatches(light)+'<h3>One accent. A defined job.</h3>'+swatches([('Star CTA and full stop','#FFB547'),('Animation done / light','#147D50'),('Animation done / dark','#3CCF8E')])+pair('Build hierarchy with surface levels, space and text greys.','Tint the neutral surfaces or use amber as decoration.'))
section('type','Precise, with a human rhythm.',[
    'Use Geist for headings, body and controls. Use Geist Mono for commands, file paths and numeric data. Both fonts are self-hosted. The wordmark remains the supplied JetBrains Mono ExtraBold outlines; never retype it in Geist.',
    'Use weights 400, 500 and 600. Display headings are usually 500, with -0.02em tracking from 32 px upwards. Body is 15 or 16 px at 1.6 line-height. Keep body measure at or below 624 px.',
    'A two-tone heading may continue in a readable neutral grey. No gradients, coloured words, bouncing type or decorative uppercase paragraphs.'
],table(['Specimen','Token / size','Use'],[['<span class="type72">Aa</span>','Display / 72 px','Hero; 40 to 44 px on phones'],['<span class="type48">Aa</span>','Heading / 48 px','Major sections; 32 px on phones'],['<span class="type32">Aa</span>','Title / 32 px','Section heading'],['<span class="type24">Aa</span>','Subtitle / 24 px','Panel heading'],['One ask. A team that reports back.','Body / 16 px','Reading text; line-height 1.6'],['Read the docs','Label / 14 px','Controls; weight 500'],['<code>stampede new --file ask.md</code>','Mono / 13 px','Commands and numeric data'],['Asset specifications','Small / 12 px','Supporting labels, never body']]))
section('layout','Space does the organising.',[
    'Work on a 4 px base. Use 4, 8, 12, 16, 24, 32, 48, 64 and 96 px. Reserve 64 to 96 px between desktop sections and 40 to 64 px on phones.',
    'At 390 px: four columns with 20 px gutters and 12 px gaps. At 768 px: eight columns with 28 px gutters and 16 px gaps. At 1440 px: twelve columns, a 1200 px content width and 24 px gaps. Text columns stay narrower than image fields.',
    'Use radii 4, 8 and 16 px by scale. On dark, build depth with neutral surface steps and a single hairline, without drop shadows. Over scenery, use a 95 percent opaque neutral panel with a 36 px backdrop blur; that strong ground protects the words.',
    'Controls have a target of at least 44 by 44 px and a visible 2 px focus ring, offset 4 px. Keep these rules on desktop as well as on phones.'
],'<div class="specimen columns">'+'<i></i>'*12+'</div><div class="spacing">'+''.join(f'<div><b style="height:{n}px"></b>{n}</div>' for n in [4,8,12,16,24,32,48,64,96])+'</div>')
section('voice','Say what happens.',[
    'Write in plain, short sentences. Name the action and the result. Use the present tense. Keep the main point first and the next step concrete.',
    'Write stampede in lowercase. Write Claude Code, Codex, Cursor, Herdr and other product names as their makers do. Use simple punctuation and no em or en dashes.',
    'Do not narrate the page or add captions that tell the reader a picture is a picture. Keep source and production details in credits. Never invent a run, a result, an endorsement or a release claim.'
],pair('One ask. A team that reports back.','A revolutionary agent orchestration ecosystem.')+pair('Read the docs.','Discover the possibilities of seamless productivity.')+pair('The lead asks before merging.','Enjoy peace of mind with unprecedented control.'))
section('imagery','A quiet world. A sharp foreground.',[
    'Keep two separate layers: a painterly atmosphere underneath and crisp product UI above. The scenery carries mood. The UI carries meaning. Logos and agent marks stay on solid neutral fields.',
    'Our worlds are valleys, mountains, lakes, planet surfaces, outer worlds and grassy landscapes. Use soft watercolour, gouache-like washes or the luminous painted-board handling in the selected references. Keep natural colour muted, edges soft and the upper half or one side genuinely quiet.',
    'Use one scene at the emotional turn of a page. A guide may show several specimens; a product page should not feel like a gallery. Low terrain, broad sky and modest detail make room for the foreground.',
    'Light treatment: pale scenery with near-black text on a strong white panel. Dark treatment: retain the painting and flip the panel to near-black with soft white text. Protect the text locally instead of making the entire painting grey.',
    'Keep the original image, exact prompt, references, provider, date and output dimensions in the source record. Record model and seed only when exposed. Inspect native-size detail and all four edges before use. Credit third-party sources and retain their rights statements.'
],pair('Reserve a calm region and mount real UI on a solid or strongly frosted panel.','Paint lettering or logos into the scenery, use a visible mount, or place text over a busy horizon.')+'<div class="genre-grid"><figure><img src="imagery/valley.webp" alt="Golden valley with low rolling hills and a wide quiet sky" loading="lazy"><figcaption>Valleys</figcaption></figure><figure><img src="imagery/mountains.webp" alt="Pale lilac ridges beneath a cream sky" loading="lazy"><figcaption>Mountains</figcaption></figure><figure><img src="imagery/lake.webp" alt="Still lavender lake and a low wooded shore" loading="lazy"><figcaption>Lakes</figcaption></figure><figure><img src="imagery/planet-surface.webp" alt="Dusty rose mesas on a quiet mineral plain" loading="lazy"><figcaption>Planet surfaces</figcaption></figure><figure><img src="imagery/outer-world.webp" alt="Indigo world with a faint sage aurora at the horizon" loading="lazy"><figcaption>Outer worlds</figcaption></figure><figure><img src="imagery/grassland.webp" alt="Muted sage meadow beneath an open silver sky" loading="lazy"><figcaption>Grasslands</figcaption></figure></div><div class="sample-grid" id="imagery-samples"><article class="sample" data-surface="light"><img class="ground" src="imagery/valley.webp" alt="" loading="lazy"><div class="sample-panel"><img src="lockup-light.svg" alt="stampede"><h4>One ask.<br>A team that reports back.</h4><div class="stp-actions">\n  <a class="stp-star" href="https://github.com/vib-z/stampede" data-star-count="false">\n    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 2.8 5.7 6.3.9-4.5 4.4 1.1 6.2-5.7-3-5.7 3 1.1-6.2-4.5-4.4 6.3-.9Z"/></svg>\n    <span>Star on GitHub</span><span class="stp-count" hidden></span>\n  </a>\n  <a class="stp-docs" href="https://github.com/vib-z/stampede#readme">Read the docs<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3 10h13m-5-5 5 5-5 5"/></svg></a>\n</div>\n</div><span class="sample-label">Social card</span></article><article class="sample" data-surface="light"><img class="ground" src="imagery/lake.webp" alt="" loading="lazy"><div class="sample-panel"><img src="lockup-light.svg" alt="stampede"><h4>stampede</h4><code>stampede new --file ask.md</code></div><span class="sample-label">README header</span></article><article class="sample" data-surface="dark"><img class="ground" src="imagery/outer-world.webp" alt="" loading="lazy"><div class="sample-panel"><img src="lockup-dark.svg" alt="stampede"><h4>Give the team room.</h4><div class="stp-actions">\n  <a class="stp-star" href="https://github.com/vib-z/stampede" data-star-count="false">\n    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 2.8 5.7 6.3.9-4.5 4.4 1.1 6.2-5.7-3-5.7 3 1.1-6.2-4.5-4.4 6.3-.9Z"/></svg>\n    <span>Star on GitHub</span><span class="stp-count" hidden></span>\n  </a>\n  <a class="stp-docs" href="https://github.com/vib-z/stampede#readme">Read the docs<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3 10h13m-5-5 5 5-5 5"/></svg></a>\n</div>\n</div><span class="sample-label">Launch post</span></article></div>')
section('motion','One entrance. Then still.',[
    'Open gate keeps the original 2400 ms run, once on load. Cells enter from behind the left bracket, land in slots 3, 2 and 1, and squash for 80 ms on contact. Do not add a new drop, dust effect or status sequence.',
    'At 640 ms the cells begin their 12 fps scan. At 1140 ms the middle cell holds amber. At 1390 ms the left turns green. From 1890 to 2240 ms the cells return to ink. The mark rests from then on; the dark full stop remains amber.',
    'Reduced motion and data-motion="off" show the static mark immediately. Body text, agent logos and ordinary product branding remain still. Never use the logo run as a progress indicator.',
    'For ordinary UI, use 100 ms feedback, 150 ms presses and up to 250 ms transitions. The Star CTA has a 120 ms press, 150 ms release and one 600 ms sheen on hover or keyboard focus. Reduced motion removes the sheen and transform.'
],'<div class="specimen"><div class="motion-display">'+INLINE+'</div><div class="motion-actions"><span>2400 ms / plays once</span><button class="copy" data-replay type="button">Replay</button></div></div>'+table(['Time','Action'],[['0 to 500 ms','Cells enter and land'],['640 ms','Working scan'],['1140 ms','Middle cell waits'],['1390 ms','Left cell done'],['1890 to 2240 ms','Return to ink'],['2400 ms onward','Rest']]))
section('marks','Respect every maker.',[
    'Show agent marks unaltered, in their supplied colours and proportions, on a neutral chip. Use equal optical heights, usually 24 to 32 px. They identify the tools; they do not form a stampede logo or imply endorsement.',
    'The star and arrows are original stampede interface icons under the code licence. Use one 1.6 px stroke, currentColor and 16, 20 or 24 px canvases. The gold button uses our own star, with no GitHub Invertocat.',
    'Agent names and logos belong to their owners and identify compatible tools. Anthropic owns Claude; OpenAI owns Codex; Anysphere owns Cursor. Grok Bot belongs to xAI and Tailscale belongs to Tailscale. Keep the source links and rights notes with the assets. No Herdr partner lockup is part of this kit.'
],'<div class="roster">'+''.join(f'<div class="agent-chip"><img src="agents/{n}.svg" alt="{label}"><span>{label}</span></div>' for n,label in [('claude','Claude'),('codex','Codex'),('cursor','Cursor'),('grokbot','Grok Bot'),('tailscale','Tailscale')])+'</div>'+pair('Place an original agent mark on its own neutral field.','Recolour it to amber, animate it or combine it with Open gate.'))
section('components','One clear next step.',[
    'Star on GitHub is the primary action. Its base is exactly #FFB547, with black text, a restrained metallic surface and a single light sweep. The target is 48 px tall. Keep Read the docs beside it in plain ink.',
    'The count is optional. The component fetches the public repository API, caches a valid count for one hour, and hides it on timeout, HTTP error or invalid data. No credentials are sent. Without JavaScript, it remains a working link. Portable previews disable the API request.',
    'The standalone component contains its HTML, CSS and tiny script. The guide uses the same styles and real links. Use the secondary neutral button for ordinary actions. Focus, hover and pressed states are available on the controls below.',
    'Terminal frames use a simple bar, one command area and written status. A cell is a neutral square; a status dot always sits beside a label. Keep shell commands copyable and do not add invented output.'
],'<div class="specimen component-stage">'+ACTIONS+'</div><h3>Install</h3><div class="codebox"><code>git clone https://github.com/vib-z/stampede.git</code><button class="copy" data-copy="git clone https://github.com/vib-z/stampede.git" type="button">Copy</button></div><h3>Terminal</h3><div class="terminal"><div class="bar">New job</div><pre>stampede new --file ask.md</pre><div class="status"><b></b><i></i>Ready to start</div></div>')
readme='''<picture>\n  <source media="(prefers-color-scheme: dark)" srcset="site/brand/lockup-dark.svg">\n  <img src="site/brand/lockup-light.svg" alt="stampede" width="320">\n</picture>'''
section('templates','Ready for the next release.',[
    'Use the 1200 by 630 px social card for Open Graph and the 1280 by 640 px image for the GitHub repository preview. Keep essential content 64 px inside every edge. The GitHub PNG stays under 1 MB.',
    'The README header uses the static lockup in a light and dark picture element, 320 px wide. Preserve the source aspect ratio and clear space.',
    'For the hero, place hero-mark/component.html directly above the h1. The mark is centred at 124 px wide on desktop and 96 px on phones, with a 32 px or 24 px gap. The original run plays once. Keep the title as real Geist text.',
    'Use the adaptive SVG favicon, ICO fallbacks at 16 and 32 px, a 180 px Apple touch icon, 192 and 512 px app icons, and the maskable 512 px icon. The mark stays inside the maskable central safe circle. Reference the supplied web app manifest.'
],'<img class="template-img" src="og-image.png" width="1200" height="630" alt="stampede social card"><h3>README header</h3><div class="codebox"><code>'+escape(readme)+'</code><button class="copy" data-copy="'+escape(readme,quote=True)+'" type="button">Copy</button></div><h3>Hero mark</h3><div class="specimen hero-snippet">'+HERO+'<h3>stampede</h3><p>One ask. A team that reports back.</p></div>')
assets=[('mark.svg','Adaptive mark / SVG'),('mark-light.svg','Black mark / SVG'),('mark-dark.svg','White mark / SVG'),('lockup.svg','Adaptive lockup / SVG'),('lockup-light.svg','Light lockup / SVG'),('lockup-dark.svg','Dark lockup / SVG'),('lockup-mono-dark.svg','One-ink dark lockup / SVG'),('lockup-animated.svg','Animated lockup / SVG'),('lockup.inline.svg','Inline lockup / SVG'),('logo.css','Logo motion / CSS'),('favicon.svg','Adaptive favicon / SVG'),('favicon.ico','Favicon / ICO'),('favicon-16.png','Favicon / 16 px PNG'),('favicon-32.png','Favicon / 32 px PNG'),('apple-touch-icon.png','Apple touch / 180 px PNG'),('icon-192.png','App icon / 192 px PNG'),('icon-512.png','App icon / 512 px PNG'),('icon-maskable-512.png','Maskable icon / 512 px PNG'),('site.webmanifest','Web app manifest'),('og-image.png','Open Graph / 1200 x 630 PNG'),('github-social.png','GitHub preview / 1280 x 640 PNG'),('cta/component.html','Star CTA / self-contained HTML'),('hero-mark/component.html','Hero mark / self-contained HTML'),('tokens.css','Design tokens / CSS'),('GUIDE.md','Guide / Markdown')]
assets += [('lockup-mono.svg','Adaptive one-ink lockup / SVG'),('cta/star.css','CTA styles / CSS'),('cta/star.js','Optional star count / JS'),('cta/actions.html','CTA markup / HTML'),('hero-mark/mark.inline.svg','Hero mark / inline SVG'),('hero-mark/hero-mark.css','Hero styles / CSS'),('README.md','Usage / Markdown'),('CREDITS.md','Credits / Markdown'),('imagery/sources.json','Image prompts and provenance / JSON')]
assets += [(f'imagery/{n}.webp',n.replace('-',' ').capitalize()+' / native WebP') for n in ['valley','mountains','lake','planet-surface','outer-world','grassland']]
assets += [(f'agents/{n}.svg',label+' / original SVG') for n,label in [('claude','Claude'),('codex','Codex'),('cursor','Cursor'),('grokbot','Grok Bot'),('tailscale','Tailscale')]]
assets += [('fonts/geist-latin.woff2','Geist / WOFF2'),('fonts/geist-mono-latin.woff2','Geist Mono / WOFF2'),('fonts/Geist-OFL.txt','Geist font notice'),('fonts/GeistMono-OFL.txt','Geist Mono font notice'),('fonts/JetBrainsMono-OFL.txt','Wordmark font notice')]
section('downloads','Use the source files.',[
    'Download the whole kit, or take the asset you need. SVGs remain crisp at every size; PNGs are for platforms that need a raster image. Keep the font notices and credits with redistributed assets.'
],'<a class="pill" href="brand-kit.zip" download data-bundle>Download the kit</a><div class="asset-list">'+''.join(f'<a href="{url}" download>{label}<span aria-hidden="true">↓</span></a>' for url,label in assets)+'</div>')
section('credits','Names and sources matter.',[
    'The code licence does not grant rights to the stampede name or marks. Use the supplied assets to identify or link to stampede. Do not alter them, imply endorsement, use the name as your own product name or put it on merchandise without permission.',
    'The Open gate geometry and animation come from the supplied stampede brand kit. Only the resting ink changed to pure black and white; the dark amber full stop remains the default. The wordmark uses JetBrains Mono 2.304 ExtraBold outlines. Geist and Geist Mono serve the interface. These fonts carry the SIL Open Font License 1.1.',
    'Linear is the primary reference for calm composition, type and motion. Vercel and Geist inform the guide structure. No source code, screenshots, marks or artwork from either brand are included.',
    'Third-party agent marks retain their owners\' rights. See the credits for the exact source URLs, font notices and image provenance.'
],'<a class="pill" href="credits.html">Sources and licences</a>')
nav=''.join(f'<a href="#{id}">{label}</a>' for (id,_,_,_),label in zip(sections,['Identity','Logo','Colour','Typography','Layout','Voice','Imagery','Motion','Agent marks','Components','Templates','Downloads','Credits']))
head='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="dark light"><title>stampede / Brand guide</title><link rel="icon" href="favicon.svg" type="image/svg+xml"><link rel="stylesheet" href="tokens.css"><link rel="stylesheet" href="logo.css"><link rel="stylesheet" href="cta/star.css"><link rel="stylesheet" href="guide.css"></head><body><div class="guide-shell"><header class="guide-top"><a href="preview.html" aria-label="stampede brand preview"><img class="logo-on-light" src="lockup-light.svg" alt="stampede"><img class="logo-on-dark" src="lockup-dark.svg" alt="stampede"></a><div class="top-actions"><a href="#downloads">Downloads</a><div class="theme-pick" aria-label="Colour theme"><button data-theme-pick="system" aria-pressed="true">System</button><button data-theme-pick="light" aria-pressed="false">Light</button><button data-theme-pick="dark" aria-pressed="false">Dark</button></div></div></header><div class="guide-layout"><nav class="guide-nav" aria-label="Brand guide sections">'''
intro='''</nav><main class="guide-main"><section class="guide-intro"><div class="kicker">stampede / Brand guide 0.1</div><h1>Give the team room.<br><span>Keep the intent clear.</span></h1><p>One ask. A team that reports back.<br>A working kit for everything we put into the world.</p><a class="pill" href="brand-kit.zip" download data-bundle>Download brand assets <span aria-hidden="true">↓</span></a></section>'''
html=head+nav+intro
md=['# stampede brand guide','', 'Identity 0.1. Updated 22 October 2026.', '', 'One ask. A team that reports back.', '', '[Open the visual guide](guide.html). [Download the kit](brand-kit.zip).','']
for i,(id,title,paragraphs,visual) in enumerate(sections,1):
    html+=f'\n<section class="guide-section" id="{id}"><div class="section-title"><span>{i:02}</span><h2>{title}</h2></div>'+''.join('<p>'+escape(p)+'</p>' for p in paragraphs)+visual+'</section>'
    md.extend(['## '+title,'',*sum(([p,''] for p in paragraphs),[])])
    parser=Tables(); parser.feed(visual)
    for rows in parser.tables:
        if rows:
            md.extend(['| '+' | '.join(rows[0])+' |','| '+' | '.join(['---']*len(rows[0]))+' |'])
            md.extend('| '+' | '.join(row)+' |' for row in rows[1:]); md.append('')
    import re
    for label,copy in re.findall(r'<strong>(Do|Avoid)</strong><p>(.*?)</p>',visual):
        md.extend(['**'+label+':** '+unescape(re.sub('<[^>]+>','',copy)),''])
    if id=='colour':
        md.extend(['| Role | Light | Dark |','| --- | --- | --- |']+[f'| {l[0]} | `{l[1]}` | `{d[1]}` |' for l,d in zip(light,dark)]+[''])
    if id=='imagery': md.extend(['[Six native grounds and prompts](imagery/sources.json). The visual guide shows social, README and launch compositions.',''])
    if id=='templates': md.extend(['```html',readme,'```',''])
    if id=='downloads': md.extend([f'- [{label}]({url})' for url,label in assets]+[''])
html+='''</main></div><footer class="guide-footer"><span>stampede</span><span>One ask. A team that reports back.</span><a href="credits.html">Credits</a></footer></div><div class="visually-hidden" role="status" aria-live="polite" id="copy-status"></div><script src="guide.js"></script><script src="preview.js"></script></body></html>'''
(ROOT/'guide.html').write_text(html)
(ROOT/'GUIDE.md').write_text('\n'.join(md))
print('Built 13 guide sections and the Markdown twin.')
