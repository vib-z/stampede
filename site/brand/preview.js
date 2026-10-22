document.querySelectorAll('[data-replay]').forEach(button => {
  button.addEventListener('click', () => {
    const logo = button.closest('section').querySelector('.stp-logo');
    logo.classList.remove('is-running');
    logo.getBoundingClientRect();
    logo.classList.add('is-running');
  });
});
