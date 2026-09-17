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

    import os
    profile_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "browser_profiles", "techzone")
    os.makedirs(profile_dir, exist_ok=True)

    with sync_playwright() as p:
        browser_context = None
        for channel in ["chrome", None]:
            try:
                kwargs = {
                    "user_data_dir": profile_dir,
                    "headless": False,
                    "args": ["--disable-blink-features=AutomationControlled", "--no-default-browser-check"],
                    "viewport": {"width": 1280, "height": 800}
                }
                if channel:
                    kwargs["channel"] = channel
                browser_context = p.chromium.launch_persistent_context(**kwargs)
                break
            except Exception:
                continue

        if not browser_context:
            print("Failed to launch browser.")
            return

        browser_page = browser_context.pages[0] if browser_context.pages else browser_context.new_page()
        browser_page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")

        while True:
            page_url = BASE_URL if page == 1 else f"{BASE_URL.rstrip('/')}/page/{page}/"
            print(f"\n[+] Loading Page {page}: {page_url}")

            try:
                response = browser_page.goto(page_url, wait_until="domcontentloaded", timeout=45000)
                if response and response.status == 404:
                    print("Reached 404 end of category.")
                    break

                # Cloudflare check එක සම්පූර්ණ වීමට බලා සිටීම
                start_cf = time.time()
                while time.time() - start_cf < 25:
                    title = browser_page.title()
                    if "Just a moment" not in title and "Security" not in title and title.strip():
                        break
                    time.sleep(1)

                try:
                    browser_page.wait_for_selector("li.product, div.product-small, .product-item, .type-product", timeout=8000)
                except Exception:
                    pass

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