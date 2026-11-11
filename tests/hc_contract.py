"""What stampede uses of Herdr Core's API, held against hc's own schema (`hc schema`, an OpenRPC document).

USES names, per hc command the product runs: its API method, the parameters stampede passes, the error kinds stampede
or its fake tells apart, and the result fields it reads. view(schema) is that part of a schema, plus the event types
events.subscribe sends. tests/test_hc_contract.py holds the product code and tests/fake_hc.py to the committed snapshot
(tests/fixtures/hc-schema-<version>.json); the live eval V03 compares the snapshot's view with `hc schema` on the
machine, so a Herdr Core that changes anything stampede relies on fails there before it fails a job."""
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / 'tests/fixtures/hc-schema-0.1.20.json'
TERMINAL = ('address', 'argv', 'exit_code', 'keep', 'labels', 'name', 'reason', 'state', 'status', 'status_ms', 'turn')
USES = {
    'run': ('terminal.run', ('argv', 'cwd', 'keep', 'labels', 'name', 'no_notify', 'no_parent'), ('name_taken', 'spawn_failed'), ('address', 'name')),
    'ls': ('terminal.list', ('all', 'labels'), (), ('terminals',)),
    'get': ('terminal.get', ('terminal',), ('not_found',), TERMINAL),
    'send': ('terminal.send', ('force', 'if', 'terminal', 'text'), ('blocked', 'cancelled', 'finished', 'not_found', 'status_mismatch'),
             ('started', 'status', 'turn')),
    'wait': ('terminal.wait', ('terminal', 'timeout'), ('not_found',), ('ended', 'exit_code', 'reason', 'status', 'terminal', 'turn')),
    'read': ('terminal.read', ('lines', 'terminal'), ('not_found',), ('text',)),
    'kill': ('terminal.kill', ('terminal',), ('not_found',), TERMINAL),
    'rm': ('terminal.rm', ('terminal',), ('live', 'not_found'), ('removed',)),
    'keep': ('terminal.keep', ('keep', 'terminal'), ('not_found',), TERMINAL),
    'label': ('terminal.label', ('labels', 'terminal'), ('not_found',), TERMINAL),
    'keys': ('terminal.keys', ('keys', 'terminal'), ('not_found',), ('status', 'turn')),
    'events': ('events.subscribe', ('labels',), (), ('terminals',)),
    'exec': ('machine.exec', ('argv',), (), ()),  # the core's own environment: /usr/bin/env, read only
}


def snapshot():
    return json.loads(SNAPSHOT.read_text())


def fields(schema, method):
    """The property names of a method's result."""
    result = method.get('result', {}).get('schema', {})
    name = result.get('$ref', '').rsplit('/', 1)[-1]
    return set((schema['components']['schemas'].get(name) or result).get('properties', {}))


def event_types(schema):
    """The event types events.subscribe names in its description: "(created, lost, ..., doc)"."""
    method = next(m for m in schema['methods'] if m['name'] == 'events.subscribe')
    return sorted(re.search(r'\(((?:[a-z_]+, )+[a-z_]+)\)', method['description']).group(1).split(', '))


def view(schema):
    """The part of a schema stampede depends on; a name it uses that the schema lacks shows as missing:<name>."""
    methods, out = {m['name']: m for m in schema['methods']}, {}
    for command, (name, params, kinds, results) in USES.items():
        method = methods.get(name)
        if method is None:
            out[command] = 'missing:' + name
            continue
        have = ({p['name'] for p in method['params']}, {e['data']['kind'] for e in method.get('errors', [])}, fields(schema, method))
        out[command] = {'method': name, **{label: sorted(n if n in found else 'missing:' + n for n in wanted)
                                           for label, wanted, found in zip(('params', 'errors', 'result'), (params, kinds, results), have)}}
    out['event types'] = event_types(schema)
    out['heartbeat'] = 'heartbeat' in next(m for m in schema['methods'] if m['name'] == 'events.subscribe')['description']
    return out
