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
