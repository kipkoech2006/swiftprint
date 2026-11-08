/* Shared behaviour: dark mode, mobile menu, closable messages, confirm dialogs, double-click guard. */
(function () {
  var root = document.documentElement;
  root.classList.add('js');

  function applyTheme(theme) {
    root.dataset.theme = theme;
    document.querySelectorAll('.theme-toggle').forEach(function (b) {
      b.textContent = theme === 'dark' ? 'Light mode' : 'Dark mode';
      b.setAttribute('aria-pressed', String(theme === 'dark'));
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    applyTheme(root.dataset.theme || 'light');

    document.querySelectorAll('.theme-toggle').forEach(function (b) {
      b.addEventListener('click', function () {
        var next = root.dataset.theme === 'dark' ? 'light' : 'dark';
        applyTheme(next);
        try { localStorage.setItem('swiftprint-theme', next); } catch (e) {}
      });
    });

    var toggle = document.querySelector('.nav-toggle');
    var nav = document.getElementById('site-nav');
    if (toggle && nav) {
      toggle.addEventListener('click', function () {
        var open = nav.classList.toggle('open');
        toggle.setAttribute('aria-expanded', String(open));
      });
    }

    document.querySelectorAll('.flash button').forEach(function (b) {
      b.addEventListener('click', function () { b.closest('.flash').remove(); });
    });
  });

  // One handler for every form: confirm destructive actions, then block double submits.
  document.addEventListener('submit', function (e) {
    var form = e.target;
    var message = form.getAttribute && form.getAttribute('data-confirm');
    if (message && !window.confirm(message)) { e.preventDefault(); return; }
    if (e.defaultPrevented || !form.hasAttribute('data-busy')) return;
    var btn = form.querySelector('button[type=submit],button:not([type])');
    if (btn) {
      setTimeout(function () { btn.disabled = true; btn.textContent = form.getAttribute('data-busy') || 'Please wait…'; }, 0);
    }
  });
})();
