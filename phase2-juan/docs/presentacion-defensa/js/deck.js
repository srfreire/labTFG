/* reveal.js init + GSAP wiring. */
Reveal.initialize({
  hash: true,
  transition: 'fade',
  transitionSpeed: 'slow',
  backgroundTransition: 'fade',
  backgroundColor: '#f6f7f9',
  center: false,
  width: 1280,
  height: 720,
  margin: 0.055,
  controlsTutorial: false,
  slideNumber: 'c/t',
  pdfSeparateFragments: false,
  // N is repurposed as the speaker-notes toggle (see deck.js), so drop reveal's
  // default N=next-slide binding — otherwise pressing N both toggles notes and advances.
  keyboard: { 78: null },
});

if (window.hljs) hljs.highlightAll();

/* PDF export (?print-pdf): reveal lays out every slide as a static page and never
   fires the per-slide entry animations, so count-up numbers would freeze at their
   initial "0". Snap every [data-to] counter to its final value up front. */
if (/print-pdf/.test(window.location.search)) {
  document.querySelectorAll('.stat__num[data-to]').forEach(n => {
    n.textContent = n.getAttribute('data-to');
  });
}

function idOf(section) { return section && section.dataset ? section.dataset.slide : null; }

function activate(section) {
  const id = idOf(section);
  if (!id) return;
  const tl = SlideAnim.build(id, section);
  if (!tl) return;
  // Entry animations always run; reveal .fragment reveals are independent (CSS).
  tl.play();
}

Reveal.on('ready', ev => activate(ev.currentSlide));

Reveal.on('slidechanged', ev => {
  const prev = idOf(ev.previousSlide);
  if (prev) SlideAnim.reset(prev);
  activate(ev.currentSlide);
});

/* Step diagrams that opt into fragment-driven playback: each .fragment can carry
   data-anim-label="X" and the builder can seek to that label; simplest form just
   advances the timeline forward on each fragment. */
Reveal.on('fragmentshown', ev => {
  const section = ev.fragment.closest('section');
  const id = idOf(section);
  const tl = id && SlideAnim.get(id);
  if (tl) tl.play();
});

/* Autoplay hero/demo video when its slide becomes active (browsers block off-DOM autoplay). */
Reveal.on('slidechanged', ev => {
  document.querySelectorAll('video').forEach(v => { v.pause(); });
  const v = ev.currentSlide.querySelector('video');
  if (v) { v.currentTime = 0; v.play().catch(() => {}); }
});

/* Lightweight speaker-notes viewer — reveal.js 5 ships the Notes plugin as a
   separate file we don't vendor, so we render the current slide's <aside class="notes">
   into a self-contained overlay. Press N (or the ? key) to toggle. */
(function speakerNotes() {
  const panel = document.createElement('div');
  panel.className = 'notes-overlay';
  panel.setAttribute('aria-hidden', 'true');
  panel.innerHTML = '<div class="notes-overlay__hd"><span class="notes-overlay__pos"></span><span class="notes-overlay__hint mono">N para ocultar</span></div><div class="notes-overlay__body"></div>';
  document.body.appendChild(panel);
  const body = panel.querySelector('.notes-overlay__body');
  const pos = panel.querySelector('.notes-overlay__pos');
  let open = false;

  function render() {
    const slide = Reveal.getCurrentSlide();
    const note = slide && slide.querySelector('aside.notes');
    const idx = Reveal.getIndices();
    const total = Reveal.getTotalSlides();
    pos.textContent = (idx.h + 1) + ' / ' + total;
    body.innerHTML = note ? note.innerHTML : '<p class="mono dim">— sin notas —</p>';
  }
  function toggle() {
    open = !open;
    panel.classList.toggle('is-open', open);
    panel.setAttribute('aria-hidden', open ? 'false' : 'true');
    if (open) render();
  }

  Reveal.on('slidechanged', () => { if (open) render(); });
  document.addEventListener('keydown', ev => {
    if (ev.defaultPrevented) return;
    const k = ev.key.toLowerCase();
    if (k === 'n') { ev.preventDefault(); toggle(); }
  });
})();

/* Click-to-zoom lightbox for inset videos marked .zoomable — enlarges the clip
   over a dim backdrop so small on-slide insets stay readable from the audience. */
(function videoZoom() {
  const overlay = document.createElement('div');
  overlay.className = 'video-zoom';
  overlay.setAttribute('aria-hidden', 'true');
  overlay.innerHTML = '<video class="video-zoom__v" autoplay loop muted playsinline></video><div class="video-zoom__hint">clic o Esc para cerrar</div>';
  document.body.appendChild(overlay);
  const zv = overlay.querySelector('video');

  function openZoom(frame) {
    const src = frame.querySelector('video');
    if (!src) return;
    zv.innerHTML = '';
    src.querySelectorAll('source').forEach(s => {
      const c = document.createElement('source');
      c.src = s.src; c.type = s.type; zv.appendChild(c);
    });
    zv.load();
    overlay.classList.add('is-open');
    overlay.setAttribute('aria-hidden', 'false');
    zv.play().catch(() => {});
  }
  function closeZoom() {
    overlay.classList.remove('is-open');
    overlay.setAttribute('aria-hidden', 'true');
    zv.pause();
  }

  document.addEventListener('click', ev => {
    const frame = ev.target.closest ? ev.target.closest('.zoomable') : null;
    if (frame) { ev.preventDefault(); openZoom(frame); return; }
    if (ev.target.closest && ev.target.closest('.video-zoom')) closeZoom();
  });
  document.addEventListener('keydown', ev => {
    const frame = ev.target.closest ? ev.target.closest('.zoomable') : null;
    if (frame && (ev.key === 'Enter' || ev.key === ' ')) { ev.preventDefault(); openZoom(frame); }
  });
  // Capture phase so Escape closes the lightbox without also opening reveal's overview.
  document.addEventListener('keydown', ev => {
    if (overlay.classList.contains('is-open') && ev.key === 'Escape') {
      ev.preventDefault(); ev.stopImmediatePropagation(); closeZoom();
    }
  }, true);
})();
