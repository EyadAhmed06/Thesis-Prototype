/* Offline map drawing for one situation: main roads, the routes SUMO drove, chargers, start and destination.
   Data comes from referee/cases_v2/test_maps.json (made by referee/make_maps.py). */
const EVMap = (() => {
  const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  let roadsBox = null;
  function prep(data) { if (roadsBox) return; roadsBox = data.roads.map(r => { let a = 1e9, b = 1e9, c = -1e9, d = -1e9;
      for (const [x, y] of r) { a = Math.min(a, x); b = Math.min(b, y); c = Math.max(c, x); d = Math.max(d, y); } return [a, b, c, d]; }); }
  function route(m, letter) { return letter ? [...(m.to[letter] || []), ...(m.from[letter] || [])] : (m.direct || []); }
  function lenOf(p) { let L = [0]; for (let i = 1; i < p.length; i++) L.push(L[i - 1] + Math.hypot(p[i][0] - p[i - 1][0], p[i][1] - p[i - 1][1])); return L; }
  function draw(cv, data, sid, o = {}) {
    prep(data); const m = data.situations[sid]; if (!m) return;
    const dpr = window.devicePixelRatio || 1, W = cv.clientWidth, H = cv.clientHeight || W * 0.62;
    if (cv.width !== W * dpr || cv.height !== H * dpr) { cv.width = W * dpr; cv.height = H * dpr; }
    const g = cv.getContext('2d'); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, W, H);
    const pts = [...(m.direct || [])]; for (const L in m.to) pts.push(...m.to[L], ...(m.from[L] || [])); for (const L in m.chargers) pts.push([m.chargers[L].lon, m.chargers[L].lat]);
    let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9; for (const [x, y] of pts) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
    const k = Math.cos((y0 + y1) / 2 * Math.PI / 180), pad = 28;
    const s = Math.min((W - 2 * pad) / ((x1 - x0) * k || 1e-3), (H - 2 * pad) / ((y1 - y0) || 1e-3));
    const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2, P = ([x, y]) => [W / 2 + (x - cx) * k * s, H / 2 - (y - cy) * s];
    const vx0 = cx - W / 2 / (k * s), vx1 = cx + W / 2 / (k * s), vy0 = cy - H / 2 / s, vy1 = cy + H / 2 / s;
    const line = (p, color, w, dash, upto) => { if (!p || p.length < 2) return; g.beginPath(); g.strokeStyle = color; g.lineWidth = w; g.setLineDash(dash || []);
      g.lineCap = 'round'; g.lineJoin = 'round'; const L = upto != null ? lenOf(p) : null, lim = L ? L[L.length - 1] * upto : 0;
      let q = P(p[0]); g.moveTo(...q); for (let i = 1; i < p.length; i++) { if (L && L[i] > lim) { const f = (lim - L[i - 1]) / ((L[i] - L[i - 1]) || 1);
          const a = p[i - 1], b = p[i]; g.lineTo(...P([a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f])); break; } g.lineTo(...P(p[i])); } g.stroke(); g.setLineDash([]); };
    // background roads in view
    g.globalAlpha = 1; data.roads.forEach((r, i) => { const b = roadsBox[i]; if (b[2] < vx0 || b[0] > vx1 || b[3] < vy0 || b[1] > vy1) return; line(r, css('--road2'), 1.6); });
    line(m.direct, css('--muted'), 1.5, [5, 5]);
    for (const L in m.to) if (L !== o.best && L !== o.model) { line(m.to[L], css('--road2'), 2); line(m.from[L], css('--road2'), 2); }
    if (o.best !== undefined) { g.globalAlpha = 0.55; line(route(m, o.best), css('--good'), 9); g.globalAlpha = 1; }
    if (o.model !== undefined && o.model !== 'invalid') { g.shadowColor = css('--accent'); g.shadowBlur = 10; line(route(m, o.model), css('--accent'), 3.8, null, o.t == null ? null : o.t); g.shadowBlur = 0; }
    // car dot along the model route
    if (o.model !== undefined && o.model !== 'invalid' && o.t != null) { const p = route(m, o.model), L = lenOf(p), lim = L[L.length - 1] * o.t;
      let i = 1; while (i < p.length - 1 && L[i] < lim) i++; const f = (lim - L[i - 1]) / ((L[i] - L[i - 1]) || 1), a = p[i - 1], b = p[i] || a;
      const [qx, qy] = P([a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f]); g.beginPath(); g.fillStyle = css('--accent'); g.arc(qx, qy, 6, 0, 7); g.fill();
      g.strokeStyle = css('--surface'); g.lineWidth = 2; g.stroke(); }
    // chargers
    g.font = '600 11px system-ui,sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
    for (const L in m.chargers) { const c = m.chargers[L], [x, y] = P([c.lon, c.lat]), sel = L === o.model, best = L === o.best, r = sel || best ? 11 : 9;
      g.beginPath(); g.arc(x, y, r, 0, 7);
      if (!c.usable) { g.fillStyle = css('--surface'); g.fill(); g.strokeStyle = css('--bad'); g.lineWidth = 2; g.setLineDash([3, 2]); g.stroke(); g.setLineDash([]); g.fillStyle = css('--bad'); }
      else { g.fillStyle = best ? css('--good') : sel ? css('--accent') : css('--surface'); g.fill(); g.strokeStyle = best ? css('--good') : sel ? css('--accent') : css('--ink'); g.lineWidth = 1.5; g.stroke();
        g.fillStyle = best || sel ? '#fff' : css('--ink'); }
      g.fillText(L, x, y + .5); if (c.level === 'DC') { g.fillStyle = css('--warn'); g.font = '700 9px system-ui'; g.fillText('⚡', x + r + 3, y - r + 2); g.font = '600 11px system-ui,sans-serif'; } }
    // start and destination
    const d = m.direct || []; if (d.length) { const [sx, sy] = P(d[0]), [ex, ey] = P(d[d.length - 1]);
      g.beginPath(); g.arc(sx, sy, 6, 0, 7); g.fillStyle = css('--ink'); g.fill(); g.font = '600 11px system-ui';
      const lab = (t, x, y) => { const w = g.measureText(t).width; g.textAlign = 'left'; const lx = x + 10 + w > W - 4 ? x - 10 - w : x + 10;
        g.lineWidth = 3; g.strokeStyle = css('--surface2'); g.strokeText(t, lx, y - 10); g.fillStyle = css('--ink'); g.fillText(t, lx, y - 10); };
      g.beginPath(); g.rect(ex - 6, ey - 6, 12, 12); g.fill(); lab('start', sx, sy); lab('destination', ex, ey); }
  }
  return { draw, route };
})();
