import csv
import time
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://mdcomputers.lk/shop/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

def scrape_all_mdcomputers():
    all_products = []
    page = 1

    print("Scraping started: https://mdcomputers.lk/shop/")

    while True:
        # WooCommerce pagination formatting (/shop/page/2/, /shop/page/3/...)
        page_url = BASE_URL if page == 1 else f"{BASE_URL}page/{page}/"
        print(f"\n[+] Fetching Page {page}: {page_url}")

        try:
            response = requests.get(page_url, headers=HEADERS, timeout=15)

            # Reached end of catalog (404 Not Found)
            if response.status_code == 404:
                print("End of catalog reached (404). Done.")
                break

            response.raise_for_status()
        except requests.RequestException as error:
            print(f"Connection stopped: {error}")
            break

        soup = BeautifulSoup(response.text, "html.parser")

        # Select all product cards
        product_cards = soup.select("li.product, div.product, .type-product")

        # Stop condition: If no products are rendered on this page
        if not product_cards:
            print(f"No products found on page {page}. Stopping.")
            break

        print(f"    Found {len(product_cards)} items on this page.")

        for card in product_cards:
            # 1. Product Title
            title_tag = card.select_one(".woocommerce-loop-product__title, h2, h3")
            title = title_tag.get_text(strip=True) if title_tag else "N/A"

            # 2. Product Price
            price_tag = card.select_one(".price ins, .price .amount, .price")
            price = price_tag.get_text(strip=True) if price_tag else "N/A"

            # 3. Product URL
            link_tag = card.select_one("a[href]")
            product_url = urljoin(BASE_URL, link_tag["href"]) if link_tag else "N/A"

            # 4. Stock Status Check
            card_classes = " ".join(card.get("class", []))
            card_text = card.get_text(separator=" ", strip=True).lower()

            if "out-of-stock" in card_classes or "out of stock" in card_text:
                stock_status = "Out of Stock"
            elif "in-stock" in card_classes or "add to cart" in card_text:
                stock_status = "In Stock"
            else:
                stock_status = "Available / Check Site"

            all_products.append({
                "Title": title,
                "Price": price,
                "Stock": stock_status,
                "URL": product_url
            })

        page += 1
        time.sleep(1.5)  # Politeness delay to prevent getting blocked

    # Save to CSV
    save_to_csv(all_products)

def save_to_csv(data, filename="mdcomputers_all_products.csv"):
    if not data:
        print("\nNo items were collected.")
        return

    fields = ["Title", "Price", "Stock", "URL"]
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(data)

    print(f"\n✅ All Done! Collected {len(data)} total products into '{filename}'.")

if __name__ == "__main__":
    scrape_all_mdcomputers()