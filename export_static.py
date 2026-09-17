"""
export_static.py - Pre-renders Static JSON Datasets for GitHub Pages & Scraper Health Telemetry

Exports:
- data/metrics.json: Top-level KPIs, category counts, and store breakdowns.
- data/products.json: Complete lightweight catalog of normalized products.
- data/scrapers.json: Detailed health, performance telemetry, and operational status for all scrapers.
"""

import os
import glob
import json
import sqlite3
from datetime import datetime
from typing import Dict, List, Any

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DATA_RAW_DIR = os.path.join(DATA_DIR, "raw")
DB_PATH = os.path.join(DATA_DIR, "market_data.db")


def format_bytes(size_bytes: int) -> str:
    """Formats raw byte count into human-readable string."""
    if size_bytes <= 0:
        return "0 B"
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB"


def get_scraper_telemetry(db_path: str = DB_PATH) -> Dict[str, Any]:
    """
    Computes comprehensive health, telemetry, and catalog statistics for all scrapers in the fleet.
    Used by both the live FastAPI /api/scrapers endpoint and pre-rendered data/scrapers.json.
    """
    from scrapers import SCRAPER_REGISTRY

    # Check database presence
    conn = None
    db_store_stats = {}
    total_db_skus = 0

    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            cur.execute("""
                SELECT 
                    Source_Store,
                    COUNT(*) as total,
                    SUM(CASE WHEN Stock_Status = 'In Stock' THEN 1 ELSE 0 END) as in_stock,
                    MIN(CASE WHEN Cleaned_Price_LKR > 0 THEN Cleaned_Price_LKR END) as min_price,
                    MAX(CASE WHEN Cleaned_Price_LKR > 0 THEN Cleaned_Price_LKR END) as max_price,
                    ROUND(AVG(CASE WHEN Cleaned_Price_LKR > 0 THEN Cleaned_Price_LKR END), 0) as avg_price,
                    COUNT(DISTINCT Category) as categories_count,
                    MAX(Scraped_Date) as latest_db_date
                FROM market_products
                GROUP BY Source_Store;
            """)
            for row in cur.fetchall():
                d = dict(row)
                store_str = d["Source_Store"]
                db_store_stats[store_str] = d
                # Also store under simplified lower key for robust matching
                simple_key = store_str.lower().replace(" ", "").replace("_", "")
                db_store_stats[simple_key] = d
                total_db_skus += d["total"]
        except Exception as e:
            print(f"[!] Error querying market_products for scraper telemetry: {e}")
        finally:
            if conn:
                conn.close()

    scrapers_list = []
    playwright_count = 0
    http_count = 0
    operational_count = 0
    fleet_total_raw_bytes = 0

    for key, val in SCRAPER_REGISTRY.items():
        s_name = val.get("name", key)
        pattern = val.get("csv_pattern", key)
        s_type = val.get("type", "Web Scraper")
        engine = val.get("engine", s_type)
        url = val.get("url", "")
        desc = val.get("description", "")

        is_playwright = "playwright" in s_type.lower() or "playwright" in engine.lower()
        if is_playwright:
            playwright_count += 1
        else:
            http_count += 1

        # Check raw CSV files in data/raw
        matching_files = glob.glob(os.path.join(DATA_RAW_DIR, f"*{pattern}*.csv"))
        raw_bytes = sum(os.path.getsize(f) for f in matching_files if os.path.exists(f))
        fleet_total_raw_bytes += raw_bytes

        last_modified_str = "No Data"
        primary_file = "None"
        if matching_files:
            latest_file = max(matching_files, key=os.path.getmtime)
            mtime = os.path.getmtime(latest_file)
            last_modified_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
            primary_file = os.path.basename(latest_file)

        # Database telemetry with resilient key matching
        lookup_key = s_name.lower().replace(" ", "").replace("_", "")
        stats = db_store_stats.get(s_name) or db_store_stats.get(lookup_key) or db_store_stats.get(key.lower()) or {}

        total_skus = stats.get("total", 0)
        in_stock = stats.get("in_stock", 0)
        out_of_stock = total_skus - in_stock
        in_stock_rate = round((in_stock / total_skus * 100), 1) if total_skus > 0 else 0.0
        min_p = stats.get("min_price") or 0
        max_p = stats.get("max_price") or 0
        avg_p = stats.get("avg_price") or 0
        cat_count = stats.get("categories_count", 0)

        # Health Scoring & Status
        if total_skus >= 100:
            status = "Operational"
            status_badge = "healthy"
            health_score = 100
            operational_count += 1
        elif total_skus > 0:
            status = "Operational"
            status_badge = "healthy"
            health_score = 95
            operational_count += 1
        elif raw_bytes > 0:
            status = "Ingestion Pending"
            status_badge = "warning"
            health_score = 65
        else:
            status = "Standby / Ready"
            status_badge = "idle"
            health_score = 50

        scrapers_list.append({
            "id": key,
            "name": s_name,
            "type": s_type,
            "engine": engine,
            "url": url,
            "description": desc,
            "status": status,
            "status_badge": status_badge,
            "health_score": health_score,
            "is_playwright": is_playwright,
            "telemetry": {
                "total_skus": total_skus,
                "in_stock_skus": in_stock,
                "out_of_stock_skus": out_of_stock,
                "in_stock_rate": in_stock_rate,
                "market_share_pct": round((total_skus / total_db_skus * 100), 1) if total_db_skus > 0 else 0.0,
                "categories_count": cat_count,
                "min_price_lkr": min_p,
                "max_price_lkr": max_p,
                "avg_price_lkr": avg_p,
                "raw_file_count": len(matching_files),
                "raw_total_bytes": raw_bytes,
                "raw_size_formatted": format_bytes(raw_bytes),
                "primary_raw_file": primary_file,
                "last_scraped": last_modified_str
            }
        })

    # Sort scrapers: Operational with highest SKU counts first
    scrapers_list.sort(key=lambda s: (s["telemetry"]["total_skus"], s["health_score"]), reverse=True)

    fleet_summary = {
        "total_scrapers": len(SCRAPER_REGISTRY),
        "operational_scrapers": operational_count,
        "operational_rate": round((operational_count / len(SCRAPER_REGISTRY) * 100), 1) if SCRAPER_REGISTRY else 0.0,
        "total_harvested_skus": total_db_skus,
        "total_raw_data_formatted": format_bytes(fleet_total_raw_bytes),
        "playwright_engines": playwright_count,
        "http_engines": http_count,
        "schedule": "Twice Daily at 07:30 AM & 07:30 PM SLST (02:00 & 14:00 UTC)",
        "last_sync": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    return {
        "fleet": fleet_summary,
        "scrapers": scrapers_list
    }


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
    conn.close()

    # 3. Comprehensive Scrapers Health & Telemetry Registry
    scrapers_payload = get_scraper_telemetry(db_path)

    # Save to data/
    metrics_file = os.path.join(DATA_DIR, "metrics.json")
    products_file = os.path.join(DATA_DIR, "products.json")
    scrapers_file = os.path.join(DATA_DIR, "scrapers.json")

    with open(metrics_file, "w", encoding="utf-8") as f:
        json.dump(metrics_payload, f, indent=2, ensure_ascii=False)

    with open(products_file, "w", encoding="utf-8") as f:
        json.dump(products_payload, f, ensure_ascii=False)

    with open(scrapers_file, "w", encoding="utf-8") as f:
        json.dump(scrapers_payload, f, indent=2, ensure_ascii=False)

    print(f"[OK] Exported metrics.json ({os.path.getsize(metrics_file):,} bytes)")
    print(f"[OK] Exported products.json ({len(products_payload):,} products, {os.path.getsize(products_file):,} bytes)")
    print(f"[OK] Exported scrapers.json ({len(scrapers_payload['scrapers'])} scrapers, {os.path.getsize(scrapers_file):,} bytes)")

    return {
        "metrics": metrics_file,
        "products": products_file,
        "scrapers": scrapers_file
    }


if __name__ == "__main__":
    export_static_data()
