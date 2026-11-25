"""grokbot-herdr's herdr-send (stampede's send.py) against a fake herdr: when it may send ctrl+c or Enter, when it
refuses, and how it confirms a submit from the status and the screen (stdlib)."""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'skills/grokbot-herdr/scripts/herdr-send'
FAKE = Path(__file__).resolve().parent / 'fake_herdr.py'
sys.path.insert(0, str(ROOT / 'skills/herdr-fleet/scripts'))
from stampede import send as send_  # noqa: E402

# Logs every call; status and screen come from FAKE_STATUS and FAKE_SCREEN. With FAKE_DROP_ENTER set, the prompt
# loses its Enter as Claude does before it has drawn its screen: the screen turns to FAKE_SCREEN_AFTER and only an
# Enter key starts the agent, which empties its prompt again.
FAKE_HERDR = '''#!/bin/bash
echo "$*" >> "$FAKE_DIR/calls"
st="$FAKE_STATUS"; [ -f "$FAKE_DIR/entered" ] && st=working
case "$1 $2" in
  "agent get") [ -n "$st" ] || exit 1
    echo "{\\"result\\":{\\"agent\\":{\\"agent_status\\":\\"$st\\",\\"focused\\":${FAKE_FOCUSED:-false}}}}";;
  "agent read") if [ -f "$FAKE_DIR/prompted" ] && [ ! -f "$FAKE_DIR/entered" ]; then printf '%s\\n' "$FAKE_SCREEN_AFTER"
    else printf '%s\\n' "$FAKE_SCREEN"; fi;;
  "agent prompt") if [ -n "$FAKE_DROP_ENTER" ]; then touch "$FAKE_DIR/prompted"; echo '{"error":{"code":"timeout"}}'
    else echo '{"result":{"type":"agent_prompted"}}'; fi;;
  "agent send-keys") [ "$4" = enter ] && [ -f "$FAKE_DIR/prompted" ] && touch "$FAKE_DIR/entered";;
  "agent wait") [ -n "$FAKE_EXITS" ] && { echo '{"error":{"code":"agent_not_running"}}'; exit 1; }
    [ "$st" = working ] && echo '{"result":{"agent":{"agent_status":"working"}}}' || echo '{"error":{"code":"timeout"}}';;
esac
'''


class quick(contextlib.ExitStack):
    """send.py with its waits cut to nothing, for a test."""

    def __enter__(self):
        super().__enter__()
        self.enter_context(mock.patch.object(send_.time, 'sleep'))
        self.enter_context(mock.patch.object(send_, 'SETTLE', 0))
        return self


class HerdrSend(unittest.TestCase):
    """The promises it kept as a shell script: ctrl+c only on a prompt with leftover text, never a key for a focused,
    blocked or missing agent, Enter again only for its own text, never for a slash command."""

    def send(self, status, screen='', text='do it', after=None, exits=False, focused=False):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / 'bin').mkdir()
            herdr = d / 'bin/herdr'
            herdr.write_text(FAKE_HERDR)
            herdr.chmod(0o755)
            env = dict(PATH=f"{d / 'bin'}:{os.environ['PATH']}", FAKE_DIR=str(d), FAKE_STATUS=status, FAKE_SCREEN=screen,
                       FAKE_EXITS='1' if exits else '', FAKE_FOCUSED='true' if focused else 'false', FAKE_DROP_ENTER='',
                       FAKE_SCREEN_AFTER='')
            if after is not None:
                env.update(FAKE_DROP_ENTER='1', FAKE_SCREEN_AFTER=after)
            out = io.StringIO()
            with mock.patch.dict(os.environ, env), quick(), contextlib.redirect_stdout(out):
                os.environ.pop('HERDR', None)
                self.code = send_.main(['build-a', text])
            calls = (d / 'calls').read_text() if (d / 'calls').exists() else ''
        return out.getvalue().strip(), calls

    def test_empty_codex_prompt_gets_no_ctrl_c(self):
        out, calls = self.send('idle', '› Ask Codex to do anything\n\n  ? for shortcuts')
        self.assertEqual(out, 'SUBMITTED build-a')
        self.assertNotIn('ctrl+c', calls)

    def test_codex_167_footer_reads_as_empty_and_its_draft_as_typed(self):  # Codex 0.167.1, live 11 Nov 2026
        out, calls = self.send('idle', '› Improve documentation in @filename\n\n  GPT model · ~/code\n'  # a placeholder no
                                       '  ← for agents · ? for shortcuts            ⚠ 2 warnings · f2 to view')  # other marker knows
        self.assertEqual(out, 'SUBMITTED build-a')
        self.assertNotIn('ctrl+c', calls)
        out, calls = self.send('idle', '› my half-written draft\n\n  GPT model · ~/code\n            ⚠ 2 warnings · f2 to view')
        self.assertEqual(out, 'SUBMITTED build-a')
        self.assertLess(calls.index('agent send-keys build-a ctrl+c'), calls.index('agent prompt build-a'))

    def test_codex_170_narrow_footer_reads_as_empty_and_its_draft_as_typed(self):  # live, 24 columns, 20 Nov 2026
        fixtures = Path(__file__).resolve().parent / 'fixtures/codex-0.170'
        for name in ('empty-w24.txt', 'empty-w24-warnings.txt'):  # placeholder cut to 'Ask Codex to do anyth'
            out, calls = self.send('idle', (fixtures / name).read_text())
            self.assertEqual(out, 'SUBMITTED build-a', name)
            self.assertNotIn('ctrl+c', calls, name)
        out, calls = self.send('idle', (fixtures / 'draft-w24-warnings.txt').read_text())
        self.assertEqual(out, 'SUBMITTED build-a')
        self.assertLess(calls.index('agent send-keys build-a ctrl+c'), calls.index('agent prompt build-a'))
        for name in ('draft-w24-ends-in-footer.txt', 'draft-w24-tall-ends-in-footer.txt',  # review R2: a quoted footer
                     'draft-w24-scrolled-ends-in-footer.txt', 'draft-w24-first-line-blank.txt'):
            screen = '\n'.join((fixtures / name).read_text().splitlines()[-8:])  # herdr-send reads 8 lines
            out, calls = self.send('idle', screen)
            self.assertEqual(out, 'SUBMITTED build-a', name)
            self.assertLess(calls.index('agent send-keys build-a ctrl+c'), calls.index('agent prompt build-a'), name)
        out, calls = self.send('idle', '• ↑\n\n» Ask Codex to do anyth\n\n  GPT-6-Astra ultra · ~…\n  ← for agents')
        self.assertEqual(out, 'SUBMITTED build-a')    # review R3: an arrow in a reply above the prompt is no scroll arrow
        self.assertNotIn('ctrl+c', calls)
        quoted = '» line one             ↑\n  > quoted text\n  continuation\n  ← for agents'  # review R4
        out, calls = self.send('idle', quoted)
        self.assertLess(calls.index('agent send-keys build-a ctrl+c'), calls.index('agent prompt build-a'))

    def test_bare_claude_prompt_gets_no_ctrl_c(self):
        out, calls = self.send('done', '──────\n❯ \n──────')
        self.assertEqual(out, 'SUBMITTED build-a')
        self.assertNotIn('ctrl+c', calls)

    def test_claude_no_break_space_prompt_gets_no_ctrl_c(self):  # Claude Code 2.1.331 draws '❯' and a no-break space
        out, calls = self.send('idle', '──────\n❯\xa0\n──────')
        self.assertEqual(out, 'SUBMITTED build-a')
        self.assertNotIn('ctrl+c', calls)

    def test_leftover_input_is_cleared_first(self):
        out, calls = self.send('idle', '› leftover junk\n\n  GPT model · ~/code')
        self.assertEqual(out, 'SUBMITTED build-a')
        self.assertLess(calls.index('agent send-keys build-a ctrl+c'), calls.index('agent prompt build-a'))

    def test_blocked_or_missing_agent_gets_nothing(self):
        for status in ('blocked', ''):
            out, calls = self.send(status, 'Update available')
            self.assertTrue(out.startswith('FAILED build-a'), out)
            self.assertNotIn('send-keys', calls)
            self.assertNotIn('prompt', calls)

    def test_focused_pane_with_a_draft_gets_no_keys_and_no_prompt(self):
        out, calls = self.send('idle', '› my half-written draft\n\n  GPT model', focused=True)
        self.assertEqual((out, self.code), ('FAILED build-a focused: the owner is in that pane; retry later', 1))
        self.assertNotIn('send-keys', calls)
        self.assertNotIn('prompt', calls)

    # Claude draws its box as ❯ plus a no-break space.
    def test_dropped_enter_is_pressed_once(self):
        out, calls = self.send('idle', '──\n❯ \n──', after='──\n❯ do it\n──')
        self.assertEqual(out, 'SUBMITTED build-a (pressed Enter again: the first was dropped)')
        self.assertEqual(calls.count('agent send-keys build-a enter'), 1)
        self.assertNotIn('ctrl+c', calls)

    def test_other_text_in_the_box_gets_no_enter(self):
        out, calls = self.send('idle', '──\n❯ \n──', after='❯ do it\n──\n❯ someone else typing\n──')
        self.assertTrue(out.startswith('FAILED build-a'), out)
        self.assertIn('another text is in its prompt', out)
        self.assertNotIn('enter', calls)
        self.assertNotIn('ctrl+c', calls)

    def test_slash_command_gets_no_enter(self):
        out, calls = self.send('idle', '──\n❯ \n──', text='/exit', after='──\n❯ /exit\n──')
        self.assertTrue(out.startswith('FAILED build-a'), out)
        self.assertNotIn('enter', calls)
        self.assertNotIn('ctrl+c', calls)

    def test_quit_that_ends_the_agent_is_submitted(self):
        out, calls = self.send('idle', 'Ask Codex to do anything', text='/quit', after='', exits=True)
        self.assertEqual(out, 'SUBMITTED build-a (the agent exited)')
        self.assertNotIn('ctrl+c', calls)


EMPTY_CLAUDE = '  Done.\n──────────────────── lead-demo ─\n❯\xa0\n────────────────────────────────\n  ⏵⏵ auto mode on'
EMPTY_CODEX = '› Ask Codex to do anything\n\n  gpt-6.2-sol medium · ~/repo\n  ← for agents · ? for shortcuts'


def claude_box(shown):
    """Claude Code 2.1.332's screen with text in its prompt box, wrapped at 48 columns as in a 50-column pane."""
    rows = [shown[i:i + 46] for i in range(0, len(shown), 46)] or ['']
    return '\n'.join(['  Done.', '──────────────────── lead-demo ─', '❯\xa0' + rows[0]] + ['  ' + row for row in rows[1:]]
                     + ['────────────────────────────────', '  ⏵⏵ auto mode on'])


class Verify(unittest.TestCase):
    """After typing, herdr-send confirms the submit from Herdr's status and the screen (Claude Code 2.1.332, Herdr 0.9.5,
    live on 25 Nov 2026): Herdr answers agent_prompt_stalled when it sees no turn start in 5 s, which Claude can take."""

    TEXT = '[fleet-job inbox for lead-demo, not typed by the owner] inbox.log: TURN build-x done | REPORT reports/build-x.md'

    def run_send(self, kind='claude', status='done', screen=EMPTY_CLAUDE, keys=True, text=TEXT, settle=0, **shape):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: subprocess.run(['rm', '-rf', str(folder)]))
        state = {'panes': {'w1:p1': {'screen': screen, 'agent': {
            'name': 'lead-demo', 'agent': kind, 'agent_status': status, 'focused': False, 'terminal_id': 'term_w1:p1',
            'completion_seq': 7, 'agent_session': None, 'args': [], 'prompts': []}}}, **shape}
        (folder / 'state.json').write_text(json.dumps(state))
        with mock.patch.dict(os.environ, {'HERDR': str(FAKE), 'FAKE_HERDR': str(folder)}), quick(), \
                mock.patch.object(send_, 'SETTLE', settle):
            ok, line = send_.submit('lead-demo', text, keys=keys)
        self.calls = [json.loads(row) for row in (folder / 'calls').read_text().splitlines()]
        self.state = json.loads((folder / 'state.json').read_text())
        return ok, line

    def keys(self, key=None):
        pressed = [call[3] for call in self.calls if call[:2] == ['agent', 'send-keys']]
        return pressed if key is None else pressed.count(key)

    def prompts(self):
        return self.state['panes']['w1:p1']['agent']['prompts']

    def test_text_still_in_the_box_after_a_send_at_done_gets_enter_again(self):
        """Every FAILED of the stall said 'now: done': the old retry ran only at idle."""
        ok, line = self.run_send(prompt_error={'lead-demo': 'agent_prompt_stalled'}, on_prompt={'lead-demo': {
            'screen': claude_box('{text}')}}, on_key={'lead-demo': {'enter': {'agent': {'agent_status': 'working'},
                                                                            'screen': EMPTY_CLAUDE}}})
        self.assertEqual((ok, line), (True, 'SUBMITTED lead-demo (pressed Enter again: the first was dropped)'))
        self.assertEqual((self.keys('enter'), self.keys('ctrl+c')), (1, 0))
        self.assertEqual(self.prompts(), [self.TEXT])

    def test_a_paste_placeholder_in_the_box_is_our_text(self):
        """Claude draws a long prompt as '[Pasted text #1]', so the start of the text is not on the prompt line."""
        long = self.TEXT + ' | ' + ' | '.join(f'TURN worker-{i} finished its step' for i in range(40))
        for shown in ('[Pasted text #1]', '[Pasted text #2 +3 lines]', '[Pasted text #3]' + long[-60:]):
            with self.subTest(shown=shown):
                ok, line = self.run_send(text=long, prompt_error={'lead-demo': 'agent_prompt_stalled'},
                                         on_prompt={'lead-demo': {'screen': claude_box(shown)}},
                                         on_key={'lead-demo': {'enter': {'agent': {'agent_status': 'working'},
                                                                         'screen': EMPTY_CLAUDE}}})
                self.assertTrue(ok, line)
                self.assertEqual(self.keys(), ['enter'])

    def test_a_late_start_is_submitted_and_typed_once(self):
        """09:33 and 13:34 on 25 Nov 2026: FAILED, yet the transcript shows the line went in; the deliverer typed it again."""
        ok, line = self.run_send(prompt_error={'lead-demo': 'agent_prompt_stalled'},
                                 on_get={'lead-demo': [{}, {}, {'agent': {'agent_status': 'working'}}]})
        self.assertEqual((ok, line), (True, 'SUBMITTED lead-demo (it started late)'))
        self.assertEqual(self.keys(), [])
        self.assertEqual(self.prompts(), [self.TEXT])

    def test_a_turn_that_ran_between_looks_is_submitted(self):
        ok, line = self.run_send(prompt_error={'lead-demo': 'agent_prompt_stalled'},
                                 on_get={'lead-demo': [{}, {'agent': {'completion_seq': 9}}]})
        self.assertEqual((ok, line), (True, 'SUBMITTED lead-demo (it started late)'))
        self.assertEqual(self.keys(), [])

    def test_text_that_left_the_box_is_submitted_after_two_looks(self):
        ok, line = self.run_send(prompt_error={'lead-demo': 'agent_prompt_stalled'})
        self.assertEqual((ok, line), (True, 'SUBMITTED lead-demo (the text left its prompt)'))
        self.assertEqual(self.keys(), [])
        self.assertEqual(len([c for c in self.calls if c[:2] == ['agent', 'get']]), 3)  # before, and two looks

    def test_a_stuck_box_is_cleared_after_the_retries(self):
        ok, line = self.run_send(prompt_error={'lead-demo': 'agent_prompt_stalled'}, on_prompt={'lead-demo': {
            'screen': claude_box('{text}')}}, on_key={'lead-demo': {'ctrl+c': {'screen': EMPTY_CLAUDE}}})
        self.assertFalse(ok)
        self.assertIn('cleared it with ctrl+c, so it can be sent again', line)
        self.assertEqual(self.keys(), ['enter'] * send_.ENTERS + ['ctrl+c'])
        self.assertEqual(self.state['panes']['w1:p1']['screen'], EMPTY_CLAUDE)

    def test_herdr_seeing_an_earlier_turn_start_is_no_proof(self):
        """Live: a prompt typed while Claude ran a slow prompt hook stayed in its box, though Herdr saw working."""
        ok, line = self.run_send(on_prompt={'lead-demo': {'screen': claude_box('{text}')}},
                                 on_get={'lead-demo': [{}, {'agent': {'agent_status': 'done'}}]},
                                 on_key={'lead-demo': {'enter': {'agent': {'agent_status': 'working'}, 'screen': EMPTY_CLAUDE}}})
        self.assertEqual((ok, line), (True, 'SUBMITTED lead-demo (pressed Enter again: the first was dropped)'))
        enter = [c for c in self.calls if c[:2] == ['agent', 'send-keys']][0]
        self.assertEqual(self.calls[self.calls.index(enter) - 1][:2], ['agent', 'get'])  # idle and unfocused just before it
        self.assertEqual(self.keys(), ['enter'])                # pressed only once it was done, never while working

    def test_an_owners_draft_is_left_alone(self):
        ok, line = self.run_send(prompt_error={'lead-demo': 'agent_prompt_stalled'},
                                 on_prompt={'lead-demo': {'screen': claude_box('my own reply, half written')}})
        self.assertFalse(ok)
        self.assertIn('another text is in its prompt, left as it is', line)
        self.assertEqual(self.keys(), [])

    def test_an_empty_codex_prompt_never_gets_ctrl_c(self):
        ok, line = self.run_send(kind='codex', status='idle', screen=EMPTY_CODEX,
                                 prompt_error={'lead-demo': 'agent_prompt_stalled'})
        self.assertEqual((ok, line), (True, 'SUBMITTED lead-demo (the text left its prompt)'))
        self.assertEqual(self.keys(), [])
        ok, line = self.run_send(kind='codex', status='idle', screen=EMPTY_CODEX, prompt_error={'lead-demo': 'timeout'},
                                 on_get={'lead-demo': [{'screen': EMPTY_CODEX}] * 9})
        self.assertNotIn('ctrl+c', self.keys())

    def test_a_codex_composer_holding_the_text_gets_enter_then_ctrl_c(self):
        composer = '› {text}\n\n  gpt-6.2-sol medium · ~/repo\n                  ⚠ 2 warnings · f2 to view'
        ok, line = self.run_send(kind='codex', status='idle', screen=EMPTY_CODEX, prompt_error={'lead-demo': 'timeout'},
                                 on_prompt={'lead-demo': {'screen': composer}},
                                 on_key={'lead-demo': {'ctrl+c': {'screen': EMPTY_CODEX}}})
        self.assertFalse(ok)
        self.assertEqual(self.keys(), ['enter'] * send_.ENTERS + ['ctrl+c'])  # ctrl+c only on a prompt holding our text

    def test_no_key_for_a_working_agent_or_a_slash_command_or_keys_false(self):
        stuck = {'prompt_error': {'lead-demo': 'agent_prompt_stalled'}, 'on_prompt': {'lead-demo': {'screen': claude_box('{text}')}}}
        ok, line = self.run_send(**stuck, on_get={'lead-demo': [{}] + [{'agent': {'agent_status': 'working'}}] * 9})
        self.assertFalse(ok)
        self.assertIn('it is working, so no key', line)
        self.assertEqual(self.keys(), [])
        ok, line = self.run_send(text='/compact', **stuck)
        self.assertIn('no key for a slash command', line)
        self.assertEqual(self.keys(), [])
        ok, line = self.run_send(keys=False, **stuck)
        self.assertIn('no keys here', line)
        self.assertEqual(self.keys(), [])

    def test_the_owner_coming_in_stops_it(self):
        ok, line = self.run_send(prompt_error={'lead-demo': 'agent_prompt_stalled'},
                                 on_prompt={'lead-demo': {'screen': claude_box('{text}')}},
                                 on_get={'lead-demo': [{}, {'agent': {'focused': True}}]})
        self.assertEqual((ok, line), (False, 'FAILED lead-demo focused: the owner came into that pane before it was '
                                             'confirmed; its prompt may still hold the text'))
        self.assertEqual(self.keys(), [])
        ok, line = self.run_send(prompt_error={'lead-demo': 'agent_prompt_stalled'},          # recheck R7: a late start
                                 on_get={'lead-demo': [{}, {'agent': {'focused': True, 'agent_status': 'working'}}]})
        self.assertEqual((ok, line), (True, 'SUBMITTED lead-demo (it started late)'))
        self.assertEqual(self.keys(), [])

    def test_an_empty_prompt_s_placeholder_is_never_our_text(self):
        """Review R2: a text that starts like Codex's dim placeholder must not read as stuck there, or ctrl+c would quit Codex."""
        dim = '› \x1b[2mAsk Codex to do anything\x1b[0m\n\n  gpt-6.2-sol medium · ~/repo\n  ← for agents · ? for shortcuts'
        ok, line = self.run_send(kind='codex', status='idle', screen=dim, text='Ask Codex to do anything about the report',
                                 prompt_error={'lead-demo': 'agent_prompt_stalled'})
        self.assertEqual((ok, line), (True, 'SUBMITTED lead-demo (the text left its prompt)'))
        self.assertEqual(self.keys(), [])
        ok, line = self.run_send(kind='codex', status='idle', screen=dim.replace('\x1b[2m', '').replace('\x1b[0m', ''),
                                 text='Ask Codex to do anything about the report', prompt_error={'lead-demo': 'timeout'})
        self.assertNotIn('ctrl+c', self.keys())                # plain text: Enter at most, never ctrl+c on it

    def test_a_screen_herdr_does_not_show_tells_nothing(self):
        """Review R3: an unread screen after an earlier turn turned working must not confirm text still in the box."""
        ok, line = self.run_send(prompt_error={'lead-demo': 'agent_prompt_stalled'}, on_prompt={'lead-demo': {
            'screen': claude_box('{text}')}}, read_fail={'lead-demo': 2},
            on_get={'lead-demo': [{}] + [{'agent': {'agent_status': 'working'}}] * 20})
        self.assertFalse(ok, line)
        self.assertEqual(self.keys(), [])
        ok, line = self.run_send(prompt_error={'lead-demo': 'agent_prompt_stalled'}, read_fail={'lead-demo': 99})
        self.assertEqual((ok, line), (False, 'FAILED lead-demo (Herdr did not show its screen: read it with herdr agent read '
                                             'lead-demo before any resend)'))

    def test_a_paste_the_owner_made_after_herdr_saw_the_turn_is_theirs(self):
        """Review R4: Herdr took the prompt; the owner came in and pasted, and may have left. Its answer stands, and
        nothing is typed again: only the text itself in the box overrides it."""
        for focus in ([{}, {'agent': {'focused': True}}], [{}]):
            ok, line = self.run_send(on_prompt={'lead-demo': {'screen': claude_box('[Pasted text #2]')}}, on_get={'lead-demo': focus})
            self.assertEqual((ok, line), (True, 'SUBMITTED lead-demo'))
            self.assertEqual((self.keys(), self.prompts()), ([], [self.TEXT]))

    def test_our_text_still_in_the_box_is_never_confirmed_while_the_owner_looks(self):
        """Recheck R8: Herdr saw an earlier turn start, the text stayed in the box, and the owner came in to look."""
        ok, line = self.run_send(on_prompt={'lead-demo': {'screen': claude_box('{text}')}},
                                 on_get={'lead-demo': [{}, {'agent': {'focused': True}}]})
        self.assertEqual((ok, line), (False, 'FAILED lead-demo focused: the owner came into that pane; its prompt still holds the text'))
        self.assertEqual(self.keys(), [])

    def test_a_blank_look_before_the_settle_time_confirms_nothing(self):
        """Recheck R3: a long paste Claude draws late looks blank at first; that look alone is no proof."""
        ok, line = self.run_send(prompt_error={'lead-demo': 'agent_prompt_stalled'}, settle=10 ** 6)
        self.assertFalse(ok, line)
        self.assertIn('it cannot tell whether the text went in', line)
        self.assertEqual(self.keys(), [])
        ok, line = self.run_send(prompt_error={'lead-demo': 'agent_prompt_stalled'}, read_fail={'lead-demo': 1}, settle=10 ** 6)
        self.assertFalse(ok, line)
        self.assertEqual(self.keys(), [])

    def test_no_key_once_the_owner_comes_in_during_a_look(self):
        """Review R5: a screen read can take seconds; the agent is looked at again just before any key."""
        ok, line = self.run_send(prompt_error={'lead-demo': 'agent_prompt_stalled'}, on_prompt={'lead-demo': {
            'screen': claude_box('{text}')}}, on_get={'lead-demo': [{}, {}, {'agent': {'focused': True}}]})
        self.assertFalse(ok)
        self.assertIn('focused', line)
        self.assertEqual(self.keys(), [])

    def test_a_tall_text_whose_prompt_line_scrolled_off_is_still_ours(self):
        """Live, 25 Nov 2026: a 787-character draft in a 21-row pane shows no prompt line; it is not 'gone'."""
        long = self.TEXT + ' | ' + ' | '.join(f'TURN worker-{i} done {i}' for i in range(25))
        ok, line = self.run_send(text=long, prompt_error={'lead-demo': 'agent_prompt_stalled'}, on_prompt={'lead-demo': {
            'screen': '\n'.join(claude_box(long).split('\n')[6:])}}, on_key={'lead-demo': {'enter': {
                'agent': {'agent_status': 'working'}, 'screen': EMPTY_CLAUDE}}})
        self.assertEqual((ok, line), (True, 'SUBMITTED lead-demo (pressed Enter again: the first was dropped)'))
        self.assertEqual(self.keys(), ['enter'])

    def test_a_refused_prompt_is_failed_with_nothing_pressed(self):
        ok, line = self.run_send(prompt_error={'lead-demo': 'agent_blocked'})
        self.assertEqual((ok, line), (False, 'FAILED lead-demo (blocked at a dialog; read the screen)'))
        self.assertEqual(self.keys(), [])


class Box(unittest.TestCase):
    def test_what_the_box_holds(self):
        text = '[fleet-job inbox for lead-demo, not typed by the owner] inbox.log: TURN build-x finished its step'
        for screen, want in ((claude_box(text), True), (claude_box(text[:70]), True),              # drawn in part
                             (claude_box('[Pasted text #1]'), True), (claude_box('[Pasted text #1 +2 lines]'), True),
                             (claude_box('[Pasted text #4]x finished its step'), True),          # a paste, then typing
                             (claude_box(text + ' and a word of mine'), False), (claude_box('ok'), False),
                             (EMPTY_CLAUDE, False), ('› ' + text + '\n\n  gpt model', True), ('', False)):
            with self.subTest(screen=screen):
                self.assertEqual(send_.holds(screen, [text]), want)
        self.assertFalse(send_.holds(claude_box('[Pasted text #1]'), [text], lone=False))
        tall = claude_box(text * 3).split('\n')[5:]   # live, a 787-character draft in a 21-row pane: no prompt line shows
        self.assertEqual((send_.shape('\n'.join(tall))[1], send_.holds('\n'.join(tall), [text * 3])), (True, True))
        self.assertFalse(send_.holds('\n'.join(tall), [text]))                         # a run of another text is not it
        owner = claude_box('my own instructions first, then a copy: ' + text * 3).split('\n')[5:]   # review R11
        self.assertTrue(send_.holds('\n'.join(owner), [text * 3]))                  # right after typing it, as herdr-send asks
        self.assertFalse(send_.holds('\n'.join(owner), [text * 3], clipped=False))  # later, as the deliverer asks: maybe theirs
        codex = '  output above\n' + '─' * 40 + '\n› ' + text + '\n\n  gpt model'   # a rule in Codex's history is no box border
        self.assertEqual(send_.shape(codex), (text, False))
        dim = '❯\xa0\x1b[2m' + text[:40] + '\x1b[0m\n────'           # Claude's dim hint is no typed text
        self.assertEqual((send_.box(dim), send_.holds(dim, [text])), ('', False))
        self.assertTrue(send_.holds(dim.replace('\x1b[2m', ''), [text]))
        self.assertFalse(send_.holds(claude_box('[Pasted text #1]'), []))


class Shim(unittest.TestCase):
    """The herdr-send script runs send.py from the herdr-fleet skill beside it, through its link too."""

    def test_the_script_runs_send(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / 'bin').mkdir()
            (d / 'bin/herdr').write_text(FAKE_HERDR)
            (d / 'bin/herdr').chmod(0o755)
            (d / 'bin/herdr-send').symlink_to(SCRIPT)
            env = dict(os.environ, PATH=f"{d / 'bin'}:{os.environ['PATH']}", FAKE_DIR=str(d), FAKE_STATUS='idle',
                       FAKE_SCREEN='──\n❯\xa0\n──')
            env.pop('HERDR', None)
            sent = subprocess.run([str(d / 'bin/herdr-send'), 'build-a', 'do it'], env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual((sent.returncode, sent.stdout), (0, 'SUBMITTED build-a\n'))
            usage = subprocess.run([str(d / 'bin/herdr-send'), 'build-a'], env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(usage.returncode, 2)
            self.assertIn('usage: herdr-send', usage.stderr)


if __name__ == '__main__':
    unittest.main()
