import re
import sys
import json
import time
from pathlib import Path
from typing import List, Set, Optional, Tuple

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# Standardinställningar
DEFAULT_URL = "https://arbetsformedlingen.se/platsbanken/annonser?q=J%C3%B6nk%C3%B6pings%20l%C3%A4n"
DEFAULT_OUTPUT = "matches.txt"

BANNER = r"""
========================================
  Platsbanken Scraper (Playwright)
========================================
"""

HELP = """
Vad programmet gör:
- Går igenom X sidor av sökresultatet (klickar 'Nästa')
- Samlar alla annonslänkar
- Öppnar varje annons, letar efter något av dina nyckelord
- Sparar träffar i formatet: [Sökord] | [Företag] | [URL]

Tips:
- Ange valfri Platsbanken-sökadress (med filter) i menyn
"""

# Tar en kommaseparerad lista med ord och gör om till lista utan dubbletter
def normalize_keywords(kw_str: str) -> List[str]:
    kws = [k.strip() for k in kw_str.split(",") if k.strip()]
    seen = set()
    out = []
    for k in kws:
        low = k.lower()
        if low not in seen:
            seen.add(low)
            out.append(k)
    return out

# Scrollar sidan och returnerar annonslänkar
def collect_ad_links(page, max_wait_seconds: int = 20) -> List[str]:
    start_time = time.time()
    seen_links: Set[str] = set()

    # Tillåt querystring/fragments efter annons-id
    ad_path_re = re.compile(r"^/platsbanken/annonser/.*$", re.IGNORECASE)
    base = "https://arbetsformedlingen.se"

    last_count = -1
    idle_rounds = 0

    while True:
        hrefs = page.eval_on_selector_all(
            "a[href]", "els => els.map(e => e.getAttribute('href'))"
        )
        for href in hrefs:
            if not href:
                continue
            if href.startswith("http"):
                url = href
            elif href.startswith("/"):
                url = base + href
            else:
                continue

            path = re.sub(r"^https?://[^/]+", "", url)
            if ad_path_re.match(path):
                seen_links.add(url)

        if len(seen_links) == last_count:
            idle_rounds += 1
        else:
            idle_rounds = 0
        last_count = len(seen_links)

        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(0.7)

        if idle_rounds >= 3 or (time.time() - start_time) > max_wait_seconds:
            break

    return sorted(seen_links)

# Försök hämta företagsnamn (robust: JSON-LD -> etikett "Arbetsgivare" -> fallback)
def extract_company(page) -> Optional[str]:
    # 1) JSON-LD (JobPosting.hiringOrganization.name)
    try:
        scripts = page.locator('script[type="application/ld+json"]')
        for i in range(scripts.count()):
            raw = scripts.nth(i).inner_text(timeout=1000)
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except Exception:
                continue

            def find_name(obj):
                if isinstance(obj, dict):
                    typ = obj.get("@type") or obj.get("type")
                    if (typ == "JobPosting") and isinstance(obj.get("hiringOrganization"), dict):
                        name = obj["hiringOrganization"].get("name")
                        if name:
                            return name
                    # Sök rekursivt
                    for v in obj.values():
                        n = find_name(v)
                        if n:
                            return n
                elif isinstance(obj, list):
                    for it in obj:
                        n = find_name(it)
                        if n:
                            return n
                return None

            name = find_name(data)
            if name:
                return name.strip()
    except Exception:
        pass

    # 2) Leta efter textmönster "Arbetsgivare" i main/body
    try:
        text = ""
        try:
            text = page.locator("main").inner_text(timeout=1500)
        except Exception:
            text = page.locator("body").inner_text(timeout=1500)
        if text:
            # Vanligt mönster: "Arbetsgivare\nHusqvarna AB"
            m = re.search(r"Arbetsgivare\s*\n\s*([^\n]+)", text, flags=re.IGNORECASE)
            if m:
                cand = m.group(1).strip()
                # Rensa ev. trailing etiketter på samma rad
                cand = re.split(r"\s{2,}|  +", cand)[0].strip()
                return cand
    except Exception:
        pass

    # 3) Som sista utväg: ofta visas företaget strax under H1 i detaljsidan
    try:
        h1 = page.locator("h1")
        if h1.count() > 0:
            # Titta på närmaste container runt titeln
            container = h1.first.locator("xpath=..").inner_text(timeout=1000)
            lines = [l.strip() for l in container.splitlines() if l.strip()]
            # Försök hitta en rad som ser ut som "Företagsnamn - Ort"
            for l in lines[1:3]:  # kolla 1-2 rader under rubriken
                if " - " in l:
                    return l.split(" - ", 1)[0].strip()
    except Exception:
        pass

    return None

# Returnerar vilket nyckelord som matchade (eller None)
def find_matching_keyword_in_page(page, keywords: List[str]) -> Optional[str]:
    try:
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass

        # Försök stänga samtycke/cookies
        try:
            for txt in ["Acceptera", "Godkänn", "Tillåt alla", "Acceptera alla", "OK"]:
                btn = page.locator(f'button:has-text("{txt}")')
                if btn.count() > 0 and btn.first.is_enabled():
                    btn.first.click()
                    page.wait_for_timeout(400)
                    break
        except Exception:
            pass

        text_blobs = []

        try:
            title_el = page.locator("h1")
            if title_el.count() > 0:
                text_blobs.append(title_el.first.inner_text(timeout=2000))
        except Exception:
            pass

        try:
            text_blobs.append(page.locator("main").inner_text(timeout=3000))
        except Exception:
            pass

        try:
            text_blobs.append(page.locator("body").inner_text(timeout=3000))
        except Exception:
            pass

        if not any(text_blobs):
            try:
                text_blobs.append(page.evaluate("document.body && document.body.innerText || ''"))
            except Exception:
                return None

        big_text = "\n".join(tb for tb in text_blobs if tb).lower()

        for kw in keywords:
            if kw.lower() in big_text:
                return kw  # returnera första matchande nyckelordet
        return None

    except Exception:
        return None

# Gå till nästa sökresultatsida
def go_to_next_results_page(page) -> bool:
    next_link = page.locator('a[rel="next"]')
    if next_link.count() > 0 and next_link.first.is_enabled():
        next_link.first.click()
        page.wait_for_load_state("domcontentloaded", timeout=30000)
        return True

    next_text_link = page.locator('a:has-text("Nästa")')
    if next_text_link.count() > 0 and next_text_link.first.is_enabled():
        next_text_link.first.click()
        page.wait_for_load_state("domcontentloaded", timeout=30000)
        return True

    next_btn = page.locator('button:has-text("Nästa")')
    if next_btn.count() > 0 and next_btn.first.is_enabled():
        next_btn.first.click()
        page.wait_for_load_state("domcontentloaded", timeout=30000)
        return True

    return False

# Scraping med flera sidor + sparar i önskat format
def scrape(url: str, keywords: List[str], output_file: str, headless: bool = True, max_pages: int = 1):
    output_path = Path(output_file)
    rows = []  # varje rad: "[Sökord] | [Företag] | [URL]"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (compatible; PlatsbankenScraper/1.3)",
            viewport={"width": 1280, "height": 2000},
        )
        page = context.new_page()

        print(f"\nÖppnar söksidan (sida 1):\n{url}\n")
        page.goto(url, wait_until="domcontentloaded", timeout=60000)

        all_ad_links: Set[str] = set()
        current_page = 1

        while True:
            print(f"Samlar in annonslänkar på sida {current_page}…")
            page_links = collect_ad_links(page)
            print(f"— Hittade {len(page_links)} annonser på denna sida.")
            for l in page_links:
                all_ad_links.add(l)

            if current_page >= max_pages:
                break

            try:
                print(f"▶ Försöker gå vidare till sida {current_page + 1} …")
                moved = go_to_next_results_page(page)
            except Exception:
                moved = False

            if not moved:
                print("Ingen nästa sida hittades – stoppar här.")
                break

            current_page += 1
            time.sleep(0.6)

        print(f"\nTotalt unika annonslänkar (över {current_page} sida/or): {len(all_ad_links)}")

        if not all_ad_links:
            browser.close()
            print("Inga annonser hittades. Testa att ändra sök-URL, filter eller antal sidor.")
            return

        print("\nSöker efter nyckelord i varje annons:", ", ".join(keywords))
        for link in sorted(all_ad_links):
            time.sleep(0.25)
            try:
                page.goto(link, wait_until="domcontentloaded", timeout=60000)
            except PlaywrightTimeoutError:
                print(f"  [timeout] {link}")
                continue

            matched_kw = find_matching_keyword_in_page(page, keywords)
            if matched_kw:
                company = extract_company(page) or "(okänt företag)"
                line = f"{matched_kw} | {company} | {link}"
                print(f"  [TRÄFF] {line}")
                rows.append(line)
            else:
                print(f"  [ingen] {link}")

        browser.close()

    # Spara rader i önskat format, undvik dubbletter
    if rows:
        existing = set()
        if output_path.exists():
            existing.update(output_path.read_text(encoding="utf-8").splitlines())

        new_rows = [r for r in rows if r not in existing]
        if new_rows:
            with output_path.open("a", encoding="utf-8") as f:
                for r in new_rows:
                    f.write(r + "\n")
            print(f"\nSparade {len(new_rows)} nya träffar till: {output_path.resolve()}")
        else:
            print("\nAlla träffar fanns redan i filen – inget nytt sparat.")
    else:
        print("\nInga träffar hittades för dina nyckelord.")

# Meny
def menu():
    print(BANNER)
    print(HELP)

    start_url = DEFAULT_URL
    output_file = DEFAULT_OUTPUT
    keywords: List[str] = ["developer", "python", "cybersecurity", "nätverk", "linux"]
    pages_to_scan: int = 3  # standard

    while True:
        print("\n--- Alternativ ---")
        print(f"1) Ändra nyckelord (nuvarande: {', '.join(keywords)})")
        print(f"2) Ändra start-URL (nuvarande: {start_url})")
        print(f"3) Ändra utdatafil (nuvarande: {output_file})")
        print(f"4) Ändra antal sidor (nuvarande: {pages_to_scan})")
        print( "5) Kör scraping nu")
        print( "6) Avsluta")
        choice = input("Välj ett alternativ [1–6]: ").strip()

        if choice == "1":
            kw_str = input("Skriv nyckelord separerade med kommatecken: ").strip()
            new_kws = normalize_keywords(kw_str)
            if new_kws:
                keywords = new_kws
                print("Nyckelord uppdaterade.")
            else:
                print("Inga giltiga nyckelord; behåller gamla.")
        elif choice == "2":
            su = input("Klistra in en Platsbanken-sök-URL: ").strip()
            if su.startswith("http"):
                start_url = su
                print("Start-URL uppdaterad.")
            else:
                print("Ogiltig URL; behåller gamla.")
        elif choice == "3":
            of = input("Ange filnamn (t.ex. matches.txt): ").strip()
            if of:
                output_file = of
                print("Filnamn uppdaterat.")
            else:
                print("Ogiltigt filnamn; behåller gamla.")
        elif choice == "4":
            try:
                val = int(input("Hur många sidor vill du skanna? (t.ex. 3): ").strip())
                if val >= 1:
                    pages_to_scan = val
                    print(f"Antal sidor uppdaterat till {pages_to_scan}.")
                else:
                    print("Ange ett heltal >= 1.")
            except ValueError:
                print("Ogiltigt tal.")
        elif choice == "5":
            if not keywords:
                print("Du måste ange minst ett nyckelord först.")
                continue
            scrape(start_url, keywords, output_file, headless=True, max_pages=pages_to_scan)
        elif choice == "6":
            print("Hejdå!")
            sys.exit(0)
        else:
            print("Välj ett nummer mellan 1–6.")

if __name__ == "__main__":
    try:
        menu()
    except KeyboardInterrupt:
        print("\nAvbrutet. Hejdå!")
