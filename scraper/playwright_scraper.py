"""
Playwright-basert henting av enheter fra Finn-prosjektsider.

Bakgrunn: Finn paginerer enhetstabellen med JavaScript på klientsiden.
Hele datasettet er IKKE i HTML — det lastes dynamisk når brukeren klikker
"side 2", "side 3" osv. Derfor må vi bruke en headless nettleser.

Strategi:
1. Naviger til prosjektsiden
2. Vent til enhetstabellen er rendret
3. Les tabellen
4. Klikk "neste side"-knappen
5. Vent på at tabellen oppdateres
6. Gjenta til knappen forsvinner eller vi har sett alle enheter

Ved feil eller tomt resultat — fallback til vanlig HTML-parsing.
"""

import logging
import re
import time
from typing import Optional

logger = logging.getLogger(__name__)


def fetch_units_with_playwright(url: str, max_pages: int = 20,
                                page_timeout_ms: int = 20_000) -> Optional[list]:
    """
    Henter ALLE enheter fra et prosjekt ved å klikke gjennom paginering.

    Returnerer liste med dicts: {unit_id, floor, bra_m2, bedrooms, total_price, sold}
    eller None ved feil (kalleren bør falle tilbake til HTML-parsing).
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("Playwright ikke installert — kan ikke pagine")
        return None

    units_by_id = {}  # unit_id -> dict; deduplisering på tvers av sider

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                locale="nb-NO",
            )
            page = context.new_page()

            try:
                page.goto(url, timeout=page_timeout_ms, wait_until="domcontentloaded")
            except Exception as e:
                logger.warning(f"Goto-feil for {url}: {e}")
                browser.close()
                return None

            # Aksepter cookies hvis det dukker opp en banner
            _try_accept_cookies(page)

            # Vent på at enhetstabellen rendres
            try:
                page.wait_for_selector("table", timeout=10_000)
            except Exception:
                logger.info(f"Ingen tabell funnet for {url}")
                browser.close()
                return []

            # Loop gjennom sider
            for page_num in range(1, max_pages + 1):
                # Les nåværende tabell
                page_units = _extract_units_from_dom(page)
                if not page_units:
                    break

                new_count = 0
                for u in page_units:
                    if u["unit_id"] not in units_by_id:
                        units_by_id[u["unit_id"]] = u
                        new_count += 1

                logger.info(f"  Side {page_num}: {len(page_units)} enheter ({new_count} nye)")

                # Hvis ingen nye enheter på denne siden, vi er ferdige
                if new_count == 0:
                    break

                # Hvis side 1 har færre enn 15, paginering ikke aktiv
                if page_num == 1 and len(page_units) < 15:
                    break

                # Prøv å klikke "neste side"
                if not _click_next_page(page):
                    break

                # Vent på at tabellen oppdateres med ny data
                time.sleep(0.8)

            browser.close()
            return list(units_by_id.values())

    except Exception as e:
        logger.warning(f"Playwright-feil for {url}: {e}")
        return None


def _try_accept_cookies(page) -> None:
    """Klikk vekk cookie-banner hvis den finnes."""
    selectors = [
        'button:has-text("Godta")',
        'button:has-text("Aksepter")',
        'button:has-text("Accept")',
        'button[id*="cookie"]',
        '#didomi-notice-agree-button',
    ]
    for sel in selectors:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=1500):
                btn.click(timeout=2000)
                page.wait_for_timeout(400)
                return
        except Exception:
            continue


def _extract_units_from_dom(page) -> list[dict]:
    """
    Finn enhetstabellen i DOM-en og hent ut radene.

    Vi leter etter table med 'enhet' og 'totalpris' i headerne.
    """
    js = r"""
    () => {
      function parseInt_(s) {
        if (!s) return null;
        const cleaned = String(s).replace(/[^\d]/g, '');
        return cleaned ? parseInt(cleaned, 10) : null;
      }

      const tables = document.querySelectorAll('table');
      for (const table of tables) {
        const headers = Array.from(table.querySelectorAll('th'))
          .map(th => th.textContent.trim().toLowerCase());
        if (!headers.includes('enhet') || !headers.includes('totalpris')) continue;

        const colIdx = {};
        headers.forEach((h, i) => { colIdx[h] = i; });

        // Bruk tbody hvis det finnes — hvis ikke, alle tr som IKKE er i thead
        let rows;
        const tbody = table.querySelector('tbody');
        if (tbody) {
          rows = Array.from(tbody.querySelectorAll('tr'));
        } else {
          const thead = table.querySelector('thead');
          rows = Array.from(table.querySelectorAll('tr')).filter(r => !thead || !thead.contains(r));
        }
        rows = rows.filter(r => r.querySelectorAll('td').length > 0);

        const units = [];
        const seenInTable = new Set();
        for (const row of rows) {
          const cells = row.querySelectorAll('td, th');
          const cellText = (key) => {
            const i = colIdx[key];
            if (i === undefined || i >= cells.length) return '';
            return cells[i].textContent.trim();
          };

          const unitId = cellText('enhet');
          // Hopp over header-aktige rader og duplikater innenfor samme side
          if (!unitId || unitId.toLowerCase() === 'enhet') continue;
          if (seenInTable.has(unitId)) continue;
          seenInTable.add(unitId);

          const priceText = cellText('totalpris');
          const sold = priceText.toLowerCase().includes('solgt');

          units.push({
            unit_id: unitId,
            floor: parseInt_(cellText('etasje')),
            bra_m2: parseInt_(cellText('bra-i') || cellText('areal')),
            bedrooms: parseInt_(cellText('soverom')),
            total_price: sold ? null : parseInt_(priceText),
            sold: sold,
          });
        }
        return units;
      }
      return [];
    }
    """
    try:
        return page.evaluate(js) or []
    except Exception as e:
        logger.warning(f"DOM-uttrekk feilet: {e}")
        return []


def _click_next_page(page) -> bool:
    """
    Prøver å klikke 'neste side'-knappen for enhetstabellen.

    Finn-strukturen er typisk:
        <nav aria-labelledby="Enhetsvelger">
          <div>
            <button aria-current="page">1</button>
            <button aria-current="false">2</button>
            <button aria-current="false">3</button>
          </div>
          <button aria-label="Neste side">...</button>
        </nav>

    Returnerer True hvis vi klikket, False hvis ikke (= vi er på siste side).
    """
    # Strategi 1: direkte nav-basert. Inne i nav[aria-labelledby="Enhetsvelger"]
    # finner vi den siste knappen — det er "Neste side"-knappen.
    try:
        nav = page.locator('nav[aria-labelledby="Enhetsvelger"]').first
        if nav.count() > 0:
            next_btn = nav.locator('button[aria-label="Neste side"]').first
            if next_btn.count() > 0:
                # Sjekk at den er enabled (på siste side er den disabled)
                is_disabled = next_btn.get_attribute("disabled")
                aria_disabled = next_btn.get_attribute("aria-disabled")
                if is_disabled is not None or aria_disabled == "true":
                    return False
                next_btn.scroll_into_view_if_needed(timeout=2000)
                next_btn.click(timeout=3000)
                page.wait_for_timeout(700)
                return True
    except Exception as e:
        logger.debug(f"Strategi 1 feilet: {e}")

    # Strategi 2: aria-label-basert generelt
    selectors = [
        'button[aria-label="Neste side"]',
        'button[aria-label*="Neste" i]',
        'button[aria-label*="next" i]',
        'a[aria-label*="Neste" i]',
    ]
    for sel in selectors:
        try:
            btn = page.locator(sel).first
            if btn.count() == 0:
                continue
            # Sjekk disabled
            if btn.get_attribute("disabled") is not None:
                continue
            if btn.get_attribute("aria-disabled") == "true":
                continue
            btn.scroll_into_view_if_needed(timeout=2000)
            btn.click(timeout=3000)
            page.wait_for_timeout(700)
            return True
        except Exception as e:
            logger.debug(f"Strategi 2 ({sel}) feilet: {e}")
            continue

    # Strategi 3: numerisk navigasjon — finn aktiv side, klikk neste tall
    try:
        next_num = page.evaluate(r"""
        () => {
          const nav = document.querySelector('nav[aria-labelledby="Enhetsvelger"]');
          if (!nav) return null;
          const buttons = nav.querySelectorAll('button[aria-current]');
          let current = 1;
          let max = 1;
          for (const b of buttons) {
            const num = parseInt(b.textContent.trim(), 10);
            if (!isNaN(num)) {
              max = Math.max(max, num);
              if (b.getAttribute('aria-current') === 'page') {
                current = num;
              }
            }
          }
          return current < max ? current + 1 : null;
        }
        """)
        if next_num:
            btn = page.locator(
                f'nav[aria-labelledby="Enhetsvelger"] button:has-text("{next_num}")'
            ).first
            if btn.count() > 0:
                btn.scroll_into_view_if_needed(timeout=2000)
                btn.click(timeout=3000)
                page.wait_for_timeout(700)
                return True
    except Exception as e:
        logger.debug(f"Strategi 3 feilet: {e}")

    return False
