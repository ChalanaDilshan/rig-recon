import csv
import re
import time
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://redtech.lk"
DOMAIN = "redtech.lk"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

class RedtechFullCrawler:
    def __init__(self, start_url):
        self.start_url = start_url
        self.category_queue = []
        self.visited_categories = set()
        self.all_products = []
        self.seen_product_urls = set()

    def is_valid_category_url(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.netloc and DOMAIN not in parsed.netloc:
            return False

        path = parsed.path.lower()
        if "/product-category/" not in path:
            return False

        ignored = ["/cart", "/checkout", "/my-account", ".jpg", ".png"]
        return not any(x in path for x in ignored)

    def discover_categories(self):
        """Scans navigation and menus to find all product categories."""
        print(f"Discovering categories from homepage: {BASE_URL}")
        try:
            res = requests.get(BASE_URL, headers=HEADERS, timeout=15)
            if res.status_code != 200:
                print(f"Failed to fetch homepage. Status: {res.status_code}")
                return

            soup = BeautifulSoup(res.text, "html.parser")
            for a_tag in soup.find_all("a", href=True):
                clean_url = urljoin(BASE_URL, a_tag["href"]).split("#")[0].split("?")[0].rstrip("/") + "/"
                if self.is_valid_category_url(clean_url):
                    if clean_url not in self.category_queue and clean_url not in self.visited_categories:
                        self.category_queue.append(clean_url)

            print(f"Discovered {len(self.category_queue)} categories.\n")
        except requests.RequestException as e:
            print(f"Error during category discovery: {e}")

    def scrape_category_pages(self, category_url):
        """Crawls all pagination pages (/page/1/, /page/2/...) of a category."""
        category_name = [s for s in urlparse(category_url).path.split("/") if s][-1].replace("-", " ").title()
        page = 1
        previous_first_title = None
        category_total = 0

        print(f"📂 Crawling Category: [{category_name}] -> {category_url}")

        while True:
            page_url = category_url if page == 1 else f"{category_url.rstrip('/')}/page/{page}/"
            print(f"   -> Page {page}: {page_url}")

            try:
                res = requests.get(page_url, headers=HEADERS, timeout=15)
                if res.status_code in [404, 403]:
                    break

                soup = BeautifulSoup(res.text, "html.parser")

                # WooCommerce standard product cards
                product_cards = soup.select(
                    "li.product, div.product, div.product-small, .type-product, div.product-inner"
                )

                if not product_cards:
                    print(f"      No products found on page {page}. Category complete.")
                    break

                # Loop prevention
                first_title_el = product_cards[0].select_one(
                    ".woocommerce-loop-product__title, .product-title, h2, h3, .name a"
                )
                first_title = first_title_el.get_text(strip=True) if first_title_el else ""
                if first_title and first_title == previous_first_title:
                    print("      Duplicate page detected. End reached.")
                    break
                previous_first_title = first_title

                page_items = 0
                for card in product_cards:
                    # 1. Title
                    title_el = card.select_one(
                        ".woocommerce-loop-product__title, .product-title, .name a, h2, h3"
                    )
                    title = title_el.get_text(strip=True) if title_el else None
                    if not title or len(title) < 3:
                        continue

                    # 2. Price
                    price_el = card.select_one(
                        ".price ins .woocommerce-Price-amount, .price .woocommerce-Price-amount, .price, .amount"
                    )
                    if price_el:
                        price = price_el.get_text(strip=True)
                    else:
                        match = re.search(r"(?:Rs\.?|LKR)\s*[\d,]+(?:\.\d{2})?", card.get_text())
                        price = match.group(0) if match else "N/A"

                    # 3. Product URL
                    link_el = card.select_one("a.product-loop-title, a.woocommerce-LoopProduct-link, h2 a, h3 a, a[href*='/product/']")
                    product_url = urljoin(BASE_URL, link_el["href"]).split("?")[0] if (link_el and link_el.get("href")) else "N/A"

                    if not link_el or product_url == "N/A" or product_url in self.seen_product_urls:
                        continue

                    # 4. Stock Status
                    card_classes = " ".join(card.get("class", [])).lower()
                    card_text = card.get_text(separator=" ", strip=True).lower()

                    if "out-of-stock" in card_classes or "outofstock" in card_classes or "out of stock" in card_text:
                        stock = "Out of Stock"
                    elif "in-stock" in card_classes or "instock" in card_classes or "add to cart" in card_text:
                        stock = "In Stock"
                    else:
                        stock = "In Stock"

                    self.seen_product_urls.add(product_url)
                    self.all_products.append({
                        "Category": category_name,
                        "Title": title,
                        "Price": price,
                        "Stock": stock,
                        "URL": product_url
                    })

                    page_items += 1
                    category_total += 1
                    print(f"      [{stock}] {title} -> {price}")

                print(f"      Extracted {page_items} items from page {page}")
                if page_items == 0:
                    break

                page += 1
                time.sleep(1.2)

            except requests.RequestException as err:
                print(f"      Request error on page {page}: {err}")
                break

        print(f"✔️ Finished [{category_name}]: Total {category_total} items.\n")

    def run(self):
        self.discover_categories()

        # Fallback category list if menu links are hidden
        if not self.category_queue:
            print("Using fallback category list...")
            self.category_queue = [
                "https://redtech.lk/product-category/pc-components/gpu/",
                "https://redtech.lk/product-category/pc-components/processors/",
                "https://redtech.lk/product-category/pc-components/motherboard/",
                "https://redtech.lk/product-category/pc-components/ram/",
                "https://redtech.lk/product-category/pc-components/storage/",
                "https://redtech.lk/product-category/pc-components/power-supply/",
                "https://redtech.lk/product-category/pc-components/casing/",
                "https://redtech.lk/product-category/monitors/",
                "https://redtech.lk/product-category/laptops/",
            ]

        while self.category_queue:
            cat_url = self.category_queue.pop(0)
            if cat_url in self.visited_categories:
                continue

            self.visited_categories.add(cat_url)
            self.scrape_category_pages(cat_url)
            time.sleep(1.5)

        self.save_csv()

    def save_csv(self, filename="redtech_all_products.csv"):
        if not self.all_products:
            print("\n❌ No products collected.")
            return

        fields = ["Category", "Title", "Price", "Stock", "URL"]
        with open(filename, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(self.all_products)

        print(f"\n✅ All Done! Total {len(self.all_products)} products saved into '{filename}'.")

if __name__ == "__main__":
    crawler = RedtechFullCrawler(BASE_URL)
    crawler.run()