const root = document.documentElement;
const themeButtons = [...document.querySelectorAll('[data-theme-pick]')];
function reflectTheme() {
  const theme = root.getAttribute('data-theme') || 'system';
  themeButtons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.themePick === theme)));
}
themeButtons.forEach(button => button.addEventListener('click', () => {
  if (button.dataset.themePick === 'system') root.removeAttribute('data-theme');
  else root.setAttribute('data-theme', button.dataset.themePick);
  reflectTheme();
}));
reflectTheme();
document.querySelectorAll('[data-copy]').forEach(button => button.addEventListener('click', async () => {
  const text = button.dataset.copy;
  let copied = false;
  try { await navigator.clipboard.writeText(text); copied = true; } catch {
    const field = document.createElement('textarea');
    field.value = text; field.style.cssText = 'position:fixed;opacity:0';
    document.body.append(field); field.select();
    try { copied = document.execCommand('copy'); } catch { /* Selection remains available in the specimen. */ }
    field.remove(); button.focus();
  }
  document.getElementById('copy-status').textContent = copied ? `Copied ${text}` : 'Copy was unavailable. Select the value to copy it.';
}));
