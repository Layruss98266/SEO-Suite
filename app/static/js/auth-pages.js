// Auth (login + signup) page interactions.
// Loaded from external file because CSP is `script-src 'self'` — no inline scripts.

(function () {
  function togglePw(id) {
    var i = document.getElementById(id);
    if (!i) return;
    var open = i.type === 'password';
    i.type = open ? 'text' : 'password';
    var eye = document.getElementById(id + '-eye') || document.getElementById('pw-eye');
    if (eye) eye.style.color = open ? '#6366f1' : '';
  }

  function onSub(submitText) {
    var b = document.getElementById('sub-btn');
    if (!b) return;
    b.classList.add('loading');
    b.innerHTML =
      '<svg viewBox="0 0 24 24" style="animation:spin .7s linear infinite">' +
      '<line x1="12" y1="2" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="22"/>' +
      '<line x1="4.93" y1="4.93" x2="7.76" y2="7.76"/><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"/>' +
      '<line x1="2" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="22" y2="12"/>' +
      '<line x1="4.93" y1="19.07" x2="7.76" y2="16.24"/><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"/>' +
      '</svg> ' + submitText;
  }

  function init() {
    // Wire any [data-pw-toggle="<id>"] button to flip that field's type.
    document.querySelectorAll('[data-pw-toggle]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        togglePw(btn.getAttribute('data-pw-toggle'));
      });
    });

    // Wire <form data-loading-text="..."> to show a spinner on submit.
    document.querySelectorAll('form[data-loading-text]').forEach(function (f) {
      f.addEventListener('submit', function () {
        onSub(f.getAttribute('data-loading-text'));
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
