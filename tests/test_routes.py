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

    # The settings file, ~/.config/stampede/config: herdr-platform reads it, so a timer, which starts a script with no
    # environment, sees what a shell does. The environment wins over the file.
    def settings(self, text):
        config = self.home / '.config/stampede/config'
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(text)

    def bare(self, script, *args, **env):
        """A script as a timer starts it: HOME and nothing else, plus what the caller names."""
        return subprocess.run(['/bin/bash', str(script), *args], env={'HOME': str(self.home), **env},
                              capture_output=True, text=True, timeout=30)

    def queued(self):
        return sorted((self.home / '.herdr-events/queue').glob('*.json'))

    def test_the_settings_file_reaches_every_relay_script_started_with_no_environment(self):
        self.route('bot-alpha', 'https://alpha.invalid/hook')
        (self.home / 'repos/r').mkdir(parents=True)
        subprocess.run(['git', 'init', '-q', str(self.home / 'repos/r')], check=True)
        event = json.dumps({'source': 'test', 'pane': 'w1:p1', 'state': 'blocked'})
        plugin = {'HERDR_BIN_PATH': str(self.home / '.local/bin/herdr'), 'HERDR_PLUGIN_EVENT_JSON': json.dumps(
            {'data': {'pane_id': 'w1:p1', 'workspace_id': 'w1', 'agent_status': 'done', 'agent': 'codex'}})}
        # with no file: the default routes folder (empty here) and the default trust root (missing here)
        self.assertIn('no route for bot-alpha', self.bare(SCRIPTS / 'herdr-events-owner', 'w1', 'bot-alpha').stderr)
        self.assertIn('refused', self.bare(SCRIPTS / 'herdr-trust', str(self.home / 'repos/r')).stderr)
        self.settings(f'export HERDR_EVENTS_ROUTES_DIR={self.routes}\nexport HERDR_EVENTS_MACHINE=box-one\n'
                      f'FLEET_TRUST_ROOT={self.home}/repos\nexport HERDR_EVENTS_DRYRUN=1\nexport OTHER=1\n')
        for shown in (self.bare(SCRIPTS / 'herdr-event-post', event), self.bare(ROOT / 'scripts/herdr-plugin-event', **plugin)):
            first, payload = shown.stdout.splitlines()
            self.assertTrue(first.endswith(' owner=bot-alpha route=bot-alpha'), shown.stdout + shown.stderr)
            self.assertEqual(json.loads(payload)['machine'], 'box-one')
        tag = self.bare(SCRIPTS / 'herdr-events-owner', 'w1', 'bot-alpha')
        self.assertEqual((tag.returncode, tag.stderr), (0, ''))
        trust = self.bare(SCRIPTS / 'herdr-trust', str(self.home / 'repos/r'))
        self.assertIn('claude: trusted', trust.stdout, trust.stderr)
        self.assertEqual(self.queued(), [])

    def test_the_environment_wins_over_the_settings_file_even_when_empty(self):
        self.route('bot-alpha', 'https://alpha.invalid/hook')
        self.settings('export HERDR_EVENTS_MACHINE=box-one\nexport HERDR_EVENTS_DRYRUN=1\n')
        event = json.dumps({'source': 'test', 'pane': 'w1:p1', 'state': 'blocked'})
        shown = self.bare(SCRIPTS / 'herdr-event-post', event, HERDR_EVENTS_MACHINE='box-two',
                          HERDR_EVENTS_ROUTES_DIR=str(self.routes))
        self.assertEqual(json.loads(shown.stdout.splitlines()[1])['machine'], 'box-two')
        shown = self.bare(SCRIPTS / 'herdr-event-post', event, HERDR_EVENTS_DRYRUN='', HERDR_EVENTS_ROUTES_DIR=str(self.routes))
        self.assertEqual(shown.stdout, '')   # an empty DRYRUN in the environment: a real event, sent
        self.assertIn('https://alpha.invalid/hook', self.sent.read_text())

    def test_a_broken_settings_file_gives_one_line_and_the_event_still_goes(self):
        self.route('bot-alpha', 'https://alpha.invalid/hook')
        self.settings(f'export HERDR_EVENTS_ROUTES_DIR={self.routes}\nif then\nexport HERDR_EVENTS_MACHINE=never\n')
        shown = self.bare(SCRIPTS / 'herdr-event-post', json.dumps({'source': 'test', 'pane': 'w1:p1', 'state': 'blocked'}))
        self.assertEqual(shown.returncode, 0)
        lines = shown.stderr.splitlines()
        self.assertEqual(len(lines), 1, shown.stderr)
        self.assertTrue(lines[0].startswith('stampede settings: ') and 'syntax error' in lines[0], lines)
        self.assertIn('https://alpha.invalid/hook', self.sent.read_text())   # what came before the error was read

    def test_a_dry_run_prints_the_event_and_leaves_no_log_queue_de_dupe_or_post(self):
        self.route('bot-alpha', 'https://alpha.invalid/hook')
        event = {'source': 'test', 'pane': 'w1:p1', 'state': 'done', 'last_assistant_message': 'long'}
        shown = subprocess.run([str(SCRIPTS / 'herdr-event-post'), json.dumps(event)], capture_output=True, text=True,
                               env={**self.env, 'HERDR_EVENTS_DRYRUN': '1'}, timeout=30)
        first, payload = shown.stdout.splitlines()
        self.assertEqual(first, 'DRYRUN test pane=w1:p1 state=done owner=bot-alpha route=bot-alpha')
        self.assertEqual({k: json.loads(payload).get(k) for k in ('route', 'owner', 'workspace', 'last_assistant_message')},
                         {'route': 'bot-alpha', 'owner': 'bot-alpha', 'workspace': 'w1', 'last_assistant_message': None})
        self.assertEqual(self.queued(), [])
        self.assertFalse(self.sent.exists())
        self.assertFalse(any('pane=w1:p1' in p.read_text() for p in self.home.rglob('herdr-events.log')))
        self.assertIn('https://alpha.invalid/hook', self.post('w1:p1'))   # recorded no de-dupe: the real one goes


if __name__ == '__main__':
    unittest.main()
