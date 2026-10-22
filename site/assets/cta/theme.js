/* Resolve before first paint; storage is optional and system is the default. */
(() => {
  const root = document.documentElement;
  const system = matchMedia('(prefers-color-scheme: dark)');
  let choice = 'system';
  try {
    const saved = localStorage.getItem('stampede:theme');
    if (['light', 'dark', 'system'].includes(saved)) choice = saved;
  } catch { /* Private browsing can refuse storage. */ }
  const apply = () => {
    const theme = choice === 'system' ? (system.matches ? 'dark' : 'light') : choice;
    if (root.dataset.theme !== theme) root.dataset.theme = theme;
    document.querySelectorAll('[data-theme-choice]').forEach(button => {
      button.setAttribute('aria-pressed', String(button.dataset.themeChoice === choice));
    });
  };
  apply();
  system.addEventListener('change', () => { if (choice === 'system') apply(); });
  addEventListener('DOMContentLoaded', () => {
    const control = document.querySelector('.theme-switch');
    control.hidden = false;
    control.addEventListener('click', event => {
      const button = event.target.closest('[data-theme-choice]');
      if (!button) return;
      choice = button.dataset.themeChoice;
      try { localStorage.setItem('stampede:theme', choice); } catch { /* Optional. */ }
      apply();
    });
    apply();
  });
})();
