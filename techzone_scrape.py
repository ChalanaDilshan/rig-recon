import csv
import time
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BASE_URL = "https://techzone.lk/product-category/computer-components/graphic-card/"

def scrape_techzone_with_browser():
    all_products = []
    page = 1
    previous_first_title = None

    print(f"Starting browser crawl: {BASE_URL}")

    with sync_playwright() as p:
        # Browser එක launch කිරීම (headless=False මඟින් Cloudflare challenge සාර්ථකව pass වේ)
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        browser_page = context.new_page()

        while True:
            page_url = BASE_URL if page == 1 else f"{BASE_URL.rstrip('/')}/page/{page}/"
            print(f"\n[+] Loading Page {page}: {page_url}")

            try:
                # පිටුවට පිවිසීම සහ Load වන තෙක් බලා සිටීම
                response = browser_page.goto(page_url, wait_until="domcontentloaded", timeout=45000)
                
                # Cloudflare check එක සම්පූර්ණ වීමට සුළු වේලාවක් ලබා දීම
                time.sleep(3)

                if response and response.status in [404, 403]:
                    print(f"Reached end of category or blocked (Status: {response.status}).")
                    break

                html_content = browser_page.content()
                soup = BeautifulSoup(html_content, "html.parser")

                # Product Cards සොයා ගැනීම
                product_cards = soup.select("li.product, div.product-small, .product-item, .type-product")

                if not product_cards:
                    print(f"No products found on page {page}. Stopping.")
                    break

                # නැවත එකම පිටුව load වීම වැළැක්වීම
                first_title_el = product_cards[0].select_one(
                    ".woocommerce-loop-product__title, .name.product-title, h2, h3"
                )
                first_title = first_title_el.get_text(strip=True) if first_title_el else ""
                if first_title == previous_first_title:
                    print("Duplicate page detected. End reached.")
                    break
                previous_first_title = first_title

                print(f"    Found {len(product_cards)} items on Page {page}.")

                for card in product_cards:
                    # Title
                    title_el = card.select_one(
                        ".woocommerce-loop-product__title, .name.product-title, .product-title a, h2, h3"
                    )
                    title = title_el.get_text(strip=True) if title_el else "N/A"

                    # Price
                    price_el = card.select_one(
                        ".price ins .woocommerce-Price-amount, .price .woocommerce-Price-amount, .price"
                    )
                    price = price_el.get_text(strip=True) if price_el else "N/A"

                    # Link
                    link_el = card.select_one("a[href]")
                    product_url = urljoin(BASE_URL, link_el["href"]) if link_el else "N/A"

                    # Stock Check
                    card_classes = " ".join(card.get("class", []))
                    card_text = card.get_text(separator=" ", strip=True).lower()

                    if "out-of-stock" in card_classes or "outofstock" in card_classes or "out of stock" in card_text:
                        stock_status = "Out of Stock"
                    elif "in-stock" in card_classes or "instock" in card_classes or "add to cart" in card_text:
                        stock_status = "In Stock"
                    else:
                        stock_status = "In Stock"

                    all_products.append({
                        "Title": title,
                        "Price": price,
                        "Stock": stock_status,
                        "URL": product_url
                    })

                    print(f"[{stock_status}] {title} -> {price}")

                page += 1

            except Exception as e:
                print(f"Error on page {page}: {e}")
                break

        browser.close()

    save_to_csv(all_products)

def save_to_csv(data, filename="techzone_gpus.csv"):
    if not data:
        print("\nNo items were collected to save.")
        return

    fields = ["Title", "Price", "Stock", "URL"]
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(data)

    print(f"\n✅ Finished! Successfully saved {len(data)} items to '{filename}'.")

if __name__ == "__main__":
    scrape_techzone_with_browser()