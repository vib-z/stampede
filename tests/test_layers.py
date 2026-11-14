"""The stampede package's layers, read with ast (nothing is imported or started): who may import whom, no import
cycle at load, every call through the module (`from . import job as job_`, never `from .job import backend` or an
absolute import of the package), every module under 1,000 lines and the fleet_job.py entry under 20. An import in an
if, try, with or class body runs at load and counts as one; an import inside a function is lazy and must be in LAZY."""
import ast, unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/herdr-fleet/scripts'
PACKAGE = SCRIPTS / 'stampede'
LOWER = {'settings': set(), 'base': set(), 'job': {'base', 'settings'}, 'hcapi': {'base', 'job', 'settings'},
         'herdrapi': {'base'}}  # all they may import at load: settings is the bottom layer, it imports nothing of the package
NEVER = {'native': {'tui', 'relay', 'handed', 'hooks'}, 'tui': {'relay', 'handed', 'native'}}
DELETED = {'relay', 'handed'}  # deleted in v0.3.0: only these reach them, each inside the function, besides each other
LAZY = {
    ('cli', 'new'): {'relay'},
    ('cli', 'start'): {'relay', 'handed'},
    ('cli', 'run'): {'relay'},
    ('owner', 'finish'): {'handed', 'native', 'gates'},  # gates imports owner (gate_ok) at load
    # Exceptions, each a function that branches on the backend and is called from a layer below cli, so a load-time
    # import would be a cycle: tell and notify_lead (owner and hooks call them), lead_alive and caller_ids reach native;
    # tell reaches a relay job's Codex and handed agents; the deliverer types into a relay job's Core terminal; the
    # front door's wait asks native whether the lead is blocked.
    ('owner', 'tell'): {'relay', 'handed', 'native'},
    ('owner', 'notify_lead'): {'native'},
    ('owner', 'lead_alive'): {'native'},
    ('owner', 'caller_ids'): {'native'},
    ('owner', 'wait'): {'native'},
    ('tui', 'deliver'): {'relay'},
    ('tui', 'type_unread'): {'relay'},
}


def scan(text):
    """(modules imported at load, {top-level function: modules imported inside it}, [import lines in another form than
    `from . import x as x_`]) for one module's source. Every import of the package counts, whatever its form or depth."""
    load, inside, bad = set(), {}, []

    def record(node, mods, canonical, function):
        if not canonical:
            bad.append(f'line {node.lineno}: {ast.unparse(node)}')
        if function:
            inside.setdefault(function, set()).update(mods)
        else:
            load.update(mods)

    def visit(node, function):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            function = function or getattr(node, 'name', '<lambda>')
        if isinstance(node, ast.ImportFrom):
            module = node.module or ''
            if node.level:  # from . import x, from .x import y, from .. import ...
                mods = {a.name for a in node.names} if not module else {module.split('.')[0]}
                canonical = node.level == 1 and not module and all(a.asname == a.name + '_' for a in node.names)
                record(node, mods, canonical, function)
            elif module == 'stampede':
                record(node, {a.name for a in node.names}, False, function)
            elif module.startswith('stampede.'):
                record(node, {module.split('.')[1]}, False, function)
        elif isinstance(node, ast.Import):
            mods = {a.name.split('.')[1] if '.' in a.name else '__init__' for a in node.names
                    if a.name == 'stampede' or a.name.startswith('stampede.')}
            if mods:
                record(node, mods, False, function)
        for child in ast.iter_child_nodes(node):
            visit(child, function)

    visit(ast.parse(text), None)
    return load, inside, bad


def read():
    return {p.stem: p.read_text() for p in sorted(PACKAGE.glob('*.py')) if p.stem != '__init__'}


def problems(sources):
    """Every broken layer rule of a package given as {module: source}, as one line each; [] when it keeps its layers."""
    mods = {mod: scan(text) for mod, text in sources.items()}
    out = []
    for mod, (load, inside, bad) in mods.items():
        out += [f'{mod}: {b}: call through the module, from . import x as x_' for b in bad]
        out += [f'{mod}: imports {m}, which is no module of the package'
                for m in load | set().union(*inside.values()) if m not in mods]
    for mod, allowed in LOWER.items():
        load, inside, _ = mods[mod]
        out += [f'{mod}: imports {m} at load' for m in sorted(load - allowed)]
        out += [f'{mod}.{f}: imports {sorted(m)} inside' for f, m in inside.items()]
    for mod, banned in NEVER.items():
        load, inside, _ = mods[mod]
        out += [f'{mod}: imports {m}, which it must never reach' for m in sorted(load & banned)]
        out += [f'{mod}.{f}: imports {m}, which it must never reach' for f, found in inside.items()
                for m in sorted(found & banned - LAZY.get((mod, f), set()))]
    for mod, (load, _, _) in mods.items():
        if mod != 'cli' and 'native' in load:
            out.append(f'{mod}: imports native at load (only cli does)')
        if mod not in DELETED:
            out += [f'{mod}: imports {m} at load (relay and handed only inside a function)' for m in sorted(load & DELETED)]
    if 'relay' in mods['handed'][0]:
        out.append('handed: imports relay (relay imports handed, never the other way)')
    found = {(mod, f): names for mod, (_, inside, _) in mods.items() for f, names in inside.items()}
    if found != LAZY:
        out.append(f'imports inside functions differ from LAZY: found {found}')
    cycle = find_cycle({mod: load & set(mods) for mod, (load, _, _) in mods.items()})
    if cycle:
        out.append('cycle at load: ' + ' -> '.join(cycle))
    return out


def find_cycle(graph):
    done, path = set(), []

    def visit(mod):
        if mod in path:
            return path[path.index(mod):] + [mod]
        if mod in done:
            return None
        path.append(mod)
        for other in sorted(graph[mod]):
            cycle = visit(other)
            if cycle:
                return cycle
        path.pop()
        done.add(mod)
        return None
    for mod in sorted(graph):
        cycle = visit(mod)
        if cycle:
            return cycle
    return None


class Layers(unittest.TestCase):
    def test_the_package_keeps_its_layers(self):
        self.assertEqual(problems(read()), [])

    def test_every_module_is_under_1000_lines_and_the_entry_under_20(self):
        for path in PACKAGE.glob('*.py'):
            self.assertLess(len(path.read_text().splitlines()), 1000, path.name)
        self.assertLess(len((SCRIPTS / 'fleet_job.py').read_text().splitlines()), 20)
        self.assertEqual((PACKAGE / '__init__.py').read_text(),
                         '"""stampede: the job commands behind the stampede and fleet-job CLIs."""\n')


class Mutations(unittest.TestCase):
    """The guard catches each way a later change could break a layer: the package's own sources, one module changed in
    memory."""

    def caught(self, module, extra, words):
        sources = read()
        sources[module] += '\n' + extra
        found = problems(sources)
        self.assertTrue(any(words in line for line in found), f'not caught: {extra!r} in {module}: {found}')

    def test_a_forbidden_relative_import(self):
        self.caught('native', 'from . import tui as tui_\n', 'native: imports tui, which it must never reach')

    def test_a_forbidden_absolute_import(self):
        self.caught('native', 'import stampede.tui as tui_\n', 'native: imports tui, which it must never reach')
        self.caught('native', 'from stampede import tui\n', 'call through the module')

    def test_a_cycle_by_an_absolute_import(self):
        self.caught('base', 'import stampede.hcapi as hcapi_\n', 'cycle at load: ')
        self.caught('job', 'from . import hcapi as hcapi_\n', 'cycle at load: ')

    def test_an_import_in_an_if_try_with_or_class_body_runs_at_load(self):
        self.caught('native', 'if True:\n    from . import tui as tui_\n', 'native: imports tui, which it must never reach')
        self.caught('native', 'try:\n    from . import hooks as hooks_\nexcept ImportError:\n    pass\n', 'native: imports hooks')
        self.caught('owner', 'class Late:\n    from . import native as native_\n', 'owner: imports native at load')

    def test_a_name_imported_from_a_module_and_not_through_it(self):
        self.caught('owner', 'from .job import backend\n', 'call through the module')
        self.caught('owner', 'from stampede.job import backend\n', 'call through the module')

    def test_a_lazy_import_not_in_lazy(self):
        self.caught('hooks', 'def later():\n    from . import relay as relay_\n', 'differ from LAZY')


if __name__ == '__main__':
    unittest.main()
