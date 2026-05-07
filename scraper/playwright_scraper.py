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

        const tbody = table.querySelector('tbody') || table;
        const rows = Array.from(tbody.querySelectorAll('tr')).filter(r => r.querySelectorAll('td, th').length > 0);

        const units = [];
        for (const row of rows) {
          const cells = row.querySelectorAll('td, th');
          const cellText = (key) => {
            const i = colIdx[key];
            if (i === undefined || i >= cells.length) return '';
            return cells[i].textContent.trim();
          };

          const unitId = cellText('enhet');
          if (!unitId) continue;

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

    Returnerer True hvis vi klikket, False hvis ikke (= vi er på siste side).

    Strategi: lete etter SVG/knapp med arial-label/title som inneholder
    "Neste" eller en typisk pil-til-høyre. Som fallback prøver vi å trykke
    på en knapp med teksten "2", "3" osv. inne i pagineringskontainer.
    """
    # Prøv 1: knapp med aria-label "Neste"/"Next"
    selectors = [
        'button[aria-label*="Neste" i]',
        'button[aria-label*="next" i]',
        'a[aria-label*="Neste" i]',
        'button[title*="Neste" i]',
        '[role="button"][aria-label*="Neste" i]',
    ]
    for sel in selectors:
        try:
            btn = page.locator(sel).first
            if btn.count() > 0 and btn.is_visible(timeout=500) and btn.is_enabled(timeout=500):
                btn.scroll_into_view_if_needed(timeout=2000)
                btn.click(timeout=3000)
                page.wait_for_timeout(700)
                return True
        except Exception:
            continue

    # Prøv 2: bestem nåværende sidenummer og klikk neste
    try:
        # Finn aktiv side ved å lete etter "aria-current" eller en utheving
        next_num = page.evaluate(r"""
        () => {
          // Søk etter pagineringselementer med tall
          const pagers = document.querySelectorAll('[aria-label*="paginering" i], nav, ul');
          for (const pager of pagers) {
            const buttons = pager.querySelectorAll('button, a');
            const labels = Array.from(buttons).map(b => b.textContent.trim());
            const numbers = labels.filter(l => /^\d+$/.test(l));
            if (numbers.length < 2) continue;
            // Finn aktiv (aria-current="page" eller klasse "active")
            let current = null;
            buttons.forEach(b => {
              if (b.getAttribute('aria-current') === 'page' || b.getAttribute('aria-current') === 'true' ||
                  /^\d+$/.test(b.textContent.trim()) && b.getAttribute('disabled') !== null) {
                current = parseInt(b.textContent.trim(), 10);
              }
            });
            if (current === null) {
              // Anta vi er på side 1 hvis ingen er markert som aktiv
              current = 1;
            }
            return current + 1;
          }
          return null;
        }
        """)
        if next_num:
            btn = page.locator(f'button:has-text("{next_num}"), a:has-text("{next_num}")').first
            if btn.count() > 0 and btn.is_visible(timeout=500):
                btn.click(timeout=3000)
                page.wait_for_timeout(700)
                return True
    except Exception:
        pass

    return False
