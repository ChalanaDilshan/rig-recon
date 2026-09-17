import csv
import re
import time
from urllib.parse import urljoin, urlparse, parse_qs
from bs4 import BeautifulSoup

# Cloudflare WAF block වීම වැළැක්වීමට curl_cffi භාවිතය
try:
    from curl_cffi import requests
    USE_CURL_CFFI = True
except ImportError:
    import requests
    USE_CURL_CFFI = False

BASE_URL = "https://www.gamestreet.lk"
START_URL = "https://www.gamestreet.lk/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

class GameStreetFullCrawler:
    def __init__(self, start_url):
        self.start_url = start_url
        self.category_queue = []
        self.visited_categories = set()
        self.all_products = []
        self.seen_product_urls = set()

    def fetch(self, url):
        """Fetches page HTML with browser impersonation."""
        if USE_CURL_CFFI:
            return requests.get(url, impersonate="chrome120", timeout=20)
        return requests.get(url, headers=HEADERS, timeout=20)

    def discover_categories(self):
        """Discovers all category and sub-category URLs from the main navigation menu."""
        print(f"Discovering categories from homepage: {self.start_url}")
        try:
            res = self.fetch(self.start_url)
            if res.status_code != 200:
                print(f"Failed to fetch homepage. Status: {res.status_code}")
                return

            soup = BeautifulSoup(res.text, "html.parser")
            
            # Game Street category links use the pattern 'products.php?cat='
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"].strip()
                if "products.php?cat=" in href:
                    clean_url = urljoin(BASE_URL, href).split("#")[0]
                    cat_name = a_tag.get_text(strip=True)
                    if not cat_name or len(cat_name) < 2:
                        cat_name = "Hardware"

                    if clean_url not in [url for _, url in self.category_queue] and clean_url not in self.visited_categories:
                        self.category_queue.append((cat_name, clean_url))

            print(f"Discovered {len(self.category_queue)} categories.\n")
        except Exception as e:
            print(f"Error during category discovery: {e}")

    def scrape_category(self, cat_name, category_url):
        """Scrapes all products and handles pagination inside a category."""
        print(f"📂 Crawling Category: [{cat_name}] -> {category_url}")
        page = 1
        previous_first_title = None
        category_item_count = 0

        while True:
            # Handle pagination if parameter exists
            page_url = f"{category_url}&page={page}" if page > 1 else category_url

            try:
                res = self.fetch(page_url)
                if res.status_code in [404, 403]:
                    break

                soup = BeautifulSoup(res.text, "html.parser")

                # Find all product links
                product_links = soup.find_all("a", href=lambda h: h and "product_view.php?pid=" in h)
                if not product_links:
                    break

                # Extract product cards
                page_items = 0
                for link in product_links:
                    product_url = urljoin(BASE_URL, link["href"]).split("&page=")[0]
                    if product_url in self.seen_product_urls:
                        continue

                    # Card container
                    card = link.find_parent("div", class_=lambda c: c and any(k in c for k in ["col-", "product", "item"]))
                    if not card:
                        card = link.parent

                    card_text = card.get_text(separator=" ", strip=True)

                    # 1. Product Title
                    title = None
                    for heading in card.find_all(["h2", "h3", "h4", "h5", "h6"]):
                        h_text = heading.get_text(strip=True)
                        if h_text and len(h_text) > 4:
                            title = h_text
                            break

                    if not title:
                        a_text = link.get_text(strip=True)
                        if a_text and a_text.lower() not in ["more details", "details", "add to quote"]:
                            title = a_text

                    if not title:
                        img = card.find("img")
                        if img and img.get("alt"):
                            title = img["alt"].strip()

                    if not title:
                        continue

                    # 2. Product Price
                    price_match = re.search(r"Rs\.?\s*([\d,]+(?:\.\d{2})?)", card_text)
                    price = f"Rs. {price_match.group(1)}" if price_match else "N/A"

                    # 3. Stock Status
                    lower_text = card_text.lower()
                    if "out of stock" in lower_text or "out-of-stock" in lower_text:
                        stock = "Out of Stock"
                    elif "add to quote" in lower_text or "in stock" in lower_text:
                        stock = "In Stock"
                    else:
                        stock = "Available / Check Site"

                    # Check for repeating page loop
                    if page_items == 0 and previous_first_title == title:
                        return

                    if page_items == 0:
                        previous_first_title = title

                    self.seen_product_urls.add(product_url)
                    self.all_products.append({
                        "Category": cat_name,
                        "Title": title,
                        "Price": price,
                        "Stock": stock,
                        "URL": product_url
                    })
                    page_items += 1
                    category_item_count += 1

                if page_items == 0:
                    break

                # Check if next page link exists
                has_next = soup.find("a", href=lambda h: h and f"page={page + 1}" in h)
                if not has_next:
                    break

                page += 1
                time.sleep(1.2)

            except Exception as err:
                print(f"   ⚠️ Error loading page: {err}")
                break

        print(f"   ✔️ Extracted {category_item_count} items from [{cat_name}].")

    def run(self):
        self.discover_categories()

        # Fallback if navigation links are rendered dynamically
        if not self.category_queue:
            print("Using manual fallback category list...")
            self.category_queue = [
                ("Graphics Cards", "https://www.gamestreet.lk/products.php?cat=Mg==&scat=Ng=="),
                ("Processors", "https://www.gamestreet.lk/products.php?cat=Mg==&scat=MQ=="),
                ("Motherboards", "https://www.gamestreet.lk/products.php?cat=Mg==&scat=Mg=="),
                ("Memory / RAM", "https://www.gamestreet.lk/products.php?cat=Mg==&scat=Mw=="),
                ("Storage / SSD / HDD", "https://www.gamestreet.lk/products.php?cat=Mg==&scat=NA=="),
                ("Power Supply", "https://www.gamestreet.lk/products.php?cat=Mg==&scat=NQ=="),
                ("Casings", "https://www.gamestreet.lk/products.php?cat=Mg==&scat=Nw=="),
                ("Cooling Solutions", "https://www.gamestreet.lk/products.php?cat=Mg==&scat=OA=="),
                ("Monitors", "https://www.gamestreet.lk/products.php?cat=NA==&scat=MA=="),
                ("Laptops", "https://www.gamestreet.lk/products.php?cat=MQ==&scat=MA=="),
                ("Pre Built PC", "https://www.gamestreet.lk/products.php?cat=NQ==&scat=MA=="),
            ]

        for cat_name, cat_url in self.category_queue:
            if cat_url in self.visited_categories:
                continue

            self.visited_categories.add(cat_url)
            self.scrape_category(cat_name, cat_url)
            time.sleep(1.5)

        self.save_to_csv()

    def save_to_csv(self, filename="gamestreet_all_products.csv"):
        if not self.all_products:
            print("\n❌ No products collected.")
            return

        fields = ["Category", "Title", "Price", "Stock", "URL"]
        with open(filename, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(self.all_products)

        print(f"\n✅ Finished! Saved {len(self.all_products)} total items across all categories into '{filename}'.")

if __name__ == "__main__":
    crawler = GameStreetFullCrawler(START_URL)
    crawler.run()