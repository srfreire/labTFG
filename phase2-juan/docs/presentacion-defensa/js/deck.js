/* reveal.js init + GSAP wiring. */
Reveal.initialize({
  hash: true,
  transition: 'fade',
  transitionSpeed: 'slow',
  backgroundTransition: 'fade',
  backgroundColor: '#0a0a0a',
  center: false,
  width: 1280,
  height: 720,
  margin: 0.055,
  controlsTutorial: false,
  slideNumber: 'c/t',
  pdfSeparateFragments: false,
});

if (window.hljs) hljs.highlightAll();

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
