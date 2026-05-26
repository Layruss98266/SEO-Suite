async function submitContact(e) {
  e.preventDefault();
  var msg = document.getElementById('contact-msg');
  var btn = document.getElementById('c-submit');
  msg.className = 'form-msg';
  var payload = {
    name:    document.getElementById('c-name').value.trim(),
    email:   document.getElementById('c-email').value.trim(),
    message: document.getElementById('c-message').value.trim(),
  };
  if (!payload.name || !payload.email || !payload.message) {
    msg.className = 'form-msg err'; msg.textContent = 'Please fill in all fields.'; return false;
  }
  btn.disabled = true; var orig = btn.textContent; btn.textContent = 'Sending…';
  try {
    var r = await fetch('/contact', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    var d = await r.json();
    if (r.ok && d.ok) {
      msg.className = 'form-msg ok';
      msg.textContent = d.message || 'Thanks, your message has been received.';
      document.getElementById('contact-form').reset();
    } else {
      msg.className = 'form-msg err'; msg.textContent = (d && d.error) || 'Something went wrong. Please try again.';
    }
  } catch (err) {
    msg.className = 'form-msg err'; msg.textContent = 'Network error. Please try again.';
  } finally {
    btn.disabled = false; btn.textContent = orig;
  }
  return false;
}
