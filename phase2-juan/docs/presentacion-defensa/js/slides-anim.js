/* Per-slide GSAP timeline builders. Registered on load; deck.js plays them. */

/* Reusable count-up over every .stat__num[data-to] inside `el`. */
function countUp(tl, el, at = 0.1) {
  el.querySelectorAll('.stat__num[data-to]').forEach(n => {
    const end = +n.dataset.to;
    const o = { v: 0 };
    n.textContent = '0';
    tl.to(o, {
      v: end, duration: 1.0, ease: 'power1.out',
      onUpdate: () => { n.textContent = Math.round(o.v); },
    }, at);
  });
}

/* 1 · Portada — agent faces stagger in, then title */
SlideAnim.register('portada', el => {
  const tl = gsap.timeline({ paused: true });
  tl.fromTo(el.querySelectorAll('[data-anim="face"]'),
    { opacity: 0, y: 16, scale: 0.9 },
    { opacity: 1, y: 0, scale: 1, duration: 0.5, stagger: 0.1, ease: 'back.out(1.5)' }, 0);
  tl.fromTo(el.querySelector('h1'), { opacity: 0, y: 12 }, { opacity: 1, y: 0, duration: 0.5, ease: 'power2.out' }, 0.45);
  return tl;
});

/* 4 · Dos fases */
SlideAnim.register('dos-fases', el => {
  const tl = gsap.timeline({ paused: true });
  const p1 = el.querySelector('[data-anim="p1"]');
  const p2 = el.querySelector('[data-anim="p2"]');
  const bridge = el.querySelector('[data-anim="bridge"]');
  tl.fromTo(p1, { opacity: 0, x: -20 }, { opacity: 1, x: 0, duration: 0.5, ease: 'power2.out' }, 0);
  tl.fromTo(bridge, { opacity: 0, scale: 0.4 }, { opacity: 1, scale: 1, duration: 0.4, ease: 'back.out(2)' }, 0.35);
  tl.fromTo(p2, { opacity: 0, x: 20 }, { opacity: 1, x: 0, duration: 0.5, ease: 'power2.out' }, 0.2);
  return tl;
});

/* Estado del arte — panels stagger in on entry, then footer */
SlideAnim.register('arte', el => {
  const tl = gsap.timeline({ paused: true });
  tl.fromTo(el.querySelectorAll('[data-anim="p"]'),
    { opacity: 0, y: 14 }, { opacity: 1, y: 0, duration: 0.4, stagger: 0.12, ease: 'power2.out' }, 0);
  tl.fromTo(el.querySelector('[data-anim="foot"]'),
    { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.4, ease: 'power2.out' }, 0.55);
  return tl;
});

/* LLM-as-a-judge — three families, then rubric line, then two principles */
SlideAnim.register('judge', el => {
  const tl = gsap.timeline({ paused: true });
  tl.fromTo(el.querySelectorAll('[data-anim="fam"]'),
    { opacity: 0, y: 14 }, { opacity: 1, y: 0, duration: 0.4, stagger: 0.12, ease: 'power2.out' }, 0);
  tl.fromTo(el.querySelector('[data-anim="rub"]'),
    { opacity: 0 }, { opacity: 1, duration: 0.35 }, 0.5);
  tl.fromTo(el.querySelectorAll('[data-anim="pri"]'),
    { opacity: 0, y: 12 }, { opacity: 1, y: 0, duration: 0.4, stagger: 0.12, ease: 'power2.out' }, 0.6);
  return tl;
});

/* Arquitectura — layered bands cascade top to bottom */
SlideAnim.register('arquitectura', el => {
  const tl = gsap.timeline({ paused: true });
  tl.fromTo(el.querySelectorAll('[data-anim="band"]'),
    { opacity: 0, y: 14 }, { opacity: 1, y: 0, duration: 0.4, stagger: 0.14, ease: 'power2.out' }, 0);
  return tl;
});

/* 9 · Dominio 2D — build grid, mark resources + agent, gentle pulse */
SlideAnim.register('dominio', el => {
  const grid = el.querySelector('#dom-grid');
  if (grid && !grid.childElementCount) {
    // varios paradigmas a la vez en el mismo tablero → varios agentes de distinto color
    const agents = [
      { cell: 27, color: 'var(--color-architect)', main: true },
      { cell: 20, color: 'var(--color-analyst)' },
      { cell: 45, color: 'var(--color-tracker)' },
    ];
    const food = new Set([9, 13, 34, 38, 41, 52, 58]);
    const agentAt = new Map(agents.map(a => [a.cell, a]));
    for (let i = 0; i < 64; i++) {
      const c = document.createElement('div');
      c.className = 'cell';
      const a = agentAt.get(i);
      if (a) {
        c.classList.add('cell--agent');
        c.style.background = a.color;
        c.style.boxShadow = `0 0 12px ${a.color}`;
        if (a.main) c.id = 'dom-agent-cell';
      } else if (food.has(i)) {
        c.classList.add('cell--food');
        const pellet = document.createElement('span');
        pellet.className = 'dom-food';
        c.appendChild(pellet);
      }
      grid.appendChild(c);
    }
  }
  const tl = gsap.timeline({ paused: true });
  tl.fromTo(grid.querySelectorAll('.cell'),
    { opacity: 0 }, { opacity: 1, duration: 0.5, stagger: { each: 0.006, from: 'random' } }, 0);
  const agent = el.querySelector('#dom-agent-cell');
  if (agent) tl.to(agent, { scale: 1.25, duration: 0.7, ease: 'sine.inOut', yoyo: true, repeat: -1, transformOrigin: 'center' }, 0.6);
  tl.fromTo(grid.querySelectorAll('.dom-food'),
    { scale: 0.7 }, { scale: 1, duration: 1.1, ease: 'sine.inOut', yoyo: true, repeat: -1, transformOrigin: 'center', stagger: 0.2 }, 0.6);
  return tl;
});

/* Casos de uso (UML) — the actor reaches out to each use case in turn:
   frame settles, actor pops, then ray-draws + case-pop pair up one by one,
   finally the external systems slide in with their links and the «include» arcs. */
SlideAnim.register('casos-uso', el => {
  const tl = gsap.timeline({ paused: true });
  const frame = el.querySelector('[data-anim="frame"]');
  const actor = el.querySelector('[data-anim="actor"]');
  const cases = el.querySelectorAll('[data-anim="case"]');
  const exts = el.querySelectorAll('[data-anim="ext"]');
  const rays = el.querySelectorAll('.uc-edge:not(.uc-edge--inc):not(.uc-edge--ext)');
  const incs = el.querySelectorAll('.uc-edge--inc');
  const extEdges = el.querySelectorAll('.uc-edge--ext');

  if (frame) tl.fromTo(frame, { opacity: 0, scale: 0.985 },
    { opacity: 1, scale: 1, duration: 0.5, ease: 'power2.out', transformOrigin: 'center' }, 0);
  tl.fromTo(actor, { opacity: 0, x: -16, scale: 0.9 },
    { opacity: 1, x: 0, scale: 1, duration: 0.45, ease: 'back.out(1.5)' }, 0.15);

  cases.forEach((c, i) => {
    const at = 0.55 + i * 0.26;
    if (rays[i]) tl.to(rays[i], { strokeDashoffset: 0, duration: 0.3, ease: 'power1.inOut' }, at);
    tl.fromTo(c, { opacity: 0, scale: 0.82, x: -6 },
      { opacity: 1, scale: 1, x: 0, duration: 0.42, ease: 'back.out(1.7)' }, at + 0.14);
  });

  const tail = 0.55 + cases.length * 0.26;
  tl.fromTo(exts, { opacity: 0, x: 22 },
    { opacity: 1, x: 0, duration: 0.45, stagger: 0.14, ease: 'power2.out' }, tail);
  tl.to(extEdges, { opacity: 1, duration: 0.4 }, tail + 0.15);
  tl.to(incs, { opacity: 1, duration: 0.45 }, tail + 0.45);
  return tl;
});

/* Recuperación híbrida — two columns in, query dot pulses */
SlideAnim.register('retrieval', el => {
  const tl = gsap.timeline({ paused: true });
  tl.fromTo(el.querySelectorAll('[data-anim="col"]'),
    { opacity: 0, y: 14 }, { opacity: 1, y: 0, duration: 0.4, stagger: 0.15, ease: 'power2.out' }, 0);
  tl.fromTo(el.querySelector('[data-anim="foot"]'), { opacity: 0 }, { opacity: 1, duration: 0.4 }, 0.6);
  const ring = el.querySelector('.retr-qring');
  if (ring) tl.fromTo(ring, { attr: { r: 9 }, opacity: 0.6 },
    { attr: { r: 22 }, opacity: 0, duration: 1.5, ease: 'sine.out', repeat: -1 }, 0.6);
  return tl;
});

/* 11 · Los 4 agentes — dim face strip staggers in; each lights up on advance (CSS :has) */
SlideAnim.register('agentes', el => {
  const tl = gsap.timeline({ paused: true });
  tl.fromTo(el.querySelectorAll('[data-anim="tile"]'),
    { opacity: 0, y: 16 }, { opacity: 1, y: 0, duration: 0.4, stagger: 0.09, ease: 'power2.out' }, 0);
  return tl;
});

/* 12 · Knowledge Backbone — hub, then stores fly from corners */
SlideAnim.register('knowledge', el => {
  const tl = gsap.timeline({ paused: true });
  const hub = el.querySelector('[data-anim="hub"]');
  const stores = el.querySelectorAll('[data-anim="store"]');
  tl.fromTo(hub, { opacity: 0, scale: 0.8 }, { opacity: 1, scale: 1, duration: 0.4, ease: 'back.out(1.6)' }, 0);
  const offs = [[-40, -30], [40, -30], [-40, 30], [40, 30]];
  stores.forEach((s, i) => {
    tl.fromTo(s, { opacity: 0, x: offs[i][0], y: offs[i][1] },
      { opacity: 1, x: 0, y: 0, duration: 0.45, ease: 'power2.out' }, 0.25 + i * 0.12);
  });
  drawEdge(tl, '.kb-edge', el, 0.3, 0.8);
  return tl;
});

/* 14 · Bucle de desarrollo — hub, then stations light up clockwise (opacity only:
   stations are transform-centered, so animating y would clobber their position) */
SlideAnim.register('bucle', el => {
  const tl = gsap.timeline({ paused: true });
  const hub = el.querySelector('[data-anim="hub"]');
  if (hub) tl.fromTo(hub, { opacity: 0 }, { opacity: 1, duration: 0.4, ease: 'power2.out' }, 0);
  const steps = el.querySelectorAll('[data-anim="step"]');
  tl.fromTo(steps, { opacity: 0 }, { opacity: 1, duration: 0.4, stagger: 0.18, ease: 'power2.out' }, 0.15);
  const next = el.querySelector('.loop-next');
  if (next) tl.fromTo(next, { opacity: 0 }, { opacity: 1, duration: 0.4 }, 0.95);
  return tl;
});

/* Resultados — counters + check rows */
SlideAnim.register('resultados', el => {
  const tl = gsap.timeline({ paused: true });
  tl.fromTo(el.querySelectorAll('.check'),
    { opacity: 0, x: -12 }, { opacity: 1, x: 0, duration: 0.35, stagger: 0.12, ease: 'power2.out' }, 0);
  countUp(tl, el, 0.4);
  return tl;
});

/* Anécdota — stat count-up */
SlideAnim.register('anecdota', el => {
  const tl = gsap.timeline({ paused: true });
  tl.fromTo(el.querySelectorAll('.panel'),
    { opacity: 0, y: 12 }, { opacity: 1, y: 0, duration: 0.35, stagger: 0.1, ease: 'power2.out' }, 0);
  countUp(tl, el, 0.3);
  return tl;
});
