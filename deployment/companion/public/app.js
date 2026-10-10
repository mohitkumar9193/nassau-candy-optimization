/* Default exported snapshot; calculations stay in the Python dashboard. */
(async function () {
  'use strict';
  const byId = id => document.getElementById(id);
  const text = (id, value) => { byId(id).textContent = value; };
  const fmt = value => value === null ? 'N/A' : Number(value).toLocaleString('en-US', {maximumFractionDigits: 2, minimumFractionDigits: 2});
  function publicUrl(value) {
    try { const url = new URL(value); return url.protocol === 'https:' && !url.username && !url.password && !['localhost','127.0.0.1','[::1]'].includes(url.hostname) ? url.href : null; } catch { return null; }
  }
  for (const [key,id] of [['dashboard','dashboard-link'],['github','github-link']]) {
    const url = publicUrl((window.PROJECT_LINKS || {})[key]);
    if (url) { byId(id).href = url; byId(id).hidden = false; if(key === 'dashboard') byId('dashboard-pending').hidden = true; }
  }
  try {
    const response = await fetch('project-data.json');
    if (!response.ok) throw new Error('Snapshot unavailable');
    const data = await response.json();
    const k = data.kpis;
    text('lead',fmt(k.modeled_lead_time_reduction_pct)+'%');
    text('stability',fmt(k.profit_impact_stability_pct)+'%');
    text('confidence',fmt(k.scenario_confidence_score)+'/100');
    text('coverage',fmt(k.recommendation_coverage_pct)+'%');
    const select = byId('product'); select.replaceChildren();
    for (const item of data.products) { const option = document.createElement('option'); option.value = item.id; option.textContent = item.name; select.appendChild(option); }
    function update() {
      const item = data.products.find(p => p.id === select.value);
      text('product-name',item.name);text('current',item.current);text('selected',item.selected);
      text('decision',item.decision);text('product-lead',fmt(item.dispatch_reduction_pct)+'%');
      text('product-profit',fmt(item.contribution_change));
    }
    select.disabled = false; select.value = data.products.find(p => p.id === 'CHO-MIL-31000')?.id || data.products[0].id;
    select.addEventListener('change',update); update();
  } catch (error) { byId('load-error').hidden = false; }
})();
