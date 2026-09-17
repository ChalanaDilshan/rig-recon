import csv
import requests
from bs4 import BeautifulSoup

URL = "https://www.nanotek.lk/category/graphics-card"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

def scrape_nanotek_gpus():
    print("Fetching page data...")
    try:
        response = requests.get(URL, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except requests.RequestException as error:
        print(f"Failed to retrieve data: {error}")
        return

    soup = BeautifulSoup(response.text, "html.parser")
    
    # Locate all individual product listing items
    product_items = soup.find_all("li", class_="ty-catPage-productListItem")
    print(f"Found {len(product_items)} items.\n" + "=" * 60)

    gpu_catalog = []

    for item in product_items:
        # Extract product title
        title_div = item.find("div", class_="ty-productBlock-title")
        title = title_div.get_text(strip=True) if title_div else "N/A"

        # Extract product price
        price_div = item.find("div", class_="ty-productBlock-price")
        price = price_div.get_text(strip=True) if price_div else "N/A"

        # Extract product link
        link_tag = item.find("a", href=True)
        product_url = link_tag["href"] if link_tag else "N/A"

        # Extract availability / stock notice
        special_msg = item.find("div", class_="ty-productBlock-specialMsg")
        stock_status = special_msg.get_text(strip=True) if special_msg else "In Stock"

        gpu_record = {
            "Title": title,
            "Price": price,
            "Stock": stock_status,
            "URL": product_url
        }
        gpu_catalog.append(gpu_record)

        # Output to console
        print(f"Product: {title}")
        print(f"Price:   {price}")
        print(f"Stock:   {stock_status}")
        print(f"URL:     {product_url}")
        print("-" * 60)

    save_to_csv(gpu_catalog)

def save_to_csv(data, filename="nanotek_gpus.csv"):
    if not data:
        print("No items to export.")
        return
    
    fields = ["Title", "Price", "Stock", "URL"]
    
    with open(filename, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fields)
        writer.writeheader()
        writer.writerows(data)
        
    print(f"Export complete: Data saved to '{filename}'.")

if __name__ == "__main__":
    scrape_nanotek_gpus()