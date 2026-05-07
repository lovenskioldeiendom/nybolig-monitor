"""
Genererer statisk dashboard/index.html fra databasen.

Kjøres etter scraperen:
    python build_dashboard.py
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scraper.database import (
    get_latest_snapshots,
    compute_sales_stats,
    get_project_history,
    get_current_units,
    get_recent_changes,
)

OUT_DIR = Path(__file__).parent / "dashboard"
OUT_FILE = OUT_DIR / "index.html"


def build_data() -> dict:
    """Bygger JSON-strukturen for dashbordet."""
    snapshots = get_latest_snapshots()

    projects = []
    for s in snapshots:
        finn_code = s["finn_code"]
        history = get_project_history(finn_code, days=365)
        units = get_current_units(finn_code)
        changes_week = get_recent_changes(finn_code, days_back=7)
        changes_month = get_recent_changes(finn_code, days_back=30)

        projects.append({
            "finn_code": finn_code,
            "title": s["project_title"],
            "address": s["address"],
            "municipality": s["municipality"],
            "sales_stage": s["sales_stage"],
            "units_total": s["units_total"],
            "units_for_sale": s["units_for_sale"],
            "units_sold": s["units_sold"],
            "avg_price_per_m2": s["avg_price_per_m2"],
            "min_price": s["min_price"],
            "max_price": s["max_price"],
            "url": s["project_url"],
            "scraped_at": s["scraped_at"],
            "sold_last_week": compute_sales_stats(finn_code, 7),
            "sold_last_month": compute_sales_stats(finn_code, 30),
            "sold_last_year": compute_sales_stats(finn_code, 365),
            "history": history,
            "units": units,
            "changes_week": changes_week,
            "changes_month": changes_month,
        })

    projects.sort(key=lambda p: (p["municipality"] or "", p["title"] or ""))

    return {
        "updated": projects[0]["scraped_at"][:10] if projects else None,
        "projects": projects,
    }


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="nb">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Nyboligprosjekter Akershus</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js"></script>
<style>
  :root {
    --bg: #ffffff;
    --bg-secondary: #f5f4ee;
    --bg-tertiary: #faf9f4;
    --text: #1a1a1a;
    --text-muted: #6b6b6b;
    --text-faint: #999;
    --border: #e5e3dc;
    --accent: #185fa5;
    --success: #0f6e56;
    --warning: #854f0b;
    --danger: #a32d2d;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #1a1a1a;
      --bg-secondary: #252525;
      --bg-tertiary: #1e1e1e;
      --text: #e8e8e8;
      --text-muted: #a0a0a0;
      --text-faint: #707070;
      --border: #353535;
      --accent: #85B7EB;
      --success: #5DCAA5;
      --warning: #EF9F27;
      --danger: #F09595;
    }
  }
  * { box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
    background: var(--bg);
    color: var(--text);
    margin: 0;
    padding: 1.5rem;
    line-height: 1.5;
  }
  .container { max-width: 1300px; margin: 0 auto; }
  h1 { font-size: 22px; font-weight: 500; margin: 0; }
  h2 { font-size: 16px; font-weight: 500; margin: 0 0 12px; }
  h3 { font-size: 14px; font-weight: 500; margin: 0 0 8px; color: var(--text-muted); }
  .header { display: flex; align-items: baseline; justify-content: space-between;
            margin-bottom: 1.5rem; flex-wrap: wrap; gap: 8px; }
  .updated { font-size: 13px; color: var(--text-muted); margin: 4px 0 0; }
  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
           gap: 12px; margin-bottom: 1.5rem; }
  .stat { background: var(--bg-secondary); border-radius: 8px; padding: 1rem; }
  .stat-label { font-size: 13px; color: var(--text-muted); margin: 0; }
  .stat-value { font-size: 24px; font-weight: 500; margin: 4px 0 0; }
  .card { background: var(--bg); border: 1px solid var(--border); border-radius: 12px;
          padding: 1rem 1.25rem; margin-bottom: 1.5rem; }
  .controls { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
  .controls select, .controls input {
    font-size: 13px; padding: 6px 10px; background: var(--bg-secondary);
    color: var(--text); border: 1px solid var(--border); border-radius: 6px;
  }
  table { width: 100%; font-size: 13px; border-collapse: collapse; }
  th { text-align: left; padding: 8px 6px; font-weight: 500; color: var(--text-muted);
       border-bottom: 1px solid var(--border); font-size: 11px; text-transform: uppercase;
       letter-spacing: 0.04em; }
  th.num, td.num { text-align: right; font-variant-numeric: tabular-nums; }
  td { padding: 10px 6px; border-bottom: 1px solid var(--border); vertical-align: top; }
  td.muni { font-size: 11px; color: var(--text-faint); text-transform: uppercase;
            letter-spacing: 0.04em; }
  .stage-pill { display: inline-block; font-size: 11px; padding: 2px 8px;
                border-radius: 10px; background: var(--bg-secondary);
                color: var(--text-muted); margin-left: 6px; }
  a { color: var(--accent); text-decoration: none; }
  a:hover { text-decoration: underline; }
  .footer { font-size: 12px; color: var(--text-faint); margin-top: 2rem; text-align: center; }
  .empty { color: var(--text-muted); padding: 2rem; text-align: center; }
  .num-zero { color: var(--text-faint); }
  .expander {
    display: inline-block; width: 18px; height: 18px;
    text-align: center; cursor: pointer;
    color: var(--text-muted);
    font-size: 11px; line-height: 18px;
    user-select: none; transition: transform 0.15s;
  }
  .expander.open { transform: rotate(90deg); }
  tr.detail-row > td {
    padding: 0; background: var(--bg-tertiary);
    border-bottom: 2px solid var(--border);
  }
  .detail-content { padding: 16px 20px; }
  .detail-section { margin-bottom: 18px; }
  .detail-section:last-child { margin-bottom: 0; }
  .unit-table { font-size: 12px; }
  .unit-table th { padding: 6px 8px; }
  .unit-table td { padding: 6px 8px; }
  .download-btn {
    font-size: 12px; padding: 6px 12px; background: var(--bg);
    color: var(--text); border: 1px solid var(--border);
    border-radius: 6px; cursor: pointer; margin-left: 8px;
  }
  .download-btn:hover { background: var(--bg-secondary); }
  .badge {
    display: inline-block; padding: 1px 6px; font-size: 10px;
    border-radius: 8px; margin: 2px;
    background: var(--bg-secondary); color: var(--text-muted);
  }
  .badge-sold { background: rgba(15, 110, 86, 0.15); color: var(--success); }
  .badge-up { background: rgba(163, 45, 45, 0.15); color: var(--danger); }
  .badge-down { background: rgba(15, 110, 86, 0.15); color: var(--success); }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div>
      <h1>Nyboligprosjekter Akershus</h1>
      <p class="updated">Asker, Bærum, Nordre Follo, Ås · Sist oppdatert: <span id="updated-date">—</span></p>
    </div>
  </div>

  <div class="stats" id="stats"></div>

  <div class="card">
    <div class="controls">
      <select id="muni-filter">
        <option value="">Alle kommuner</option>
      </select>
      <input id="search" type="search" placeholder="Søk prosjekt..." style="flex: 1; min-width: 180px;">
    </div>
    <div style="overflow-x: auto;">
      <table>
        <thead>
          <tr>
            <th style="width: 24px;"></th>
            <th>Prosjekt</th>
            <th class="num">Til salgs</th>
            <th class="num">Solgt</th>
            <th class="num">Pris/m²</th>
            <th class="num">Siste uke</th>
            <th class="num">Siste måned</th>
            <th class="num">Siste 12 mnd</th>
          </tr>
        </thead>
        <tbody id="project-table"></tbody>
      </table>
    </div>
    <div id="empty-msg" class="empty" style="display:none;">Ingen prosjekter matcher filteret.</div>
  </div>

  <p class="footer">
    Genereret automatisk fra Finn.no. Salg og prisendringer estimeres ved diff mellom snapshots.
  </p>
</div>

<script>
const DATA = __DATA_PLACEHOLDER__;

function fmt(n) {
  if (n === null || n === undefined) return '–';
  return new Intl.NumberFormat('nb-NO').format(Math.round(n));
}

function fmtPct(n) {
  if (n === null || n === undefined) return '–';
  const sign = n > 0 ? '+' : '';
  return sign + n.toFixed(1) + ' %';
}

function escapeHtml(text) {
  if (text === null || text === undefined) return '';
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function projectsFiltered() {
  const muniFilter = document.getElementById('muni-filter').value;
  const search = document.getElementById('search').value.toLowerCase();
  return DATA.projects.filter(p => {
    if (muniFilter && p.municipality !== muniFilter) return false;
    if (search && !(p.title || '').toLowerCase().includes(search)) return false;
    return true;
  });
}

function renderStats() {
  const projects = projectsFiltered();
  const totalProjects = projects.length;
  const totalForSale = projects.reduce((s, p) => s + (p.units_for_sale || 0), 0);
  const totalSoldWeek = projects.reduce((s, p) => s + (p.sold_last_week || 0), 0);
  const totalSoldMonth = projects.reduce((s, p) => s + (p.sold_last_month || 0), 0);

  const muniFilter = document.getElementById('muni-filter').value;
  const scopeLabel = muniFilter || 'totalt';

  document.getElementById('stats').innerHTML = `
    <div class="stat"><p class="stat-label">Prosjekter (${escapeHtml(scopeLabel)})</p><p class="stat-value">${totalProjects}</p></div>
    <div class="stat"><p class="stat-label">Enheter til salgs</p><p class="stat-value">${fmt(totalForSale)}</p></div>
    <div class="stat"><p class="stat-label">Solgt siste uke</p><p class="stat-value" style="color: var(--success);">${fmt(totalSoldWeek)}</p></div>
    <div class="stat"><p class="stat-label">Solgt siste måned</p><p class="stat-value" style="color: var(--success);">${fmt(totalSoldMonth)}</p></div>
  `;
}

function renderTable() {
  const projects = projectsFiltered();
  const body = document.getElementById('project-table');
  body.innerHTML = '';

  for (const p of projects) {
    const stage = p.sales_stage ? `<span class="stage-pill">${escapeHtml(p.sales_stage)}</span>` : '';
    const cls = (n) => (n === 0 ? 'num num-zero' : 'num');
    const hasDetail = (p.units && p.units.length > 0);
    const arrow = hasDetail ? `<span class="expander" data-finn="${p.finn_code}">▶</span>` : '';

    body.insertAdjacentHTML('beforeend', `
      <tr data-finn="${p.finn_code}">
        <td>${arrow}</td>
        <td>
          <div class="muni">${escapeHtml(p.municipality || '')}</div>
          <div><a href="${escapeHtml(p.url)}" target="_blank" rel="noopener">${escapeHtml(p.title || '—')}</a>${stage}</div>
          <div style="font-size:12px;color:var(--text-faint);margin-top:2px;">${escapeHtml(p.address || '')}</div>
        </td>
        <td class="num">${fmt(p.units_for_sale)}</td>
        <td class="num">${fmt(p.units_sold)}</td>
        <td class="num">${p.avg_price_per_m2 ? fmt(p.avg_price_per_m2) : '–'}</td>
        <td class="${cls(p.sold_last_week)}">${fmt(p.sold_last_week)}</td>
        <td class="${cls(p.sold_last_month)}">${fmt(p.sold_last_month)}</td>
        <td class="${cls(p.sold_last_year)}">${fmt(p.sold_last_year)}</td>
      </tr>
    `);
  }

  document.getElementById('empty-msg').style.display = projects.length === 0 ? 'block' : 'none';

  body.querySelectorAll('.expander').forEach(el => {
    el.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleDetail(el.dataset.finn, el);
    });
  });
}

function toggleDetail(finnCode, expander) {
  const mainRow = document.querySelector(`tr[data-finn="${finnCode}"]`);
  const existing = document.getElementById(`detail-${finnCode}`);
  if (existing) {
    existing.remove();
    expander.classList.remove('open');
    return;
  }

  const project = DATA.projects.find(p => p.finn_code === finnCode);
  if (!project) return;

  const detailRow = document.createElement('tr');
  detailRow.id = `detail-${finnCode}`;
  detailRow.className = 'detail-row';
  detailRow.innerHTML = `<td colspan="8">${renderDetailContent(project)}</td>`;
  mainRow.insertAdjacentElement('afterend', detailRow);
  expander.classList.add('open');

  detailRow.querySelector(`#export-${finnCode}`).addEventListener('click', () => exportToExcel(project));
}

function renderDetailContent(p) {
  const units = (p.units || []).slice().sort((a, b) => {
    if (a.sold !== b.sold) return a.sold - b.sold;
    if ((a.floor || 0) !== (b.floor || 0)) return (a.floor || 0) - (b.floor || 0);
    return (a.unit_id || '').localeCompare(b.unit_id || '');
  });

  const unitsHtml = units.length === 0 ? '<div class="empty">Ingen enhetsdata.</div>' : `
    <table class="unit-table">
      <thead><tr>
        <th>Enhet</th><th class="num">Etasje</th><th class="num">BRA</th>
        <th class="num">Soverom</th><th class="num">Pris</th><th class="num">Pris/m²</th><th>Status</th>
      </tr></thead>
      <tbody>
        ${units.map(u => {
          const ppm = (u.total_price && u.bra_m2) ? Math.round(u.total_price / u.bra_m2) : null;
          const status = u.sold ? '<span class="badge badge-sold">Solgt</span>' : '';
          return `<tr>
            <td>${escapeHtml(u.unit_id)}</td>
            <td class="num">${u.floor ?? '–'}</td>
            <td class="num">${u.bra_m2 ? u.bra_m2 + ' m²' : '–'}</td>
            <td class="num">${u.bedrooms ?? '–'}</td>
            <td class="num">${u.total_price ? fmt(u.total_price) + ' kr' : '–'}</td>
            <td class="num">${ppm ? fmt(ppm) + ' kr' : '–'}</td>
            <td>${status}</td>
          </tr>`;
        }).join('')}
      </tbody>
    </table>
  `;

  const week = p.changes_week || {sold: [], price_changes: []};
  const month = p.changes_month || {sold: [], price_changes: []};

  const renderChanges = (label, ch) => {
    if (!ch.sold.length && !ch.price_changes.length) return '';
    const soldHtml = ch.sold.length ? `
      <div style="margin-top: 8px;"><strong>Solgt:</strong> ${ch.sold.map(s => `
        <span class="badge badge-sold">${escapeHtml(s.unit_id)} · ${fmt(s.last_seen_price)} kr</span>
      `).join(' ')}</div>` : '';
    const priceHtml = ch.price_changes.length ? `
      <div style="margin-top: 8px;"><strong>Prisendring:</strong> ${ch.price_changes.map(c => {
        const cls = c.change_pct > 0 ? 'badge-up' : 'badge-down';
        return `<span class="badge ${cls}">${escapeHtml(c.unit_id)} · ${fmt(c.old_price)} → ${fmt(c.new_price)} (${fmtPct(c.change_pct)})</span>`;
      }).join(' ')}</div>` : '';
    return `<div class="detail-section"><h3>${label}</h3>${soldHtml}${priceHtml}</div>`;
  };

  return `
    <div class="detail-content">
      <div class="detail-section">
        <h3 style="display:inline-block;margin-right:8px;">Enheter</h3>
        <button class="download-btn" id="export-${p.finn_code}">Last ned Excel</button>
        ${unitsHtml}
      </div>
      ${renderChanges('Endringer siste uke', week)}
      ${renderChanges('Endringer siste måned', month)}
    </div>
  `;
}

function exportToExcel(project) {
  const rows = [
    ['Enhet', 'Etasje', 'BRA-i (m²)', 'Soverom', 'Totalpris (kr)', 'Pris/m²', 'Status'],
  ];
  for (const u of (project.units || [])) {
    const ppm = (u.total_price && u.bra_m2) ? Math.round(u.total_price / u.bra_m2) : null;
    rows.push([
      u.unit_id || '',
      u.floor ?? '',
      u.bra_m2 ?? '',
      u.bedrooms ?? '',
      u.total_price ?? '',
      ppm ?? '',
      u.sold ? 'Solgt' : 'Til salgs',
    ]);
  }

  const wb = XLSX.utils.book_new();
  const ws = XLSX.utils.aoa_to_sheet(rows);
  ws['!cols'] = [{wch: 10}, {wch: 8}, {wch: 12}, {wch: 8}, {wch: 16}, {wch: 12}, {wch: 12}];
  XLSX.utils.book_append_sheet(wb, ws, 'Enheter');

  const changeRows = [['Type', 'Enhet', 'Detalj', 'Periode']];
  const week = project.changes_week || {sold: [], price_changes: []};
  const month = project.changes_month || {sold: [], price_changes: []};
  for (const s of week.sold) {
    changeRows.push(['Solgt (siste uke)', s.unit_id, fmt(s.last_seen_price) + ' kr', s.disappeared_after]);
  }
  for (const c of week.price_changes) {
    changeRows.push(['Prisendring (siste uke)', c.unit_id, fmt(c.old_price) + ' → ' + fmt(c.new_price) + ' (' + fmtPct(c.change_pct) + ')', c.since]);
  }
  const weekIds = new Set([...week.sold.map(s=>s.unit_id), ...week.price_changes.map(c=>c.unit_id)]);
  for (const s of month.sold) {
    if (!weekIds.has(s.unit_id)) {
      changeRows.push(['Solgt (siste måned)', s.unit_id, fmt(s.last_seen_price) + ' kr', s.disappeared_after]);
    }
  }
  for (const c of month.price_changes) {
    if (!weekIds.has(c.unit_id)) {
      changeRows.push(['Prisendring (siste måned)', c.unit_id, fmt(c.old_price) + ' → ' + fmt(c.new_price) + ' (' + fmtPct(c.change_pct) + ')', c.since]);
    }
  }
  if (changeRows.length > 1) {
    const ws2 = XLSX.utils.aoa_to_sheet(changeRows);
    ws2['!cols'] = [{wch: 28}, {wch: 12}, {wch: 40}, {wch: 14}];
    XLSX.utils.book_append_sheet(wb, ws2, 'Endringer');
  }

  const safeName = (project.title || 'prosjekt').replace(/[^\wæøåÆØÅ-]/g, '_').slice(0, 60);
  XLSX.writeFile(wb, `${safeName}.xlsx`);
}

function init() {
  document.getElementById('updated-date').textContent = DATA.updated || '—';

  const sel = document.getElementById('muni-filter');
  const munis = [...new Set(DATA.projects.map(p => p.municipality).filter(Boolean))].sort();
  for (const m of munis) {
    sel.insertAdjacentHTML('beforeend', `<option value="${m}">${m}</option>`);
  }

  function update() {
    renderStats();
    renderTable();
  }

  sel.addEventListener('change', update);
  document.getElementById('search').addEventListener('input', update);
  update();
}

document.addEventListener('DOMContentLoaded', init);
</script>
</body>
</html>
"""


def main():
    OUT_DIR.mkdir(exist_ok=True)
    data = build_data()
    html = HTML_TEMPLATE.replace("__DATA_PLACEHOLDER__", json.dumps(data, ensure_ascii=False))
    OUT_FILE.write_text(html, encoding="utf-8")
    print(f"Skrev {OUT_FILE} ({OUT_FILE.stat().st_size:,} bytes)")
    print(f"  {len(data['projects'])} prosjekter, oppdatert {data['updated']}")


if __name__ == "__main__":
    main()
