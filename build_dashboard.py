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

from scraper.database import get_latest_snapshots, compute_sales_stats, get_project_history

OUT_DIR = Path(__file__).parent / "dashboard"
OUT_FILE = OUT_DIR / "index.html"


def build_data() -> dict:
    """Bygger JSON-strukturen for dashbordet."""
    snapshots = get_latest_snapshots()

    # Per-prosjekt salgsstats
    projects = []
    for s in snapshots:
        finn_code = s["finn_code"]
        history = get_project_history(finn_code, days=365)
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
        })

    # Sorter: kommune, så tittel
    projects.sort(key=lambda p: (p["municipality"] or "", p["title"] or ""))

    # Aggregat per kommune
    by_muni = defaultdict(lambda: {
        "projects": 0, "for_sale": 0, "sold_last_week": 0, "sold_last_month": 0
    })
    for p in projects:
        m = by_muni[p["municipality"] or "Ukjent"]
        m["projects"] += 1
        m["for_sale"] += p["units_for_sale"] or 0
        m["sold_last_week"] += p["sold_last_week"]
        m["sold_last_month"] += p["sold_last_month"]

    return {
        "updated": projects[0]["scraped_at"][:10] if projects else None,
        "projects": projects,
        "municipality_stats": dict(by_muni),
    }


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="nb">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Nyboligprosjekter Akershus</title>
<style>
  :root {
    --bg: #ffffff;
    --bg-secondary: #f5f4ee;
    --text: #1a1a1a;
    --text-muted: #6b6b6b;
    --text-faint: #999;
    --border: #e5e3dc;
    --accent: #185fa5;
    --success: #0f6e56;
    --warning: #854f0b;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #1a1a1a;
      --bg-secondary: #252525;
      --text: #e8e8e8;
      --text-muted: #a0a0a0;
      --text-faint: #707070;
      --border: #353535;
      --accent: #85B7EB;
      --success: #5DCAA5;
      --warning: #EF9F27;
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
  .header { display: flex; align-items: baseline; justify-content: space-between;
            margin-bottom: 1.5rem; flex-wrap: wrap; gap: 8px; }
  .updated { font-size: 13px; color: var(--text-muted); margin: 4px 0 0; }
  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
           gap: 12px; margin-bottom: 1.5rem; }
  .stat { background: var(--bg-secondary); border-radius: 8px; padding: 1rem; }
  .stat-label { font-size: 13px; color: var(--text-muted); margin: 0; }
  .stat-value { font-size: 24px; font-weight: 500; margin: 4px 0 0; }
  .stat-sub { font-size: 12px; color: var(--text-faint); margin: 2px 0 0; }
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
    Genereret automatisk fra Finn.no. Salg estimeres ved diff mellom snapshots.
  </p>
</div>

<script>
const DATA = __DATA_PLACEHOLDER__;

function fmt(n) {
  if (n === null || n === undefined) return '–';
  return new Intl.NumberFormat('nb-NO').format(Math.round(n));
}

function init() {
  const updated = DATA.updated || '—';
  document.getElementById('updated-date').textContent = updated;

  // Stats
  const totalProjects = DATA.projects.length;
  const totalForSale = DATA.projects.reduce((s, p) => s + (p.units_for_sale || 0), 0);
  const totalSoldWeek = DATA.projects.reduce((s, p) => s + (p.sold_last_week || 0), 0);
  const totalSoldMonth = DATA.projects.reduce((s, p) => s + (p.sold_last_month || 0), 0);

  document.getElementById('stats').innerHTML = `
    <div class="stat"><p class="stat-label">Prosjekter</p><p class="stat-value">${totalProjects}</p></div>
    <div class="stat"><p class="stat-label">Enheter til salgs</p><p class="stat-value">${fmt(totalForSale)}</p></div>
    <div class="stat"><p class="stat-label">Solgt siste uke</p><p class="stat-value" style="color: var(--success);">${fmt(totalSoldWeek)}</p></div>
    <div class="stat"><p class="stat-label">Solgt siste måned</p><p class="stat-value" style="color: var(--success);">${fmt(totalSoldMonth)}</p></div>
  `;

  // Kommune-filter
  const sel = document.getElementById('muni-filter');
  const munis = [...new Set(DATA.projects.map(p => p.municipality).filter(Boolean))].sort();
  for (const m of munis) {
    sel.insertAdjacentHTML('beforeend', `<option value="${m}">${m}</option>`);
  }

  function render() {
    const muniFilter = sel.value;
    const search = document.getElementById('search').value.toLowerCase();
    const filtered = DATA.projects.filter(p => {
      if (muniFilter && p.municipality !== muniFilter) return false;
      if (search && !(p.title || '').toLowerCase().includes(search)) return false;
      return true;
    });

    const body = document.getElementById('project-table');
    body.innerHTML = '';
    for (const p of filtered) {
      const stage = p.sales_stage ? `<span class="stage-pill">${p.sales_stage}</span>` : '';
      const titleCell = `
        <td>
          <div class="muni">${p.municipality || ''}</div>
          <div><a href="${p.url}" target="_blank" rel="noopener">${p.title || '—'}</a>${stage}</div>
          <div style="font-size:12px;color:var(--text-faint);margin-top:2px;">${p.address || ''}</div>
        </td>
      `;
      const cls = (n) => (n === 0 ? 'num num-zero' : 'num');
      body.insertAdjacentHTML('beforeend', `
        <tr>
          ${titleCell}
          <td class="num">${fmt(p.units_for_sale)}</td>
          <td class="num">${fmt(p.units_sold)}</td>
          <td class="num">${p.avg_price_per_m2 ? fmt(p.avg_price_per_m2) : '–'}</td>
          <td class="${cls(p.sold_last_week)}">${fmt(p.sold_last_week)}</td>
          <td class="${cls(p.sold_last_month)}">${fmt(p.sold_last_month)}</td>
          <td class="${cls(p.sold_last_year)}">${fmt(p.sold_last_year)}</td>
        </tr>
      `);
    }

    document.getElementById('empty-msg').style.display = filtered.length === 0 ? 'block' : 'none';
  }

  sel.addEventListener('change', render);
  document.getElementById('search').addEventListener('input', render);
  render();
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
