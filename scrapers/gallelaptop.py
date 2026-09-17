"""
scrapers/gallelaptop.py - Galle Laptop Modular Scraper
Engine: Playwright (Dynamic PHP subcategory routing)
Routing: Recursive subcategory extraction (products.php?ci=...&sci=...)
"""

import re
import time
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from scrapers.base_scraper import BaseScraper

FALLBACK_SUBCATS = [
    ("GPU", "https://www.gallelaptop.lk/products.php?ci=Mw==&sci=MjM="),
    ("CPU", "https://www.gallelaptop.lk/products.php?ci=Mw==&sci=MjE="),
    ("Motherboard", "https://www.gallelaptop.lk/products.php?ci=Mw==&sci=MjI="),
    ("RAM", "https://www.gallelaptop.lk/products.php?ci=Mw==&sci=MjQ="),
    ("Storage", "https://www.gallelaptop.lk/products.php?ci=Mw==&sci=MjU="),
    ("PSU", "https://www.gallelaptop.lk/products.php?ci=Mw==&sci=Mjc="),
    ("Casing", "https://www.gallelaptop.lk/products.php?ci=Mw==&sci=Mjg="),
    ("Laptop", "https://www.gallelaptop.lk/products.php?ci=MQ==&sci=MQ==")
]


class GalleLaptopScraper(BaseScraper):
    def __init__(self, headless: bool = True):
        super().__init__(store_name="Galle Laptop", base_url="https://www.gallelaptop.lk")
        self.headless = headless

    def discover_subcategories(self, page):
        subcats = []
        seen = set()
        try:
            page.goto(self.base_url, wait_until="domcontentloaded", timeout=35000)
            time.sleep(2)
            soup = BeautifulSoup(page.content(), "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if "products.php" in href and "sci=" in href:
                    clean_url = urljoin(self.base_url, href).split("#")[0]
                    if clean_url not in seen:
                        cat_name = a.get_text(strip=True) or "Hardware"
                        seen.add(clean_url)
                        subcats.append((cat_name, clean_url))
        except Exception as e:
            print(f"[!] Error discovering Galle Laptop subcategories: {e}")

        return subcats if subcats else FALLBACK_SUBCATS

    def scrape(self, max_pages: int = 6):
        print(f"\n[+] Starting Galle Laptop Scraper...")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(
                user_agent=self.get_headers()["User-Agent"]
            )
            page = context.new_page()

            subcats = self.discover_subcategories(page)

            for cat_name, cat_url in subcats:
                print(f" -> Category: [{cat_name}] -> {cat_url}")
                current_page = 1

                while current_page <= max_pages:
                    page_param = f"&page={current_page}" if current_page > 1 else ""
                    page_url = f"{cat_url}{page_param}"

                    try:
                        res = page.goto(page_url, wait_until="domcontentloaded", timeout=30000)
                        if res and res.status in [404, 403]:
                            break

                        time.sleep(2)
                        soup = BeautifulSoup(page.content(), "html.parser")

                        product_cards = soup.select(".product-card, .single-product, div.col-md-3, div.col-sm-6, div.product")
                        if not product_cards:
                            # Fallback: search links pointing to product views
                            product_cards = soup.find_all("a", href=lambda h: h and "product" in h and "id=" in h)

                        if not product_cards:
                            break

                        page_items = 0
                        for card in product_cards:
                            card_text = card.get_text(separator=" ", strip=True)

                            # Title
                            title_el = card.find(["h3", "h4", "h5", "h2", "strong"]) if hasattr(card, "find") else None
                            title = title_el.get_text(strip=True) if title_el else card.get_text(strip=True)
                            if not title or len(title) < 3 or "view" in title.lower():
                                continue

                            # Clean leaked title text
                            title = re.split(r"Rs\.?|LKR", title)[0].strip()

                            # Price
                            price_match = re.search(r"(?:Rs\.?|LKR)\s*[\d,]+(?:\.\d{2})?", card_text)
                            price = price_match.group(0) if price_match else "N/A"

                            # URL
                            link_el = card if card.name == "a" else card.find("a", href=True)
                            url = urljoin(self.base_url, link_el["href"]).split("#")[0] if link_el else cat_url

                            stock = "Out of Stock" if "out of stock" in card_text.lower() else "In Stock"

                            if self.add_product(
                                category=cat_name,
                                title=title,
                                price=price,
                                stock=stock,
                                url=url
                            ):
                                page_items += 1

                        if page_items == 0:
                            break

                        current_page += 1
                        self.sleep_polite()

                    except Exception as e:
                        print(f"    [!] Error crawling {page_url}: {e}")
                        break

            browser.close()

        return self.save_csv()


def run(max_pages: int = 6, headless: bool = True):
    scraper = GalleLaptopScraper(headless=headless)
    return scraper.scrape(max_pages=max_pages)


if __name__ == "__main__":
    run(max_pages=1)
