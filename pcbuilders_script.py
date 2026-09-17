import csv
import time
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://pcbuilders.lk"
DOMAIN = "pcbuilders.lk"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

class PcBuildersFullCrawler:
    def __init__(self, start_url):
        self.start_url = start_url
        self.category_queue = []
        self.visited_categories = set()
        self.all_products = []

    def is_valid_category_url(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.netloc and DOMAIN not in parsed.netloc:
            return False
        
        path = parsed.path.lower()
        # Matches common WooCommerce category paths and custom category slugs
        category_indicators = [
            "/product-category/",
            "/category/",
            "/graphic-cards",
            "/processors",
            "/motherboards",
            "/ram",
            "/storage",
            "/power-supplies",
            "/casings",
            "/cooling"
        ]
        
        # Filter out carts, account pages, checkouts, and static resources
        ignored_patterns = ["/cart", "/checkout", "/my-account", "/contact", "/about", ".jpg", ".png", ".pdf"]
        if any(bad in path for bad in ignored_patterns):
            return False

        return any(ind in path for ind in category_indicators)

    def discover_categories(self):
        """Discovers product categories from the navigation menu and shop pages."""
        print(f"Discovering categories from: {self.start_url}")
        try:
            res = requests.get(self.start_url, headers=HEADERS, timeout=15)
            if res.status_code != 200:
                print(f"Failed to fetch homepage. Status: {res.status_code}")
                return

            soup = BeautifulSoup(res.text, "html.parser")
            for a_tag in soup.find_all("a", href=True):
                clean_url = urljoin(BASE_URL, a_tag["href"]).split("#")[0].split("?")[0].rstrip("/") + "/"
                if self.is_valid_category_url(clean_url):
                    if clean_url not in self.category_queue and clean_url not in self.visited_categories:
                        self.category_queue.append(clean_url)

            print(f"Discovered {len(self.category_queue)} category queues.")
        except requests.RequestException as e:
            print(f"Error while discovering categories: {e}")

    def scrape_category_pages(self, category_url):
        """Crawls all pagination pages for a specific category."""
        category_name = [seg for seg in urlparse(category_url).path.split("/") if seg][-1].replace("-", " ").title()
        page = 1
        previous_first_title = None
        category_items_count = 0

        print(f"\n📂 Crawling Category: [{category_name}]")

        while True:
            # WooCommerce supports /page/{n}/ or ?paged={n}
            page_url = category_url if page == 1 else f"{category_url}page/{page}/"
            print(f"   -> Page {page}: {page_url}")

            try:
                res = requests.get(page_url, headers=HEADERS, timeout=15)

                if res.status_code in [404, 403]:
                    break

                soup = BeautifulSoup(res.text, "html.parser")

                # WooCommerce product cards selectors
                product_cards = soup.select(
                    "li.product, div.product, div.product-small, .type-product, div.product-inner"
                )

                if not product_cards:
                    print(f"      No products found on page {page}. Moving next.")
                    break

                # Infinite loop guard: detects if WordPress is looping the last page
                first_title_el = product_cards[0].select_one(
                    ".woocommerce-loop-product__title, .product-title, h2, h3, .name a"
                )
                first_title = first_title_el.get_text(strip=True) if first_title_el else ""
                if first_title and first_title == previous_first_title:
                    print("      Duplicate page detected. End of category reached.")
                    break
                previous_first_title = first_title

                page_extracted = 0
                for card in product_cards:
                    # 1. Product Title
                    title_el = card.select_one(
                        ".woocommerce-loop-product__title, .product-title, .name a, h2, h3"
                    )
                    title = title_el.get_text(strip=True) if title_el else None

                    if not title:
                        continue

                    # 2. Product Price
                    price_el = card.select_one(
                        ".price ins .woocommerce-Price-amount, .price .woocommerce-Price-amount, .price, .amount"
                    )
                    price = price_el.get_text(strip=True) if price_el else "N/A"

                    # 3. Product URL
                    link_el = card.select_one("a[href]")
                    product_url = urljoin(BASE_URL, link_el["href"]) if link_el else "N/A"

                    # 4. Stock Status
                    card_classes = " ".join(card.get("class", []))
                    card_text = card.get_text(separator=" ", strip=True).lower()

                    if "out-of-stock" in card_classes or "outofstock" in card_classes or "out of stock" in card_text:
                        stock_status = "Out of Stock"
                    elif "in-stock" in card_classes or "instock" in card_classes or "add to cart" in card_text:
                        stock_status = "In Stock"
                    else:
                        stock_status = "Available / In Stock"

                    self.all_products.append({
                        "Category": category_name,
                        "Title": title,
                        "Price": price,
                        "Stock": stock_status,
                        "URL": product_url
                    })

                    category_items_count += 1
                    page_extracted += 1

                print(f"      Extracted {page_extracted} items from page {page}")
                page += 1
                time.sleep(1.2)

            except requests.RequestException as err:
                print(f"      Request failed on page {page}: {err}")
                break

        print(f"✔️ Finished [{category_name}]: Total {category_items_count} items extracted.")

    def run(self):
        self.discover_categories()

        # Direct category fallback if navigation links are loaded via heavy JavaScript
        if not self.category_queue:
            print("Using fallback category list...")
            self.category_queue = [
                "https://pcbuilders.lk/graphic-cards/",
                "https://pcbuilders.lk/processors/",
                "https://pcbuilders.lk/motherboards/",
                "https://pcbuilders.lk/ram/",
                "https://pcbuilders.lk/storage/",
                "https://pcbuilders.lk/power-supply/",
                "https://pcbuilders.lk/casings/",
                "https://pcbuilders.lk/cooling/",
                "https://pcbuilders.lk/monitors/"
            ]

        while self.category_queue:
            category_url = self.category_queue.pop(0)
            if category_url in self.visited_categories:
                continue

            self.visited_categories.add(category_url)
            self.scrape_category_pages(category_url)
            time.sleep(1.5)

        self.export_to_csv()

    def export_to_csv(self, filename="pcbuilders_all_products.csv"):
        if not self.all_products:
            print("\nNo products were collected.")
            return

        fields = ["Category", "Title", "Price", "Stock", "URL"]
        with open(filename, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(self.all_products)

        print(f"\n✅ Scraping complete! {len(self.all_products)} total items saved into '{filename}'.")

if __name__ == "__main__":
    crawler = PcBuildersFullCrawler(start_url=BASE_URL)
    crawler.run()