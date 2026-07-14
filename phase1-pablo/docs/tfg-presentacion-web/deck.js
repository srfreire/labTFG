/* Deck runtime: scaling, navigation, fragment steps, count-ups. */
(() => {
  const stage = document.getElementById('stage');
  const slides = Array.from(document.querySelectorAll('.slide'));
  const progress = document.getElementById('progress');
  const hud = document.getElementById('hud');
  const sectionLabel = document.getElementById('section-label');

  let current = 0;
  let step = 0;

  /* ── Scale fixed 1280×720 canvas to viewport ── */
  function rescale() {
    const s = Math.min(window.innerWidth / 1280, window.innerHeight / 720);
    stage.style.transform = `scale(${s})`;
  }
  window.addEventListener('resize', rescale);
  rescale();

  /* ── Steps ── */
  function maxStep(slide) {
    let m = parseInt(slide.dataset.steps || '0', 10);
    slide.querySelectorAll('[data-frag], [data-run], [data-show-at]').forEach(el => {
      for (const a of ['frag', 'run', 'done', 'showAt', 'hideAt']) {
        if (el.dataset[a] !== undefined) m = Math.max(m, parseInt(el.dataset[a], 10));
      }
    });
    return m;
  }

  function applyStep(slide, k) {
    // cumulative step classes s1..sk for CSS orchestration
    for (let i = 1; i <= maxStep(slide); i++) {
      slide.classList.toggle('s' + i, i <= k);
    }
    slide.querySelectorAll('[data-frag]').forEach(el => {
      const n = parseInt(el.dataset.frag, 10);
      const on = n <= k;
      const was = el.classList.contains('on');
      el.classList.toggle('on', on);
      if (on && !was && el.classList.contains('count')) runCount(el);
    });
    // status hooks: running in [run, done), done from done onwards
    slide.querySelectorAll('[data-run]').forEach(el => {
      const r = parseInt(el.dataset.run, 10);
      const d = el.dataset.done !== undefined ? parseInt(el.dataset.done, 10) : Infinity;
      el.classList.toggle('running', k >= r && k < d);
      el.classList.toggle('done', k >= d);
    });
    // visibility window: visible in [showAt, hideAt)
    slide.querySelectorAll('[data-show-at]').forEach(el => {
      const a = parseInt(el.dataset.showAt, 10);
      const b = el.dataset.hideAt !== undefined ? parseInt(el.dataset.hideAt, 10) : Infinity;
      el.classList.toggle('vis', k >= a && k < b);
    });
  }

  function resetSlide(slide) {
    slide.className = slide.className.replace(/\bs\d+\b/g, '').replace(/\s+/g, ' ').trim();
    slide.querySelectorAll('[data-frag]').forEach(el => el.classList.remove('on'));
    slide.querySelectorAll('[data-run]').forEach(el => el.classList.remove('running', 'done'));
    slide.querySelectorAll('[data-show-at]').forEach(el => el.classList.remove('vis'));
  }

  /* ── Count-up numbers ── */
  function runCount(el) {
    const to = parseFloat(el.dataset.to);
    const dec = parseInt(el.dataset.dec || '0', 10);
    const dur = 900;
    const t0 = performance.now();
    function tick(t) {
      const p = Math.min(1, (t - t0) / dur);
      const eased = 1 - Math.pow(1 - p, 3);
      el.textContent = (to * eased).toFixed(dec);
      if (p < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  /* ── Navigation ── */
  function show(i, k = 0, pushHash = true) {
    i = Math.max(0, Math.min(slides.length - 1, i));
    const prev = slides[current];
    const next = slides[i];

    if (next !== prev || !next.classList.contains('active')) {
      prev.classList.remove('active');
      prev.classList.add('leaving');
      setTimeout(() => { prev.classList.remove('leaving'); resetSlide(prev); }, 350);
      next.classList.add('active');
    }

    current = i;
    step = Math.max(0, Math.min(maxStep(next), k));
    applyStep(next, step);

    progress.style.width = (slides.length > 1 ? (i / (slides.length - 1)) * 100 : 100) + '%';
    hud.textContent = String(i + 1).padStart(2, '0') + ' / ' + slides.length;
    sectionLabel.textContent = next.dataset.section || '';
    if (pushHash) history.replaceState(null, '', '#' + (i + 1));
  }

  function nextStep() {
    const slide = slides[current];
    if (step < maxStep(slide)) {
      step++;
      applyStep(slide, step);
    } else if (current < slides.length - 1) {
      show(current + 1, 0);
    }
  }

  function prevStep() {
    const slide = slides[current];
    if (step > 0) {
      step--;
      applyStep(slide, step);
    } else if (current > 0) {
      // land on the previous slide fully revealed
      const p = slides[current - 1];
      show(current - 1, maxStep(p));
    }
  }

  /* ── Input ── */
  document.addEventListener('keydown', e => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    switch (e.key) {
      case 'ArrowRight': case 'ArrowDown': case ' ': case 'PageDown':
        e.preventDefault(); nextStep(); break;
      case 'ArrowLeft': case 'ArrowUp': case 'PageUp':
        e.preventDefault(); prevStep(); break;
      case 'Home': e.preventDefault(); show(0); break;
      case 'End':  e.preventDefault(); show(slides.length - 1); break;
      case 'f': case 'F':
        (document.fullscreenElement
          ? document.exitFullscreen()
          : document.documentElement.requestFullscreen());
        break;
    }
  });

  document.addEventListener('click', e => {
    if (e.target.closest('a')) return;
    (e.clientX > window.innerWidth * 0.33) ? nextStep() : prevStep();
  });

  let touchX = null;
  document.addEventListener('touchstart', e => { touchX = e.touches[0].clientX; }, { passive: true });
  document.addEventListener('touchend', e => {
    if (touchX === null) return;
    const dx = e.changedTouches[0].clientX - touchX;
    if (Math.abs(dx) > 40) (dx < 0 ? nextStep() : prevStep());
    touchX = null;
  }, { passive: true });

  /* ── Init from hash ── */
  const fromHash = parseInt((location.hash || '').replace('#', ''), 10);
  show(isNaN(fromHash) ? 0 : fromHash - 1, 0, false);
})();
