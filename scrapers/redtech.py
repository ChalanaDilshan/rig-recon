"""
scrapers/redtech.py - Red Tech Modular Scraper
Engine: Requests + BeautifulSoup (Fast, resilient HTTP catalog crawler)
Selectors: .product-grid-item, .wd-entities-title, a.product-loop-title
"""

import sys
import os
import time
import unicodedata
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from scrapers.base_scraper import BaseScraper
except ModuleNotFoundError:
    from base_scraper import BaseScraper

CATEGORIES = [
    ("GPU", "https://redtech.lk/product-category/gpu/"),
    ("CPU", "https://redtech.lk/product-category/processors/"),
    ("Motherboard", "https://redtech.lk/product-category/motherboards/"),
    ("RAM", "https://redtech.lk/product-category/ram/"),
    ("Storage", "https://redtech.lk/product-category/storage/"),
    ("PSU", "https://redtech.lk/product-category/psu/"),
    ("Casing", "https://redtech.lk/product-category/pc-cases/"),
    ("Cooler", "https://redtech.lk/product-category/cooling/"),
    ("Monitor", "https://redtech.lk/product-category/output/monitors/"),
    ("Laptop", "https://redtech.lk/product-category/laptops-notebooks/"),
    ("Peripherals", "https://redtech.lk/product-category/input/")
]


class RedTechScraper(BaseScraper):
    def __init__(self, headless: bool = True):
        super().__init__(store_name="Red Tech", base_url="https://redtech.lk")
        self.headless = headless
        self.session = requests.Session()

    def _parse_cards(self, cards, cat_name: str) -> int:
        added = 0
        for card in cards:
            # Skip Woodmart sub-category tiles
            if "product-category" in card.get("class", []):
                continue

            title_el = card.select_one(".wd-entities-title, .woocommerce-loop-product__title, a.product-loop-title, h2, h3")
            link_el = card.select_one("a.product-loop-title, a.woocommerce-LoopProduct-link, h2 a, h3 a, a[href*='/product/']")
            if not link_el or not link_el.get("href"):
                continue

            price_ins = card.select_one(".price ins .woocommerce-Price-amount, .price ins")
            if price_ins:
                price = price_ins.get_text(strip=True)
            else:
                price_reg = card.select_one(".price .woocommerce-Price-amount, .price")
                price = price_reg.get_text(strip=True) if price_reg else "N/A"

            title = unicodedata.normalize("NFKD", title_el.get_text(strip=True)) if title_el else None
            price = unicodedata.normalize("NFKD", price)
            url = urljoin(self.base_url, link_el["href"]).split("?")[0].strip()

            card_classes = " ".join(card.get("class", []))
            card_text = card.get_text(separator=" ", strip=True).lower()
            if "out-of-stock" in card_classes or "outofstock" in card_classes or "out of stock" in card_text:
                stock = "Out of Stock"
            else:
                stock = "In Stock"

            if title and len(title) > 2 and url and self.add_product(category=cat_name, title=title, price=price, stock=stock, url=url):
                added += 1

        return added

    def scrape(self, max_pages_per_category: int = 4):
        print(f"\n[+] Starting Red Tech Scraper (Max Pages: {max_pages_per_category})...")
        total_items_before = len(self.products)

        for cat_name, cat_url in CATEGORIES:
            print(f" -> Category: [{cat_name}] -> {cat_url}")
            current_page = 1
            prev_first_title = None

            while current_page <= max_pages_per_category:
                page_url = cat_url if current_page == 1 else f"{cat_url.rstrip('/')}/page/{current_page}/"
                res = None
                for attempt in range(2):
                    try:
                        res = self.session.get(page_url, headers=self.get_headers(), timeout=25)
                        break
                    except Exception as err:
                        if attempt == 0:
                            time.sleep(2)
                        else:
                            print(f"    [!] Error crawling {page_url}: {err}")

                if not res or res.status_code in [404, 403]:
                    break

                try:
                    soup = BeautifulSoup(res.text, "html.parser")
                    raw_cards = soup.select(".product-grid-item, div.product, li.product, .type-product")
                    # Filter out subcategory cards
                    cards = [c for c in raw_cards if "product-category" not in c.get("class", [])]
                    if not cards:
                        break

                    first_title_el = cards[0].select_one(".wd-entities-title, .woocommerce-loop-product__title, a.product-loop-title, h2, h3")
                    first_title = first_title_el.get_text(strip=True) if first_title_el else ""
                    if first_title and first_title == prev_first_title:
                        break
                    prev_first_title = first_title

                    added = self._parse_cards(cards, cat_name)
                    print(f"   [Page {current_page}] Harvested {len(cards)} items ({added} new).")

                    current_page += 1
                    self.sleep_polite()

                except Exception as e:
                    print(f"    [!] Error parsing {page_url}: {e}")
                    break

        total_scraped = len(self.products) - total_items_before
        print(f"\n[+] Red Tech Scraping Completed: {total_scraped} total products harvested.")
        return self.save_csv()


def run(max_pages: int = 4, headless: bool = True):
    scraper = RedTechScraper(headless=headless)
    return scraper.scrape(max_pages_per_category=max_pages)


if __name__ == "__main__":
    run(max_pages=3)
