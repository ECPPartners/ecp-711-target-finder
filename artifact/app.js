/* 7-Eleven Target Area Finder — ECP Partners (confidential). Data files are written by the scheduled refresh. */
(() => {
'use strict';
const MI = 1609.344;
const MANAGERS = ['Bauer', 'Golden', 'Antonacci'];
const MGR_FULL = { Bauer: 'Jim Bauer · Northeast Florida', Golden: 'Richard Golden · Tampa Bay & North', Antonacci: 'Chris Antonacci · Southwest & Southeast Florida' };
const FACTORS = [
  ['new_rooftops', 'New rooftops'], ['traffic', 'Traffic'], ['new_grocery', 'New grocery'], ['gap_to_7eleven', 'Gap to 7-Eleven'],
  ['retail_node', 'Retail node'], ['signal', 'Signal'], ['rooftop_pipeline', 'Platted lots'],
];
const STATUSES = ['Sent', 'Under review', 'Accepted', 'LOI', 'Lease', 'Passed', 'Withdrawn'];
const PASS_REASONS = ['', 'Too close to existing store', 'Trade area / demographics', 'Traffic', 'Access / median', 'Site size or shape', 'Price / rent', 'Competition', 'Zoning / entitlements', 'Already working this area', 'Other'];

const $ = (s, el = document) => el.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = n => n == null || n === '' ? '—' : Number(n).toLocaleString('en-US', { maximumFractionDigits: 0 });
const fmt1 = n => n == null ? '—' : Number(n).toFixed(1);
const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const toast = msg => { const t = $('#toast'); t.textContent = msg; t.classList.add('on'); clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.remove('on'), 2600); };
const gmaps = c => `https://www.google.com/maps/search/?api=1&query=${c.lat},${c.lon}`;
const title = s => String(s || '').toLowerCase().replace(/\b([a-z])/g, m => m.toUpperCase()).replace(/\b(Sr|Us|Cr|Ne|Nw|Se|Sw|Fl)\b/g, m => m.toUpperCase()).replace(/\bSt\b(?= [A-Z])/g, 'St');

const S = {
  data: null, filtered: [], sel: null, sort: { key: 'pos', dir: 1 },
  reviews: {}, packs: {}, subs: [], db: null, user: null, sample: null, downloads: null, canWrite: null, names: {},
};

/* ---------- data ---------- */
async function loadData() {
  const files = ['meta', 'candidates', 'stores', 'competitors', 'anchors', 'rooftops', 'backtest'];
  const geo = ['counties', 'roads'];
  const get = async f => (await fetch(f)).json();
  const [arr, g] = await Promise.all([
    Promise.all(files.map(f => get(`data/${f}.json`))),
    Promise.all(geo.map(f => get(`data/${f}.json`))),
  ]);
  const d = Object.fromEntries(files.map((f, i) => [f, arr[i]]));
  d.counties = g[0]; d.roads = g[1];
  d.byId = Object.fromEntries(d.candidates.map(c => [c.id, c]));
  return d;
}

/* ---------- filters ---------- */
function readFilters() {
  return { m: $('#fManager').value, c: $('#fCounty').value, t: $('#fTier').value, k: $('#fMarket').value, top: $('#fTop').checked, redev: $('#fRedev').checked, q: $('#fSearch').value.trim().toLowerCase() };
}
function applyFilters() {
  const f = readFilters();
  S.filtered = S.data.candidates.filter(c =>
    (f.redev || c.raw_ok) && (!f.m || c.re_manager === f.m) && (!f.c || c.county === f.c) && (!f.t || c.tier === f.t) &&
    (!f.k || (f.k === 'Proven' ? c.market_type.startsWith('Proven') : c.market_type === 'White space')) &&
    (!f.top || c.top50) && (!f.q || (c.intersection_name + ' ' + c.county + ' ' + (c.nearest_7eleven || '')).toLowerCase().includes(f.q)));
  S.data.candidates.forEach(c => { c.pos = null; });
  S.filtered.sort((a, b) => b.score - a.score); S.filtered.forEach((c, i) => { c.pos = i + 1; });
  $('#fCount').textContent = `${S.filtered.length} corners${f.redev ? ' incl. redevelopment' : ' with raw land'}`;
  renderList(); renderTable(); drawCandidates();
}

/* ---------- map ---------- */
let map, layers = {}, candLayer, selRing;
function tierStyle(t) {
  return t === 'A' ? { r: 7, fill: css('--brand'), stroke: css('--surface'), w: 1.5 }
    : t === 'B' ? { r: 5, fill: css('--brand-tint'), stroke: css('--brand'), w: 1 }
    : { r: 3.5, fill: css('--line-strong'), stroke: css('--surface'), w: 0.5 };
}
function initMap() {
  map = L.map('map', { preferCanvas: true, zoomSnap: 0.5, attributionControl: false }).setView([28.9, -81.6], 7);
  const mgrFill = { Bauer: css('--mgr-bauer'), Golden: css('--mgr-golden'), Antonacci: css('--mgr-antonacci') };
  layers.counties = L.geoJSON(S.data.counties, {
    style: f => ({ color: f.properties.pilot ? css('--line-strong') : css('--line'), weight: f.properties.pilot ? 1.2 : 0.6,
      fillColor: f.properties.pilot ? mgrFill[f.properties.manager] : css('--paper'), fillOpacity: f.properties.pilot ? 0.8 : 0.4 }),
    interactive: false,
  }).addTo(map);
  layers.countyLabels = L.layerGroup(S.data.counties.features.filter(f => f.properties.pilot).map(f => {
    const c = L.geoJSON(f).getBounds().getCenter();
    return L.marker(c, { icon: L.divIcon({ className: 'countylabel', html: esc(f.properties.county) + '<br>' + esc(f.properties.manager), iconSize: [120, 30], iconAnchor: [60, 15] }), interactive: false });
  })).addTo(map);
  const rv = { interstate: [css('--ink-muted'), 2.2], arterial: [css('--ink-muted'), 1.2], collector: [css('--line-strong'), 0.7] };
  layers.roads = L.geoJSON(S.data.roads, { style: f => ({ color: rv[f.properties.cls][0], weight: rv[f.properties.cls][1], opacity: 0.75 }), interactive: false }).addTo(map);
  // rooftop growth: 1 km cells
  const maxU = Math.max(...S.data.rooftops.map(r => r[2]));
  layers.rooftops = L.layerGroup(S.data.rooftops.map(([la, lo, u]) => {
    const dLat = 500 / 111320, dLon = 500 / (111320 * Math.cos(la * Math.PI / 180));
    return L.rectangle([[la - dLat, lo - dLon], [la + dLat, lo + dLon]], { stroke: false, fillColor: css('--positive'), fillOpacity: Math.min(0.85, 0.12 + 0.7 * Math.log(u) / Math.log(maxU)), interactive: false });
  }));
  layers.anchors = L.layerGroup(S.data.anchors.filter(a => a.category !== 'National QSR/retail').map(a =>
    L.circleMarker([a.lat, a.lon], { radius: 3, color: css('--ink-muted'), weight: 0.5, fillColor: css('--sand'), fillOpacity: 1 }).bindTooltip(`${esc(a.brand)} · ${esc(title(a.street))}`)));
  layers.competitors = L.layerGroup(S.data.competitors.map(c =>
    L.circleMarker([c.lat, c.lon], { radius: 3.5, color: css('--comp'), weight: 1, fillColor: css('--comp'), fillOpacity: 0.55 }).bindTooltip(`${esc(c.brand)} · ${esc(title(c.address))}, ${esc(title(c.city))}`)));
  layers.stores = L.layerGroup(S.data.stores.map(s => {
    const nb = s.vintage === 'New build (2018+)', nf = s.has_fuel === 'N';
    return L.circleMarker([s.lat, s.lon], { radius: nb ? 6 : 4.5, color: nb ? css('--positive') : css('--ink'), weight: nf ? 2 : 1,
      fillColor: nf ? css('--paper') : (nb ? css('--positive') : css('--ink')), fillOpacity: nf ? 1 : 0.85 })
      .bindTooltip(`${esc(s.brand)} · ${esc(title(s.address))}, ${esc(title(s.city))}<br>${nf ? 'Non-fuel' : 'Fuel'} · ${esc(s.vintage)}${s.year_built ? ' (' + s.year_built + ')' : ''}<br><span style="opacity:.7">${esc(s.source_short)}</span>`);
  })).addTo(map);
  layers.spacing = L.layerGroup(S.data.stores.filter(s => s.has_fuel === 'Y').map(s =>
    L.circle([s.lat, s.lon], { radius: 2 * MI, color: css('--ink'), weight: 0.5, opacity: 0.35, fill: true, fillColor: css('--ink'), fillOpacity: 0.04, interactive: false })));
  candLayer = L.layerGroup().addTo(map);
  layers.candidates = candLayer;
  // layer toggles
  const defs = [['candidates', 'Candidates', true], ['stores', '7-Eleven stores', true], ['competitors', 'Competitors', false], ['rooftops', 'New rooftops 2023–25', false],
    ['spacing', '2-mile spacing rings', false], ['anchors', 'Anchors & grocers', false], ['roads', 'Roads', true], ['counties', 'Counties & territories', true]];
  $('#layerToggles').innerHTML = defs.map(([k, l, on]) => `<label><input type="checkbox" data-layer="${k}" ${on ? 'checked' : ''}> ${l}</label>`).join('');
  $('#layerToggles').addEventListener('change', e => {
    const k = e.target.dataset.layer; if (!k) return;
    if (e.target.checked) { layers[k].addTo(map); if (k === 'counties') layers.countyLabels.addTo(map); }
    else { map.removeLayer(layers[k]); if (k === 'counties') map.removeLayer(layers.countyLabels); }
    candLayer.eachLayer(l => l.bringToFront && l.bringToFront());
  });
  $('#legend').innerHTML = [
    `<span><i class="dot" style="background:${css('--brand')}"></i>Tier A</span>`,
    `<span><i class="dot" style="background:${css('--brand-tint')}"></i>Tier B</span>`,
    `<span><i class="dot" style="background:${css('--line-strong')}"></i>Tier C</span>`,
    `<span><i class="dot" style="background:${css('--paper')};border:2px solid ${css('--brand-tint')}"></i>Redevelopment (toggle)</span>`,
    `<span><i class="dot" style="background:${css('--positive')}"></i>7-Eleven built 2018+</span>`,
    `<span><i class="dot" style="background:${css('--ink')}"></i>7-Eleven older</span>`,
    `<span><i class="dot" style="background:${css('--paper')};border:2px solid ${css('--ink')}"></i>Non-fuel</span>`,
    `<span><i class="dot" style="background:${css('--comp')}"></i>Competitor</span>`,
    `<span><i class="sq" style="background:${css('--positive')};opacity:.6"></i>New homes / km²</span>`,
  ].join('');
  const pilot = L.geoJSON({ type: 'FeatureCollection', features: S.data.counties.features.filter(f => f.properties.pilot) });
  map.fitBounds(pilot.getBounds(), { padding: [10, 10] });
}
function drawCandidates() {
  if (!candLayer) return;
  candLayer.clearLayers();
  const order = [...S.filtered].sort((a, b) => (a.tier < b.tier ? 1 : -1));
  for (const c of order) {
    const st = tierStyle(c.tier);
    const m = c.raw_ok ? L.circleMarker([c.lat, c.lon], { radius: st.r, color: st.stroke, weight: st.w, fillColor: st.fill, fillOpacity: 1 })
      : L.circleMarker([c.lat, c.lon], { radius: st.r, color: st.fill, weight: 2, fillColor: css('--paper'), fillOpacity: 1 });
    m.bindTooltip(`<b>${esc(title(c.intersection_name))}</b><br>Score ${fmt1(c.score)} · Tier ${c.tier}${c.raw_ok ? '' : ' · redevelopment'}`);
    m.on('click', () => select(c.id, false));
    candLayer.addLayer(m);
  }
}

/* ---------- side list ---------- */
function renderList() {
  const rows = S.filtered.slice(0, 200);
  $('#clist').innerHTML = rows.map(c => `<li data-id="${c.id}" class="${S.sel === c.id ? 'sel' : ''}">
      <span class="rk num">${c.pos}</span>
      <span><span class="nm">${esc(title(c.intersection_name))}</span><br>
        <span class="sub">${esc(c.county)} · ${esc(c.re_manager)} · <span class="pill ${c.market_type.startsWith('Proven') ? 'proven' : 'white'}">${c.market_type.startsWith('Proven') ? 'Proven' : 'White space'}</span>${S.reviews[c.id] ? ' · ' + (S.reviews[c.id].chase === 'yes' ? 'Would chase' : S.reviews[c.id].chase === 'no' ? "Won't chase" : '') : ''}</span></span>
      <span style="text-align:right"><span class="score">${fmt1(c.score)}</span><br><span class="pill ${c.tier}">Tier ${c.tier}</span></span></li>`).join('')
    + (S.filtered.length > 200 ? `<li class="sub" style="display:block;cursor:default">Showing the top 200. Narrow the filters to see more.</li>` : '');
}
$('#clist').addEventListener('click', e => { const li = e.target.closest('li[data-id]'); if (li) select(li.dataset.id, true); });

/* ---------- detail ---------- */
function select(id, pan) {
  S.sel = id; const c = S.data.byId[id]; if (!c) return;
  if (location.hash !== '#map') location.hash = '#map';
  if (selRing) map.removeLayer(selRing);
  selRing = L.layerGroup([
    L.circle([c.lat, c.lon], { radius: 3 * MI, color: css('--brand'), weight: 1, dashArray: '4 4', fill: false, interactive: false }),
    L.circleMarker([c.lat, c.lon], { radius: 11, color: css('--brand'), weight: 2, fill: false, interactive: false }),
  ]).addTo(map);
  if (pan) map.setView([c.lat, c.lon], Math.max(map.getZoom(), 12));
  renderDetail(c); renderList();
  const li = $(`#clist li[data-id="${id}"]`); if (li) li.scrollIntoView({ block: 'nearest' });
}
function renderDetail(c) {
  const d = $('#detail'); d.hidden = false;
  const rv = S.reviews[c.id] || {};
  const inPack = MANAGERS.filter(m => (S.packs[m]?.ids || []).includes(c.id));
  const w = S.data.meta.weights;
  d.innerHTML = `
    <button class="btn ghost small close" id="dClose" aria-label="Close">Close</button>
    <div class="eyebrow">${c.pos ? 'Rank ' + c.pos + ' · ' : ''}Tier ${c.tier}${c.top50 ? ' · Top 50' : ''}${c.raw_ok ? '' : ' · Redevelopment'}</div>
    <h3>${esc(title(c.intersection_name))}</h3>
    <div class="sub muted">${esc(c.county)} County · ${esc(MGR_FULL[c.re_manager] || c.re_manager)}</div>
    <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px">
      <span class="pill ${c.market_type.startsWith('Proven') ? 'proven' : 'white'}">${esc(c.market_type)}</span>
      ${c.access_flag ? `<span class="pill flag">${esc(c.access_flag)}</span>` : ''}</div>
    <div style="display:flex;align-items:baseline;gap:8px;margin-top:12px"><span class="score" style="font-size:40px">${fmt1(c.score)}</span><span class="muted">of 100</span></div>
    <div class="bars">${FACTORS.map(([k, l]) => { const v = c['pts_' + k] || 0, mx = w[k]; return `<div class="bar"><span>${l}</span><span class="track"><span class="fill" style="width:${mx ? 100 * v / mx : 0}%"></span></span><span class="v">${fmt1(v)}/${mx}</span></div>`; }).join('')}</div>
    <p class="why">${esc(c.why_here)}</p>
    <div class="block" style="margin-top:0;border-top:0;padding-top:0">
      <div class="label">Raw land at the corner</div>
      ${c.raw_corner ? `<p class="why" style="margin:4px 0">${c.aerial_qa ? '<b>Flagged:</b> ' + esc(c.aerial_qa) + '. ' : ''}${esc(c.raw_best_use)}, ${fmt1(c.raw_best_acres)} ac${c.raw_parcels > 1 ? ` (+${c.raw_parcels - 1} more raw parcel${c.raw_parcels > 2 ? 's' : ''})` : ''}<br><span class="src">Parcel ${esc(c.raw_best_parcel)} · Owner: ${esc(c.raw_best_owner)}</span></p>`
        : '<p class="why" style="margin:4px 0">No raw parcel of 1.3+ acres touches this corner. It would be a redevelopment site.</p>'}
      <div class="src">FL DOR 2026 tax roll. Vacant/ag use codes are the county's classification; confirm on the aerial.</div>
    </div>
    <dl class="kv">
      <dt>New homes 2023–25 within 3 mi</dt><dd>${fmt(c.new_rooftops_3mi)}</dd>
      <dt>Vacant platted lots within 3 mi</dt><dd>${fmt(c.pipeline_lots_3mi)}</dd>
      <dt>Grocers on 2023+ parcels within 3 mi</dt><dd>${fmt(c.new_grocers_3mi)}</dd>
      <dt>Combined AADT (FDOT 2025)</dt><dd>${c.combined_aadt == null ? 'No count' : fmt(c.combined_aadt)}</dd>
      <dt>Trucks per day (busiest road)</dt><dd>${fmt(c.max_trucks_per_day)}</dd>
      <dt>Signal</dt><dd>${esc(c.signal)}</dd>
      <dt>Nearest 7-Eleven</dt><dd>${fmt1(c.dist_to_7eleven_mi)} mi</dd>
      <dt></dt><dd style="font-weight:400">${esc(title(c.nearest_7eleven))}</dd>
      <dt>Anchors within ½ mi</dt><dd style="font-weight:400">${esc(c.anchors_half_mi || 'None')}</dd>
      <dt>Nationals within ½ mi</dt><dd style="font-weight:400">${esc(c.nationals_half_mi || 'None')}</dd>
      <dt>Nearest competitor</dt><dd style="font-weight:400">${esc(c.nearest_competitor)}</dd>
    </dl>
    <div class="btnrow"><a class="btn ghost small" href="${gmaps(c)}" target="_blank" rel="noopener">Open in Google Maps</a></div>
    <div class="src">Rooftops and lots: FL DOR 2026 tax roll. Traffic and signals: FDOT. Stores: FDEP + 7-Eleven. Grocer age and "proven" are inferences from parcel year built.</div>
    <div class="block" id="reviewBlock">
      <div class="label">Deal-maker review</div>
      <div style="display:flex;gap:8px;align-items:center;margin-top:6px;flex-wrap:wrap">
        <div class="seg" role="group" aria-label="Would you chase this corner?">
          <button type="button" data-chase="yes" aria-pressed="${rv.chase === 'yes'}">Would chase</button>
          <button type="button" data-chase="no" aria-pressed="${rv.chase === 'no'}">Won't chase</button></div>
        <label style="font-size:12px;display:flex;gap:6px;align-items:center"><input type="checkbox" id="accessOk" ${rv.accessVerified ? 'checked' : ''}> Access verified</label>
      </div>
      <label for="revNote" class="label" style="display:block;margin-top:8px">Why</label>
      <textarea id="revNote" placeholder="e.g. Corner parcel owned by a church; median blocks lefts from SR-54">${esc(rv.note || '')}</textarea>
      <div class="btnrow" style="margin-top:6px"><button class="btn small" id="saveRev">Save review</button><span class="src" id="revBy"></span></div>
    </div>
    <div class="block">
      <div class="label">Manager pack</div>
      <div class="btnrow" style="margin-top:6px">
        <button class="btn ghost small" id="packToggle" data-m="${esc(c.re_manager)}">${inPack.includes(c.re_manager) ? 'Remove from' : 'Pin to'} ${esc(c.re_manager)} pack</button>
        <button class="btn ghost small" id="logThis">Log a submittal here</button></div>
    </div>
    <div class="block" id="claudeBlock" ${S.sample ? '' : 'hidden'}>
      <div class="label">Draft with Claude</div>
      <p class="src">Drafts a short note you could use with ${esc(c.re_manager)}, from this corner's numbers only. Check it before you send it.</p>
      <button class="btn small" id="draftBtn">Draft a pitch note</button>
      <div class="draft" id="draftOut"></div>
    </div>`;
  $('#dClose').onclick = () => { d.hidden = true; S.sel = null; if (selRing) map.removeLayer(selRing); renderList(); };
  d.querySelectorAll('[data-chase]').forEach(b => b.onclick = () => {
    d.querySelectorAll('[data-chase]').forEach(x => x.setAttribute('aria-pressed', x === b && x.getAttribute('aria-pressed') !== 'true'));
  });
  $('#saveRev').onclick = () => saveReview(c);
  $('#packToggle').onclick = () => togglePack(c);
  $('#logThis').onclick = () => { location.hash = '#log'; openSubForm({ candidateId: c.id }); };
  if ($('#draftBtn')) $('#draftBtn').onclick = () => draftPitch(c);
  if (!S.db) { $('#reviewBlock').insertAdjacentHTML('beforeend', '<p class="src">Reviews, packs and the log save once the page connects to its shared database.</p>'); }
  if (rv.by) showName(rv.by).then(n => { const el = $('#revBy'); if (el) el.textContent = `Last saved by ${n}${rv.at ? ' · ' + rv.at.slice(0, 10) : ''}`; });
}

/* ---------- table ---------- */
const TCOLS = [
  ['pos', 'Rank', 'n'], ['score', 'Score', 'n'], ['tier', 'Tier'], ['intersection_name', 'Intersection'], ['county', 'County'], ['re_manager', 'Manager'],
  ['market_type', 'Market'], ['raw', 'Raw land'], ['new_rooftops_3mi', 'New homes 3 mi', 'n'], ['pipeline_lots_3mi', 'Platted lots', 'n'], ['new_grocers_3mi', 'New grocers', 'n'],
  ['combined_aadt', 'AADT', 'n'], ['signal', 'Signal'], ['dist_to_7eleven_mi', '7-Eleven mi', 'n'], ['anchors_half_mi', 'Anchors ½ mi'],
  ['nearest_competitor', 'Nearest competitor'], ['access_flag', 'Access flag'], ['review', 'Review'], ['why_here', 'Why here', 'wrap'],
];
function renderTable() {
  const k = S.sort.key, dir = S.sort.dir;
  const rows = [...S.filtered].sort((a, b) => { const x = a[k], y = b[k]; if (x == null) return 1; if (y == null) return -1; return (x > y ? 1 : x < y ? -1 : 0) * dir; });
  $('#rankTable').innerHTML = `<thead><tr>${TCOLS.map(([key, l]) => `<th data-k="${key}" scope="col">${l}${k === key ? (dir > 0 ? ' ▲' : ' ▼') : ''}</th>`).join('')}</tr></thead>
    <tbody>${rows.map(c => `<tr data-id="${c.id}">${TCOLS.map(([key, , cls]) => {
      let v = c[key];
      if (key === 'raw') v = c.raw_ok ? `${c.raw_best_use}, ${fmt1(c.raw_best_acres)} ac` : (c.aerial_qa ? 'Flagged: no raw land on aerial' : 'None (redevelopment)');
      else if (key === 'review') v = S.reviews[c.id]?.chase === 'yes' ? 'Would chase' : S.reviews[c.id]?.chase === 'no' ? "Won't chase" : '';
      else if (key === 'intersection_name') v = title(v);
      else if (key === 'market_type') v = String(v).startsWith('Proven') ? 'Proven' : 'White space';
      else if (key === 'dist_to_7eleven_mi' || key === 'score') v = fmt1(v);
      else if (cls === 'n') v = fmt(v);
      return `<td class="${cls || ''}">${esc(v)}</td>`; }).join('')}</tr>`).join('')}</tbody>`;
}
$('#rankTable').addEventListener('click', e => {
  const th = e.target.closest('th'); if (th) { const k = th.dataset.k; S.sort = { key: k, dir: S.sort.key === k ? -S.sort.dir : 1 }; renderTable(); return; }
  const tr = e.target.closest('tr[data-id]'); if (tr) { location.hash = '#map'; setTimeout(() => { map.invalidateSize(); select(tr.dataset.id, true); }, 50); }
});

/* ---------- downloads ---------- */
async function saveFile(filename, data) {
  if (!S.downloads) { toast('Downloads are not available in this view.'); return; }
  try { await S.downloads.save({ filename, data }); }
  catch (e) { if (e && e.code !== 'declined') toast(e.code === 'rate_limited' ? 'A save prompt is already open.' : 'Could not save the file.'); }
}
function xlsxBlob(sheets) {
  const wb = XLSX.utils.book_new();
  for (const [name, rows] of sheets) XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(rows), name.slice(0, 31));
  return new Blob([XLSX.write(wb, { bookType: 'xlsx', type: 'array' })]);
}
$('#exportList').onclick = () => {
  const rows = S.filtered.map(c => ({
    Rank: c.pos, Score: c.score, 'Raw land at corner': c.raw_ok ? 'Y' : 'N', 'Raw parcel use': c.raw_best_use || '', 'Raw parcel acres': c.raw_best_acres, 'Raw parcel ID': c.raw_best_parcel || '', 'Raw parcel owner': c.raw_best_owner || '', 'Aerial check': c.aerial_qa || '', Tier: c.tier, 'Top 50': c.top50 ? 'Y' : '', Intersection: title(c.intersection_name), County: c.county, 'RE manager': c.re_manager,
    Market: c.market_type, 'Why here': c.why_here, 'New homes 2023-25 (3 mi)': c.new_rooftops_3mi, 'Vacant platted lots (3 mi)': c.pipeline_lots_3mi,
    'Grocers on 2023+ parcels (3 mi)': c.new_grocers_3mi, 'Combined AADT': c.combined_aadt, Signal: c.signal, 'Nearest 7-Eleven (mi)': c.dist_to_7eleven_mi,
    'Nearest 7-Eleven': title(c.nearest_7eleven), 'Anchors 1/2 mi': c.anchors_half_mi, 'Nationals 1/2 mi': c.nationals_half_mi, 'Nearest competitor': c.nearest_competitor,
    'Access flag': c.access_flag, Review: S.reviews[c.id]?.chase || '', 'Review note': S.reviews[c.id]?.note || '', Lat: c.lat, Lon: c.lon, 'Google Maps': gmaps(c),
  }));
  const method = S.data.meta.method.map(m => ({ Item: m.Item, Method: m.Method }));
  saveFile(`7-Eleven candidates ${S.data.meta.built}.xlsx`, xlsxBlob([['Candidates', rows], ['Method', method]]));
};

/* ---------- packs ---------- */
function defaultPack(m) {
  const picked = [];
  for (const c of S.data.candidates.filter(c => c.re_manager === m && c.top50).sort((a, b) => b.score - a.score)) {
    if (picked.length >= 5) break; picked.push(c.id);
  }
  return picked;
}
function packIds(m) { return S.packs[m]?.ids?.length ? S.packs[m].ids.filter(id => S.data.byId[id]) : defaultPack(m); }
function miniMap(c) {
  const R = 3.2 * MI, W = 320, H = 200, k = Math.cos(c.lat * Math.PI / 180);
  const px = (la, lo) => [W / 2 + ((lo - c.lon) * 111320 * k) / R * (W / 2), H / 2 - ((la - c.lat) * 111320) / R * (W / 2)];
  const near = (la, lo) => Math.abs(la - c.lat) < 0.06 && Math.abs(lo - c.lon) < 0.07;
  let roads = '';
  for (const f of S.data.roads.features) {
    const lines = f.geometry.type === 'LineString' ? [f.geometry.coordinates] : f.geometry.type === 'MultiLineString' ? f.geometry.coordinates : [];
    for (const ln of lines) {
      if (!ln.some(([lo, la]) => near(la, lo))) continue;
      const d = ln.map(([lo, la], i) => (i ? 'L' : 'M') + px(la, lo).map(v => v.toFixed(1)).join(',')).join('');
      roads += `<path d="${d}" fill="none" stroke="${f.properties.cls === 'collector' ? '#9a9ca0' : '#5e636a'}" stroke-width="${f.properties.cls === 'interstate' ? 2.4 : f.properties.cls === 'arterial' ? 1.4 : 0.8}"/>`;
    }
  }
  const dots = (arr, col, r, test = () => true) => arr.filter(s => near(s.lat, s.lon) && test(s)).map(s => { const [x, y] = px(s.lat, s.lon); return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${r}" fill="${col}"/>`; }).join('');
  const ring = (mi, dash) => `<circle cx="${W / 2}" cy="${H / 2}" r="${(mi * MI) / R * (W / 2)}" fill="none" stroke="#3333cc" stroke-width="1" ${dash ? 'stroke-dasharray="4 3"' : ''}/>`;
  return `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Map of ${esc(title(c.intersection_name))} and surroundings">
    <rect width="${W}" height="${H}" fill="#faf8f4"/>${roads}${ring(3, true)}
    ${dots(S.data.competitors, '#b4542d', 2.6)}${dots(S.data.stores, '#1c1a42', 3.4)}
    <circle cx="${W / 2}" cy="${H / 2}" r="6" fill="#3333cc" stroke="#fff" stroke-width="2"/>
    <rect x="0" y="${H - 18}" width="${W}" height="18" fill="#faf8f4" opacity="0.92"/>
    <text x="6" y="${H - 6}" font-family="Montserrat, Arial" font-size="9" fill="#5e636a">Dashed ring: 3-mile trade area · navy: 7-Eleven · rust: competitor</text></svg>`;
}
function renderPacks() {
  $('#packs').innerHTML = `<div class="packgrid">${MANAGERS.map(m => {
    const ids = packIds(m), pinned = !!S.packs[m]?.ids?.length;
    return `<section class="pack"><div class="packhead"><div><div class="eyebrow">${pinned ? 'Pinned by the team' : 'Default: top Tier A in territory'}</div><h2>${esc(MGR_FULL[m])}</h2></div>
      <div class="btnrow"><button class="btn small" data-word="${m}">Download Word pack</button><button class="btn ghost small" data-copy="${m}">Copy as text</button>${pinned ? `<button class="btn ghost small" data-reset="${m}">Reset to default</button>` : ''}</div></div>
      ${ids.length ? `<div class="areas">${ids.map(id => { const c = S.data.byId[id]; return `<article class="area">
        <div class="eyebrow">${esc(c.county)} County · Tier ${c.tier}</div><h3>${esc(title(c.intersection_name))}</h3>${miniMap(c)}
        <p class="why">${esc(pitchLine(c))}</p>
        <dl class="kv"><dt>New homes 2023–25, 3 mi</dt><dd>${fmt(c.new_rooftops_3mi)}</dd><dt>Combined AADT</dt><dd>${c.combined_aadt == null ? 'No count' : fmt(c.combined_aadt)}</dd>
        <dt>Nearest 7-Eleven</dt><dd>${fmt1(c.dist_to_7eleven_mi)} mi</dd><dt>Anchors ½ mi</dt><dd style="font-weight:400">${esc(c.anchors_half_mi || 'None')}</dd></dl>
        <div class="btnrow"><button class="btn ghost small" data-open="${c.id}">Open on map</button><a class="btn ghost small" href="${gmaps(c)}" target="_blank" rel="noopener">Google Maps</a></div></article>`; }).join('')}</div>`
        : `<p class="empty">No Top 50 corners in this territory yet. Pin candidates from the map.</p>`}</section>`;
  }).join('')}</div>`;
}
function pitchLine(c) {
  const bits = [`${fmt(c.new_rooftops_3mi)} homes built in 2023–25 within 3 miles`];
  if (c.combined_aadt) bits.push(`${fmt(c.combined_aadt)} vehicles a day on the two roads`);
  bits.push(`the nearest 7-Eleven is ${fmt1(c.dist_to_7eleven_mi)} miles away`);
  if (c.anchors_half_mi) bits.push(`${c.anchors_half_mi} within half a mile`);
  return bits.join('; ') + '.';
}
$('#packs').addEventListener('click', async e => {
  const b = e.target.closest('button'); if (!b) return;
  if (b.dataset.open) { location.hash = '#map'; setTimeout(() => { map.invalidateSize(); select(b.dataset.open, true); }, 50); }
  if (b.dataset.copy) {
    const m = b.dataset.copy; const txt = `${MGR_FULL[m]} — target areas from ECP Partners\n\n` + packIds(m).map((id, i) => { const c = S.data.byId[id]; return `${i + 1}. ${title(c.intersection_name)} (${c.county} County)\n   ${pitchLine(c)}\n   ${gmaps(c)}`; }).join('\n\n');
    try { await navigator.clipboard.writeText(txt); toast('Copied.'); } catch { toast('Copy was blocked by the browser.'); }
  }
  if (b.dataset.reset) { await writePack(b.dataset.reset, []); }
  if (b.dataset.word) await wordPack(b.dataset.word);
});
async function svgToPng(svg) {
  const img = new Image(); const url = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml' }));
  await new Promise((res, rej) => { img.onload = res; img.onerror = rej; img.src = url; });
  const cv = document.createElement('canvas'); cv.width = 640; cv.height = 400;
  cv.getContext('2d').drawImage(img, 0, 0, 640, 400); URL.revokeObjectURL(url);
  return new Uint8Array(await (await new Promise(r => cv.toBlob(r, 'image/png'))).arrayBuffer());
}
async function wordPack(m) {
  if (!window.docx) { toast('Word export library did not load.'); return; }
  const D = window.docx; const kids = [];
  const P = (text, o = {}) => new D.Paragraph({ children: [new D.TextRun({ text, font: o.font || 'Montserrat', size: o.size || 20, bold: o.bold, color: o.color || '1C1A42' })], spacing: { after: o.after ?? 120 }, heading: o.heading });
  kids.push(P('ECP PARTNERS · CONFIDENTIAL', { size: 16, bold: true, color: '3333CC' }));
  kids.push(P(`Target areas for ${MGR_FULL[m].split(' · ')[0]}`, { font: 'Source Serif 4', size: 40, after: 80 }));
  kids.push(P(`${MGR_FULL[m].split(' · ')[1]} · Prepared ${new Date().toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })}`, { color: '5E636A', after: 240 }));
  const ids = packIds(m);
  for (let i = 0; i < ids.length; i++) {
    const c = S.data.byId[ids[i]];
    kids.push(new D.Paragraph({ children: [new D.TextRun({ text: `${i + 1}. ${title(c.intersection_name)}`, font: 'Source Serif 4', size: 30 })], spacing: { before: i ? 360 : 0, after: 60 }, pageBreakBefore: i > 0 }));
    kids.push(P(`${c.county} County`, { color: '5E636A' }));
    try { kids.push(new D.Paragraph({ children: [new D.ImageRun({ data: await svgToPng(miniMap(c)), transformation: { width: 480, height: 300 } })], spacing: { after: 120 } })); } catch { /* map image is optional */ }
    kids.push(P(pitchLine(c), { after: 160 }));
    const row = (a, b) => new D.TableRow({ children: [a, b].map((t, j) => new D.TableCell({ width: { size: j ? 3000 : 6000, type: D.WidthType.DXA }, children: [new D.Paragraph({ children: [new D.TextRun({ text: String(t), font: 'Montserrat', size: 18, bold: j === 1 })] })] })) });
    kids.push(new D.Table({ width: { size: 9000, type: D.WidthType.DXA }, rows: [
      row('Homes built 2023–25 within 3 miles (FL DOR tax roll)', fmt(c.new_rooftops_3mi)),
      row('Combined traffic, vehicles per day (FDOT 2025)', c.combined_aadt == null ? 'No count' : fmt(c.combined_aadt)),
      row('Nearest 7-Eleven', `${fmt1(c.dist_to_7eleven_mi)} mi`),
      row('Anchors within ½ mile', c.anchors_half_mi || 'None'),
      row('Raw land at the corner (FL DOR)', c.raw_ok ? `${c.raw_best_use}, ${fmt1(c.raw_best_acres)} acres` : 'None'),
      row('Signalized intersection', c.signal),
      row('Market', c.market_type),
    ] }));
    kids.push(P(`Location: ${c.lat}, ${c.lon} · ${gmaps(c)}`, { size: 16, color: '5E636A' }));
  }
  kids.push(P('Sources: FL Dept. of Revenue 2026 tax roll; FDOT 2025 traffic counts; FDEP storage-tank registry and 7-Eleven store data. Prepared by ECP Partners for discussion; not an offer.', { size: 16, color: '5E636A' }));
  const doc = new D.Document({ sections: [{ properties: {}, children: kids }] });
  const blob = await D.Packer.toBlob(doc);
  saveFile(`ECP target areas - ${m} - ${S.data.meta.built}.docx`, blob);
}

/* ---------- shared data (db) ---------- */
async function showName(id) {
  if (!id) return 'Someone';
  if (S.names[id]) return S.names[id];
  try { const ps = await S.user.profiles([id]); S.names[id] = (ps[id] && ps[id].name) || 'Someone'; } catch { S.names[id] = 'Someone'; }
  return S.names[id];
}
async function myId() { try { return S.user ? await S.user.id() : null; } catch { return null; } }
async function saveReview(c) {
  if (!S.db) { toast('Not connected to the shared database.'); return; }
  const chase = [...document.querySelectorAll('[data-chase]')].find(b => b.getAttribute('aria-pressed') === 'true')?.dataset.chase || '';
  const body = { candidateId: c.id, intersection: c.intersection_name, chase, accessVerified: $('#accessOk').checked, note: $('#revNote').value.trim().slice(0, 2000), by: await myId(), at: new Date().toISOString() };
  try { await S.db.collection('reviews').doc(c.id).set(body); toast('Review saved.'); }
  catch (e) { toast(e?.code === 'invalid_argument' ? 'You have view-only access, so reviews can’t be saved.' : 'Could not save. Try again.'); }
}
async function writePack(m, ids) {
  if (!S.db) { toast('Not connected to the shared database.'); return; }
  try { await S.db.collection('packs').doc(m).set({ ids, by: await myId(), at: new Date().toISOString() }); toast(ids.length ? 'Pack updated.' : 'Pack reset to default.'); }
  catch { toast('Could not update the pack.'); }
}
async function togglePack(c) {
  const m = c.re_manager; let ids = [...(S.packs[m]?.ids?.length ? S.packs[m].ids : defaultPack(m))];
  ids = ids.includes(c.id) ? ids.filter(x => x !== c.id) : [...ids, c.id];
  await writePack(m, ids);
}
function listen() {
  const t = setTimeout(() => { $('#logNote').textContent = 'The shared log is taking a while to load. What you see may be out of date.'; }, 10000);
  S.db.collection('reviews').onSnapshot(s => { S.reviews = Object.fromEntries(s.docs.map(d => [d.id, d.data()])); renderList(); renderTable(); if (S.sel) renderDetail(S.data.byId[S.sel]); }, () => {});
  S.db.collection('packs').onSnapshot(s => { S.packs = Object.fromEntries(s.docs.map(d => [d.id, d.data()])); renderPacks(); }, () => {});
  S.db.collection('submittals').orderBy('dateSent', 'desc').onSnapshot(s => {
    if (!s.metadata.fromCache) { clearTimeout(t); $('#logNote').textContent = ''; }
    S.subs = s.docs.map(d => ({ id: d.id, ...d.data() })); renderLog();
  }, () => { clearTimeout(t); $('#logNote').textContent = 'The shared log could not be loaded.'; });
}

/* ---------- submittal log ---------- */
function openSubForm(pre = {}) {
  const f = $('#subForm'); f.hidden = false;
  const cand = pre.candidateId ? S.data.byId[pre.candidateId] : null;
  const s = pre.id ? S.subs.find(x => x.id === pre.id) : {};
  const v = (k, d = '') => esc(s[k] ?? d);
  f.innerHTML = `
    <label class="full">Candidate intersection (optional)
      <select id="sCand"><option value="">Not from the list</option>${S.data.candidates.slice().sort((a, b) => a.intersection_name.localeCompare(b.intersection_name)).map(c => `<option value="${c.id}" ${(s.candidateId || cand?.id) === c.id ? 'selected' : ''}>${esc(title(c.intersection_name))} · ${esc(c.county)}</option>`).join('')}</select></label>
    <label>Site address or parcel<input type="text" id="sSite" value="${v('site', cand ? title(cand.intersection_name) : '')}"></label>
    <label>RE manager<select id="sMgr">${[...MANAGERS, 'McDonald', 'Other'].map(m => `<option ${(s.manager || cand?.re_manager) === m ? 'selected' : ''}>${m}</option>`).join('')}</select></label>
    <label>Date sent<input type="date" id="sDate" value="${v('dateSent', new Date().toISOString().slice(0, 10))}"></label>
    <label>Status<select id="sStatus">${STATUSES.map(x => `<option ${s.status === x ? 'selected' : ''}>${x}</option>`).join('')}</select></label>
    <label>Response date<input type="date" id="sResp" value="${v('responseDate')}"></label>
    <label>Pass reason<select id="sReason">${PASS_REASONS.map(x => `<option ${s.passReason === x ? 'selected' : ''}>${x}</option>`).join('')}</select></label>
    <label>Acres<input type="text" id="sAcres" value="${v('acres')}" inputmode="decimal"></label>
    <label class="full">Notes (what 7-Eleven said, in their words if you have them)<textarea id="sNotes">${v('notes')}</textarea></label>
    <div class="btnrow full"><button class="btn" type="submit">${pre.id ? 'Save changes' : 'Add to log'}</button><button class="btn ghost" type="button" id="sCancel">Cancel</button>
      ${pre.id ? '<button class="btn ghost" type="button" id="sDelete">Delete</button>' : ''}</div>`;
  f.onsubmit = async e => {
    e.preventDefault();
    if (!S.db) { toast('Not connected to the shared database.'); return; }
    const cid = $('#sCand').value; const c = S.data.byId[cid];
    const body = { candidateId: cid || null, intersection: c ? c.intersection_name : null, score: c ? c.score : null, site: $('#sSite').value.trim(), manager: $('#sMgr').value,
      dateSent: $('#sDate').value, status: $('#sStatus').value, responseDate: $('#sResp').value, passReason: $('#sReason').value, acres: $('#sAcres').value.trim(),
      notes: $('#sNotes').value.trim().slice(0, 4000), by: s.by || await myId(), updatedBy: await myId(), updatedAt: new Date().toISOString() };
    if (!body.site) { toast('Add the site address first.'); return; }
    try { pre.id ? await S.db.collection('submittals').doc(pre.id).set(body) : await S.db.collection('submittals').add(body); f.hidden = true; toast('Saved to the log.'); }
    catch (e2) { toast(e2?.code === 'invalid_argument' ? 'You have view-only access, so the log can’t be changed.' : e2?.code === 'quota_exceeded' ? 'The log is full. Delete old test rows.' : 'Could not save. Try again.'); }
  };
  $('#sCancel').onclick = () => { f.hidden = true; };
  if ($('#sDelete')) $('#sDelete').onclick = async () => { if (!$('#sDelete').dataset.armed) { $('#sDelete').dataset.armed = 1; $('#sDelete').textContent = 'Click again to delete'; return; } await S.db.collection('submittals').doc(pre.id).delete(); f.hidden = true; toast('Deleted.'); };
  f.scrollIntoView({ block: 'start' });
}
async function renderLog() {
  const t = $('#logTable');
  if (!S.db) { t.innerHTML = ''; $('#logNote').textContent = 'The log needs the page’s shared database, which isn’t available in this view.'; return; }
  if (!S.subs.length) { t.innerHTML = '<tbody><tr><td class="empty">No submittals logged yet. Log each site when it goes to 7-Eleven, including the ones they pass on.</td></tr></tbody>'; return; }
  const ids = [...new Set(S.subs.map(s => s.by).filter(Boolean))];
  if (S.user && ids.length) { try { const ps = await S.user.profiles(ids); ids.forEach(i => S.names[i] = (ps[i] && ps[i].name) || 'Someone'); } catch { } }
  t.innerHTML = `<thead><tr><th>Date sent</th><th>Site</th><th>Manager</th><th>Status</th><th>Response</th><th>Pass reason</th><th>Model score</th><th>Notes</th><th>Logged by</th></tr></thead><tbody>
    ${S.subs.map(s => `<tr data-sub="${s.id}"><td class="n">${esc(s.dateSent)}</td><td>${esc(s.site)}${s.intersection ? `<br><span class="src">${esc(title(s.intersection))}</span>` : ''}</td><td>${esc(s.manager)}</td>
      <td><span class="status ${esc(s.status)}">${esc(s.status)}</span></td><td class="n">${esc(s.responseDate)}</td><td>${esc(s.passReason)}</td><td class="n">${s.score == null ? '—' : fmt1(s.score)}</td>
      <td class="wrap">${esc(s.notes)}</td><td>${esc(S.names[s.by] || '')}</td></tr>`).join('')}</tbody>`;
}
$('#logTable').addEventListener('click', e => { const tr = e.target.closest('tr[data-sub]'); if (tr) openSubForm({ id: tr.dataset.sub }); });
$('#newSub').onclick = () => openSubForm();
$('#exportLog').onclick = () => saveFile(`7-Eleven submittal log ${new Date().toISOString().slice(0, 10)}.xlsx`, xlsxBlob([['Submittals', S.subs.map(s => ({
  'Date sent': s.dateSent, Site: s.site, Intersection: s.intersection ? title(s.intersection) : '', 'RE manager': s.manager, Status: s.status, 'Response date': s.responseDate,
  'Pass reason': s.passReason, Acres: s.acres, 'Model score': s.score, Notes: s.notes, 'Logged by': S.names[s.by] || '' }))]]));

/* ---------- methods ---------- */
function renderMethods() {
  const m = S.data.meta, bt = S.data.backtest;
  const wo = m.weight_options || [];
  $('#methods').innerHTML = `
    <section><div class="eyebrow">How the score works</div><h2>Weights in use</h2>
      <p class="muted">Option B, approved by Ross on November 10, 2026 after the backtest. Filters first: 2+ miles from any 7-Eleven or Speedway fuel store, an intersection of two FDOT arterial or collector roads, and (by default, approved November 11) a raw parcel of 1.3+ acres touching the corner.</p>
      <div class="tablewrap"><table class="grid"><thead><tr><th>Factor</th><th>Points</th></tr></thead><tbody>${FACTORS.map(([k, l]) => `<tr><td>${l}</td><td class="n">${m.weights[k]}</td></tr>`).join('')}</tbody></table></div></section>
    <section><div class="eyebrow">Does it find where 7-Eleven builds?</div><h2>Backtest</h2>
      <p class="muted">The ${bt.length} pilot 7-Elevens built since 2018 were scored at their own corners and ranked against all ${fmt(m.counts.intersections)} pilot intersections. Rooftop counts are as of today, not when 7-Eleven chose each site.</p>
      <div class="tablewrap"><table class="grid"><thead><tr>${Object.keys(wo[0] || {}).map(k => `<th>${esc(k)}</th>`).join('')}</tr></thead><tbody>${wo.map(r => `<tr>${Object.values(r).map(v => `<td>${esc(v)}</td>`).join('')}</tr>`).join('')}</tbody></table></div></section>
    <section><div class="eyebrow">Method</div><h2>Definitions</h2>
      <div class="tablewrap"><table class="grid"><tbody>${m.method.map(r => `<tr><td style="white-space:nowrap;font-weight:600">${esc(r.Item)}</td><td>${esc(r.Method)}</td></tr>`).join('')}</tbody></table></div></section>
    <section><div class="eyebrow">Where the numbers come from</div><h2>Sources and dates</h2>
      <div class="keyrow"><span><b>Hard data</b>: as published by the source</span><span><b>ECP data</b>: from ECP's own files</span><span><b>Inference</b>: derived by Claude; verify before relying on it</span></div>
      <div class="tablewrap" style="margin-top:10px"><table class="grid"><thead><tr><th>Dataset</th><th>Source</th><th>As of</th><th>Data class</th></tr></thead><tbody>${m.sources.map(r => `<tr><td>${esc(r.Dataset)}</td><td class="wrap">${esc(r.Source)}</td><td>${esc(r['As of'])}</td><td class="wrap">${esc(r['Data class'])}</td></tr>`).join('')}</tbody></table></div></section>
    <section><div class="eyebrow">Known limits</div><h2>Data gaps</h2>
      <div class="tablewrap"><table class="grid"><thead><tr><th>Gap</th><th>Detail</th><th>Fix</th></tr></thead><tbody>${m.gaps.map(r => `<tr><td>${esc(r.Gap)}</td><td class="wrap">${esc(r.Detail)}</td><td class="wrap">${esc(r.Fix)}</td></tr>`).join('')}</tbody></table></div></section>
    <section><p class="muted">Confidential to ECP Partners. Do not share with brokers or other developers. The map has no street basemap: artifact pages can't load map tiles, so use the Google Maps link on each corner for aerials.</p></section>`;
}

/* ---------- Claude ---------- */
function candBrief(c) {
  return { id: c.id, rank: c.rank, score: c.score, tier: c.tier, intersection: title(c.intersection_name), county: c.county, re_manager: c.re_manager, market: c.market_type,
    new_homes_2023_25_3mi: c.new_rooftops_3mi, vacant_platted_lots_3mi: c.pipeline_lots_3mi, grocers_on_2023plus_parcels_3mi: c.new_grocers_3mi,
    combined_aadt: c.combined_aadt, signal: c.signal, raw_land_at_corner: c.raw_ok ? `${c.raw_best_use}, ${c.raw_best_acres} ac` : 'none (redevelopment)', miles_to_nearest_7eleven: Number(fmt1(c.dist_to_7eleven_mi)), nearest_7eleven: title(c.nearest_7eleven),
    anchors_half_mi: c.anchors_half_mi, nationals_half_mi: c.nationals_half_mi, nearest_competitor: c.nearest_competitor, access_flag: c.access_flag,
    deal_maker_review: S.reviews[c.id] ? { chase: S.reviews[c.id].chase, note: S.reviews[c.id].note } : null };
}
async function draftPitch(c) {
  const out = $('#draftOut'); out.textContent = 'Drafting…'; $('#draftBtn').disabled = true;
  const prompt = `You help ECP Partners, a Florida build-to-suit developer, bring target areas to 7-Eleven's real estate managers.
Write a short note (90-130 words) Ross could use with 7-Eleven RE manager ${c.re_manager} about the corner below. Voice: plain, warm, direct, specific, first person plural; no hype words (premier, leading), no exclamation points. Use only the numbers given; say "about" for rounded figures. Say what ECP would do next (search for a 1.3+ acre corner parcel with access on both roads). If access_flag is set, mention it as something ECP will verify. End with one question for the manager.
Then on a new line starting "Check:", list any claim in your note that depends on an inference (grocer ages and "proven market" are inferences from parcel year built).
Corner data (JSON): ${JSON.stringify(candBrief(c))}`;
  try {
    await S.sample(prompt, { modelTier: 'default', onText: ({ text }) => { out.textContent = text; } });
  } catch (e) {
    out.textContent = e?.code === 'not_granted' ? 'Claude drafting is turned off for this page.' : e?.code === 'rate_limited' ? 'Too many requests. Try again in a minute.' : 'Claude could not draft this right now.';
    if (e?.code === 'not_granted') $('#claudeBlock').hidden = true;
  } finally { const b = $('#draftBtn'); if (b) b.disabled = false; }
}
async function ask() {
  const q = $('#askInput').value.trim(); if (!q) return;
  const out = $('#askOut'); out.textContent = 'Thinking…'; $('#askBtn').disabled = true;
  const tools = [{
    name: 'search_candidates',
    description: 'Search scored 7-Eleven candidate intersections in the 8 pilot counties. Returns up to `limit` rows sorted by `sort` (descending).',
    inputSchema: { type: 'object', properties: {
      re_manager: { type: 'string', enum: MANAGERS }, county: { type: 'string', description: 'One of: ' + [...new Set(S.data.candidates.map(c => c.county))].join(', ') },
      tier: { type: 'string', enum: ['A', 'B', 'C'] }, market: { type: 'string', enum: ['Proven', 'White space'] },
      min_new_homes: { type: 'number' }, min_aadt: { type: 'number' }, min_miles_to_7eleven: { type: 'number' }, requires_anchor: { type: 'boolean' },
      include_redevelopment: { type: 'boolean', description: 'Include corners with no raw 1.3+ acre parcel. Default false.' }, min_raw_acres: { type: 'number' },
      name_contains: { type: 'string' }, sort: { type: 'string', enum: ['score', 'new_rooftops_3mi', 'combined_aadt', 'dist_to_7eleven_mi'] }, limit: { type: 'number' } } },
    execute(a) {
      let r = S.data.candidates.filter(c => (a.include_redevelopment || c.raw_ok) && (!a.min_raw_acres || (c.raw_best_acres || 0) >= a.min_raw_acres) && (!a.re_manager || c.re_manager === a.re_manager) && (!a.county || c.county.toLowerCase() === String(a.county).toLowerCase())
        && (!a.tier || c.tier === a.tier) && (!a.market || (a.market === 'Proven') === c.market_type.startsWith('Proven'))
        && (!a.min_new_homes || c.new_rooftops_3mi >= a.min_new_homes) && (!a.min_aadt || (c.combined_aadt || 0) >= a.min_aadt)
        && (!a.min_miles_to_7eleven || c.dist_to_7eleven_mi >= a.min_miles_to_7eleven) && (!a.requires_anchor || c.anchors_half_mi)
        && (!a.name_contains || c.intersection_name.toLowerCase().includes(String(a.name_contains).toLowerCase())));
      const k = a.sort || 'score'; r.sort((x, y) => (y[k] || 0) - (x[k] || 0));
      return { total_matches: r.length, rows: r.slice(0, Math.min(a.limit || 10, 25)).map(candBrief) };
    },
  }];
  const prompt = `You answer questions from ECP Partners' deal makers about scored 7-Eleven candidate corners. Use the search_candidates tool; never invent corners or numbers. Answer in plain sentences, under 160 words, naming intersections with their rank and score. Say when a number is an inference (grocer ages, "proven" market) or missing (no traffic count). By default only corners with a raw (vacant or agricultural) parcel of 1.3+ acres count; about 72% of Florida 7-Eleven build-to-suits were built on raw land. Scoring: new homes 30, traffic 25, grocery 10, gap to 7-Eleven 10, retail node 10, signal 10, platted lots 5.
Question: ${q}`;
  try {
    await S.sample(prompt, { tools, modelTier: 'default', onText: ({ text }) => { out.textContent = text; } });
  } catch (e) {
    out.textContent = e?.code === 'not_granted' ? 'Claude is turned off for this page.' : e?.code === 'rate_limited' ? 'Too many requests. Try again in a minute.' : 'Claude could not answer right now.';
  } finally { $('#askBtn').disabled = false; }
}

/* ---------- routing ---------- */
function route() {
  const v = (location.hash || '#map').slice(1);
  const views = ['map', 'list', 'packs', 'log', 'methods'];
  const cur = views.includes(v) ? v : 'map';
  views.forEach(x => { $('#view-' + x).hidden = x !== cur; });
  document.querySelectorAll('.tabs a').forEach(a => { if (a.dataset.view === cur) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
  $('.filters').hidden = !['map', 'list'].includes(cur);
  if (cur === 'map' && map) setTimeout(() => map.invalidateSize(), 30);
}
window.addEventListener('hashchange', route);

/* ---------- boot ---------- */
(async function boot() {
  route();
  try { S.data = await loadData(); }
  catch { $('#metaLine').textContent = 'The data files could not be loaded.'; return; }
  const m = S.data.meta;
  $('#metaLine').innerHTML = `Pilot: 8 counties · ${fmt(m.counts.raw_ok)} raw-land corners (${m.counts.tierA_raw} Tier A) · ${fmt(m.counts.candidates)} incl. redevelopment · Data built ${esc(m.built)}`;
  const counties = [...new Set(S.data.candidates.map(c => c.county))].sort();
  $('#fCounty').insertAdjacentHTML('beforeend', counties.map(c => `<option>${esc(c)}</option>`).join(''));
  ['#fManager', '#fCounty', '#fTier', '#fMarket', '#fTop', '#fRedev'].forEach(s => $(s).addEventListener('change', applyFilters));
  $('#fSearch').addEventListener('input', () => { clearTimeout(boot._t); boot._t = setTimeout(applyFilters, 200); });
  initMap(); applyFilters(); renderPacks(); renderMethods(); renderLog();
  $('#askBtn').onclick = ask; $('#askInput').addEventListener('keydown', e => { if (e.key === 'Enter') ask(); });
  if (window.claude && claude.use) {
    claude.use('db').then(db => { if (db) { S.db = db; listen(); } else renderLog(); });
    claude.use('user').then(u => { S.user = u; });
    claude.use('sample').then(s => { if (s) { S.sample = s; $('#askBox').hidden = false; if (S.sel) renderDetail(S.data.byId[S.sel]); } });
    claude.use('downloads').then(d => { S.downloads = d; if (!d) { $('#exportList').hidden = true; $('#exportLog').hidden = true; } });
  } else { renderLog(); $('#exportList').hidden = true; $('#exportLog').hidden = true; }
})();
})();
