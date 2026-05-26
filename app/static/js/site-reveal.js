// Minimal animation: reveal elements on scroll.
// Defensive: .reveal starts at opacity:0, so content must NEVER stay hidden if
// the observer misfires. We reveal on intersection, and a safety timer reveals
// everything regardless after a short delay.
(function () {
  var els = Array.prototype.slice.call(document.querySelectorAll('.reveal'));
  if (!els.length) return;
  function show(e) { e.classList.add('in'); }
  if (!('IntersectionObserver' in window)) { els.forEach(show); return; }
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (en) { if (en.isIntersecting) { show(en.target); io.unobserve(en.target); } });
  }, { threshold: 0, rootMargin: '0px 0px -40px 0px' });
  els.forEach(function (e) { io.observe(e); });
  // Safety net: guarantees content appears even if the observer never fires.
  setTimeout(function () { els.forEach(show); }, 1600);
})();
