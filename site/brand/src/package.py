"""Build the downloadable kit and an optional portable static-host preview."""
import argparse
import re
import shutil
import struct
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def pack_ico():
    images = [(size, (ROOT / f'favicon-{size}.png').read_bytes()) for size in (16, 32)]
    offset = 6 + 16 * len(images)
    directory = bytearray(struct.pack('<HHH', 0, 1, len(images)))
    for size, data in images:
        directory.extend(struct.pack('<BBBBHHII', size, size, 0, 0, 1, 32, len(data), offset))
        offset += len(data)
    (ROOT / 'favicon.ico').write_bytes(directory + b''.join(data for _, data in images))


def files():
    return sorted(p for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name != 'brand-kit.zip')


def build_zip():
    with zipfile.ZipFile(ROOT / 'brand-kit.zip', 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files():
            archive.write(path, path.relative_to(ROOT))
    assert (ROOT / 'brand-kit.zip').stat().st_size < 10 * 1024 * 1024


def preview(destination):
    destination.mkdir(parents=True, exist_ok=True)
    source_files = files() + [ROOT / 'brand-kit.zip']
    allowed = {'.html', '.css', '.js', '.mp4', '.webm', '.webp', '.png', '.jpg', '.svg', '.woff2', '.json', '.bin'}
    names = {}
    for path in source_files:
        name = str(path.relative_to(ROOT)).replace('/', '-')
        if path.name == 'preview.html':
            name = 'index.html'
        if path.suffix not in allowed:
            name += '.bin'
        names[path.resolve()] = name
    assert len(set(names.values())) == len(names)
    for path in source_files:
        name = names[path.resolve()]
        target = destination / name
        if path.suffix not in {'.html', '.css', '.js', '.svg'}:
            shutil.copy2(path, target)
            continue
        text = path.read_text()

        def resolve(value):
            u = urlsplit(value)
            if u.scheme or u.netloc or not u.path or value.startswith('data:'):
                return value
            source = (path.parent / u.path).resolve()
            if source not in names:
                raise ValueError(f'Missing local asset: {path.name}: {value}')
            return names[source] + ('?' + u.query if u.query else '') + ('#' + u.fragment if u.fragment else '')

        if path.suffix == '.html':
            text = re.sub(r'(href|src)="([^"]+)"', lambda m: m[1] + '="' + resolve(m[2]) + '"', text)
            text = re.sub(r'url\(([\'\"]?)([^)\'\"]+)\1\)', lambda m: 'url(' + m[1] + resolve(m[2]) + m[1] + ')', text)
            text = re.sub(r'<!doctype[^>]*>|</?(?:html|head|body)\b[^>]*>', '', text, flags=re.I)
            text = text.replace('data-star-count="true"', 'data-star-count="false"')
            text = re.sub(r'<a\b([^>]*?)href="([^"]+\.bin)"([^>]*)>', lambda m: '<a' + m[1] + 'href="' + m[2] + '"' + re.sub(r'\sdownload(?:="[^"]*")?', '', m[3]) + ' download="' + next(p.name for p, n in names.items() if n == m[2]) + '">', text)
            if name == 'index.html':
                text = re.sub(r'<title>.*?</title>', '', text, flags=re.S)
                text = '<title>stampede / Brand</title>' + text
        elif path.suffix == '.css':
            text = re.sub(r'url\(([\'\"]?)([^)\'\"]+)\1\)', lambda m: 'url(' + m[1] + resolve(m[2]) + m[1] + ')', text)
        target.write_text(text)
    # Remove stale files only from this pack's known previous manifest.
    manifest = destination / 'MANIFEST.txt'
    if manifest.exists():
        for line in manifest.read_text().splitlines():
            if '\t' in line:
                old = line.split('\t', 1)[0]
                if '/' not in old and old not in set(names.values()) and (destination / old).is_file():
                    (destination / old).unlink()
    outputs = sorted(p for p in destination.iterdir() if p.is_file() and p.name != 'MANIFEST.txt')
    assert len(outputs) + 1 <= 200
    total = sum(p.stat().st_size for p in outputs)
    assert total < 60 * 1024 * 1024 and all(p.stat().st_size < 14 * 1024 * 1024 for p in outputs)
    manifest.write_text('\n'.join(f'{p.name}\t{p.stat().st_size}' for p in outputs) + f'\nTotal: {total} bytes; {len(outputs)} files plus this manifest.\nBrowser check: pending; see production report.\n')
    print(f'Preview: {len(outputs)} files, {total} bytes')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--preview-dir', type=Path)
    args = parser.parse_args()
    pack_ico()
    build_zip()
    if args.preview_dir:
        preview(args.preview_dir)
    print(f'Kit ZIP: {(ROOT / "brand-kit.zip").stat().st_size} bytes')
