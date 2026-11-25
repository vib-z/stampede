"""herdr-send: type one prompt into a Herdr TUI agent's pane, and confirm from its status and its screen that it went in.
Every place stampede types into a pane uses submit: the herdr-send script (tell, the deliverer of a Codex or a Claude
lead, a Codex lead's brief pointer, reopen.sh --prompt) and a Core job's handed agent (keys=False)."""
import os, re, shutil, subprocess, sys, time
from pathlib import Path

from . import herdrapi as herdrapi_

CALL = 15  # seconds one herdr look may take
PAUSES = (2, 2, 3, 4, 5, 6)  # seconds between looks after a prompt Herdr did not see start: about 22 s in all
ENTERS = 3  # Enter presses at most while the box still holds the text
SETTLE = 8  # seconds before a box that no longer shows the text counts as submitted: Claude can draw a long paste late
CLEARED = 2  # seconds to let ctrl+c redraw the box before reading it again

# herdr-send's markers of an empty prompt: Codex's placeholder and footer, Claude's hint, a bare prompt line (Claude's
# ends in a no-break space).
EMPTY_PROMPT = re.compile(r'Ask Codex to do anything|for shortcuts|To get started|describe a task|Try "|^ *(>|❯|›)[ \xa0]*$',
                          re.IGNORECASE | re.MULTILINE)
# Codex 0.170 in a narrow pane cuts its placeholder to 'Ask Codex to do anyth' and its footer to '← for agents ⚠ 2 · f2'
# (live, 20 Nov 2026). That footer marks an empty prompt only as the last row, right under a status row, with no scroll
# arrow from the last prompt line down: a draft can quote it, and a tall draft hides the status rows and scrolls.
NARROW_FOOTER = re.compile(r' *← for agents( ·( \?( for( [a-z]*)?)?)?)?( +⚠ .*)?')
PROMPT_LINE = re.compile(r'[»›❯>]( |$)')  # the prompt line, in column 0: a draft's own lines are indented
# A long prompt shows as a paste placeholder: Claude Code 2.1.332 draws '[Pasted text #1]', or '[Pasted text #1 +3 lines]',
# sometimes followed by the end of the text typed as usual (live, 25 Nov 2026). Codex 0.169 showed a 1600-character text
# whole, in a composer that scrolls (live, 25 Nov 2026); its own placeholder, '[Pasted Content 1600 chars]', is matched too.
PLACEHOLDER = re.compile(r'\[Pasted (?:text #\d+(?: \+\d+ lines?)?|Content \d+ chars)\]')

ESCAPE = re.compile(r'\x1b(?:\[([0-9;:?]*)([@-~])|\][^\x07\x1b]*(?:\x07|\x1b\\)|.)')  # CSI, OSC, or a two-byte escape


def cells(row):
    """[(character, dim)] for one row of a screen read with --format ansi: each printed character, and whether it was
    drawn dim (SGR 2). A row of plain text gives every character as not dim."""
    out, dim, at = [], False, 0
    for found in ESCAPE.finditer(row):
        out += [(char, dim) for char in row[at:found.start()] if char != '\r']
        at = found.end()
        if found.group(2) == 'm' and '?' not in found.group(1):
            codes, i = [int(code) if code else 0 for code in found.group(1).replace(':', ';').split(';')], 0
            while i < len(codes):
                if codes[i] in (38, 48, 58):  # a colour, then 5;n or 2;r;g;b
                    i += 3 if codes[i + 1:i + 2] == [5] else 5
                    continue
                dim = True if codes[i] == 2 else False if codes[i] in (0, 22) else dim
                i += 1
    return out + [(char, dim) for char in row[at:] if char != '\r']


def plain(screen):
    """A screen read with --format ansi as plain text: its characters without their styles."""
    return '\n'.join(''.join(char for char, _ in cells(row)) for row in screen.splitlines())

def narrow_footer(screen):
    """True when a screen ends in Codex's footer cut to fit a narrow pane. Arrows count only from the last prompt line
    down (the whole screen when none shows), so one in a reply above it changes nothing."""
    rows = [row.rstrip() for row in screen.splitlines()]
    while rows and not rows[-1]:
        rows.pop()
    prompts = [i for i, row in enumerate(rows) if PROMPT_LINE.match(row)]
    composer = rows[prompts[-1]:] if prompts else rows
    return (len(rows) > 1 and bool(rows[-2]) and bool(NARROW_FOOTER.fullmatch(rows[-1]))
            and not any(arrow in row for row in composer for arrow in '↑↓'))


def typed(screen, empty=EMPTY_PROMPT):
    """True when a screen's last 8 non-empty lines show no empty-prompt marker, and it does not end in Codex's narrow
    footer: text already typed in the prompt."""
    return not empty.search('\n'.join([line for line in screen.splitlines() if line.strip()][-8:])) and not narrow_footer(screen)


def box(screen):
    """The text typed in a screen's prompt box: what follows the marker on the last prompt line, and the rows under it up
    to the box's lower border (Claude) or a blank row (Codex). '' when it shows no prompt line, or, in a screen read
    with its styles (screen), when everything in the box is dim: Claude's and Codex's placeholder and hints, which typed
    text never is. Plain text cannot tell a placeholder from a draft."""
    lines = [cells(row) for row in screen.splitlines()]
    rows = [''.join(char for char, _ in line).replace('\xa0', ' ').rstrip() for line in lines]
    prompts = [i for i, row in enumerate(rows) if PROMPT_LINE.match(row)]
    if not prompts:
        return ''
    held = [lines[prompts[-1]][1:]]
    for at in range(prompts[-1] + 1, len(rows)):
        if not rows[at].strip() or rows[at].lstrip().startswith('─'):
            break
        held.append(lines[at])
    if '\x1b[' in screen and all(dim for line in held for char, dim in line if char.strip()):
        return ''
    return ' '.join(''.join(char for char, _ in line).replace('\xa0', ' ').strip() for line in held).strip()


def holds(screen, texts, lone=True):
    """True when a screen's prompt box shows one of texts typed, or its start (a box drawn in part, or cut): compared
    with no whitespace, since a wrapped row is indented, and each paste placeholder standing for any part of the text.
    A box of placeholders alone holds one of texts only when lone says it may."""
    shown = box(screen)
    pieces = [re.sub(r'\s+', '', piece) for piece in PLACEHOLDER.split(shown)]
    if not any(pieces):
        return lone and bool(PLACEHOLDER.search(shown)) and bool(texts)
    pattern = re.compile('.*'.join(re.escape(piece) for piece in pieces), re.S)
    return any(pattern.match(re.sub(r'\s+', '', text)) for text in texts)


def herdr_path():
    """The herdr that herdr-send runs: $HERDR, the one on PATH, else ~/.local/bin/herdr (an ssh command's PATH lacks it)."""
    found = os.environ.get('HERDR') or shutil.which('herdr') or str(Path.home() / '.local/bin/herdr')
    os.environ['HERDR'] = found  # herdrapi runs $HERDR
    return found


def shown(target):
    """{status, focused, seq} of the agent Herdr shows by that name or pane, or None when it shows none. seq is Herdr's
    completion counter: it moves when a turn ends, and is null while one runs."""
    try:
        agent = herdrapi_.herdr('agent', 'get', target, timeout=CALL).get('agent')
    except (herdrapi_.HerdrError, ValueError):
        return None
    if not isinstance(agent, dict) or not agent.get('agent_status'):
        return None
    return {'status': agent['agent_status'], 'focused': bool(agent.get('focused')), 'seq': agent.get('completion_seq')}


def screen(target, lines):
    """The agent's visible screen, its last lines rows, with its styles (--format ansi), or as plain text from a Herdr
    that cannot give them; None when Herdr does not show it, which tells nothing."""
    read = [herdr_path(), 'agent', 'read', target, '--source', 'visible', '--lines', str(lines)]
    try:
        for args in (read + ['--format', 'ansi'], read):
            shown = subprocess.run(args, capture_output=True, text=True, timeout=CALL)
            if shown.returncode == 0:
                return shown.stdout
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def calm(target):
    """True when Herdr shows the agent idle or done and nobody in its pane, read just before a key: a screen read can
    take seconds, and the owner may have come in meanwhile."""
    now = shown(target)
    return now is not None and now['status'] in ('idle', 'done') and not now['focused']


def press(target, key):
    try:
        subprocess.run([herdr_path(), 'agent', 'send-keys', target, key], capture_output=True, timeout=CALL)
    except (OSError, subprocess.TimeoutExpired):
        pass


REFUSED = ('(not a live agent)', 'focused: the owner is in that pane; retry later', '(blocked at a dialog; read the screen)')


def refused(line):
    """True for a FAILED line of submit that typed nothing: no agent, the owner in its pane, or a dialog."""
    return line.startswith('FAILED ') and line.endswith(REFUSED)


def submit(target, text, keys=True):
    """Type text into the agent's prompt: (True, a SUBMITTED line) or (False, a FAILED line).
    Never a key for a focused, blocked or working agent. At idle or done it first clears leftover typed input with
    ctrl+c, only when the prompt is not empty (ctrl+c on an EMPTY idle Codex prompt quits Codex). Then Herdr types the
    text; if it sees no turn start in 5 s (Claude Code 2.1.332 can take longer), verify decides from the screen.
    keys=False presses no key at all (a Core job's handed agent): its caller checked the prompt is empty."""
    herdr_path()
    first = shown(target)
    if first is None:
        return False, f'FAILED {target} {REFUSED[0]}'
    if first['focused']:
        return False, f'FAILED {target} {REFUSED[1]}'
    if first['status'] == 'blocked':
        return False, f'FAILED {target} {REFUSED[2]}'
    before = screen(target, 8) if keys and first['status'] in ('idle', 'done') else None
    if before and typed(plain(before)) and calm(target):  # an unread screen gets no key
        press(target, 'ctrl+c')
        time.sleep(1)
    try:
        answer = herdrapi_.herdr('agent', 'prompt', target, text, '--wait', '--until', 'working', '--until', 'blocked',
                                 '--timeout', '15000', timeout=CALL + 20)
        # Herdr saw a turn start, but it can be an earlier prompt's: Claude Code 2.1.332, slow to submit one, kept a prompt
        # typed meanwhile in its box (live, 25 Nov 2026). Its answer stands unless the box still shows the text itself; a
        # paste placeholder alone there may be the owner's, made since.
        if answer.get('type') == 'agent_prompted':
            read = screen(target, 30)
            if read is None or not holds(read, [text], lone=False):
                return True, f'SUBMITTED {target}'
            now = shown(target)
            if now is not None and now['focused']:
                return False, f'FAILED {target} focused: the owner came into that pane; its prompt still holds the text'
        code = 'agent_prompt_stalled' if answer.get('type') == 'agent_prompted' else ''
    except herdrapi_.HerdrError as error:
        code = error.code
    except ValueError:
        code = ''
    if code == 'agent_blocked':  # Herdr refused it before typing anything
        return False, f'FAILED {target} {REFUSED[2]}'
    if text in ('/exit', '/quit'):  # it ends the agent, which never shows working (a Codex quit read as FAILED, 2026-10-17)
        try:
            herdrapi_.herdr('agent', 'wait', target, '--until', 'unknown', '--timeout', '30000', timeout=CALL + 30)
        except herdrapi_.HerdrError as error:
            if error.code == 'agent_not_running':
                return True, f'SUBMITTED {target} (the agent exited)'
        except ValueError:
            pass
    return verify(target, text, first, keys, typed_in=code in ('agent_prompt_stalled', 'timeout'))


def verify(target, text, first, keys, typed_in):
    """Decide whether a prompt Herdr did not see start went in, from a few looks over about 22 s (PAUSES):
    - SUBMITTED once the prompt no longer shows the text typed and a turn started (working or blocked) or ended (seq
      moved), or once it has shown nothing typed for two looks in a row after SETTLE seconds, when Herdr typed the
      text (typed_in, from its answer) or a look saw it: a late start is not a failure, and nothing is typed twice;
    - while the prompt still shows the text at idle or done (Claude kept it, or its paste placeholder, and lost the
      Enter), Enter again, at most ENTERS times; never for a slash command;
    - still there after the last look: ctrl+c once to clear it, then FAILED with the prompt empty, so the next send can
      type. Any other text there is left as it is (FAILED).
    A look whose screen Herdr does not show tells nothing, and a blank look before SETTLE seconds proves nothing (a long
    paste is drawn late). Once the owner is in the pane a look presses nothing: a late start still counts, else FAILED.
    No key unless Herdr shows the agent idle or done with nobody in its pane just before it (calm)."""
    slash, enters, seen, gone, looked, held, other = text.startswith('/'), 0, False, False, False, False, False
    started = time.monotonic()
    for pause in PAUSES:
        time.sleep(pause)
        now = shown(target)
        if now is None:
            return False, f'FAILED {target} (it left its pane)'
        read = screen(target, 30)
        if now['focused']:  # a look with no key: a turn that started late still counts
            if read is not None and not holds(read, [text]) and (now['status'] in ('working', 'blocked') or moved(first, now)):
                return True, submitted(target, enters, 'it started late')
            return False, f'FAILED {target} focused: the owner came into that pane before it was confirmed; its prompt may still hold the text'
        if read is None:
            continue
        looked, held = True, holds(read, [text])
        other, seen = not held and bool(box(read)) and typed(plain(read)), seen or held  # plain text: an empty prompt's markers
        if not held and (now['status'] in ('working', 'blocked') or moved(first, now)):
            return True, submitted(target, enters, 'it started late')
        if held:
            gone = False
            if keys and not slash and enters < ENTERS and calm(target):
                press(target, 'enter')
                enters += 1
        elif other:  # someone else's text: never ours to send or clear
            gone = False
        elif (typed_in or seen) and time.monotonic() - started >= SETTLE:
            if gone:
                return True, submitted(target, enters, 'the text left its prompt')
            gone = True
    if not looked:
        return False, f'FAILED {target} (Herdr did not show its screen: read it with herdr agent read {target} before any resend)'
    if not held:
        if other:
            return False, f'FAILED {target} (status before: {first["status"]}, now: {now["status"]}; another text is in its prompt, left as it is)'
        if gone:  # the last look Herdr showed came after SETTLE seconds, with nothing typed
            return True, submitted(target, enters, 'the text left its prompt')
        why = 'it cannot tell whether the text went in' if typed_in or seen else 'the text never showed in its prompt'
        return False, f'FAILED {target} (status before: {first["status"]}, now: {now["status"]}; {why}: read it with herdr agent read {target} before any resend)'
    if not keys or slash:
        why = 'no key for a slash command' if slash else 'no keys here'
        return False, f'FAILED {target} (the text is still in its prompt, {why}: read it with herdr agent read {target} before any resend)'
    last, now = screen(target, 30), shown(target)
    if now is None or now['focused'] or now['status'] not in ('idle', 'done'):
        why = 'it left its pane' if now is None else 'the owner is in that pane' if now['focused'] else f'it is {now["status"]}'
        return False, f'FAILED {target} (the text is still in its prompt, {why}, so no key: read it with herdr agent read {target} before any resend)'
    if last is None or not holds(last, [text]) or not typed(plain(last)):  # never ctrl+c a prompt that may be empty
        return False, f'FAILED {target} (its prompt did not show the text clearly at the last look, so no key: read it with herdr agent read {target} before any resend)'
    press(target, 'ctrl+c')
    time.sleep(CLEARED)
    after = screen(target, 30)
    if after is None or holds(after, [text]):
        return False, f'FAILED {target} (the text is still in its prompt after {enters} Enter and a ctrl+c: read it with herdr agent read {target})'
    return False, f'FAILED {target} (the text stayed in its prompt through {enters} Enter; cleared it with ctrl+c, so it can be sent again)'


def moved(first, now):
    """True when Herdr's completion counter moved since the first look: a turn ended in between."""
    return isinstance(now['seq'], int) and now['seq'] != first['seq']


def submitted(target, enters, how):
    return f'SUBMITTED {target} (' + ('pressed Enter again: the first was dropped' if enters else how) + ')'


def main(argv):
    """herdr-send <agent-name-or-pane> <text>: one SUBMITTED line (exit 0) or FAILED line (exit 1)."""
    if len(argv) < 2:
        print('usage: herdr-send <agent-name-or-pane> <text>', file=sys.stderr)
        return 2
    ok, line = submit(argv[0], argv[1])
    print(line)
    return 0 if ok else 1
