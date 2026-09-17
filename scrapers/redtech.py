"""
scrapers/redtech.py - Red Tech Modular Scraper
Engine: Playwright (WooCommerce / Woodmart Theme)
Selectors: .product-grid-item, .wd-entities-title
"""

import sys
import os
import re
import time
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# Resilient import allowing direct execution from scrapers/ or workspace root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from scrapers.base_scraper import BaseScraper
except ModuleNotFoundError:
    from base_scraper import BaseScraper

CATEGORIES = [
    ("GPU", "https://redtech.lk/product-category/pc-components/gpu/consumer-graphic-cards/"),
    ("CPU", "https://redtech.lk/product-category/pc-components/processors/intel-processors/"),
    ("CPU", "https://redtech.lk/product-category/pc-components/processors/amd-processors/"),
    ("Motherboard", "https://redtech.lk/product-category/pc-components/motherboard/"),
    ("RAM", "https://redtech.lk/product-category/pc-components/ram/desktop-ram/"),
    ("Storage", "https://redtech.lk/product-category/pc-components/storage/internal-ssd/"),
    ("PSU", "https://redtech.lk/product-category/pc-components/power-supply/"),
    ("Casing", "https://redtech.lk/product-category/pc-components/casing/"),
    ("Monitor", "https://redtech.lk/product-category/monitors/"),
    ("Laptop", "https://redtech.lk/product-category/laptops/")
]


class RedTechScraper(BaseScraper):
    def __init__(self, headless: bool = True):
        super().__init__(store_name="Red Tech", base_url="https://redtech.lk")
        self.headless = headless

    def scrape(self, max_pages_per_category: int = 4):
        print(f"\n[+] Starting Red Tech Scraper...")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(
                user_agent=self.get_headers()["User-Agent"]
            )
            page = context.new_page()

            for cat_name, cat_url in CATEGORIES:
                print(f" -> Category: [{cat_name}] -> {cat_url}")
                current_page = 1
                prev_first_title = None

                while current_page <= max_pages_per_category:
                    page_url = cat_url if current_page == 1 else f"{cat_url.rstrip('/')}/page/{current_page}/"
                    try:
                        res = page.goto(page_url, wait_until="domcontentloaded", timeout=35000)
                        if res and res.status in [404, 403]:
                            break

                        time.sleep(2)
                        # Scroll to hydrate Woodmart grid
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2);")
                        time.sleep(1)

                        soup = BeautifulSoup(page.content(), "html.parser")
                        cards = soup.select(".product-grid-item, div.product, li.product, .type-product")
                        if not cards:
                            break

                        first_title_el = cards[0].select_one(".wd-entities-title, .woocommerce-loop-product__title, h2, h3")
                        first_title = first_title_el.get_text(strip=True) if first_title_el else ""
                        if first_title and first_title == prev_first_title:
                            break
                        prev_first_title = first_title

                        for card in cards:
                            title_el = card.select_one(".wd-entities-title, .woocommerce-loop-product__title, h2, h3, a.product-title")
                            price_el = card.select_one(".price ins, .price .amount, .price")
                            link_el = card.select_one("a[href]")

                            title = title_el.get_text(strip=True) if title_el else None
                            price = price_el.get_text(strip=True) if price_el else "N/A"
                            url = urljoin(self.base_url, link_el["href"]).split("?")[0] if link_el else ""

                            # Skip sub-category cards that lack prices
                            if not price_el or price == "N/A":
                                continue

                            card_classes = " ".join(card.get("class", []))
                            card_text = card.get_text(separator=" ", strip=True).lower()
                            if "out-of-stock" in card_classes or "out of stock" in card_text:
                                stock = "Out of Stock"
                            else:
                                stock = "In Stock"

                            if title and len(title) > 3:
                                self.add_product(
                                    category=cat_name,
                                    title=title,
                                    price=price,
                                    stock=stock,
                                    url=url
                                )

                        current_page += 1
                        self.sleep_polite()

                    except Exception as e:
                        print(f"    [!] Error crawling {page_url}: {e}")
                        break

            browser.close()

        return self.save_csv()


def run(max_pages: int = 4, headless: bool = True):
    scraper = RedTechScraper(headless=headless)
    return scraper.scrape(max_pages_per_category=max_pages)


if __name__ == "__main__":
    run(max_pages=2)
