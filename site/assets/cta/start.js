(() => {
  const prompt = 'Install stampede from https://github.com/vib-z/stampede using its README. Clone it to ~/stampede (if that path exists, inspect it and preserve existing files). In that folder, run ./install.sh --dry-run, then ./install.sh. Ensure ~/.local/bin is on my PATH and check that stampede --version prints 0.1.0. Report any skipped links and missing prerequisites: Herdr, signed-in Claude Code, Python 3, git, jq and curl. Explain the optional tools, including Moshi for phone questions, and any remaining owner-run setup. Ask which project to trust before running herdr-trust. Stop before starting the first job.';
  const popover = document.querySelector('#install-prompt');
  const text = document.querySelector('#prompt-text');
  const status = popover.querySelector('.copy-status');
  const buttons = [...document.querySelectorAll('.stp-start')];
  const timers = new Map();
  let opener = null, currentButton = null, attempt = 0;
  const isOpen = () => popover.showPopover ? popover.matches(':popover-open') : popover.classList.contains('is-open');
  const label = 'Get started: copy the install prompt';
  text.value = prompt;
  buttons.forEach(button => {
    const group = button.closest('.stp-actions');
    group.querySelector('.start-help').hidden = false;
    button.setAttribute('role', 'button');
    button.setAttribute('aria-label', label);
    button.setAttribute('aria-controls', 'install-prompt');
    button.setAttribute('aria-expanded', 'false');
    button.addEventListener('click', event => {
      event.preventDefault();
      currentButton = button;
      opener = button;
      copy(button);
    });
    button.addEventListener('keydown', event => {
      if (event.key === ' ') { event.preventDefault(); button.click(); }
    });
    group.querySelector('.see-prompt').addEventListener('click', event => {
      currentButton = button;
      opener = event.currentTarget;
      show('Copy this prompt, then paste it into your agent.');
    });
  });
  function reset(button) {
    button.classList.remove('is-copied');
    button.setAttribute('aria-label', label);
  }
  function show(message) {
    status.textContent = message;
    if (popover.showPopover) { if (!isOpen()) popover.showPopover(); }
    else popover.classList.add('is-open');
    document.querySelectorAll('[aria-controls="install-prompt"]').forEach(control => control.setAttribute('aria-expanded', String(control === opener)));
    text.focus({preventScroll:true});
    text.select();
  }
  function close() {
    attempt++;
    if (popover.hidePopover) popover.hidePopover();
    else popover.classList.remove('is-open');
    document.querySelectorAll('[aria-controls="install-prompt"]').forEach(control => control.setAttribute('aria-expanded', 'false'));
    opener?.focus({preventScroll:true});
  }
  function copy(button) {
    const token = ++attempt;
    const feedback = button.closest('.stp-actions').querySelector('.start-status');
    let write;
    // Preserve user activation: call the Clipboard API synchronously on click.
    try { write = navigator.clipboard.writeText(prompt); }
    catch { write = Promise.reject(); }
    feedback.textContent = 'Copying…';
    button.setAttribute('aria-busy', 'true');
    Promise.resolve(write).then(() => {
      if (token !== attempt) return;
      clearTimeout(timers.get(button));
      button.classList.add('is-copied');
      button.setAttribute('aria-label', 'Copied. Paste it into Claude Code or Codex.');
      feedback.textContent = 'Paste it into Claude Code or Codex.';
      if (isOpen()) status.textContent = 'Copied. Paste it into Claude Code or Codex.';
      timers.set(button, setTimeout(() => reset(button), 2000));
    }, () => {
      if (token !== attempt) return;
      clearTimeout(timers.get(button));
      reset(button);
      feedback.textContent = '';
      show('Select and copy the prompt below, or try Copy prompt again.');
    }).finally(() => button.removeAttribute('aria-busy'));
  }
  popover.querySelector('.prompt-copy').addEventListener('click', () => { if (currentButton) copy(currentButton); });
  popover.querySelector('.prompt-close').addEventListener('click', close);
  popover.addEventListener('toggle', event => {
    if (event.newState === 'closed') document.querySelectorAll('[aria-controls="install-prompt"]').forEach(control => control.setAttribute('aria-expanded', 'false'));
  });
  addEventListener('keydown', event => { if (event.key === 'Escape' && isOpen()) close(); });
})();
