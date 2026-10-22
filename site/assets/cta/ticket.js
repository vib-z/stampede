(() => {
  const prompt = 'Install stampede from https://github.com/vib-z/stampede using its README. Clone it to ~/stampede (if that path exists, inspect it and preserve existing files). In that folder, run ./install.sh --dry-run, then ./install.sh. Ensure ~/.local/bin is on my PATH and check that stampede --version prints 0.1.0. Report any skipped links and missing prerequisites: Herdr, signed-in Claude Code, Python 3, git, jq and curl. Explain the optional tools, including Moshi for phone questions, and any remaining owner-run setup. Ask which project to trust before running herdr-trust. Stop before starting the first job.';
  const popover = document.querySelector('#install-prompt');
  const text = document.querySelector('#prompt-text');
  const status = popover.querySelector('.copy-status');
  const tickets = [...document.querySelectorAll('.stp-ticket')];
  let trigger = null, attempt = 0;
  text.value = prompt;
  // The href stays usable without this script; with JS it behaves as a button.
  tickets.forEach(ticket => {
    ticket.setAttribute('role', 'button');
    ticket.setAttribute('aria-label', 'Get started: copy the install prompt');
    ticket.setAttribute('aria-controls', 'install-prompt');
    ticket.setAttribute('aria-expanded', 'false');
    ticket.addEventListener('click', event => {
      event.preventDefault();
      trigger = ticket;
      copy();
    });
    ticket.addEventListener('keydown', event => {
      if (event.key === ' ') { event.preventDefault(); ticket.click(); }
    });
  });
  function show() {
    if (popover.showPopover) { if (!popover.matches(':popover-open')) popover.showPopover(); }
    else popover.classList.add('is-open');
    tickets.forEach(ticket => ticket.setAttribute('aria-expanded', String(ticket === trigger)));
  }
  function close() {
    attempt++;
    if (popover.hidePopover) popover.hidePopover();
    else popover.classList.remove('is-open');
    tickets.forEach(ticket => ticket.setAttribute('aria-expanded', 'false'));
    trigger?.focus({preventScroll:true});
  }
  function result(copied) {
    status.textContent = copied ? 'Copied. Paste it into Claude Code or Codex.' : 'Select and copy the prompt below, or try Copy prompt again.';
    trigger?.classList.toggle('is-copied', copied);
    if (trigger) trigger.querySelector('.ticket-stamp').textContent = copied ? 'COPIED' : 'COPY';
    if (!copied) { text.focus({preventScroll:true}); text.select(); }
  }
  function copy() {
    const token = ++attempt;
    // Invoke directly in the click handler to retain browser user activation.
    let write;
    try { write = navigator.clipboard.writeText(prompt); }
    catch { write = Promise.reject(); }
    show();
    status.textContent = 'Copying your install prompt…';
    Promise.resolve(write).then(() => { if (token === attempt) result(true); }, () => { if (token === attempt) result(false); });
  }
  popover.querySelector('.prompt-copy').addEventListener('click', copy);
  popover.querySelector('.prompt-close').addEventListener('click', close);
  popover.addEventListener('toggle', event => {
    if (event.newState === 'closed') {
      attempt++;
      tickets.forEach(ticket => ticket.setAttribute('aria-expanded', 'false'));
    }
  });
  addEventListener('keydown', event => {
    if (event.key === 'Escape' && (popover.matches(':popover-open') || popover.classList.contains('is-open'))) close();
  });
})();
