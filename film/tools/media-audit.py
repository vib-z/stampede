"""Decode every master frame, extract bookends, and preserve measured metadata."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

folder = Path(os.environ['FILM_MEDIA'])
rows = []
for cut, width, height in [('desktop', 1920, 1080), ('phone', 1080, 1920)]:
    for theme in ['light', 'dark']:
        file = folder / f'{cut}-{theme}.mp4'
        info = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-count_frames', '-show_streams', '-show_format', '-of', 'json', str(file)]))
        stream = info['streams'][0]
        assert (stream['width'], stream['height'], stream['nb_read_frames']) == (width, height, '420')
        assert stream['avg_frame_rate'] == '30/1'
        assert float(info['format']['duration']) == 14
        subprocess.run(['ffmpeg', '-v', 'error', '-i', str(file), '-f', 'null', '-'], check=True)
        for label, frame in [('first', 0), ('last', 419)]:
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(file), '-vf', f'select=eq(n\\,{frame})', '-frames:v', '1', str(folder / f'{cut}-{theme}-{label}.png')], check=True)
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(file), '-vf', 'fps=2,scale=320:-1,tile=7x4', '-frames:v', '1', str(folder / f'{cut}-{theme}-decoded-sheet.jpg')], check=True)
        rows.append({'file': file.name, 'bytes': file.stat().st_size, 'sha256': hashlib.sha256(file.read_bytes()).hexdigest(), 'width': width, 'height': height, 'frames': 420, 'fps': 30, 'durationSeconds': 14, 'allFramesDecoded': True, 'audio': False})
(folder / 'media-manifest.json').write_text(json.dumps(rows, indent=2) + '\n')
print(json.dumps(rows, indent=2))
