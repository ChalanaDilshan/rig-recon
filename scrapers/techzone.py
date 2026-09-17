"""
scrapers/techzone.py - Techzone.lk Modular Scraper
Engine: Playwright Persistent Context + BeautifulSoup (Resilient to Cloudflare Turnstile)
Pagination: /page/{n}/
"""

import sys
import os
import time
from urllib.parse import urljoin
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from scrapers.base_scraper import BaseScraper
except ModuleNotFoundError:
    from base_scraper import BaseScraper

CATEGORIES = [
    ("GPU", "https://techzone.lk/product-category/computer-components/graphic-card/"),
    ("CPU", "https://techzone.lk/product-category/computer-components/processor/"),
    ("Motherboard", "https://techzone.lk/product-category/computer-components/motherboard/"),
    ("RAM", "https://techzone.lk/product-category/computer-components/memory/"),
    ("Storage", "https://techzone.lk/product-category/storage/"),
    ("PSU", "https://techzone.lk/product-category/computer-components/power-supply/"),
    ("Casing", "https://techzone.lk/product-category/computer-components/computer-cases/"),
    ("Cooler", "https://techzone.lk/product-category/computer-components/cooler/"),
    ("Monitor", "https://techzone.lk/product-category/computer-components/monitors/"),
    ("Laptop", "https://techzone.lk/product-category/gaming-laptops-computers/laptops/")
]

PROFILE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "browser_profiles", "techzone")


class TechzoneScraper(BaseScraper):
    def __init__(self, headless: bool = False):
        super().__init__(store_name="Techzone", base_url="https://techzone.lk")
        self.headless = headless
        os.makedirs(PROFILE_DIR, exist_ok=True)

    def _wait_for_cloudflare(self, page, timeout: int = 25) -> bool:
        """Waits for Cloudflare challenge/Turnstile to resolve."""
        start = time.time()
        while time.time() - start < timeout:
            try:
                title = page.title()
                if "Just a moment" not in title and "Security" not in title and "Attention" not in title and title.strip():
                    return True
            except Exception:
                pass
            time.sleep(1)
        return False

    def _parse_cards(self, cards, cat_name: str) -> int:
        added = 0
        for card in cards:
            title_el = card.select_one(".woocommerce-loop-product__title, h2, h3")
            
            # Extract product specific URL (avoiding category tag URLs inside the card)
            link_el = card.select_one("a.woocommerce-LoopProduct-link, a.woocommerce-loop-product__link, a[href*='/product/']")
            if not link_el:
                link_el = card.select_one("h2 a, h3 a, .woocommerce-loop-product__title a")

            # Extract accurate price (favor sale ins over del)
            price_ins = card.select_one(".price ins .woocommerce-Price-amount, .price ins")
            if price_ins:
                price = price_ins.get_text(strip=True)
            else:
                price_reg = card.select_one(".price .woocommerce-Price-amount, .price")
                price = price_reg.get_text(strip=True) if price_reg else "N/A"

            title = title_el.get_text(strip=True) if title_el else None
            url = urljoin(self.base_url, link_el["href"]).strip() if (link_el and link_el.get("href")) else ""

            card_classes = " ".join(card.get("class", []))
            card_text = card.get_text(separator=" ", strip=True).lower()
            if "out-of-stock" in card_classes or "outofstock" in card_classes or "out of stock" in card_text:
                stock = "Out of Stock"
            else:
                stock = "In Stock"

            if title and url and self.add_product(category=cat_name, title=title, price=price, stock=stock, url=url):
                added += 1

        return added

    def scrape(self, max_pages_per_category: int = 5):
        from playwright.sync_api import sync_playwright

        print(f"\n[+] Starting Techzone Scraper (Headless: {self.headless})...")
        total_items_before = len(self.products)

        with sync_playwright() as p:
            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--no-default-browser-check"
            ]

            # Prefer installed real Chrome to minimize Cloudflare bot flags, fallback to chromium
            context = None
            for channel in ["chrome", None]:
                try:
                    kwargs = {
                        "user_data_dir": PROFILE_DIR,
                        "headless": self.headless,
                        "args": launch_args,
                        "viewport": {"width": 1280, "height": 800}
                    }
                    if channel:
                        kwargs["channel"] = channel
                    context = p.chromium.launch_persistent_context(**kwargs)
                    break
                except Exception as e:
                    if channel == "chrome":
                        continue
                    print(f"   [!] Browser launch error: {e}")
                    return self.save_csv()

            if not context:
                print("   [!] Could not launch browser.")
                return self.save_csv()

            page = context.pages[0] if context.pages else context.new_page()
            page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")

            for cat_name, cat_url in CATEGORIES:
                print(f"\n -> Category: {cat_name} -> {cat_url}")
                page_num = 1
                prev_first_title = None

                while page_num <= max_pages_per_category:
                    page_url = cat_url if page_num == 1 else f"{cat_url.rstrip('/')}/page/{page_num}/"

                    try:
                        res = page.goto(page_url, wait_until="domcontentloaded", timeout=45000)
                        if res and res.status == 404:
                            break

                        # Check if Cloudflare challenge is shown
                        if "Just a moment" in page.title() or "Security" in page.title():
                            print("   [!] Cloudflare challenge detected. Waiting for verification...")
                            cleared = self._wait_for_cloudflare(page, timeout=25)
                            if not cleared:
                                print(f"   [!] Cloudflare challenge did not clear on page {page_num}. Moving to next category.")
                                break

                        # Wait briefly for WooCommerce product catalog DOM
                        try:
                            page.wait_for_selector("li.product, div.product-small, .product-item, .type-product", timeout=8000)
                        except Exception:
                            pass

                        soup = BeautifulSoup(page.content(), "html.parser")
                        cards = soup.select("li.product, div.product-small, .product-item, .type-product")
                        if not cards:
                            # No products found on this page
                            break

                        # Prevent duplicate page loops
                        first_title_el = cards[0].select_one(".woocommerce-loop-product__title, h2, h3")
                        first_title = first_title_el.get_text(strip=True) if first_title_el else ""
                        if first_title and first_title == prev_first_title:
                            break
                        prev_first_title = first_title

                        added = self._parse_cards(cards, cat_name)
                        print(f"   [Page {page_num}] Harvested {len(cards)} items ({added} new).")

                        page_num += 1
                        self.sleep_polite()

                    except Exception as e:
                        print(f"   [!] Error on {page_url}: {e}")
                        break

            context.close()

        total_scraped = len(self.products) - total_items_before
        print(f"\n[+] Techzone Scraping Completed: {total_scraped} total products harvested.")
        return self.save_csv()


def run(max_pages: int = 5, headless: bool = False):
    scraper = TechzoneScraper(headless=headless)
    return scraper.scrape(max_pages_per_category=max_pages)


if __name__ == "__main__":
    run(max_pages=2, headless=False)
