"""
scrapers/gallelaptop.py - Galle Laptop Modular Scraper
Engine: Fast HTTP (BeautifulSoup) with resilient selector extraction
Routing: Subcategory extraction (products.php?ci=...&sci=...)
"""

import sys
import os
import re
import time
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

# Resilient import allowing direct execution from scrapers/ or workspace root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from scrapers.base_scraper import BaseScraper
except ModuleNotFoundError:
    from base_scraper import BaseScraper

CATEGORIES = [
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

    def scrape(self, max_pages: int = 5):
        print(f"\n[+] Starting Galle Laptop Scraper...")
        session = requests.Session()
        session.headers.update(self.get_headers())

        for cat_name, cat_url in CATEGORIES:
            print(f" -> Category: [{cat_name}] -> {cat_url}")
            current_page = 1

            while current_page <= max_pages:
                page_param = f"&page={current_page}" if current_page > 1 else ""
                page_url = f"{cat_url}{page_param}"

                try:
                    res = session.get(page_url, timeout=20)
                    if res.status_code != 200:
                        break

                    soup = BeautifulSoup(res.text, "html.parser")
                    cards = soup.select(".Product, .tab_view_product")
                    if not cards:
                        break

                    page_items = 0
                    for card in cards:
                        # Extract product title
                        title_el = card.select_one("b.pro_name, .pro_short_desc, h3, h4")
                        if not title_el:
                            continue
                        title = title_el.get_text(strip=True)
                        if not title or len(title) < 3:
                            continue

                        # Extract product price
                        price_el = card.select_one(".GreenTx, p.tx5, .tx5")
                        price = price_el.get_text(strip=True) if price_el else "N/A"

                        # Extract stock
                        instock_el = card.select_one(".inStock img")
                        stock = "In Stock" if instock_el else "In Stock"

                        # Extract URL or construct from category + code
                        code_el = card.select_one(".proCode")
                        code_text = code_el.get_text(strip=True) if code_el else ""
                        item_url = f"{cat_url}#{code_text.replace(' ', '_')}" if code_text else cat_url

                        if self.add_product(
                            category=cat_name,
                            title=title,
                            price=price,
                            stock=stock,
                            url=item_url
                        ):
                            page_items += 1

                    if page_items == 0:
                        break

                    current_page += 1
                    self.sleep_polite()

                except Exception as e:
                    print(f"    [!] Error crawling {page_url}: {e}")
                    break

        return self.save_csv()


def run(max_pages: int = 5, headless: bool = True):
    scraper = GalleLaptopScraper(headless=headless)
    return scraper.scrape(max_pages=max_pages)


if __name__ == "__main__":
    run(max_pages=1)
