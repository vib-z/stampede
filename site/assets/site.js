/* Theme before first paint, then the header, the theme toggle and the Get started copy. Storage is optional. */
(() => {
  const root = document.documentElement, system = matchMedia('(prefers-color-scheme: dark)');
  let choice = 'system';
  try { const saved = localStorage.getItem('stampede:theme'); if (saved === 'light' || saved === 'dark') choice = saved; } catch { /* Private browsing can refuse storage. */ }
  if (choice === 'system' && (root.dataset.theme === 'light' || root.dataset.theme === 'dark')) choice = root.dataset.theme; // A host page may set the theme on the html element.
  const apply = () => {
    const theme = choice === 'system' ? (system.matches ? 'dark' : 'light') : choice;
    if (root.dataset.theme !== theme) root.dataset.theme = theme;
    if (choice !== 'system') document.querySelectorAll('meta[name="theme-color"]').forEach(m => { m.content = theme === 'dark' ? '#0a0a0a' : '#ffffff'; });
  };
  apply();
  system.addEventListener('change', () => { if (choice === 'system') apply(); });

  addEventListener('DOMContentLoaded', () => {
    const toggle = document.querySelector('.theme-toggle');
    const label = () => toggle.setAttribute('aria-label', root.dataset.theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme');
    toggle.hidden = false;
    label();
    toggle.addEventListener('click', () => {
      choice = root.dataset.theme === 'dark' ? 'light' : 'dark';
      try { localStorage.setItem('stampede:theme', choice); } catch { /* Optional. */ }
      apply();
      label();
    });

    // The Open gate run: once on load, again on hover or tap, and when Get started copies. Still under reduced motion.
    const reduce = matchMedia('(prefers-reduced-motion: reduce)');
    const replay = svg => {
      if (reduce.matches || performance.now() - (svg.ranAt || -9999) < 2600) return;
      svg.ranAt = performance.now();
      svg.classList.remove('is-running'); svg.getBoundingClientRect(); svg.classList.add('is-running');
    };
    const heroMark = document.querySelector('.hero .stp-logo');
    heroMark.ranAt = 0;
    document.querySelectorAll('.stp-logo').forEach(svg => svg.addEventListener('pointerenter', () => replay(svg)));
    heroMark.addEventListener('click', () => replay(heroMark));

    const header = document.querySelector('.site-header');
    let last = scrollY;
    const onScroll = () => {
      const y = scrollY;
      header.toggleAttribute('data-scrolled', y > 4);
      if (y > 96 && y > last + 2) header.toggleAttribute('data-hidden', true);
      else if (y < last - 2 || y <= 96) header.toggleAttribute('data-hidden', false);
      last = y;
    };
    addEventListener('scroll', onScroll, {passive: true});
    onScroll();

    const prompt = 'Install stampede from https://github.com/vib-z/stampede using its README. Clone it to ~/stampede (if that path exists, inspect it and preserve existing files). In that folder, run ./install.sh --dry-run, then ./install.sh. Ensure ~/.local/bin is on my PATH and check that stampede --version prints 0.1.6. Report any skipped links and missing prerequisites: Herdr, signed-in Claude Code, Python 3, git, jq and curl. Explain the optional tools, including Moshi for phone questions, and any remaining owner-run setup. Ask which project to trust before running herdr-trust. Stop before starting the first job.';
    const go = document.querySelector('.go'), status = document.querySelector('.go-status');
    const panel = document.querySelector('#install-prompt'), text = panel.querySelector('textarea');
    text.value = prompt;
    // The href stays usable without this script; with it, the link behaves as a button.
    go.setAttribute('role', 'button');
    go.setAttribute('aria-label', 'Get started: copy the install prompt');
    let timer = 0;
    const copied = () => {
      go.classList.add('is-copied');
      replay(heroMark);
      status.textContent = 'Copied. Paste it into Claude Code, Codex or Cursor.';
      clearTimeout(timer);
      timer = setTimeout(() => { go.classList.remove('is-copied'); status.textContent = ''; }, 5000);
    };
    const open = () => {
      if (panel.showPopover) { if (!panel.matches(':popover-open')) panel.showPopover(); }
      else panel.classList.add('is-open');
      text.focus({preventScroll: true});
      text.select();
    };
    const close = () => {
      if (panel.hidePopover) panel.hidePopover(); else panel.classList.remove('is-open');
      go.focus({preventScroll: true});
    };
    const copy = done => {
      // Call the clipboard directly in the click handler to keep the browser's user activation.
      let write;
      try { write = navigator.clipboard.writeText(prompt); } catch { write = Promise.reject(); }
      Promise.resolve(write).then(() => done(true), () => done(false));
    };
    go.addEventListener('click', event => { event.preventDefault(); copy(ok => ok ? copied() : open()); });
    go.addEventListener('keydown', event => { if (event.key === ' ') { event.preventDefault(); go.click(); } });
    panel.querySelector('.prompt-copy').addEventListener('click', () => copy(ok => { if (ok) { close(); copied(); } else { text.focus(); text.select(); } }));
    panel.querySelector('.prompt-close').addEventListener('click', close);
    addEventListener('keydown', event => { if (event.key === 'Escape' && panel.classList.contains('is-open')) close(); });
  });
})();
