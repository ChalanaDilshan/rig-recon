"""
export_static.py - Pre-renders Static JSON Datasets for GitHub Pages

Exports:
- data/metrics.json: Top-level KPIs, category counts, and store breakdowns.
- data/products.json: Complete lightweight catalog of normalized products.
- data/scrapers.json: Registry of scrapers and current catalog item counts.
"""

import os
import json
import sqlite3
from typing import Dict, List

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DB_PATH = os.path.join(DATA_DIR, "market_data.db")


def export_static_data(db_path: str = DB_PATH) -> Dict[str, str]:
    if not os.path.exists(db_path):
        print(f"[-] Database not found at {db_path}")
        return {}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1. Metrics & KPIs
    cursor.execute("SELECT COUNT(*), COUNT(DISTINCT Source_Store), COUNT(DISTINCT Category) FROM market_products;")
    total_skus, active_stores, total_categories = cursor.fetchone()

    cursor.execute("SELECT COUNT(*) FROM market_products WHERE Stock_Status = 'In Stock';")
    in_stock_skus = cursor.fetchone()[0]

    cursor.execute("""
        SELECT Category, COUNT(*) as count,
               ROUND(AVG(Cleaned_Price_LKR), 0) as avg_price,
               MIN(Cleaned_Price_LKR) as min_price,
               MAX(Cleaned_Price_LKR) as max_price
        FROM market_products
        WHERE Cleaned_Price_LKR IS NOT NULL AND Cleaned_Price_LKR > 0
        GROUP BY Category
        ORDER BY count DESC;
    """)
    categories = [dict(r) for r in cursor.fetchall()]

    cursor.execute("""
        SELECT Source_Store, COUNT(*) as total,
               SUM(CASE WHEN Stock_Status = 'In Stock' THEN 1 ELSE 0 END) as in_stock
        FROM market_products
        GROUP BY Source_Store
        ORDER BY total DESC;
    """)
    stores = []
    for r in cursor.fetchall():
        d = dict(r)
        d["in_stock_rate"] = round((d["in_stock"] / d["total"]) * 100, 1) if d["total"] else 0
        stores.append(d)

    in_stock_rate = round((in_stock_skus / total_skus * 100), 1) if total_skus else 0

    metrics_payload = {
        "total_skus": total_skus,
        "active_stores": active_stores,
        "total_categories": total_categories,
        "in_stock_skus": in_stock_skus,
        "in_stock_rate": in_stock_rate,
        "categories": categories,
        "stores": stores
    }

    # 2. Products Catalog
    cursor.execute("""
        SELECT Source_Store, Category, Title, Raw_Price, Cleaned_Price_LKR, Stock_Status, Product_URL, Scraped_Date
        FROM market_products
        ORDER BY Cleaned_Price_LKR ASC;
    """)
    products_payload = [dict(r) for r in cursor.fetchall()]

    # 3. Scrapers Registry
    scrapers_list = []
    try:
        from scrapers import SCRAPER_REGISTRY
        store_counts = {s["Source_Store"]: s["total"] for s in stores}
        for key, val in SCRAPER_REGISTRY.items():
            s_name = val.get("name", key)
            scrapers_list.append({
                "id": key,
                "name": s_name,
                "type": val.get("type", "Web Scraper"),
                "description": val.get("description", ""),
                "status": "Operational",
                "products_count": store_counts.get(s_name, 0)
            })
    except Exception as e:
        print(f"[!] Warning reading scrapers registry: {e}")

    conn.close()

    # Save to data/
    metrics_file = os.path.join(DATA_DIR, "metrics.json")
    products_file = os.path.join(DATA_DIR, "products.json")
    scrapers_file = os.path.join(DATA_DIR, "scrapers.json")

    with open(metrics_file, "w", encoding="utf-8") as f:
        json.dump(metrics_payload, f, indent=2, ensure_ascii=False)

    with open(products_file, "w", encoding="utf-8") as f:
        json.dump(products_payload, f, ensure_ascii=False)

    with open(scrapers_file, "w", encoding="utf-8") as f:
        json.dump(scrapers_list, f, indent=2, ensure_ascii=False)

    print(f"[OK] Exported metrics.json ({os.path.getsize(metrics_file):,} bytes)")
    print(f"[OK] Exported products.json ({len(products_payload):,} products, {os.path.getsize(products_file):,} bytes)")
    print(f"[OK] Exported scrapers.json ({len(scrapers_list)} scrapers, {os.path.getsize(scrapers_file):,} bytes)")

    return {
        "metrics": metrics_file,
        "products": products_file,
        "scrapers": scrapers_file
    }


if __name__ == "__main__":
    export_static_data()
