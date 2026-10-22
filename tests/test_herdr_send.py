"""grokbot-herdr's herdr-send against a fake herdr: when it may send ctrl+c, and when it refuses (stdlib)."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'skills/grokbot-herdr/scripts/herdr-send'

# Logs every call; status and screen come from FAKE_STATUS and FAKE_SCREEN. With FAKE_DROP_ENTER set, the prompt
# loses its Enter as Claude does before it has drawn its screen: the screen turns to FAKE_SCREEN_AFTER and only an
# Enter key starts the agent.
FAKE_HERDR = '''#!/bin/bash
echo "$*" >> "$FAKE_DIR/calls"
st="$FAKE_STATUS"; [ -f "$FAKE_DIR/entered" ] && st=working
case "$1 $2" in
  "agent get") [ -n "$st" ] || exit 1
    echo "{\\"result\\":{\\"agent\\":{\\"agent_status\\":\\"$st\\",\\"focused\\":${FAKE_FOCUSED:-false}}}}";;
  "agent read") if [ -f "$FAKE_DIR/prompted" ]; then printf '%s\\n' "$FAKE_SCREEN_AFTER"; else printf '%s\\n' "$FAKE_SCREEN"; fi;;
  "agent prompt") if [ -n "$FAKE_DROP_ENTER" ]; then touch "$FAKE_DIR/prompted"; echo '{"error":{"code":"timeout"}}'
    else echo '{"result":{"type":"agent_prompted"}}'; fi;;
  "agent send-keys") [ "$4" = enter ] && [ -f "$FAKE_DIR/prompted" ] && touch "$FAKE_DIR/entered";;
  "agent wait") [ -n "$FAKE_EXITS" ] && { echo '{"error":{"code":"agent_not_running"}}'; exit 1; }
    [ "$st" = working ] && echo '{"result":{"agent":{"agent_status":"working"}}}' || echo '{"error":{"code":"timeout"}}';;
esac
'''


class HerdrSend(unittest.TestCase):
    def send(self, status, screen='', text='do it', after=None, exits=False, focused=False):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / 'bin').mkdir()
            herdr = d / 'bin/herdr'
            herdr.write_text(FAKE_HERDR)
            herdr.chmod(0o755)
            env = dict(os.environ, PATH=f"{d / 'bin'}:{os.environ['PATH']}", FAKE_DIR=str(d),
                       FAKE_STATUS=status, FAKE_SCREEN=screen, FAKE_EXITS='1' if exits else '',
                       FAKE_FOCUSED='true' if focused else 'false')
            if after is not None:
                env.update(FAKE_DROP_ENTER='1', FAKE_SCREEN_AFTER=after)
            r = subprocess.run(['bash', str(SCRIPT), 'build-a', text], env=env,
                               capture_output=True, text=True, timeout=30)
            calls = (d / 'calls').read_text() if (d / 'calls').exists() else ''
        self.code = r.returncode
        return r.stdout.strip(), calls

    def test_empty_codex_prompt_gets_no_ctrl_c(self):
        out, calls = self.send('idle', '› Ask Codex to do anything\n\n  ? for shortcuts')
        self.assertEqual(out, 'SUBMITTED build-a')
        self.assertNotIn('ctrl+c', calls)

    def test_bare_claude_prompt_gets_no_ctrl_c(self):
        out, calls = self.send('done', '──────\n❯ \n──────')
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
        out, calls = self.send('idle', '──\n❯ \n──', after='──\n❯\u00a0do it\n──')
        self.assertTrue(out.startswith('SUBMITTED build-a (pressed Enter again'), out)
        self.assertEqual(calls.count('agent send-keys build-a enter'), 1)
        self.assertNotIn('ctrl+c', calls)

    def test_other_text_in_the_box_gets_no_enter(self):
        out, calls = self.send('idle', '──\n❯ \n──', after='❯\u00a0do it\n──\n❯\u00a0someone else typing\n──')
        self.assertTrue(out.startswith('FAILED build-a'), out)
        self.assertNotIn('enter', calls)

    def test_slash_command_gets_no_enter(self):
        out, calls = self.send('idle', '──\n❯ \n──', text='/exit', after='──\n❯\u00a0/exit\n──')
        self.assertTrue(out.startswith('FAILED build-a'), out)
        self.assertNotIn('enter', calls)

    def test_quit_that_ends_the_agent_is_submitted(self):
        out, calls = self.send('idle', 'Ask Codex to do anything', text='/quit', after='', exits=True)
        self.assertEqual(out, 'SUBMITTED build-a (the agent exited)')
        self.assertNotIn('ctrl+c', calls)


if __name__ == '__main__':
    unittest.main()
