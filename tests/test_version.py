"""The version: one VERSION file, printed by stampede and by fleet-job as install.sh links it, and named by the plugin."""
import os
import re
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Version(unittest.TestCase):
    def test_stampede_and_fleet_job_print_the_version_file(self):
        version = (ROOT / 'VERSION').read_text().strip()
        self.assertRegex(version, r'^\d+\.\d+\.\d+$')
        with tempfile.TemporaryDirectory() as folder:
            fleet_job = Path(folder) / 'fleet-job'
            fleet_job.symlink_to(ROOT / 'scripts/stampede')  # what install.sh makes in ~/.local/bin
            for command in (ROOT / 'scripts/stampede', fleet_job):
                for flag in ('--version', '-V'):
                    out = subprocess.run([str(command), flag], capture_output=True, text=True, timeout=30,
                                         env={**os.environ, 'STAMPEDE_NO_UPDATE_CHECK': '1'})  # no network
                    self.assertEqual((out.returncode, out.stdout.strip()), (0, version), (command, flag, out.stderr))

    def test_the_changelog_names_the_version(self):
        version = (ROOT / 'VERSION').read_text().strip()
        self.assertIn('## ' + version, (ROOT / 'CHANGELOG.md').read_text())

    def test_the_plugin_manifest_names_the_version_file(self):
        """TOML cannot read another file, so this test keeps herdr-plugin.toml in step with VERSION (RELEASING.md)."""
        version = (ROOT / 'VERSION').read_text().strip()
        toml = tomllib.loads((ROOT / 'herdr-plugin.toml').read_text())['version']
        self.assertEqual(toml, version, 'herdr-plugin.toml version differs from VERSION')

    def test_the_readme_and_the_site_name_the_version_file(self):
        """The README badge, the README's stampede --version line and the site's install prompt (RELEASING.md)."""
        version = (ROOT / 'VERSION').read_text().strip()
        readme = (ROOT / 'README.md').read_text()
        site = (ROOT / 'site/assets/site.js').read_text()
        for name, text, pattern in (('README badge', readme, r'alt="Version ([^"]+)" src="https://img\.shields\.io/badge/version-\1-'),
                                    ('README --version line', readme, r'(?m)^stampede --version +# (\S+)$'),
                                    ('site install prompt', site, r'stampede --version prints (\d+\.\d+\.\d+)')):
            found = re.search(pattern, text)
            self.assertIsNotNone(found, name + ' not found (or its alt text and URL differ)')
            self.assertEqual(found.group(1), version, name + ' differs from VERSION')


if __name__ == '__main__':
    unittest.main()
