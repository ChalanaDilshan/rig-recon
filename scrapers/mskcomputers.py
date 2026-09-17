"""
scrapers/mskcomputers.py - MSK Computers Modular Scraper
Engine: Playwright (CSR with AJAX filter hydration & scrolling)
Selectors: .product-card, h3 titles, LKR price regex
"""

import re
import time
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from scrapers.base_scraper import BaseScraper

CATEGORIES = [
    ("GPU", "https://www.mskcomputers.lk/categories/graphic-card"),
    ("CPU", "https://www.mskcomputers.lk/categories/processor"),
    ("Motherboard", "https://www.mskcomputers.lk/categories/motherboards"),
    ("RAM", "https://www.mskcomputers.lk/categories/memory-ram"),
    ("Storage", "https://www.mskcomputers.lk/categories/storage"),
    ("PSU", "https://www.mskcomputers.lk/categories/power-supply"),
    ("Casing", "https://www.mskcomputers.lk/categories/casing"),
    ("Monitor", "https://www.mskcomputers.lk/categories/monitors")
]


class MSKComputersScraper(BaseScraper):
    def __init__(self, headless: bool = True):
        super().__init__(store_name="MSK Computers", base_url="https://www.mskcomputers.lk")
        self.headless = headless

    def scrape(self):
        print(f"\n[+] Starting MSK Computers Scraper...")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(
                user_agent=self.get_headers()["User-Agent"]
            )
            page = context.new_page()

            for cat_name, cat_url in CATEGORIES:
                print(f" -> Category: [{cat_name}] -> {cat_url}")
                try:
                    page.goto(cat_url, wait_until="domcontentloaded", timeout=45000)

                    # Wait for AJAX filter hydration
                    try:
                        page.wait_for_selector(".product-card", timeout=8000)
                    except Exception:
                        print(f"    [!] No products loaded for {cat_name}.")
                        continue

                    # Scroll to trigger lazy loading
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2);")
                    time.sleep(1)
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(1.5)

                    soup = BeautifulSoup(page.content(), "html.parser")
                    product_cards = soup.select(".product-card")

                    for card in product_cards:
                        card_text = card.get_text(separator=" ", strip=True)

                        # Title
                        title_el = card.select_one("h3")
                        if title_el:
                            title = title_el.get_text(strip=True)
                        else:
                            img_el = card.select_one("img[alt]")
                            title = img_el["alt"].strip() if img_el else "N/A"

                        # Price
                        price_match = re.search(r"LKR\s*[\d,]+(?:\.\d{2})?", card_text)
                        price = price_match.group(0) if price_match else "N/A"

                        # Stock
                        upper_text = card_text.upper()
                        stock = "Out of Stock" if "OUT OF STOCK" in upper_text else "In Stock"

                        # URL
                        if card.name == "a" and card.get("href"):
                            product_url = urljoin(self.base_url, card["href"])
                        else:
                            link_el = card.select_one("a[href]")
                            product_url = urljoin(self.base_url, link_el["href"]) if link_el else cat_url

                        if title and title != "N/A":
                            self.add_product(
                                category=cat_name,
                                title=title,
                                price=price,
                                stock=stock,
                                url=product_url
                            )

                    self.sleep_polite()

                except Exception as e:
                    print(f"    [!] Error loading {cat_url}: {e}")

            browser.close()

        return self.save_csv()


def run(headless: bool = True):
    scraper = MSKComputersScraper(headless=headless)
    return scraper.scrape()


if __name__ == "__main__":
    run(headless=True)
