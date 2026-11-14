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

    def test_every_setting_config_example_lists_is_read_and_no_identity_name_is(self):
        text = (ROOT / 'config.example').read_text().split('\n# Environment only')[1]
        names = sorted(set(re.findall(r'(?m)^# ([A-Z][A-Z0-9_]*)=', text))) + ['HERDR', 'HERDR_BIN_PATH', 'HERDR_PLUGIN_STATE_DIR']
        identity = ['HERDR_ENV', 'HERDR_PANE_ID', 'HERDR_TAB_ID', 'HERDR_WORKSPACE_ID', 'HERDR_PLUGIN_EVENT_JSON',
                    'HERDR_EVENTS_OWNER', 'HC_TERMINAL_ID', 'HC_TERMINAL_SOCKET', 'HC_SCOPE', 'STAMPEDE_JOB_KEY', 'FLEET_JOB_DIR']
        self.assertIn('HERDR_EVENTS_ROUTES_DIR', names)
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
