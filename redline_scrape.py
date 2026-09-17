import csv
import re
import time
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BASE_URL = "https://redtech.lk"
DOMAIN = "redtech.lk"

def is_valid_category(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.netloc and DOMAIN not in parsed.netloc:
        return False
    path = parsed.path.lower()
    if "/product-category/" not in path:
        return False
    ignored = ["/cart", "/checkout", "/my-account", ".jpg", ".png"]
    return not any(x in path for x in ignored)

def get_all_categories(page):
    """Redtech මුල් පිටුවෙන් සියලුම Category Links සොයා ගැනීම."""
    print(f"Discovering categories from {BASE_URL}...")
    page.goto(BASE_URL, wait_until="domcontentloaded", timeout=45000)
    time.sleep(3)

    soup = BeautifulSoup(page.content(), "html.parser")
    category_links = set()

    for a in soup.find_all("a", href=True):
        clean_url = urljoin(BASE_URL, a["href"]).split("#")[0].split("?")[0].rstrip("/") + "/"
        if is_valid_category(clean_url):
            category_links.add(clean_url)

    if not category_links:
        print("Fallback: Using default categories...")
        category_links = {
            "https://redtech.lk/product-category/pc-components/gpu/",
            "https://redtech.lk/product-category/pc-components/processors/",
            "https://redtech.lk/product-category/pc-components/motherboard/",
            "https://redtech.lk/product-category/pc-components/ram/",
            "https://redtech.lk/product-category/pc-components/storage/",
            "https://redtech.lk/product-category/pc-components/power-supply/",
            "https://redtech.lk/product-category/pc-components/casing/",
            "https://redtech.lk/product-category/monitors/",
            "https://redtech.lk/product-category/laptops/",
        }

    print(f"Discovered {len(category_links)} categories.\n")
    return sorted(list(category_links))

def scrape_redtech_store():
    all_products = []
    seen_urls = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        categories = get_all_categories(page)

        for cat_url in categories:
            cat_name = [s for s in urlparse(cat_url).path.split("/") if s][-1].replace("-", " ").title()
            print(f"\n📂 Crawling Category: [{cat_name}] -> {cat_url}")

            current_page = 1
            max_pages = 8

            while current_page <= max_pages:
                page_url = cat_url if current_page == 1 else f"{cat_url.rstrip('/')}/page/{current_page}/"
                print(f"   -> Loading Page {current_page}: {page_url}")

                try:
                    response = page.goto(page_url, wait_until="domcontentloaded", timeout=35000)
                    if response and response.status in [404, 403]:
                        print(f"      End of pages reached (Status: {response.status}).")
                        break

                    time.sleep(2)

                    # Lazy loading images & products load වීමට scroll කිරීම
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2);")
                    time.sleep(1)
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(1.5)

                    soup = BeautifulSoup(page.content(), "html.parser")

                    # WooCommerce / Woodmart / Custom Grid selectors
                    cards = soup.select(
                        ".product-grid-item, div.product, li.product, .type-product, div.col-inner"
                    )

                    # මිල හෝ product link සහිත cards පමණක් තෝරා ගැනීම
                    valid_cards = []
                    for card in cards:
                        if card.find("a", href=lambda h: h and ("/product/" in h)) and re.search(r"(?:Rs\.?|LKR)\s*[\d,]+", card.get_text()):
                            valid_cards.append(card)

                    if not valid_cards:
                        print(f"      No products found on page {current_page}. Category complete.")
                        break

                    page_items = 0
                    for card in valid_cards:
                        card_text = card.get_text(separator=" ", strip=True)

                        # 1. Product Title
                        title_el = card.select_one(".woocommerce-loop-product__title, .wd-entities-title, h2, h3, .product-title")
                        if title_el:
                            title = title_el.get_text(strip=True)
                        else:
                            link = card.find("a", href=lambda h: h and "/product/" in h)
                            title = link.get_text(strip=True) if link else None

                        if not title or len(title) < 4:
                            continue

                        # 2. Product Price
                        price_match = re.search(r"(?:Rs\.?|LKR)\s*([\d,]+(?:\.\d{2})?)", card_text)
                        price = f"Rs. {price_match.group(1)}" if price_match else "N/A"

                        # 3. Product URL
                        link_el = card.find("a", href=lambda h: h and "/product/" in h)
                        product_url = urljoin(BASE_URL, link_el["href"]).split("?")[0] if link_el else cat_url

                        if product_url in seen_urls:
                            continue

                        # 4. Stock Status
                        lower_text = card_text.lower()
                        card_classes = " ".join(card.get("class", [])).lower()

                        if "out-of-stock" in card_classes or "outofstock" in card_classes or "out of stock" in lower_text:
                            stock = "Out of Stock"
                        elif "in-stock" in card_classes or "add to cart" in lower_text:
                            stock = "In Stock"
                        else:
                            stock = "In Stock"

                        seen_urls.add(product_url)
                        all_products.append({
                            "Category": cat_name,
                            "Title": title,
                            "Price": price,
                            "Stock": stock,
                            "URL": product_url
                        })

                        page_items += 1
                        print(f"      [{stock}] {title} -> {price}")

                    if page_items == 0:
                        break

                    print(f"   ✔️ Extracted {page_items} items from Page {current_page}")

                    # ඊළඟ පිටුවක් ඇත්දැයි බැලීම
                    has_next = soup.select_one("a.next, .page-numbers.next")
                    if not has_next and current_page > 1:
                        break

                    current_page += 1

                except Exception as err:
                    print(f"   ⚠️ Error loading page: {err}")
                    break

        browser.close()

    save_to_csv(all_products)

def save_to_csv(data, filename="redtech_all_products.csv"):
    if not data:
        print("\n❌ No products collected.")
        return

    fields = ["Category", "Title", "Price", "Stock", "URL"]
    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(data)

    print(f"\n✅ Finished! Successfully saved {len(data)} items to '{filename}'.")

if __name__ == "__main__":
    scrape_redtech_store()