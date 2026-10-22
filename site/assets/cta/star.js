/* Opt in with data-star-count="true". A plain link is the no-JS fallback. */
(() => {
  const nodes = [...document.querySelectorAll('[data-star-count="true"] .stp-count')];
  if (!nodes.length) return;
  const key = 'stampede:github-stars:v1', ttl = 3600000;
  const valid = n => Number.isSafeInteger(n) && n >= 0;
  const show = n => nodes.forEach(node => {
    node.textContent = new Intl.NumberFormat('en', {notation:'compact', maximumFractionDigits:1}).format(n);
    node.setAttribute('aria-label', `${n.toLocaleString('en')} stars`);
    node.hidden = false;
  });
  const hide = () => nodes.forEach(node => { node.hidden = true; node.textContent = ''; });
  hide();
  try {
    const cached = JSON.parse(localStorage.getItem(key));
    if (cached && valid(cached.count) && Number.isFinite(cached.at) && Date.now() >= cached.at && Date.now() - cached.at < ttl) {
      show(cached.count); return;
    }
  } catch { /* Storage is optional. */ }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 3500);
  fetch('https://api.github.com/repos/vib-z/stampede', {
    headers: {Accept:'application/vnd.github+json'}, credentials:'omit', signal:controller.signal
  }).then(response => {
    if (!response.ok) throw new Error('Count unavailable');
    return response.json();
  }).then(data => {
    if (data.full_name !== 'vib-z/stampede' || !valid(data.stargazers_count)) throw new Error('Invalid count');
    show(data.stargazers_count);
    try { localStorage.setItem(key, JSON.stringify({count:data.stargazers_count, at:Date.now()})); } catch { /* Link stays usable. */ }
  }).catch(hide).finally(() => clearTimeout(timer));
})();
