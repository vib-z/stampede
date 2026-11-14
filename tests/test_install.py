"""install.sh and the Herdr plugin, only in temporary HOME directories with fakes (stdlib)."""
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import tempfile
import sys
try:
    import tomllib
except ImportError:  # Python 3.9 and 3.10: the manifest check below skips (stampede itself does without it)
    tomllib = None
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from events_log import events_log

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ('stampede', 'herdr-fleet', 'grokbot-herdr', 'share-plan')


class Install(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name).resolve()
        (self.home / '.claude').mkdir()
        self.env = {**os.environ, 'HOME': str(self.home)}
        self.env.pop('XDG_STATE_HOME', None)

    def run_install(self, *flags, root=ROOT, env=None):
        return subprocess.run(['bash', str(root / 'install.sh'), *flags], env=env or self.env,
                              capture_output=True, text=True, timeout=30)

    def managed_checkout(self, n):
        """A fake Herdr-managed checkout: Herdr gives each plugin install or update a new N-0 folder."""
        root = self.home / f'.config/herdr/plugins/github-installations/stampede-x/{n}-0/checkout'
        root.mkdir(parents=True)
        shutil.copy(ROOT / 'install.sh', root)
        for part in ('scripts', 'skills'):
            shutil.copytree(ROOT / part, root / part, ignore=shutil.ignore_patterns('__pycache__'))
        return root

    def test_links_skills_and_commands_and_is_idempotent(self):
        kept = self.home / '.local/bin/herdr-send'
        kept.parent.mkdir(parents=True)
        kept.write_text('the owner\'s own file')
        result = self.run_install()
        self.assertEqual(result.returncode, 0, result.stderr)
        for skill in SKILLS:
            self.assertEqual((self.home / '.claude/skills' / skill).resolve(), ROOT / 'skills' / skill)
        self.assertFalse((self.home / '.codex').exists())
        self.assertIn('skip ~/.codex/skills: no ~/.codex', result.stdout)
        bin_dir = self.home / '.local/bin'
        self.assertEqual((bin_dir / 'stampede').resolve(), ROOT / 'scripts/stampede')
        self.assertEqual((bin_dir / 'fleet-job').resolve(), ROOT / 'scripts/stampede')
        for name in ('herdr-trust', 'herdr-doctor', 'herdr-event-post', 'herdr-event-sweep', 'herdr-reopen-snapshot'):
            self.assertTrue((bin_dir / name).is_symlink(), name)
        self.assertFalse((bin_dir / 'test-relay.sh').exists())
        self.assertEqual(kept.read_text(), 'the owner\'s own file')
        self.assertIn(f'skip {kept}', result.stdout)
        self.assertIn('herdr-trust <repo dir>', result.stdout)
        again = self.run_install()
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertNotIn('linked', again.stdout)
        self.assertIn(f'ok {bin_dir / "stampede"}', again.stdout)

    def test_links_follow_a_new_managed_checkout_and_no_other(self):
        plugins = self.home / '.config/herdr/plugins/github-installations'
        bin_dir = self.home / '.local/bin'
        bin_dir.mkdir(parents=True)
        own = {  # links of the owner's that only look like stampede's: never moved
            bin_dir / 'herdr-send': plugins / 'stampede-helper-abc/1-0/checkout/skills/grokbot-herdr/scripts/herdr-send',
            bin_dir / 'herdr-trust': self.home / 'backup' / plugins.relative_to(self.home) /
            'stampede-x/1-0/checkout/skills/grokbot-herdr/scripts/herdr-trust',
            bin_dir / 'herdr-events-owner': plugins / 'stampede-x/1-0/checkout/scripts/owner-tool',
            bin_dir / 'herdr-reopen-snapshot': self.home / 'my-clone/skills/grokbot-herdr/scripts/herdr-reopen-snapshot',
        }
        for link, target in own.items():
            link.symlink_to(target)
        first, second = self.managed_checkout(1), self.managed_checkout(2)
        self.assertEqual(self.run_install(root=first).returncode, 0)
        shutil.rmtree(first)  # Herdr deletes the old checkout at its next start, so every link dangles
        stampede = self.home / '.local/bin/stampede'
        self.assertIn('would relink', self.run_install('--dry-run', root=second).stdout)
        self.assertEqual(os.readlink(stampede), str(first / 'scripts/stampede'))
        result = self.run_install(root=second)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f'relinked {stampede}', result.stdout)
        for path, target in [(stampede, 'scripts/stampede'), (self.home / '.local/bin/fleet-job', 'scripts/stampede'),
                             (self.home / '.local/bin/herdr-doctor', 'skills/grokbot-herdr/scripts/herdr-doctor'),
                             *((self.home / '.claude/skills' / s, f'skills/{s}') for s in SKILLS)]:
            self.assertEqual(path.resolve(strict=True), second / target)
        for link, target in own.items():
            self.assertEqual(os.readlink(link), str(target))
            self.assertIn(f'skip {link}: something else is there; left as is', result.stdout)

    def test_a_clone_install_relinks_nothing(self):
        stampede = self.home / '.local/bin/stampede'
        stampede.parent.mkdir(parents=True)
        plugin = self.managed_checkout(1) / 'scripts/stampede'
        stampede.symlink_to(plugin)
        result = self.run_install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(os.readlink(stampede), str(plugin))
        self.assertIn(f'skip {stampede}', result.stdout)

    def uninstall_recipe(self, intro):
        """The bash block after the paragraph that starts with intro, in docs/SETUP.md's Uninstall section."""
        text = (ROOT / 'docs/SETUP.md').read_text()
        rest = text[text.index('## Uninstall'):]
        return re.search(r'```bash\n(.*?)```', rest[rest.index(intro):], re.S).group(1)

    def test_the_uninstall_recipes_remove_only_links_into_that_checkout(self):
        shells = [s for s in ('/bin/bash', '/bin/zsh') if os.path.exists(s)]  # zsh: the macOS login shell
        for intro, kind in (('From a stable checkout', 'unlink'), ('For a GitHub-managed install', 'uninstall')):
            for shell in shells:
                with self.subTest(recipe=kind, shell=shell):
                    home = Path(tempfile.mkdtemp(dir=self.home))
                    checkout = home / 'plugin[12]/checkout'  # glob characters in the path must stay literal
                    checkout.mkdir(parents=True)
                    plugins = home / '.config/herdr/plugins/github-installations'
                    gone = {home / '.local/bin/stampede': checkout / 'scripts/stampede',
                            home / '.claude/skills/herdr-fleet': checkout / 'skills/herdr-fleet'}
                    kept = {home / '.local/bin/my-helper': plugins / 'stampede-helper-abc/1-0/checkout/scripts/tool',
                            home / '.local/bin/other': home / 'plugin1/checkout/scripts/tool',
                            home / '.codex/skills/share-plan': home / 'plugin[12]/checkout-old/skills/share-plan'}
                    for link, target in {**gone, **kept}.items():
                        link.parent.mkdir(parents=True, exist_ok=True)
                        link.symlink_to(target)
                    fake = home / 'fakebin/herdr'
                    fake.parent.mkdir()
                    fake.write_text('#!/bin/bash\ncase "$1 $2" in\n'
                                    '  "plugin list") printf \'{"result":{"plugins":[{"plugin_id":"stampede",'
                                    '"source":{"managed_path":"%s"}}]}}\' "$TEST_MANAGED";;\n'
                                    '  *) echo "$*" >> "$HOME/herdr-calls";;\nesac\n')
                    fake.chmod(0o755)
                    env = {'HOME': str(home), 'PATH': f'{fake.parent}:/usr/bin:/bin:/opt/homebrew/bin',
                           'TEST_MANAGED': str(checkout)}
                    result = subprocess.run([shell, '-c', self.uninstall_recipe(intro)], cwd=checkout, env=env,
                                            capture_output=True, text=True, timeout=30)
                    self.assertEqual(result.stderr, '')
                    for link in gone:
                        self.assertFalse(os.path.lexists(link), link)
                    for link, target in kept.items():
                        self.assertEqual(os.readlink(link), str(target))
                    self.assertEqual((home / 'herdr-calls').read_text(), f'plugin {kind} stampede\n')

    def test_a_real_skill_folder_is_left_alone(self):
        own = self.home / '.claude/skills/herdr-fleet'
        own.mkdir(parents=True)
        result = self.run_install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(own.is_symlink())
        self.assertIn(f'skip {own}', result.stdout)

    def test_codex_and_claude_links_survive_reinstall(self):
        (self.home / '.codex').mkdir()
        self.assertEqual(self.run_install('--from-plugin').returncode, 0)
        links = {self.home / app / 'skills' / skill: ROOT / 'skills' / skill
                 for app in ('.claude', '.codex') for skill in SKILLS}
        self.assertEqual(self.run_install('--from-plugin').returncode, 0)
        for path, target in links.items():
            self.assertTrue(path.is_symlink())
            self.assertEqual(path.resolve(), target)
        before = {str(p.relative_to(self.home)): os.readlink(p) if p.is_symlink() else None
                  for p in self.home.rglob('*')}
        self.assertEqual(self.run_install('--dry-run').returncode, 0)
        after = {str(p.relative_to(self.home)): os.readlink(p) if p.is_symlink() else None
                 for p in self.home.rglob('*')}
        self.assertEqual(before, after)

    def test_dry_run_changes_nothing_and_bad_flags_are_usage_errors(self):
        result = self.run_install('--dry-run')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('would link', result.stdout)
        self.assertFalse((self.home / '.local').exists())
        self.assertFalse((self.home / '.claude/skills').exists())
        self.assertEqual(self.run_install('--from-plugin').returncode, 0)
        self.assertEqual(self.run_install('--unknown').returncode, 2)

    def older_install(self):
        """What an older install leaves at the targets: a plain copy, a link into another checkout, a link whose target
        is gone, a real skill folder, and a file of the owner's that is never a target."""
        bin_dir, other = self.home / '.local/bin', self.home / 'old-checkout/scripts'
        bin_dir.mkdir(parents=True)
        other.mkdir(parents=True)
        (other / 'fleet-job').write_text('#!/bin/bash\necho old fleet-job\n')
        (bin_dir / 'herdr-send').write_text('an older copy of herdr-send')
        (bin_dir / 'fleet-job').symlink_to(other / 'fleet-job')
        (bin_dir / 'stampede').symlink_to(other / 'gone')
        (self.home / '.claude/skills/herdr-fleet').mkdir(parents=True)
        (self.home / '.claude/skills/herdr-fleet/SKILL.md').write_text('an older skill')
        (bin_dir / 'my-own-tool').write_text('never a target')

    def tree(self, skip=('.local/state', 'fake-bin')):
        """Every path under HOME but those under skip, with what it is: a link's value, a file's bytes, or a folder.
        ~/.local itself is left out: the backups live under it, so a rollback leaves it."""
        return {str(p.relative_to(self.home)): ('-> ' + os.readlink(p)) if p.is_symlink() else p.read_bytes() if p.is_file() else 'dir'
                for p in self.home.rglob('*') if not str(p.relative_to(self.home)).startswith(skip)
                and str(p.relative_to(self.home)) != '.local'}

    def rollback(self, result, out='stdout'):
        last = getattr(result, out).splitlines()[-1]
        self.assertRegex(last, rf'^rollback: bash {re.escape(str(self.home))}/\.local/state/stampede/backup-\d{{8}}-\d{{6}}(-\d+)?/rollback\.sh$')
        return Path(last.split()[-1])

    def undo(self, script, code=0, env=None):
        undone = subprocess.run(['bash', str(script)], env=env or self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(undone.returncode, code, undone.stdout + undone.stderr)
        return undone

    def fake(self, name, body):
        """A PATH whose first folder holds a fake <name> command."""
        bin_dir = self.home / 'fake-bin'
        bin_dir.mkdir(exist_ok=True)
        (bin_dir / name).write_text('#!/bin/bash\n' + body + '\n')
        (bin_dir / name).chmod(0o755)
        return {**self.env, 'PATH': f'{bin_dir}:/usr/bin:/bin'}

    def read_only(self, folder):
        folder.chmod(0o555)
        self.addCleanup(folder.chmod, 0o755)

    def test_replace_takes_over_an_older_install_with_a_backup_and_its_rollback_restores_it(self):
        self.older_install()
        before = self.tree()
        result = self.run_install('--replace')
        self.assertEqual(result.returncode, 0, result.stderr)
        backup = self.rollback(result).parent
        bin_dir = self.home / '.local/bin'
        for name in ('stampede', 'fleet-job'):
            self.assertEqual((bin_dir / name).resolve(), ROOT / 'scripts/stampede', name)
        self.assertEqual((bin_dir / 'herdr-send').resolve(), ROOT / 'skills/grokbot-herdr/scripts/herdr-send')
        self.assertEqual((self.home / '.claude/skills/herdr-fleet').resolve(), ROOT / 'skills/herdr-fleet')
        self.assertIn(f'replaced {bin_dir}/herdr-send -> {ROOT}/skills/grokbot-herdr/scripts/herdr-send '
                      f'(the old one is in {backup}/.local/bin/herdr-send)', result.stdout)
        self.assertEqual(len(re.findall(r'(?m)^replaced ', result.stdout)), 4)
        self.assertEqual((backup / '.local/bin/herdr-send').read_text(), 'an older copy of herdr-send')
        self.assertEqual(os.readlink(backup / '.local/bin/fleet-job'), str(self.home / 'old-checkout/scripts/fleet-job'))
        self.assertEqual(os.readlink(backup / '.local/bin/stampede'), str(self.home / 'old-checkout/scripts/gone'))
        self.assertEqual((backup / '.claude/skills/herdr-fleet/SKILL.md').read_text(), 'an older skill')
        self.assertEqual((bin_dir / 'my-own-tool').read_text(), 'never a target')
        installed = self.tree()
        again = self.run_install('--replace')                                  # nothing in the way: no second backup
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertNotIn('rollback:', again.stdout)
        self.assertEqual([p.name for p in backup.parent.iterdir()], [backup.name])
        self.assertEqual(self.tree(), installed)
        undone = self.undo(backup / 'rollback.sh')
        self.assertEqual(undone.stderr, '')
        self.assertIn(f'restored {bin_dir}/herdr-send', undone.stdout)
        self.assertEqual(undone.stdout.splitlines()[-1], 'rolled back: every link and folder that run made is undone')
        self.assertEqual(self.tree(), before)                                  # the links it made are gone too

    def test_a_rollback_leaves_a_target_someone_changed_since(self):
        self.older_install()
        backup = self.rollback(self.run_install('--replace')).parent
        mine = self.home / '.local/bin/herdr-send'
        mine.unlink()
        mine.write_text('put here after the install')
        undone = self.undo(backup / 'rollback.sh', 1)
        self.assertIn(f'left {mine}: something else is there now; its original is {backup}/.local/bin/herdr-send', undone.stderr)
        self.assertEqual(mine.read_text(), 'put here after the install')
        self.assertEqual((backup / '.local/bin/herdr-send').read_text(), 'an older copy of herdr-send')
        self.assertIn(f'restored {self.home}/.local/bin/fleet-job', undone.stdout)   # the rest is still undone

    @unittest.skipIf(os.geteuid() == 0, 'root can move out of a read-only folder')
    def test_a_move_that_fails_stops_before_the_link_and_leaves_the_folder(self):
        own = self.home / '.claude/skills/stampede'  # the first target, so nothing was linked before it'
        own.mkdir(parents=True)
        (own / 'SKILL.md').write_text('an older skill')
        before = self.tree()
        self.read_only(own.parent)
        result = self.run_install('--replace')
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(f'install.sh: could not move {own} to ', result.stderr)
        self.assertFalse(own.is_symlink())
        self.assertEqual((own / 'SKILL.md').read_text(), 'an older skill')
        self.assertFalse((self.home / '.local/bin').exists(), 'it stopped before the commands')
        undone = self.undo(self.rollback(result, 'stderr'))                      # journaled, never done: skipped
        self.assertNotIn('left', undone.stderr)
        self.assertEqual(self.tree(), before)

    def test_a_journal_that_cannot_be_written_after_a_move_stops_and_the_rollback_still_restores(self):
        self.older_install()
        before = self.tree()
        env = self.fake('mv', '/bin/mv "$@" || exit $?\n/bin/chmod a-w "$HOME"/.local/state/stampede/backup-*/journal')
        result = self.run_install('--replace', env=env)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn('could not write', result.stderr)
        script = self.rollback(result, 'stderr')
        self.assertIn(f'replaced {self.home}/.claude/skills/herdr-fleet', result.stdout)   # one move, then the write failed
        self.undo(script)
        self.assertEqual(self.tree(), before)

    def test_a_backup_folder_already_there_gets_a_new_name_before_anything_changes(self):
        state = self.home / '.local/state/stampede'
        stamp = subprocess.run(['date', '+%s'], capture_output=True, text=True).stdout.strip()
        taken = []
        for ahead in range(10):                                                # this second and the next nine
            name = subprocess.run(['date', '-r', str(int(stamp) + ahead), '+backup-%Y%m%d-%H%M%S'] if platform.system() == 'Darwin'
                                  else ['date', '-d', f'@{int(stamp) + ahead}', '+backup-%Y%m%d-%H%M%S'],
                                  capture_output=True, text=True).stdout.strip()
            (state / name).mkdir(parents=True)
            taken.append(state / name)
        before = self.tree(skip=('\0',))
        result = self.run_install('--replace')
        self.assertEqual(result.returncode, 0, result.stderr)
        script = self.rollback(result)
        self.assertRegex(script.parent.name, r'-2$')
        self.assertTrue(all(list(t.iterdir()) == [] for t in taken), 'a folder already there is never used')
        self.undo(script)
        self.assertEqual({k: v for k, v in self.tree(skip=('\0',)).items() if script.parent.name not in k}, before)

    @unittest.skipIf(os.geteuid() == 0, 'root can write into a read-only folder')
    def test_a_rollback_that_cannot_move_an_original_back_says_where_it_is_and_exits_1(self):
        bin_dir = self.home / '.local/bin'
        bin_dir.mkdir(parents=True)
        (bin_dir / 'stampede').write_text('an older stampede')
        script = self.rollback(self.run_install('--replace'))
        (bin_dir / 'stampede').unlink()
        self.read_only(bin_dir)
        undone = self.undo(script, 1)
        saved = script.parent / '.local/bin/stampede'
        self.assertIn(f'left {bin_dir}/stampede: could not move it back; its original is still {saved}', undone.stderr)
        self.assertEqual(saved.read_text(), 'an older stampede')
        self.assertIn('rollback incomplete', undone.stderr)
        self.assertNotIn('rolled back', undone.stdout)

    @unittest.skipIf(os.geteuid() == 0, 'root can write into a read-only folder')
    def test_a_rollback_that_cannot_remove_a_link_says_so_and_exits_1(self):
        bin_dir = self.home / '.local/bin'
        bin_dir.mkdir(parents=True)
        (bin_dir / 'stampede').write_text('an older stampede')
        script = self.rollback(self.run_install('--replace'))
        self.read_only(bin_dir)
        undone = self.undo(script, 1)
        saved = script.parent / '.local/bin/stampede'
        self.assertIn(f'left {bin_dir}/stampede: could not remove the link install.sh made', undone.stderr)
        self.assertIn(f'  its original is {saved}', undone.stderr)
        self.assertEqual(saved.read_text(), 'an older stampede')
        self.assertNotIn('rolled back', undone.stdout)

    def test_the_printed_rollback_line_runs_as_pasted_in_an_odd_home(self):
        for odd in ('a home with spaces', 'home-$(touch marker)'):
            with self.subTest(home=odd):
                scratch = Path(tempfile.mkdtemp(dir=self.home))
                home = scratch / odd
                (home / '.local/bin').mkdir(parents=True)
                (home / '.local/bin/stampede').write_text('an older stampede')
                env = {**self.env, 'HOME': str(home)}
                result = self.run_install('--replace', env=env)
                self.assertEqual(result.returncode, 0, result.stderr)
                line = result.stdout.splitlines()[-1]
                self.assertTrue(line.startswith('rollback: '), line)
                undone = subprocess.run(['bash', '-c', line[len('rollback: '):]], cwd=scratch, env=env,
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(undone.returncode, 0, undone.stderr)
                self.assertFalse((scratch / 'marker').exists(), 'the pasted line ran part of the path')
                self.assertEqual((home / '.local/bin/stampede').read_text(), 'an older stampede')

    @unittest.skipIf(os.geteuid() == 0, 'root can write into a read-only folder')
    def test_a_new_link_that_fails_after_a_replace_stops_with_exit_1_and_the_rollback_line(self):
        own = self.home / '.claude/skills/stampede'
        own.mkdir(parents=True)
        (own / 'SKILL.md').write_text('an older skill')
        bin_dir = self.home / '.local/bin'
        bin_dir.mkdir(parents=True)
        before = self.tree()
        self.read_only(bin_dir)
        result = self.run_install('--replace')
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(f'install.sh: could not link {bin_dir}/stampede; stopped', result.stderr)
        script = self.rollback(result, 'stderr')
        self.assertEqual((script.parent / '.claude/skills/stampede/SKILL.md').read_text(), 'an older skill')
        bin_dir.chmod(0o755)
        self.undo(script)
        self.assertEqual(self.tree(), before)

    def test_a_link_journaled_but_never_made_is_skipped_and_ln_exit_codes_become_1(self):
        self.older_install()
        before = self.tree()
        env = self.fake('ln', 'exit 9')
        result = self.run_install('--replace', env=env)
        self.assertEqual(result.returncode, 1, result.stdout)
        script = self.rollback(result, 'stderr')
        self.assertTrue(script.with_name('journal').read_text().startswith('step link '))
        self.undo(script)
        self.assertEqual(self.tree(), before)
        plain = self.run_install(env=env)                                       # without --replace: exit as on main
        self.assertEqual(plain.returncode, 9)
        self.assertNotIn('rollback', plain.stdout + plain.stderr)

    def test_dry_run_replace_names_each_target_and_changes_nothing(self):
        self.older_install()
        before = self.tree(skip=('\0',))
        result = self.run_install('--dry-run', '--replace')
        self.assertEqual(result.returncode, 0, result.stderr)
        replaced = re.findall(r'(?m)^would replace (\S+) \(backup in (\S+)\)$', result.stdout)
        self.assertEqual(sorted(path for path, _ in replaced), sorted(str(self.home / p) for p in (
            '.claude/skills/herdr-fleet', '.local/bin/fleet-job', '.local/bin/herdr-send', '.local/bin/stampede')))
        self.assertRegex(replaced[0][1], rf'^{re.escape(str(self.home))}/\.local/state/stampede/backup-\d{{8}}-\d{{6}}$')
        self.assertIn(f'would link {self.home}/.local/bin/herdr-doctor', result.stdout)
        self.assertNotIn('rollback:', result.stdout)
        self.assertEqual(self.tree(skip=('\0',)), before)

    def test_without_replace_the_skip_names_the_flag_and_no_backup_is_made(self):
        self.older_install()
        result = self.run_install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f'skip {self.home}/.local/bin/herdr-send: something else is there; left as is '
                      '(--replace backs it up and links)', result.stdout)
        self.assertNotIn('rollback:', result.stdout)
        self.assertFalse((self.home / '.local/state').exists())
        self.assertIn('[--replace] [--no-skills]', self.run_install('--bogus').stderr)

    def test_no_skills_links_the_commands_and_leaves_every_skill_alone(self):
        self.older_install()
        (self.home / '.codex').mkdir()
        result = self.run_install('--replace', '--no-skills')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('skip ~/.claude/skills: --no-skills', result.stdout)
        self.assertIn('skip ~/.codex/skills: --no-skills', result.stdout)
        self.assertEqual((self.home / '.claude/skills/herdr-fleet/SKILL.md').read_text(), 'an older skill')
        self.assertFalse((self.home / '.claude/skills/stampede').exists())
        self.assertFalse((self.home / '.codex/skills').exists())
        self.assertEqual((self.home / '.local/bin/fleet-job').resolve(), ROOT / 'scripts/stampede')

    def test_replace_in_a_managed_checkout_journals_its_relinks_so_the_rollback_points_them_back(self):
        first, second = self.managed_checkout(1), self.managed_checkout(2)
        self.assertEqual(self.run_install('--no-skills', '--no-supervise', root=first).returncode, 0)
        before = self.tree()
        result = self.run_install('--replace', '--no-skills', '--no-supervise', root=second)   # only relinks: still a rollback
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(os.readlink(self.home / '.local/bin/stampede'), str(second / 'scripts/stampede'))
        undone = subprocess.run(['bash', str(self.rollback(result))], env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual((undone.returncode, undone.stderr), (0, ''))
        self.assertEqual(os.readlink(self.home / '.local/bin/stampede'), str(first / 'scripts/stampede'))
        self.assertEqual(self.tree(), before)
        plain = self.run_install('--no-skills', '--no-supervise', root=second)                 # without --replace: a relink, as before
        self.assertIn(f'relinked {self.home}/.local/bin/stampede', plain.stdout)
        self.assertNotIn('rollback:', plain.stdout)

    def made_then_changed(self, change):
        """A --replace in a fresh home (it makes ~/.local/bin), then ~/.local/bin swapped by change; the rollback's result."""
        script = self.rollback(self.run_install('--replace'))
        bin_dir = self.home / '.local/bin'
        bin_dir.rename(self.home / 'moved-bin')
        change(bin_dir)
        return bin_dir, self.undo(script, 1)

    def test_a_folder_the_run_made_that_is_a_file_now_is_left_and_named(self):
        bin_dir, undone = self.made_then_changed(lambda path: path.write_text('a file of the owner'))
        self.assertIn(f'left {bin_dir}: a folder install.sh made is something else now', undone.stderr)
        self.assertEqual(bin_dir.read_text(), 'a file of the owner')
        self.assertNotIn('rolled back', undone.stdout)

    def test_a_folder_the_run_made_that_is_a_link_now_is_left_and_named(self):
        empty = self.home / 'empty'
        empty.mkdir()
        bin_dir, undone = self.made_then_changed(lambda path: path.symlink_to(empty))
        self.assertIn(f'left {bin_dir}: a folder install.sh made is a link now', undone.stderr)
        self.assertEqual(os.readlink(bin_dir), str(empty))
        self.assertTrue(empty.is_dir())
        self.assertNotIn('rolled back', undone.stdout)

    def test_a_folder_that_cannot_be_made_stops_before_its_step_is_journaled(self):
        (self.home / '.claude/skills').write_text('a file where the skills folder goes')
        result = self.run_install('--replace')
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(f'install.sh: could not make the folder {self.home}/.claude/skills: something else is there; stopped', result.stderr)
        self.assertNotIn('rollback:', result.stderr)                          # nothing changed, nothing to roll back
        journal = next((self.home / '.local/state/stampede').iterdir()) / 'journal'
        self.assertEqual(journal.read_text(), '')
        self.assertEqual((self.home / '.claude/skills').read_text(), 'a file where the skills folder goes')

    def linux(self):
        """A Linux-looking PATH: uname says Linux, systemctl --user answers and records each call."""
        env = self.fake('uname', 'echo Linux')
        self.fake('systemctl', 'echo "$*" >> "$HOME/systemctl-calls"; exit 0')
        return env

    def test_replace_saves_an_older_marked_timer_unit_and_the_rollback_says_it_stays(self):
        units = self.home / '.config/systemd/user'
        units.mkdir(parents=True)
        custom = '# stampede-unit\n[Service]\nEnvironment=USER_CUSTOM_VALUE=keep-me\n'
        (units / 'herdr-event-watchdog.service').write_text(custom)
        (units / 'herdr-events-flush.timer').write_text('[Timer]\nOnUnitActiveSec=1h\n')   # unmarked: the owner's own
        env = self.linux()
        dry = self.run_install('--dry-run', '--replace', '--supervise', env=env)
        self.assertIn(f'would replace {units}/herdr-event-watchdog.service (backup in ', dry.stdout)
        self.assertFalse((self.home / '.local/state').exists())
        result = self.run_install('--replace', '--supervise', env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        script = self.rollback(result)
        saved = script.parent / '.config/systemd/user/herdr-event-watchdog.service'
        self.assertEqual(saved.read_text(), custom)
        self.assertIn(f'replaced {units}/herdr-event-watchdog.service (stampede\'s own unit; the old one is in {saved})', result.stdout)
        self.assertIn(f'skip {units}/herdr-events-flush.timer: something else is there; left as is', result.stdout)
        self.assertEqual((units / 'herdr-events-flush.timer').read_text(), '[Timer]\nOnUnitActiveSec=1h\n')
        self.assertIn(f'timer unit files written: {units}/herdr-event-watchdog.service (its older copy is {saved}), '
                      f'{units}/herdr-event-watchdog.timer, {units}/herdr-events-flush.service. They are stampede\'s own', result.stdout)
        written = (units / 'herdr-event-watchdog.service').read_text()
        self.assertNotIn('keep-me', written)
        undone = self.undo(script)
        self.assertIn(f'kept stampede\'s own timer unit files, which a rollback leaves: {units}/herdr-event-watchdog.service '
                      f'(its older copy is {saved})', undone.stdout)
        self.assertEqual(undone.stdout.splitlines()[-1], 'rolled back: every link and folder that run made is undone')
        self.assertNotIn('every change', undone.stdout)
        self.assertEqual((units / 'herdr-event-watchdog.service').read_text(), written)   # stays, as the rollback said

    def test_replace_keeps_a_timer_unit_that_is_already_right_and_a_plain_install_rewrites_as_before(self):
        env = self.linux()
        self.assertEqual(self.run_install('--supervise', env=env).returncode, 0)
        unit = self.home / '.config/systemd/user/herdr-event-watchdog.service'
        os.utime(unit, (1, 1))
        again = self.run_install('--replace', '--supervise', env=env)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertIn(f'ok {unit}', again.stdout)
        self.assertNotIn('rollback:', again.stdout)
        self.assertFalse((self.home / '.local/state/stampede').exists(), 'nothing changed, so no backup')
        self.assertEqual(unit.stat().st_mtime, 1)
        unit.write_text('# stampede-unit\nan older one\n')
        plain = self.run_install('--supervise', env=env)                        # without --replace: rewritten, no backup
        self.assertEqual(plain.returncode, 0, plain.stderr)
        self.assertNotIn('an older one', unit.read_text())
        self.assertNotIn(str(unit), plain.stdout)
        self.assertFalse((self.home / '.local/state/stampede').exists())

    def test_a_folder_among_the_helpers_is_not_linked(self):
        root = self.managed_checkout(1)
        (root / 'skills/grokbot-herdr/scripts/__pycache__').mkdir()
        result = self.run_install(root=root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(os.path.lexists(self.home / '.local/bin/__pycache__'))
        self.assertTrue((self.home / '.local/bin/herdr-doctor').is_symlink())

    @unittest.skipIf(tomllib is None, 'tomllib is in Python 3.11 and later')
    def test_manifest_commands_exist(self):
        manifest = tomllib.loads((ROOT / 'herdr-plugin.toml').read_text())
        self.assertEqual(manifest['min_herdr_version'], '0.9.4')
        self.assertEqual(manifest['events'][0]['on'], 'pane.agent_status_changed')
        for kind in ('build', 'events'):
            for entry in manifest[kind]:
                self.assertEqual(entry['command'][0], 'bash')
                self.assertTrue((ROOT / entry['command'][1]).is_file(), entry['command'])

    def test_plugin_event_posts_done_and_idle_after_working_only(self):
        bin_dir = self.home / '.local/bin'
        bin_dir.mkdir(parents=True)
        posted = self.home / 'posted.jsonl'
        (bin_dir / 'herdr-event-post').write_text(f'#!/bin/bash\ncat >> "{posted}"\n')
        (bin_dir / 'herdr').write_text('#!/bin/bash\ncase "$1 $2" in "workspace list") '
                                       'echo \'{"result":{"workspaces":[{"workspace_id":"w1","label":"demo"}]}}\';; esac\n')
        for f in bin_dir.iterdir():
            f.chmod(0o755)
        env = {**self.env, 'PATH': f'{bin_dir}:/usr/bin:/bin:/opt/homebrew/bin'}
        env.pop('HERDR_BIN_PATH', None)
        for status in ('working', 'idle', 'idle', 'done'):
            event = {'data': {'pane_id': 'w1:p1', 'workspace_id': 'w1', 'agent_status': status, 'agent': 'claude'}}
            subprocess.run(['bash', str(ROOT / 'scripts/herdr-plugin-event')], check=True, timeout=30,
                           env={**env, 'HERDR_PLUGIN_EVENT_JSON': json.dumps(event)})
        sent = [json.loads(line) for line in posted.read_text().splitlines()]
        self.assertEqual([(e['state'], e['previous_state']) for e in sent], [('idle', 'working'), ('done', 'idle')])
        self.assertEqual((sent[0]['pane'], sent[0]['workspace_label'], sent[0]['source']), ('w1:p1', 'demo', 'herdr'))

    def test_plugin_event_without_relay_logs_only_and_never_sends(self):
        self.assertEqual(self.run_install().returncode, 0)
        bin_dir = self.home / '.local/bin'
        (bin_dir / 'herdr').write_text('#!/bin/bash\necho \'{"result":{"workspaces":[]}}\'\n')
        (bin_dir / 'curl').write_text('#!/bin/bash\ntouch "$HOME/network-called"\nexit 1\n')
        for name in ('herdr', 'curl'):
            (bin_dir / name).chmod(0o755)
        env = {k: v for k, v in self.env.items() if not k.startswith('HERDR_')}
        event = {'data': {'pane_id': 'w1:p1', 'workspace_id': 'w1', 'agent_status': 'done'}}
        env.update(PATH=f'{bin_dir}:/opt/homebrew/bin:/usr/bin:/bin',
                   HERDR_PLUGIN_EVENT_JSON=json.dumps(event), HERDR_EVENTS_MACHINE='fixture')
        result = subprocess.run(['bash', str(ROOT / 'scripts/herdr-plugin-event')],
                                env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('logged-only (no route URL)', events_log(self.home).read_text())
        self.assertFalse((self.home / 'network-called').exists())
        self.assertFalse((self.home / '.herdr-events/queue').exists())

    def _linux_env(self, systemctl):
        bin_dir = self.home / 'fake-bin'
        bin_dir.mkdir()
        (bin_dir / 'systemctl').write_text(systemctl)
        (bin_dir / 'systemctl').chmod(0o755)
        env = {**self.env, 'PATH': f'{bin_dir}:/usr/bin:/bin'}
        return env

    def _stale_loop_pid(self):
        """A pid file left by a loop that died, whose pid now belongs to an unrelated live process."""
        unrelated = subprocess.Popen(['sleep', '300'])
        self.addCleanup(lambda: (unrelated.kill(), unrelated.wait()))
        state = self.home / '.local/state/herdr-events'
        state.mkdir(parents=True, exist_ok=True)
        (state / 'supervise.pid').write_text(f'{unrelated.pid}\n')
        return unrelated

    def test_linux_systemd_units_when_the_user_bus_answers(self):
        if platform.system() != 'Linux':
            self.skipTest('systemd user timers are the Linux supervisor')
        env = self._linux_env('#!/bin/bash\nprintf \'%s\\n\' "$*" >> "$HOME/systemctl-calls"\n'
                              'case "$1 $2" in "--user show-environment") exit 0;; esac\nexit 0\n')
        unrelated = self._stale_loop_pid()
        dry = self.run_install('--dry-run', '--supervise', env=env)
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertIn('would enable systemd user timers', dry.stdout)
        self.assertFalse((self.home / '.config/systemd/user/herdr-event-watchdog.timer').exists())
        result = self.run_install('--supervise', env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('ok systemd user timers', result.stdout)
        timer = (self.home / '.config/systemd/user/herdr-event-watchdog.timer').read_text()
        self.assertIn('stampede-unit', timer)
        self.assertIn('OnUnitActiveSec=5min', timer)
        self.assertIn('OnUnitActiveSec=2min', (self.home / '.config/systemd/user/herdr-events-flush.timer').read_text())
        calls = (self.home / 'systemctl-calls').read_text()
        self.assertIn('--user enable --now herdr-event-watchdog.timer herdr-events-flush.timer', calls)
        again = self.run_install('--supervise', env=env)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertNotIn('linked', again.stdout)
        self.assertIsNone(unrelated.poll(), 'a stale pid file must never get its process killed')

    def test_linux_loop_when_systemd_user_is_absent(self):
        if platform.system() != 'Linux':
            self.skipTest('the flock loop is the Linux fallback')
        state = self.home / '.local/state/herdr-events'

        def stop():
            pidfile = state / 'supervise.pid'
            if not pidfile.is_file():
                return
            try:
                os.kill(int(pidfile.read_text().strip()), signal.SIGTERM)
            except (ProcessLookupError, ValueError):
                pass
        self.addCleanup(stop)
        env = self._linux_env('#!/bin/bash\nexit 1\n')
        unrelated = self._stale_loop_pid()
        result = self.run_install('--supervise', env=env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('started the event loop', result.stdout)
        pid = int((state / 'supervise.pid').read_text())
        self.assertNotEqual(pid, unrelated.pid)
        self.assertIsNone(unrelated.poll())
        os.kill(pid, 0)  # the flock holder is alive
        again = self.run_install('--supervise', env=env)
        self.assertIn('ok event loop', again.stdout)
        self.assertEqual(int((state / 'supervise.pid').read_text()), pid)


if __name__ == '__main__':
    unittest.main()
