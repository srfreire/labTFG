/* GSAP timeline registry. Each builder(sectionEl) returns a PAUSED gsap.timeline().
   deck.js builds lazily on slide entry and plays on entry / fragmentshown. */
window.SlideAnim = (() => {
  const builders = new Map();
  const live = new Map();
  return {
    register(id, fn) { builders.set(id, fn); },
    build(id, el) {
      if (live.has(id)) return live.get(id);
      const fn = builders.get(id);
      if (!fn) return null;
      let tl = null;
      try { tl = fn(el); } catch (e) { console.error('anim build failed', id, e); }
      live.set(id, tl);
      return tl;
    },
    reset(id) { const tl = live.get(id); if (tl) tl.progress(0).pause(); },
    get(id) { return live.get(id); },
  };
})();

/* Helper: draw an SVG path/line by tweening strokeDashoffset → 0 */
window.drawEdge = (tl, sel, el, at, dur = 0.4) => {
  const nodes = typeof sel === 'string' ? el.querySelectorAll(sel) : sel;
  tl.to(nodes, { strokeDashoffset: 0, duration: dur, ease: 'power1.inOut' }, at);
};
