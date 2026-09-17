"""
scrapers/tulip.py - Tulip Computers Modular Scraper
Engine: Playwright (Dynamic CSR / Single Page App)
Routing: Dynamic clean category base URLs (/product/c/<cat>) and product links
"""

import re
import time
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from scrapers.base_scraper import BaseScraper


class TulipScraper(BaseScraper):
    def __init__(self, headless: bool = True):
        super().__init__(store_name="Tulip Computers", base_url="https://www.tulipcom.lk")
        self.headless = headless

    def get_categories(self, page):
        categories = []
        try:
            page.goto(self.base_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)
            soup = BeautifulSoup(page.content(), "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if "/product/c/" in href:
                    clean_url = urljoin(self.base_url, href).split("#")[0].split("?")[0].rstrip("/")
                    cat_name = clean_url.split("/product/c/")[-1].replace("_", " ").replace("-", " ").title()
                    if (cat_name, clean_url) not in categories and clean_url != f"{self.base_url}/product/c":
                        categories.append((cat_name, clean_url))
        except Exception as e:
            print(f"[!] Error discovering Tulip categories: {e}")

        if not categories:
            categories = [
                ("Graphics Card", "https://www.tulipcom.lk/product/c/graphics_card"),
                ("Processors", "https://www.tulipcom.lk/product/c/processors"),
                ("Motherboards", "https://www.tulipcom.lk/product/c/motherboards"),
                ("Memory", "https://www.tulipcom.lk/product/c/ram"),
                ("Storage", "https://www.tulipcom.lk/product/c/storage"),
                ("Power Supply", "https://www.tulipcom.lk/product/c/power_supply"),
                ("Casings", "https://www.tulipcom.lk/product/c/casings"),
                ("Monitors", "https://www.tulipcom.lk/product/c/monitors"),
                ("Laptops", "https://www.tulipcom.lk/product/c/laptops")
            ]
        return categories

    def scrape(self, max_pages: int = 8):
        print(f"\n[+] Starting Tulip Computers Scraper...")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(
                user_agent=self.get_headers()["User-Agent"]
            )
            page = context.new_page()

            categories = self.get_categories(page)

            for cat_name, cat_url in categories:
                print(f" -> Category: [{cat_name}] -> {cat_url}")
                current_page = 1

                while current_page <= max_pages:
                    page_url = cat_url if current_page == 1 else f"{cat_url}?page={current_page}"
                    try:
                        res = page.goto(page_url, wait_until="domcontentloaded", timeout=30000)
                        if res and res.status in [404, 403]:
                            break

                        time.sleep(2)
                        soup = BeautifulSoup(page.content(), "html.parser")

                        # Product cards / links
                        product_links = soup.find_all("a", href=lambda h: h and ("/product/d/" in h or "/product/v/" in h))
                        if not product_links:
                            break

                        page_items = 0
                        for a in product_links:
                            card = a.find_parent("div", class_=lambda c: c and ("col" in c or "card" in c or "product" in c)) or a
                            card_text = card.get_text(separator=" ", strip=True)

                            # Title
                            title_el = card.find(["h3", "h4", "h5", "h2", "p"])
                            title = title_el.get_text(strip=True) if title_el else a.get_text(strip=True)
                            if not title or len(title) < 3 or "view" in title.lower():
                                slug = a["href"].split("/")[-1].replace("_", " ").replace("-", " ").title()
                                title = slug

                            # Price
                            price_match = re.search(r"(?:Rs\.?|LKR)\s*[\d,]+(?:\.\d{2})?", card_text)
                            price = price_match.group(0) if price_match else "N/A"

                            url = urljoin(self.base_url, a["href"]).split("?")[0]
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
                        print(f"    [!] Error loading {page_url}: {e}")
                        break

            browser.close()

        return self.save_csv()


def run(max_pages: int = 8, headless: bool = True):
    scraper = TulipScraper(headless=headless)
    return scraper.scrape(max_pages=max_pages)


if __name__ == "__main__":
    run(max_pages=1)
