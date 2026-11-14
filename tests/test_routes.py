"""The event relay with HERDR_EVENTS_ROUTES_DIR: one routes folder for selection, sending, the owner tag and the doctor.
Temporary HOME, fake herdr and curl; nothing leaves the machine (stdlib)."""
import json
import os
import re
import subprocess
import tempfile
import time
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
        self.sent, self.body = self.home / 'sent', self.home / 'body'
        (bin_dir / 'curl').write_text(f'#!/bin/bash\nfor a; do u=$a; done\nprintf "%s " "$@" >> {self.sent}; echo >> {self.sent}\n'
                                    f'case " $* " in *" @- "*) cat >> {self.body};; esac\nprintf 200\n')
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

    # HERDR_EVENTS_FALLBACK_ROUTE: where an owner with no route of its own, and a Codex turn outside Herdr, go
    def sent_to(self, event, *flags, **env):
        """The URL and payload of the one event this post sent, or None when it sent nothing."""
        before = self.sent.read_text().count('\n') if self.sent.exists() else 0
        subprocess.run([str(SCRIPTS / 'herdr-event-post'), *flags, json.dumps(event)], env={**self.env, **env},
                       capture_output=True, timeout=30)
        lines = self.sent.read_text().splitlines() if self.sent.exists() else []
        if len(lines) == before:
            return None
        return re.search(r'https://\S+', lines[-1]).group(0), json.loads(self.body.read_text().splitlines()[-1])

    def log(self):
        return ''.join(p.read_text() for p in self.home.rglob('herdr-events.log'))

    def test_an_owner_with_no_route_goes_to_default_unless_a_fallback_route_is_set(self):
        self.route('default', 'https://default.invalid/hook')
        self.route('bot-fallback', 'https://fallback.invalid/hook')
        event = {'source': 'test', 'pane': 'w1:p1', 'state': 'blocked'}
        self.assertEqual(self.sent_to(event)[0], 'https://default.invalid/hook')
        url, payload = self.sent_to({**event, 'pane': 'w1:p2'}, HERDR_EVENTS_FALLBACK_ROUTE='bot-fallback')
        self.assertEqual((url, payload['route'], payload['owner']), ('https://fallback.invalid/hook', 'bot-fallback', 'bot-alpha'))
        untagged = {'source': 'test', 'pane': 'w2:p1', 'state': 'blocked'}   # no owner: default, with or without it
        self.assertEqual(self.sent_to(untagged, HERDR_EVENTS_FALLBACK_ROUTE='bot-fallback')[1]['route'], 'default')
        self.route('bot-alpha', 'https://alpha.invalid/hook')                  # its own route wins
        self.assertEqual(self.sent_to({**event, 'pane': 'w1:p3'}, HERDR_EVENTS_FALLBACK_ROUTE='bot-fallback')[1]['route'], 'bot-alpha')

    def test_a_fallback_route_that_is_not_a_route_files_name_is_ignored(self):
        self.route('default', 'https://default.invalid/hook')
        (self.home / '.hidden').write_text('URL=https://hidden.invalid/hook\n')
        (self.routes / '.hidden').write_text('URL=https://hidden.invalid/hook\n')
        for n, bad in enumerate(('../.hidden', '.hidden', f'{self.routes}/default', 'missing')):
            with self.subTest(bad=bad):
                event = {'source': 'test', 'pane': f'w1:p{n}', 'state': 'blocked'}
                self.assertEqual(self.sent_to(event, HERDR_EVENTS_FALLBACK_ROUTE=bad)[1]['route'], 'default')
                self.assertIn('ignored HERDR_EVENTS_FALLBACK_ROUTE', self.log())
                self.assertIsNone(self.sent_to({'source': 'codex-desktop', 'state': 'agent-turn-complete', 'thread_id': f't{n}'},
                                               HERDR_EVENTS_FALLBACK_ROUTE=bad))

    def test_a_fallback_route_is_read_as_any_route_is(self):
        # a link in the routes folder is followed, as for the default route: the folder is the user's own
        outside = self.home / 'outside'
        outside.write_text('URL=https://outside.invalid/hook\n')
        (self.routes / 'linked').symlink_to(outside)
        (self.routes / 'default').symlink_to(outside)
        event = {'source': 'test', 'pane': 'w1:p1', 'state': 'blocked'}
        self.assertEqual(self.sent_to(event)[0], 'https://outside.invalid/hook')
        url, payload = self.sent_to({**event, 'pane': 'w1:p2'}, HERDR_EVENTS_FALLBACK_ROUTE='linked')
        self.assertEqual((url, payload['route']), ('https://outside.invalid/hook', 'linked'))
        self.assertNotIn('ignored HERDR_EVENTS_FALLBACK_ROUTE', self.log())

    def test_a_fallback_route_with_an_odd_name_is_ignored(self):
        self.route('default', 'https://default.invalid/hook')
        (self.routes / 'sub').mkdir()
        for name in ('with space', 'with\nnewline', '.dotted', 'sub/inner'):
            self.route(name, 'https://odd.invalid/hook')
        for n, bad in enumerate(('with space', 'with\nnewline', '.dotted', 'sub/inner')):
            with self.subTest(bad=bad):
                before = self.log().count('ignored HERDR_EVENTS_FALLBACK_ROUTE')
                url, payload = self.sent_to({'source': 'test', 'pane': f'w1:p{n}', 'state': 'blocked'}, HERDR_EVENTS_FALLBACK_ROUTE=bad)
                self.assertEqual((url, payload['route']), ('https://default.invalid/hook', 'default'))
                self.assertEqual(self.log().count('ignored HERDR_EVENTS_FALLBACK_ROUTE'), before + 1)
                tag = subprocess.run([str(SCRIPTS / 'herdr-events-owner'), 'w1', 'bot-beta'], capture_output=True, text=True,
                                     timeout=30, env={**self.env, 'HERDR_EVENTS_FALLBACK_ROUTE': bad})
                self.assertIn('events relay via the default route', tag.stderr)

    def test_a_desktop_turn_whose_queue_write_failed_goes_when_posted_again(self):
        self.route('bot-fallback', 'https://fallback.invalid/hook')
        not_a_folder = self.home / 'not-a-folder'
        not_a_folder.write_text('x')
        event = {'source': 'codex-desktop', 'state': 'agent-turn-complete', 'thread_id': 'thread-1', 'turn_id': 'turn-1'}
        self.assertIsNone(self.sent_to(event, HERDR_EVENTS_FALLBACK_ROUTE='bot-fallback', HERDR_EVENTS_HOME=str(not_a_folder)))
        self.assertIn('queue-write-failed', self.log())
        self.assertEqual(self.sent_to(event, HERDR_EVENTS_FALLBACK_ROUTE='bot-fallback')[0], 'https://fallback.invalid/hook')

    def test_any_other_event_whose_queue_write_failed_is_still_taken_as_sent(self):   # as before the desktop source
        self.route('default', 'https://default.invalid/hook')
        not_a_folder = self.home / 'not-a-folder'
        not_a_folder.write_text('x')
        event = {'source': 'test', 'pane': 'w2:p1', 'state': 'blocked'}
        self.assertIsNone(self.sent_to(event, HERDR_EVENTS_HOME=str(not_a_folder)))
        self.assertIsNone(self.sent_to(event))
        self.assertIn('dedupe-skip', self.log())

    def test_strict_never_uses_the_fallback_route(self):
        self.route('bot-fallback', 'https://fallback.invalid/hook')
        refused = subprocess.run([str(SCRIPTS / 'herdr-event-post'), '--strict', json.dumps(
            {'source': 'stampede', 'state': 'gate', 'owner': 'bot-alpha', 'gate': 'a' * 12})],
            env={**self.env, 'HERDR_EVENTS_FALLBACK_ROUTE': 'bot-fallback'}, capture_output=True, text=True, timeout=30)
        self.assertEqual(refused.returncode, 3, refused.stdout + refused.stderr)
        self.assertIn('no route of its own for owner bot-alpha', refused.stderr)
        self.assertFalse(self.sent.exists())

    def codex_turn(self, thread, **env):
        """A Codex turn as the Codex desktop app's notify runs it, with no Herdr pane and no Core terminal: the URL and
        payload it sent, or None."""
        link = self.home / '.local/bin/herdr-event-codex-notify'
        if not link.exists():
            link.symlink_to(SCRIPTS / 'herdr-event-codex-notify')
        rollouts = self.home / 'codex/sessions/2026/11/11'
        rollouts.mkdir(parents=True, exist_ok=True)
        (rollouts / f'rollout-x-{thread}.jsonl').write_text('{"payload":{}}\n')
        before = self.sent.read_text().count('\n') if self.sent.exists() else 0
        subprocess.run([str(link), json.dumps({'type': 'agent-turn-complete', 'thread-id': thread, 'turn-id': 'turn-1',
                                               'cwd': '/somewhere', 'last-assistant-message': 'hi'})],
                       env={**self.env, 'CODEX_HOME': str(self.home / 'codex'), 'HERDR_EVENTS_OWNER': 'bot-alpha', **env},
                       check=True, capture_output=True, timeout=30)
        lines = self.sent.read_text().splitlines() if self.sent.exists() else []
        return None if len(lines) == before else (re.search(r'https://\S+', lines[-1]).group(0), json.loads(self.body.read_text().splitlines()[-1]))

    def test_a_codex_turn_outside_herdr_is_skipped_unless_a_fallback_route_is_set(self):
        self.route('default', 'https://default.invalid/hook')
        self.route('bot-fallback', 'https://fallback.invalid/hook')
        self.assertIsNone(self.codex_turn('desk-1'))
        self.assertIn('skip: codex turn with no herdr pane', self.log())
        url, event = self.codex_turn('desk-2', HERDR_EVENTS_FALLBACK_ROUTE='bot-fallback')
        self.assertEqual((url, event['route'], event['source'], event.get('owner')),
                         ('https://fallback.invalid/hook', 'bot-fallback', 'codex-desktop', None))  # never the owner in its environment
        self.assertNotIn('workspace', event)
        self.assertNotIn('pane', event)
        self.assertIsNone(self.codex_turn('desk-3', HERDR_EVENTS_FALLBACK_ROUTE='a/b'))   # not a route's name: skipped, as unset
        _, in_pane = self.codex_turn('desk-4', HERDR_EVENTS_FALLBACK_ROUTE='bot-fallback', HERDR_PANE_ID='w1:p4')
        self.assertEqual((in_pane['source'], in_pane['owner'], in_pane['route']), ('codex', 'bot-alpha', 'bot-fallback'))

    def test_two_codex_desktop_turns_are_two_events_and_the_same_one_twice_is_one(self):
        self.route('bot-fallback', 'https://fallback.invalid/hook')
        env = {**self.env, 'HERDR_EVENTS_FALLBACK_ROUTE': 'bot-fallback'}
        for thread, turn in (('thread-1', 'turn-1'), ('thread-2', 'turn-1'), ('thread-2', 'turn-2'), ('thread-2', 'turn-2')):
            subprocess.run([str(SCRIPTS / 'herdr-event-post'), json.dumps({
                'source': 'codex-desktop', 'state': 'agent-turn-complete', 'thread_id': thread, 'turn_id': turn})],
                env=env, check=True, timeout=30)
        self.assertEqual(self.sent.read_text().count('https://fallback.invalid/hook'), 3)

    def test_the_owner_tag_names_the_fallback_route_when_the_bot_has_none(self):
        self.route('bot-fallback', 'https://fallback.invalid/hook')
        tag = subprocess.run([str(SCRIPTS / 'herdr-events-owner'), 'w1', 'bot-beta'], capture_output=True, text=True, timeout=30,
                             env={**self.env, 'HERDR_EVENTS_FALLBACK_ROUTE': 'bot-fallback'})
        self.assertIn('no route for bot-beta yet; events relay via the bot-fallback route', tag.stderr)

    # The settings file, ~/.config/stampede/config: herdr-platform reads its plain NAME=value lines as data, so a
    # script a timer starts with no environment sees them. It never runs the file. The environment wins.
    def settings(self, text):
        config = self.home / '.config/stampede/config'
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_bytes(text.encode())

    def bare(self, script, *args, **env):
        """A script as a timer starts it: HOME and nothing else, plus what the caller names."""
        return subprocess.run(['/bin/bash', str(script), *args], env={'HOME': str(self.home), **env},
                              capture_output=True, text=True, timeout=30)

    def read_back(self, bash, names, how='platform'):
        """What a shell holds for each name after herdr-platform (or, how='source', after sourcing the file)."""
        load = f'. {SCRIPTS / "herdr-platform"}' if how == 'platform' else 'set -a; . "$HOME/.config/stampede/config"'
        show = '; '.join(f'printf "%s\\0" "${{{n}-<unset>}}"' for n in names)
        out = subprocess.run([bash, '-c', f'{load} >/dev/null 2>&1; {show}'], env={'HOME': str(self.home)},
                             capture_output=True, timeout=30).stdout.decode()
        return dict(zip(names, out.split('\0')))

    def bashes(self):
        return sorted({'/bin/bash', *(b for b in ('/opt/homebrew/bin/bash', '/usr/local/bin/bash') if Path(b).exists())})

    def test_a_line_the_reader_takes_holds_what_a_shell_that_sources_it_holds(self):
        taken = ['N=plain', 'export N=plain', 'export\tN=tab\t# a tab between tokens', '  export   N=a.b/c:d@e%f+g,h=i-j_k', 'N=', 'N= # nothing',
                 'N=x # a comment', 'N=x\t# a tab, then a comment', "N='a $b `c` \\d \"e\"'", "N='x' # it's",
                 'N="a b $HOME ${HOME} ~/c \' !"', 'N="x" # c', 'N=$HOME/x', 'N=${HOME}/x', 'N=~/x', 'N=$HOME',
                 'N=a=b', 'N="$HOME}"', 'N=trailing   ']
        skipped = ['N=$(echo ran)', 'N=`echo ran`', 'N=$OTHER', 'N=$HOMEx', 'N=$HOME_x', 'N="${HOME:-x}"', 'N=${HOME:-x}',
                   'N="a\\"b"', 'N=a\\ b', 'N=a b', 'N=(a b)', 'N=a#b', "N='a'#b", 'N="a"b', 'N=x\\', 'N=~', 'N=a:~/b',
                   'N=*', 'N=a;b', 'export N', 'export -n N=x', 'readonly N=x', 'N=x; M=y', 'N=x && M=y', 'f() { N=x; }',
                   'if true; then N=x; fi', 'N={a,b}', 'N="$1"', 'N=é', '1N=x', 'N=a$', 'N="a$"',
                   # a control byte bash does not take as a space: after the value, before the name, after export
                   *[f'N=x{c} # c' for c in '\v\f\r'], *[f'{c}N=x' for c in '\v\f\r'], *[f'export{c}N=x' for c in '\v\f\r'],
                   "N='a\tb'", 'N="a\tb"', 'N=a\x01b']
        for bash in self.bashes():
            for line in taken + skipped:
                with self.subTest(bash=bash, line=line):
                    self.settings(line.replace('N', 'HERDR_EVENTS_MACHINE', 1) + '\n')
                    got = self.read_back(bash, ['HERDR_EVENTS_MACHINE'])['HERDR_EVENTS_MACHINE']
                    if line in skipped:
                        self.assertEqual(got, '<unset>')
                    else:
                        self.assertEqual(got, self.read_back(bash, ['HERDR_EVENTS_MACHINE'], 'source')['HERDR_EVENTS_MACHINE'])
                        self.assertNotEqual(got, '<unset>')

    def test_crlf_no_final_newline_and_the_last_line_wins(self):
        self.settings('HC=one\r\nHC=two\r\nHC_SESSION=s')
        self.assertEqual(self.read_back('/bin/bash', ['HC', 'HC_SESSION']), {'HC': 'two', 'HC_SESSION': 's'})

    def test_a_file_over_100_lines_or_4_kb_or_with_a_nul_is_skipped_whole_and_the_event_still_goes(self):
        self.route('bot-alpha', 'https://alpha.invalid/hook')
        names = [f'HERDR_EVENTS_X{i}' for i in range(100)]
        longest = [f'{n}={"v" * (38 - len(n))}' for n in names]   # 100 lines, 4 KB: the most a file may hold
        self.settings('\n'.join(longest) + '\n')
        self.assertLessEqual(len('\n'.join(longest) + '\n'), 4096)
        for bash in self.bashes():
            got = self.read_back(bash, names)
            self.assertEqual([n for n in names if got[n] == '<unset>'], [], bash)
        for text, why in (('\n'.join(longest) + '\nHC=x\n', 'over 100 lines'),
                          ('HC=x\n' + '# ' + 'x' * 4096 + '\n', 'over 4 KB'),
                          ('\n'.join(f'{n}={"v" * 400}' for n in names) + '\n', 'over 4 KB'),   # enough to overflow the environment
                          ('HC=x\n\0\nHC_SESSION=y\n', 'it holds a NUL byte'),
                          (None, 'not a readable regular file')):                          # a folder in its place
            config = self.home / '.config/stampede/config'
            if config.is_dir():
                config.rmdir()
            if text is None:
                config.unlink()
                config.mkdir()
            else:
                self.settings(text)
            doctor = self.bare(SCRIPTS / 'herdr-doctor', '--relay', HERDR_EVENTS_ROUTES_DIR=str(self.routes))
            self.assertIn(f'warn the settings file is not read: {why}; a timer and the hooks do not see it', doctor.stdout)
            self.assertNotIn('HC=x', doctor.stdout + doctor.stderr)
            for bash in self.bashes():
                self.assertEqual(set(self.read_back(bash, ['HC', 'HC_SESSION', names[0]]).values()), {'<unset>'}, (bash, why))
            post = self.bare(SCRIPTS / 'herdr-event-post', json.dumps({'source': 'test', 'pane': 'w1:p1', 'state': 'blocked'}),
                             HERDR_EVENTS_ROUTES_DIR=str(self.routes))
            self.assertEqual((post.returncode, post.stdout, post.stderr), (0, '', ''))
            self.assertIn('https://alpha.invalid/hook', self.sent.read_text())
            self.sent.unlink()
            (self.home / '.local/state/herdr-events/dedupe.tsv').unlink()
        (self.home / '.config/stampede/config').rmdir()
        self.settings('\n'.join(longest) + '\n')   # the largest file allowed: the event still goes
        post = self.bare(SCRIPTS / 'herdr-event-post', json.dumps({'source': 'test', 'pane': 'w1:p1', 'state': 'blocked'}),
                         HERDR_EVENTS_ROUTES_DIR=str(self.routes))
        self.assertEqual((post.returncode, post.stderr), (0, ''))
        self.assertIn('https://alpha.invalid/hook', self.sent.read_text())

    def test_a_variable_named_like_the_readers_own_state_does_not_let_the_file_win(self):
        self.route('bot-alpha', 'https://alpha.invalid/hook')
        (self.home / 'elsewhere').mkdir()
        self.settings('HERDR_EVENTS_ROUTES_DIR=$HOME/elsewhere\nHC=from-file\n')
        inherited = {'_hp_m_HERDR_EVENTS_ROUTES_DIR': '1', '_hp_m_HC': '1', '_hp_seen': ' HERDR_EVENTS_ROUTES_DIR HC '}
        post = self.bare(SCRIPTS / 'herdr-event-post', json.dumps({'source': 'test', 'pane': 'w1:p1', 'state': 'blocked'}),
                         HERDR_EVENTS_ROUTES_DIR=str(self.routes), **inherited)
        self.assertEqual((post.returncode, post.stderr), (0, ''))
        self.assertIn('https://alpha.invalid/hook', self.sent.read_text())   # the environment's folder: queued and sent
        for bash in self.bashes():
            shown = subprocess.run([bash, '-c', f'. {SCRIPTS / "herdr-platform"}; printf "[%s]" "${{HC-unset}}"'],
                                   env={'HOME': str(self.home), 'HC': '', **inherited}, capture_output=True, text=True, timeout=30)
            self.assertEqual(shown.stdout, '[]', bash)   # empty in the environment stays empty

    def test_with_home_unset_a_line_that_needs_it_is_skipped_and_nothing_breaks(self):
        xdg = self.home / 'xdg'
        (xdg / 'stampede').mkdir(parents=True)
        (xdg / 'stampede/config').write_text('HC=~/x\nHC_SESSION=$HOME/x\nHC_SOCKET=${HOME}/y\nHERDR_EVENTS_MACHINE=plain\n')
        show = f'. {SCRIPTS / "herdr-platform"}; printf "%s|%s|%s|%s|%s" "${{HC-unset}}" "${{HC_SESSION-unset}}" "${{HC_SOCKET-unset}}" "${{HERDR_EVENTS_MACHINE-unset}}" "$herdr_settings_skipped"'
        for bash in self.bashes():
            for strict in ('', 'set -euo pipefail; '):
                shown = subprocess.run([bash, '-c', strict + show], env={'XDG_CONFIG_HOME': str(xdg)}, capture_output=True, text=True, timeout=30)
                self.assertEqual((shown.returncode, shown.stderr, shown.stdout), (0, '', 'unset|unset|unset|plain|1 2 3'), (bash, strict))
                none = subprocess.run([bash, '-c', strict + f'. {SCRIPTS / "herdr-platform"}; printf "%s" "${{HERDR_EVENTS_MACHINE-unset}}"'],
                                      env={}, capture_output=True, text=True, timeout=30)
                self.assertEqual((none.returncode, none.stderr, none.stdout), (0, '', 'unset'), (bash, strict))

    def test_every_setting_config_example_lists_is_read_and_no_identity_name_is(self):
        text = (ROOT / 'config.example').read_text().split('\n# Environment only')[1]
        names = sorted(set(re.findall(r'(?m)^# ([A-Z][A-Z0-9_]*)=', text))) + ['HERDR', 'HERDR_BIN_PATH', 'HERDR_PLUGIN_STATE_DIR']
        identity = ['HERDR_ENV', 'HERDR_PANE_ID', 'HERDR_TAB_ID', 'HERDR_WORKSPACE_ID', 'HERDR_PLUGIN_EVENT_JSON',
                    'HERDR_EVENTS_OWNER', 'HC_TERMINAL_ID', 'HC_TERMINAL_SOCKET', 'HC_SCOPE', 'STAMPEDE_JOB_KEY', 'FLEET_JOB_DIR']
        for name in ('HERDR_EVENTS_ROUTES_DIR', 'HERDR_EVENTS_FALLBACK_ROUTE', 'HERDR_EVENTS_LAUNCHD', 'HERDR_DOCTOR_EXTRA'):
            self.assertIn(name, names)
        self.settings(''.join(f'{n}=v-{n}\n' for n in names + identity + ['PATH', 'OTHER']))
        got = self.read_back('/bin/bash', names + identity + ['OTHER'])
        self.assertEqual({n: got[n] for n in names}, {n: f'v-{n}' for n in names})
        self.assertEqual({n: got[n] for n in identity + ['OTHER']}, {n: '<unset>' for n in identity + ['OTHER']})
        listed = [line[2:].split('  # ')[0] for line in text.splitlines() if re.match(r'# [A-Z][A-Z0-9_]*=', line)]
        self.settings('\n'.join(listed) + '\n')   # each line of the block, uncommented, is one the reader takes
        self.assertNotIn('<unset>', self.read_back('/bin/bash', [line.split('=')[0] for line in listed]).values())

    def test_the_settings_file_reaches_every_relay_script_started_with_no_environment(self):
        self.route('bot-alpha', 'https://alpha.invalid/hook')
        (self.home / 'repos/r').mkdir(parents=True)
        subprocess.run(['git', 'init', '-q', str(self.home / 'repos/r')], check=True)
        # with no file: the default routes folder (empty here) and the default trust root (missing here)
        self.assertIn('no route for bot-alpha', self.bare(SCRIPTS / 'herdr-events-owner', 'w1', 'bot-alpha').stderr)
        self.assertIn('refused', self.bare(SCRIPTS / 'herdr-trust', str(self.home / 'repos/r')).stderr)
        self.assertFalse(self.sent.exists())
        self.settings(f'export HERDR_EVENTS_ROUTES_DIR={self.routes}\nexport HERDR_EVENTS_MACHINE=box-one\n'
                      'FLEET_TRUST_ROOT=$HOME/repos\n')
        post = self.bare(SCRIPTS / 'herdr-event-post', json.dumps({'source': 'test', 'pane': 'w1:p1', 'state': 'blocked'}))
        self.assertEqual((post.returncode, post.stdout, post.stderr), (0, '', ''))
        self.assertIn('https://alpha.invalid/hook', self.sent.read_text())
        self.assertEqual(json.loads(self.body.read_text().splitlines()[-1])['machine'], 'box-one')
        tag = self.bare(SCRIPTS / 'herdr-events-owner', 'w1', 'bot-alpha')
        self.assertEqual((tag.returncode, tag.stderr), (0, ''))
        trust = self.bare(SCRIPTS / 'herdr-trust', str(self.home / 'repos/r'))
        self.assertIn('claude: trusted', trust.stdout, trust.stderr)

    def test_the_plugin_hook_uses_its_own_settings_from_the_file_and_hands_them_on(self):
        self.route('bot-alpha', 'https://alpha.invalid/hook')
        herdr = self.home / 'custom-herdr'
        herdr.write_text(f'#!/bin/bash\necho "$*" >> {self.home}/custom-herdr-calls\necho "{{}}"\n')
        herdr.chmod(0o755)
        self.settings(f'export HERDR_EVENTS_ROUTES_DIR={self.routes}\nexport HERDR_EVENTS_MACHINE=box-one\n'
                      'export HERDR_BIN_PATH=$HOME/custom-herdr\nexport HERDR_PLUGIN_STATE_DIR=$HOME/custom-state\n')
        event = json.dumps({'data': {'pane_id': 'w1:p1', 'workspace_id': 'w1', 'agent_status': 'done', 'agent': 'codex'}})
        hook = self.bare(ROOT / 'scripts/herdr-plugin-event', HERDR_PLUGIN_EVENT_JSON=event)
        self.assertEqual(hook.returncode, 0, hook.stderr)
        self.assertIn('pane get w1:p1', (self.home / 'custom-herdr-calls').read_text())
        self.assertTrue((self.home / 'custom-state/panes/w1_p1').exists())
        self.assertEqual(json.loads(self.body.read_text().splitlines()[-1])['machine'], 'box-one')

    def test_the_environment_wins_over_the_settings_file_even_when_empty(self):
        self.settings('export HC_SESSION=from-file\nexport HC_SOCKET=/from/file\nexport HC=from-file\n')
        script = f'. {SCRIPTS / "herdr-platform"}; printf "%s|%s|%s" "$HC_SESSION" "$HC_SOCKET" "${{HC-unset}}"'
        shown = subprocess.run(['/bin/bash', '-c', script], env={'HOME': str(self.home), 'HC_SESSION': 'env', 'HC_SOCKET': ''},
                               capture_output=True, text=True, timeout=30).stdout
        self.assertEqual(shown, 'env||from-file')

    def test_code_in_the_settings_file_never_runs_and_nothing_of_it_is_printed(self):
        self.route('bot-alpha', 'https://alpha.invalid/hook')
        self.settings(f'export HERDR_EVENTS_ROUTES_DIR={self.routes}\n'
                      'touch "$HOME/side-effect"\nexit 3\nset -x\nIFS=_\nsleep 5\nprintf() { :; }\nset -eu; false\n'
                      'export HERDR_EVENTS_MACHINE="FAKE_SECRET_123\nexport HERDR_EVENTS_HOME=$HOME/q\n')
        started = time.monotonic()
        post = self.bare(SCRIPTS / 'herdr-event-post', json.dumps({'source': 'test', 'pane': 'w1:p1', 'state': 'blocked'}))
        self.assertLess(time.monotonic() - started, 4)
        self.assertEqual((post.returncode, post.stdout, post.stderr), (0, '', ''))
        self.assertIn('https://alpha.invalid/hook', self.sent.read_text())
        doctor = self.bare(SCRIPTS / 'herdr-doctor', '--relay')
        self.assertIn('warn settings file lines 2, 3, 4, 6, 7, 8, 9: not a plain NAME=value', doctor.stdout)
        install = subprocess.run(['./install.sh', '--dry-run'], cwd=ROOT, env={'HOME': str(self.home), 'PATH': '/usr/bin:/bin'},
                                 capture_output=True, text=True, timeout=60)
        self.assertEqual(install.returncode, 0, install.stdout + install.stderr)
        self.assertFalse((self.home / 'side-effect').exists())
        config = self.home / '.config/stampede/config'
        leaked = [p for p in self.home.rglob('*') if p.is_file() and p != config and b'FAKE_SECRET' in p.read_bytes()]
        self.assertEqual(leaked, [])
        for out in (post.stdout, post.stderr, doctor.stdout, doctor.stderr, install.stdout, install.stderr):
            self.assertNotIn('FAKE_SECRET', out)


if __name__ == '__main__':
    unittest.main()
