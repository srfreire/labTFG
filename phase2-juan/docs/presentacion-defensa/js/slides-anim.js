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

/* 7 · Requisitos — counters */
SlideAnim.register('requisitos', el => {
  const tl = gsap.timeline({ paused: true });
  countUp(tl, el, 0);
  tl.fromTo(el.querySelectorAll('.chip'),
    { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.35, stagger: 0.06, ease: 'power2.out' }, 0.5);
  return tl;
});

/* 8 · Arquitectura — nodes in, edges draw */
SlideAnim.register('arquitectura', el => {
  const tl = gsap.timeline({ paused: true });
  const nodes = el.querySelectorAll('[data-anim="n"]');
  tl.fromTo(nodes, { opacity: 0, scale: 0.85 },
    { opacity: 1, scale: 1, duration: 0.45, stagger: 0.12, ease: 'back.out(1.4)' }, 0);
  drawEdge(tl, '.edge', el, 0.5, 0.5);
  return tl;
});

/* 9 · Dominio 2D — build grid, mark resources + agent, gentle pulse */
SlideAnim.register('dominio', el => {
  const grid = el.querySelector('#dom-grid');
  if (grid && !grid.childElementCount) {
    const resources = new Set([9, 22, 41, 52]);
    const agentCell = 27;
    for (let i = 0; i < 64; i++) {
      const c = document.createElement('div');
      c.className = 'cell';
      if (resources.has(i)) c.style.background = 'color-mix(in srgb, var(--color-accent-green) 55%, transparent)';
      if (i === agentCell) { c.style.background = 'var(--color-architect)'; c.id = 'dom-agent-cell'; c.style.boxShadow = '0 0 12px var(--color-architect)'; }
      grid.appendChild(c);
    }
  }
  const tl = gsap.timeline({ paused: true });
  tl.fromTo(grid.querySelectorAll('.cell'),
    { opacity: 0 }, { opacity: 1, duration: 0.5, stagger: { each: 0.006, from: 'random' } }, 0);
  const agent = el.querySelector('#dom-agent-cell');
  if (agent) tl.to(agent, { scale: 1.25, duration: 0.7, ease: 'sine.inOut', yoyo: true, repeat: -1, transformOrigin: 'center' }, 0.6);
  return tl;
});

/* 11 · Los 4 agentes — light up in sequence, in color */
SlideAnim.register('agentes', el => {
  const tl = gsap.timeline({ paused: true });
  const nodes = el.querySelectorAll('[data-anim="agent"]');
  const arrows = el.querySelectorAll('[data-anim="edge"]');
  nodes.forEach((n, i) => {
    const color = getComputedStyle(n).getPropertyValue('--agent').trim();
    tl.fromTo(n, { opacity: 0, y: 16 }, { opacity: 1, y: 0, duration: 0.4, ease: 'power2.out' }, i * 0.4);
    tl.fromTo(n, { boxShadow: '0 0 0 rgba(0,0,0,0)' },
      { boxShadow: `0 0 26px ${color}66`, duration: 0.35 }, i * 0.4 + 0.2);
    if (arrows[i]) tl.fromTo(arrows[i], { opacity: 0, x: -8 }, { opacity: 1, x: 0, duration: 0.25 }, i * 0.4 + 0.35);
  });
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
  return tl;
});

/* 14 · Bucle de desarrollo — steps in, loop edges draw */
SlideAnim.register('bucle', el => {
  const tl = gsap.timeline({ paused: true });
  const steps = el.querySelectorAll('[data-anim="step"]');
  tl.fromTo(steps, { opacity: 0, y: 12 }, { opacity: 1, y: 0, duration: 0.4, stagger: 0.2, ease: 'power2.out' }, 0);
  drawEdge(tl, '.edge', el, 0.5, 0.9);
  return tl;
});

/* 16 · Cronograma — grow bars */
SlideAnim.register('cronograma', el => {
  const tl = gsap.timeline({ paused: true });
  tl.to(el.querySelectorAll('.gantt__bar'),
    { scaleX: 1, duration: 0.6, stagger: 0.09, ease: 'power2.out' }, 0.1);
  return tl;
});

/* 19 · Resultados — counters + check rows */
SlideAnim.register('resultados', el => {
  const tl = gsap.timeline({ paused: true });
  tl.fromTo(el.querySelectorAll('.check'),
    { opacity: 0, x: -12 }, { opacity: 1, x: 0, duration: 0.35, stagger: 0.12, ease: 'power2.out' }, 0);
  countUp(tl, el, 0.4);
  return tl;
});
