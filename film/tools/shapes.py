"""Outline the existing brand font and embed the supplied official marks."""
import json
import re
from pathlib import Path
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.varLib.instancer import instantiateVariableFont

root = Path(__file__).resolve().parents[2]
font = TTFont(root / 'site/assets/fonts/geist-latin.woff2')
if 'fvar' in font:
    font = instantiateVariableFont(font, {'wght': 500})
glyphs = font.getGlyphSet()
cmap = font.getBestCmap()
units = font['head'].unitsPerEm
texts = ['Build the pricing page.', 'Build the', 'pricing page.', 'Pricing page ready.',
         'Ready for your review.', 'Ready on staging.', 'Tested. Reviewed. Your call.', 'Tested. Reviewed.', 'Your call.', 'On it.', 'Your lead has the team.', 'You can get back to your day.', 'Grok Bot', 'your Mac', 'always on', 'cloud',
         'lead', 'research', 'test', 'build', 'design', 'review', 'Tailscale',
         'All agents closed.', 'Reopen any time.', 'Pricing', 'Ready for', 'your review.']
texts += ['Research pins the brief.', 'Builders move to cloud.', 'Build. Then refine.', 'Test. Review. Test again.', 'Starter', 'Team', 'Scale', 'round 1', 'round 2', 'One ask.', 'A lead lands.', 'Two builders cross.', 'The page takes shape.', 'The work comes home.', 'Every agent closes.']
texts += ['Build the pricing page.'[:n] for n in range(9, 24)]
texts += ['pricing page.'[:n] for n in range(1, 14)]
texts += ['Build the'[:n] for n in range(1, 10)]
texts += ['Ready on', 'staging.']
texts = list(dict.fromkeys(texts))
out = {'text': {}, 'logos': {}}
for value in texts:
    pen = SVGPathPen(glyphs)
    advance = 0
    for char in value:
        name = cmap[ord(char)]
        glyphs[name].draw(TransformPen(pen, (1/units, 0, 0, -1/units, advance, 0)))
        advance += glyphs[name].width / units
    outline = re.sub(r'-?\d+\.\d+(?:e[-+]?\d+)?', lambda m: format(round(float(m[0]), 4), '.4f').rstrip('0').rstrip('.'), pen.getCommands())
    out['text'][value] = {'path': outline, 'width': advance}
for name in ['claude', 'codex', 'cursor', 'grokbot', 'tailscale']:
    out['logos'][name] = (root / f'site/assets/logos/{name}.svg').read_text()
(root / 'film/brand/shapes.js').write_text('window.SHAPES = ' + json.dumps(out) + ';\n')
