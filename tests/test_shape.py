"""Shape of the repo: line limits, frontmatter, links, dashes, personal paths.

Run from the repo root: python3 -m unittest tests.test_shape
"""
import hashlib
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP = {".git", ".herdr-stampede", ".stampede", ".claude", "__pycache__", "node_modules"}
SKIP_PATHS = {ROOT / "docs" / "superpowers"}
PLAYBOOK_DIRS = ("skills", "remote")
TEXT_EXT = {".md", ".py", ".sh", ".toml", ".html", ".css", ".js", ".json", ".jsonl", ".txt", ".example", ".plist", ".tsv", ".yml", ".yaml"}
DASHES = re.compile("[\u2013\u2014]")
LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
PERSONAL = re.compile(r"/Use" r"rs/(?!you\b|<|\$USER|USER\b)[A-Za-z0-9._-]+|/home/(?!you\b|<|\$USER|user\b|linuxbrew/)[a-z0-9._-]+/"
                      r"|-Users-[A-Za-z]|[A-Za-z0-9-]+\.ts\.net\b")
# /home/linuxbrew is Homebrew's own prefix on Linux, not a person's home.
# Private words (the owner's name, hosts, bots, projects, private skills), kept as sha256 prefixes so this file never names them.
PRIVATE = {"05bd4b1a17d3955b", "1afc78a3a8aca49e", "270d76c78b081db7", "34d87f87a274e311", "4e09d4303ab499d0", "5a5a908605d4726a",
           "60019f2d98774f2e", "60c268171f89f3ed", "61ea0803f8853523", "6ea1969caf4636dc", "7221ac81b18aa788", "7277ce043c1567e2",
           "926b5c9ce5f79e20", "a5ccbc8dbcb36c0b", "c8914ee7e7531aaf", "e444bd3bca2736f3", "ef194d30114c4521",
           "4e09d4303ab499d0", "cafd568139954f07"}  # the last two: forms of the machine's own name, as Herdr Core 0.1.20 names a core
PRIVATE_PATH = re.compile(r"~/co" r"de/skills\b|skills/pers" r"onal/")  # the private skills checkout and its layout
MAX_BYTES = 10 * 1024 * 1024  # AGENTS.md: never commit media over 10 MB
USERS_DIR = "/" + "Users" + "/"  # owner, 19:05: nothing hard-coded; built here so this file does not match itself
HERDR_ID = re.compile(r"\bw[0-9][A-Za-z0-9]*:[pt][0-9A-Za-z]+\b")  # a raw Herdr id such as w1A:p2
MODEL = re.compile(r"\b(claude-(opus|sonnet|haiku|fable)-[0-9][0-9-]*|gpt-[0-9][A-Za-z0-9.-]*)\b")
MODEL_OK = ("config.example", "skills/", "tests/")  # the only places a model name may appear
SKILL_BYTES, PLAYBOOK_BYTES, LINE_CHARS = 6000, 8000, 400  # a playbook is read whole by an agent: short in bytes, not only lines
# core-relay.md describes the deprecated --core --relay path and is deleted in v0.3.0: no byte or line-length limit until then.
LONG_OK = {"skills/herdr-fleet/references/core-relay.md"}
MONTHS = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
HISTORY = re.compile(r"\b20[0-9]{2}-[01][0-9]-[0-3][0-9]\b|\b[0-3]?[0-9] (?:" + MONTHS + r")[a-z]* 20[0-9]{2}\b"
                     r"|owner's rule|owner-approved|Seen 20", re.I)


def not_ignored():
    """Tracked and untracked files git does not ignore, or None outside a git checkout."""
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-co", "--exclude-standard", "-z"],
                             capture_output=True, check=True).stdout.decode()
    except (OSError, subprocess.CalledProcessError):
        return None
    return {ROOT / f for f in out.split("\0") if f}


KEEP = not_ignored()  # another tool's ignored state (.gstack/) never fails the shape tests


def files():
    for p in sorted(ROOT.rglob("*")):
        rel = p.relative_to(ROOT)
        if p.is_dir() or any(part in SKIP for part in rel.parts) or any(s in p.parents for s in SKIP_PATHS):
            continue
        if KEEP is not None and p not in KEEP:
            continue
        yield p


def text_files():
    for p in files():
        if p.suffix in TEXT_EXT or p.name in ("LICENSE", ".gitignore", "install.sh") or (
                p.suffix == "" and p.parent.name == "scripts"):
            yield p


def md_files():
    return [p for p in files() if p.suffix == ".md"]


def rel(p):
    return str(p.relative_to(ROOT))


def is_playbook(p):
    r = p.relative_to(ROOT)
    return r == Path("SKILL.md") or (r.parts[0] in PLAYBOOK_DIRS and p.suffix == ".md")


def strip_code(text):
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    return re.sub(r"`[^`\n]*`", "", text)


def sections(text):
    """Map each '## ' heading to its body lines, in file order."""
    out, cur = {}, None
    for line in text.splitlines():
        if line.startswith("## "):
            cur = line[3:].strip()
            out[cur] = []
        elif cur is not None:
            out[cur].append(line)
    return out


def slug(heading):
    h = re.sub(r"[`*_\[\]()]", "", heading.strip().lower())
    h = re.sub(r"[^\w\- ]", "", h)
    return h.replace(" ", "-")


def anchors(p):
    seen, out = {}, set()
    for line in strip_code_blocks(p.read_text(encoding="utf-8")).splitlines():
        m = re.match(r"#{1,6}\s+(.*)", line)
        if m:
            s = slug(m.group(1))
            n = seen.get(s, 0)
            out.add(s if n == 0 else f"{s}-{n}")
            seen[s] = n + 1
    return out


def strip_code_blocks(text):
    return re.sub(r"```.*?```", "", text, flags=re.S)


def frontmatter(text):
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end < 0:
        return None
    fm = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm


def too_long(p, name):
    """A playbook's size over its limit, counted on disk (CRLF counts), and each line over LINE_CHARS characters."""
    size, limit = p.stat().st_size, SKILL_BYTES if p.name == "SKILL.md" else PLAYBOOK_BYTES
    bad = [f"{name}: {size} bytes, limit {limit}"] if size > limit else []
    return bad + [f"{name}:{i}: {len(line)} characters, limit {LINE_CHARS}"
                  for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if len(line) > LINE_CHARS]


class Shape(unittest.TestCase):
    def test_line_limits(self):
        bad = []
        for p in md_files():
            if not is_playbook(p):
                continue
            r = p.relative_to(ROOT)
            limit = 140 if r.parts[0] == "skills" and len(r.parts) == 3 and p.name == "SKILL.md" else 160
            n = len(p.read_text(encoding="utf-8").splitlines())
            if n > limit:
                bad.append(f"{rel(p)}: {n} lines, limit {limit}")
        self.assertEqual(bad, [], "\n".join(bad))

    def test_playbook_bytes_and_line_length(self):
        """SKILL.md at most SKILL_BYTES, every other playbook file at most PLAYBOOK_BYTES, no line over LINE_CHARS (code too)."""
        bad = [b for p in md_files() if is_playbook(p) and rel(p) not in LONG_OK for b in too_long(p, rel(p))]
        self.assertEqual(bad, [], "\n".join(bad))

    def test_playbook_bytes_count_the_disk(self):
        """The byte limit reads the file's bytes, so CRLF line ends count."""
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "SKILL.md"
            body = ("x" * 99 + "\n") * 60   # 6,000 bytes with LF: at the limit
            p.write_bytes(body.encode())
            self.assertEqual(too_long(p, "SKILL.md"), [])
            p.write_bytes(body.replace("\n", "\r\n").encode())   # 6,060 bytes on disk, 6,000 read as text
            self.assertEqual(too_long(p, "SKILL.md"), ["SKILL.md: 6060 bytes, limit 6000"])

    def test_no_history_in_playbooks(self):
        """Playbooks hold rules, not their history (AGENTS.md section 2): no dates, no "owner's rule", no "Seen 20..."."""
        bad = [f"{rel(p)}:{i}: history: {HISTORY.search(line).group(0)}" for p in md_files()
               if is_playbook(p)
               for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if HISTORY.search(line)]
        self.assertEqual(bad, [], "\n".join(bad))

    def test_skill_frontmatter(self):
        bad = []
        for p in md_files():
            if p.name != "SKILL.md":
                continue
            fm = frontmatter(p.read_text(encoding="utf-8"))
            if fm is None or not fm.get("name") or not fm.get("description"):
                bad.append(f"{rel(p)}: needs frontmatter with name and description")
        self.assertEqual(bad, [], "\n".join(bad))

    def test_links_resolve(self):
        bad = []
        for p in md_files():
            text = strip_code(p.read_text(encoding="utf-8"))
            for target in LINK.findall(text):
                if re.match(r"[a-z][a-z0-9+.-]*:", target) or target.startswith("//"):
                    continue
                path, _, anchor = target.partition("#")
                dest = (p.parent / path).resolve() if path else p
                if not dest.exists():
                    bad.append(f"{rel(p)}: broken link {target}")
                elif anchor and dest.suffix == ".md" and anchor not in anchors(dest):
                    bad.append(f"{rel(p)}: missing anchor {target}")
        self.assertEqual(bad, [], "\n".join(bad))

    def test_no_dashes(self):
        bad = []
        for p in text_files():
            for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if DASHES.search(line):
                    bad.append(f"{rel(p)}:{i}: em or en dash")
        self.assertEqual(bad, [], "\n".join(bad))

    def test_no_personal_paths(self):
        """Every text file, the history under docs/superpowers too: no home paths, private paths or private words."""
        bad = []
        for p in list(text_files()) + sorted((ROOT / "docs" / "superpowers").rglob("*.md")):
            for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                words = {w for token in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", line.lower()) for w in [token, *token.split("-")]}
                if PERSONAL.search(line) or PRIVATE_PATH.search(line) or any(
                        hashlib.sha256(w.encode()).hexdigest()[:16] in PRIVATE for w in words):
                    bad.append(f"{rel(p)}:{i}: personal detail")
        self.assertEqual(bad, [], "\n".join(bad))

    def test_no_agent_instruction_names(self):
        """A file named claude.md or agents.md (any case) below the root is loaded as agent instructions."""
        bad = [rel(p) for p in files() if p.name.lower() in ("claude.md", "agents.md") and p.parent != ROOT]
        self.assertEqual(bad, [], "\n".join(bad))

    def test_nothing_hard_coded(self):
        """Owner, 19:05: no home paths anywhere; raw Herdr ids and model names only in tests and the skills' own examples."""
        bad = []
        for p in text_files():
            r = rel(p)
            if r == "tests/test_shape.py":
                continue
            for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if USERS_DIR in line:
                    bad.append(f"{r}:{i}: home path")
                if not r.startswith(("tests/", "skills/")) and HERDR_ID.search(line):
                    bad.append(f"{r}:{i}: raw Herdr id {HERDR_ID.search(line).group(0)}; take ids from Herdr's JSON")
                if not r.startswith(MODEL_OK) and MODEL.search(line):
                    bad.append(f"{r}:{i}: model name {MODEL.search(line).group(0)}; put it in config.example or skills/")
        self.assertEqual(bad, [], "\n".join(bad))

    def test_front_doors_relay_no_gate(self):
        """A front door relays plan approval and ordinary answers only. A gate is the owner's own tap on the lead's card or phone,
        or, in a job a bot started, the owner's yes that the bot records with approve-gate (owner, 23 Oct 2026)."""
        relay = re.compile(r"yes (at|to) (a|the) gate|says yes to|pass(es)? (on )?(your|their) yes", re.I)
        bad = [f"{rel(p)}:{i}: relays a gate yes" for p in sorted((ROOT / "remote").rglob("*.md"))
               for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if relay.search(line)]
        for name in ("claude-code.md", "codex.md"):
            if "own tap on the lead's card" not in (ROOT / "remote" / name).read_text(encoding="utf-8"):
                bad.append(f"remote/{name}: says nothing of the owner's own tap on the lead's card")
        for name in ("README.md", "events.md", "grokbot/send.md"):
            if "approve-gate" not in (ROOT / "remote" / name).read_text(encoding="utf-8"):
                bad.append(f"remote/{name}: says nothing of approve-gate, the only way a bot passes a gate yes")
        self.assertEqual(bad, [], "\n".join(bad))

    def test_front_doors_outside_herdr_name_a_target(self):
        """Outside Herdr there is no current workspace, so `stampede new` needs --workspace or --pane (review round 1, R3)."""
        for name in ("skills/stampede/SKILL.md", "README.md", "remote/other.md"):
            lines = (ROOT / name).read_text(encoding="utf-8").splitlines()
            self.assertTrue(any("outside Herdr" in l and "--workspace" in l and "--pane" in l for l in lines), name)

    def test_using_is_the_front_page(self):
        """USING.md: one short page an agent reads first, linked from every entry point."""
        using = ROOT / "USING.md"
        text = using.read_text(encoding="utf-8")
        self.assertLess(len(text.encode()), 4000)
        self.assertEqual([l for l in text.splitlines() if len(l) > 300], [])
        for name in ("README.md", "AGENTS.md", "CLAUDE.md", "SKILL.md"):
            self.assertIn("](USING.md)", (ROOT / name).read_text(encoding="utf-8"), name)

    def test_one_gate_list(self):
        """The gate list lives in gates.md alone; every other playbook links to it ("sitemap" marks a copy of the list)."""
        gates = ROOT / "skills" / "herdr-fleet" / "references" / "gates.md"
        self.assertLess(len(gates.read_bytes()), 3000)
        self.assertIn("sitemap", gates.read_text(encoding="utf-8"))
        self.assertIn("reviewed commit is the commit the gate names", gates.read_text(encoding="utf-8"))  # merge only what was reviewed
        copies = [rel(p) for p in md_files() if is_playbook(p) and p != gates and "sitemap" in p.read_text(encoding="utf-8").lower()]
        self.assertEqual(copies, [])

    def test_no_large_files(self):
        bad = [f"{rel(p)}: {p.stat().st_size // 1048576} MB" for p in files() if p.stat().st_size > MAX_BYTES]
        self.assertEqual(bad, [], "\n".join(bad))



if __name__ == "__main__":
    unittest.main()
