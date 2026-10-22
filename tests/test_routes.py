"""The event relay with HERDR_EVENTS_ROUTES_DIR: one routes folder for selection, sending, the owner tag and the doctor.
Temporary HOME, fake herdr and curl; nothing leaves the machine (stdlib)."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills/grokbot-herdr/scripts'


class Routes(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name).resolve()
        bin_dir = self.home / '.local/bin'
        bin_dir.mkdir(parents=True)
        for name in ('herdr-event-post', 'herdr-event-flush', 'herdr-events-owner', 'herdr-doctor'):
            (bin_dir / name).symlink_to(SCRIPTS / name)
        self.sent = self.home / 'sent'
        (bin_dir / 'curl').write_text(f'#!/bin/bash\nfor a; do u=$a; done\nprintf "%s " "$@" >> {self.sent}; echo >> {self.sent}\nprintf 200\n')
        (bin_dir / 'herdr').write_text('#!/bin/bash\ncase "$1 $2" in "workspace get") [ "$3" = w1 ];; *) echo "{}";; esac\n')
        for f in ('curl', 'herdr'):
            (bin_dir / f).chmod(0o755)
        self.routes = self.home / 'custom-routes'
        self.routes.mkdir()
        (self.home / '.config/herdr-events/owners').mkdir(parents=True)
        (self.home / '.config/herdr-events/owners/w1').write_text('owner=bot-alpha\n')
        self.env = {'HOME': str(self.home), 'PATH': f'{bin_dir}:/usr/bin:/bin', 'HERDR_EVENTS_ROUTES_DIR': str(self.routes),
                    'FLEET_TRUST_ROOT': str(self.home)}

    def route(self, name, url):
        (self.routes / name).write_text(f'URL={url}\nKEY=k\n')
        (self.routes / name).chmod(0o600)

    def post(self, pane, state='done'):
        subprocess.run([str(SCRIPTS / 'herdr-event-post'), json.dumps({'source': 'test', 'pane': pane, 'state': state})],
                       env=self.env, check=True, timeout=30)
        return self.sent.read_text() if self.sent.exists() else ''

    def test_a_bots_route_in_the_custom_folder_is_used_even_beside_a_default(self):
        self.route('bot-alpha', 'https://alpha.invalid/hook')
        self.route('default', 'https://default.invalid/hook')
        sent = self.post('w1:p1')
        self.assertIn('https://alpha.invalid/hook', sent)
        self.assertNotIn('default.invalid', sent)

    def test_a_bots_route_needs_no_default(self):
        self.route('bot-alpha', 'https://alpha.invalid/hook')
        self.assertIn('https://alpha.invalid/hook', self.post('w1:p1'))
        self.assertNotIn('w2', self.post('w2:p1', 'blocked'))     # untagged, no default: logged only

    def test_owner_tag_and_doctor_read_the_same_folder(self):
        self.route('bot-alpha', 'https://alpha.invalid/hook')
        tag = subprocess.run([str(SCRIPTS / 'herdr-events-owner'), 'w1', 'bot-alpha'], env=self.env,
                             capture_output=True, text=True, timeout=30)
        self.assertEqual(tag.returncode, 0, tag.stderr)
        self.assertNotIn('no route', tag.stderr)
        doctor = subprocess.run([str(SCRIPTS / 'herdr-doctor')], env=self.env, capture_output=True, text=True, timeout=60)
        routes = [l for l in doctor.stdout.splitlines() if 'route' in l]
        self.assertTrue(routes and all(l.startswith('ok ') for l in routes), doctor.stdout)


if __name__ == '__main__':
    unittest.main()
