"""The stampede package's layers, read with ast (nothing is imported or started): who may import whom, no import
cycle at load, every call through the module (`from . import job as job_`, never `from .job import backend`), every
module under 1,000 lines and the fleet_job.py entry under 20."""
import ast, unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/herdr-fleet/scripts'
PACKAGE = SCRIPTS / 'stampede'
LOWER = {'base': set(), 'job': {'base'}, 'hcapi': {'base', 'job'}, 'herdrapi': {'base'}}  # all they may import at load
NEVER = {'native': {'tui', 'relay', 'handed', 'hooks'}, 'tui': {'relay', 'handed', 'native'}}
DELETED = {'relay', 'handed'}  # deleted in v0.3.0: only these reach them, each inside the function, besides each other
LAZY = {
    ('cli', 'new'): {'relay'},
    ('cli', 'start'): {'relay', 'handed'},
    ('cli', 'run'): {'relay'},
    ('owner', 'finish'): {'handed', 'native'},
    # Exceptions, each a function that branches on the backend and is called from a layer below cli, so a load-time
    # import would be a cycle: tell and notify_lead (owner and hooks call them), lead_alive and caller_ids reach native;
    # tell reaches a relay job's Codex and handed agents; the deliverer types into a relay job's Core terminal.
    ('owner', 'tell'): {'relay', 'handed', 'native'},
    ('owner', 'notify_lead'): {'native'},
    ('owner', 'lead_alive'): {'native'},
    ('owner', 'caller_ids'): {'native'},
    ('tui', 'deliver'): {'relay'},
    ('tui', 'type_unread'): {'relay'},
}


def imports(path):
    """(modules imported at load, {function: modules imported inside it}, every ImportFrom of the package)."""
    tree = ast.parse(path.read_text())
    load, inside, froms = set(), {}, []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.level or (node.module or '').startswith('stampede')):
            froms.append(node)
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.level:
            load |= {a.name for a in node.names}
        if isinstance(node, ast.FunctionDef):
            found = {a.name for x in ast.walk(node) if isinstance(x, ast.ImportFrom) and x.level for a in x.names}
            if found:
                inside[node.name] = found
    return load, inside, froms


class Layers(unittest.TestCase):
    def setUp(self):
        self.mods = {p.stem: imports(p) for p in sorted(PACKAGE.glob('*.py')) if p.stem != '__init__'}

    def test_every_import_of_the_package_is_a_module_under_its_alias(self):
        for mod, (_, _, froms) in self.mods.items():
            for node in froms:
                self.assertEqual((node.level, node.module), (1, None), f'{mod}: call through the module, from . import x as x_')
                for alias in node.names:
                    self.assertIn(alias.name, self.mods, mod)
                    self.assertEqual(alias.asname, alias.name + '_', f'{mod}: import {alias.name} as {alias.name}_')

    def test_the_lower_layers_import_only_what_is_below_them(self):
        for mod, allowed in LOWER.items():
            load, inside, _ = self.mods[mod]
            self.assertLessEqual(load, allowed, mod)
            self.assertEqual(inside, {}, mod)

    def test_native_and_tui_never_import_the_paths_they_must_not_reach(self):
        for mod, banned in NEVER.items():
            load, inside, _ = self.mods[mod]
            self.assertFalse(load & banned, mod)
            for function, found in inside.items():
                self.assertFalse(found & banned - LAZY.get((mod, function), set()), f'{mod}.{function}')

    def test_only_cli_imports_native_at_load_and_nothing_imports_relay_or_handed_at_load(self):
        for mod, (load, _, _) in self.mods.items():
            if mod != 'cli':
                self.assertNotIn('native', load, mod)
            if mod not in DELETED:
                self.assertFalse(load & DELETED, mod)
        self.assertNotIn('relay', self.mods['handed'][0], 'relay imports handed, never the other way')

    def test_the_imports_inside_functions_are_exactly_the_listed_ones(self):
        found = {(mod, function): names for mod, (_, inside, _) in self.mods.items() for function, names in inside.items()}
        self.assertEqual(found, LAZY)

    def test_no_import_cycle_at_load(self):
        graph = {mod: load for mod, (load, _, _) in self.mods.items()}
        done, path = set(), []

        def visit(mod):
            self.assertNotIn(mod, path, 'cycle: ' + ' -> '.join(path + [mod]))
            if mod in done:
                return
            path.append(mod)
            for other in sorted(graph[mod]):
                visit(other)
            path.pop()
            done.add(mod)
        for mod in sorted(graph):
            visit(mod)

    def test_every_module_is_under_1000_lines_and_the_entry_under_20(self):
        for path in PACKAGE.glob('*.py'):
            self.assertLess(len(path.read_text().splitlines()), 1000, path.name)
        self.assertLess(len((SCRIPTS / 'fleet_job.py').read_text().splitlines()), 20)
        self.assertEqual((PACKAGE / '__init__.py').read_text(),
                         '"""stampede: the job commands behind the stampede and fleet-job CLIs."""\n')


if __name__ == '__main__':
    unittest.main()
