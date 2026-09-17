"""
dashboard.py - Executive B2B Competitor Pricing Intelligence Dashboard
FastAPI + SQLite + Pure HTML/CSS/JS Frontend
"""

import os
import sqlite3
import pandas as pd
from typing import Optional
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from merger import compile_master_dataset, DB_PATH, MASTER_CSV_PATH

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
INDEX_HTML_PATH = os.path.join(TEMPLATES_DIR, "index.html")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

app = FastAPI(title="Sri Lanka PC Hardware Market Intelligence")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.get("/api/metrics")
def get_market_metrics():
    """Returns top-level executive KPI numbers and category metrics."""
    if not os.path.exists(DB_PATH):
        return {"error": "Database not found. Please run merger.py first."}

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*), COUNT(DISTINCT Source_Store), COUNT(DISTINCT Category) FROM market_products;")
    total_skus, active_stores, total_categories = cursor.fetchone()

    cursor.execute("SELECT COUNT(*) FROM market_products WHERE Stock_Status = 'In Stock';")
    in_stock_skus = cursor.fetchone()[0]

    # Category breakdowns with median prices and counts
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
    categories = [dict(row) for row in cursor.fetchall()]

    # Store breakdown with availability health
    cursor.execute("""
        SELECT Source_Store, COUNT(*) as total,
               SUM(CASE WHEN Stock_Status = 'In Stock' THEN 1 ELSE 0 END) as in_stock
        FROM market_products
        GROUP BY Source_Store
        ORDER BY total DESC;
    """)
    stores = []
    for row in cursor.fetchall():
        d = dict(row)
        d["in_stock_rate"] = round((d["in_stock"] / d["total"]) * 100, 1) if d["total"] else 0
        stores.append(d)

    conn.close()

    in_stock_rate = round((in_stock_skus / total_skus * 100), 1) if total_skus else 0

    return {
        "total_skus": total_skus,
        "active_stores": active_stores,
        "total_categories": total_categories,
        "in_stock_skus": in_stock_skus,
        "in_stock_rate": in_stock_rate,
        "categories": categories,
        "stores": stores
    }


@app.get("/api/products")
def get_products(
    q: Optional[str] = Query(None, description="Search query"),
    category: Optional[str] = Query(None),
    store: Optional[str] = Query(None),
    stock: Optional[str] = Query(None),
    min_price: Optional[float] = Query(None),
    max_price: Optional[float] = Query(None),
    sort: Optional[str] = Query("price_asc"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200)
):
    """Filterable and searchable products catalog."""
    if not os.path.exists(DB_PATH):
        return {"items": [], "total": 0, "page": page, "limit": limit}

    conn = get_db()
    cursor = conn.cursor()

    conditions = ["1=1"]
    params = []

    if q:
        keywords = q.strip().split()
        for kw in keywords:
            conditions.append("Title LIKE ?")
            params.append(f"%{kw}%")

    if category and category != "All":
        conditions.append("Category = ?")
        params.append(category)

    if store and store != "All":
        conditions.append("Source_Store = ?")
        params.append(store)

    if stock and stock != "All":
        conditions.append("Stock_Status = ?")
        params.append(stock)

    if min_price is not None:
        conditions.append("Cleaned_Price_LKR >= ?")
        params.append(min_price)

    if max_price is not None:
        conditions.append("Cleaned_Price_LKR <= ?")
        params.append(max_price)

    where_clause = " AND ".join(conditions)

    # Count total
    count_sql = f"SELECT COUNT(*) FROM market_products WHERE {where_clause}"
    cursor.execute(count_sql, params)
    total_items = cursor.fetchone()[0]

    # Sorting
    sort_map = {
        "price_asc": "Cleaned_Price_LKR ASC",
        "price_desc": "Cleaned_Price_LKR DESC",
        "title_asc": "Title ASC",
        "title_desc": "Title DESC"
    }
    order_clause = sort_map.get(sort, "Cleaned_Price_LKR ASC")

    offset = (page - 1) * limit
    sql = f"""
        SELECT Source_Store, Category, Title, Raw_Price, Cleaned_Price_LKR, Stock_Status, Product_URL, Scraped_Date
        FROM market_products
        WHERE {where_clause}
        ORDER BY {order_clause}
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])

    cursor.execute(sql, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return {
        "items": rows,
        "total": total_items,
        "page": page,
        "limit": limit,
        "total_pages": (total_items + limit - 1) // limit if limit else 1
    }


@app.get("/api/compare")
def compare_models(
    model: str = Query(..., min_length=2, description="Model to compare, e.g. 'RTX 4060'"),
    category: Optional[str] = Query(None, description="Optional category filter (e.g. 'GPU', 'Laptop', 'CPU')")
):
    """Cross-store price comparison matrix with comparative savings calculation."""
    conn = get_db()
    cursor = conn.cursor()

    keywords = model.strip().split()
    conditions = ["Title LIKE ?"] * len(keywords)
    params = [f"%{kw}%" for kw in keywords]

    if category and category != "All":
        conditions.append("Category = ?")
        params.append(category)
    else:
        # If user searches for a GPU model like 'RTX 4060', exclude Laptops and Prebuilt PCs unless specifically asked
        m_lower = model.lower()
        if any(k in m_lower for k in ["rtx", "gtx", "rx 6", "rx 7", "rx 9", "radeon", "geforce"]) and not any(k in m_lower for k in ["laptop", "notebook"]):
            conditions.append("Category = 'GPU'")

    where_clause = " AND ".join(conditions)

    sql = f"""
        SELECT Source_Store, Category, Title, Cleaned_Price_LKR, Stock_Status, Product_URL
        FROM market_products
        WHERE {where_clause} AND Cleaned_Price_LKR IS NOT NULL
        ORDER BY Cleaned_Price_LKR ASC;
    """
    cursor.execute(sql, params)
    results = [dict(r) for r in cursor.fetchall()]
    conn.close()

    if not results:
        return {
            "query": model,
            "matches": 0,
            "results": [],
            "cheapest": None,
            "max_price": 0,
            "avg_price": 0,
            "savings_lkr": 0,
            "savings_pct": 0
        }

    cheapest = results[0]
    prices = [r["Cleaned_Price_LKR"] for r in results]
    min_p = min(prices)
    max_p = max(prices)
    avg_p = sum(prices) / len(prices)

    savings_lkr = round(max_p - min_p, 0)
    savings_pct = round((savings_lkr / max_p * 100), 1) if max_p > 0 else 0

    # Add comparative difference to each record
    for r in results:
        diff = round(r["Cleaned_Price_LKR"] - min_p, 0)
        pct = round((diff / min_p * 100), 1) if min_p > 0 else 0
        r["diff_from_cheapest_lkr"] = diff
        r["diff_pct"] = pct

    return {
        "query": model,
        "matches": len(results),
        "cheapest": cheapest,
        "min_price": min_p,
        "max_price": max_p,
        "avg_price": round(avg_p, 0),
        "savings_lkr": savings_lkr,
        "savings_pct": savings_pct,
        "results": results
    }


@app.post("/api/trigger-merge")
def trigger_merge():
    """Triggers cleaner + merger to refresh database."""
    try:
        df = compile_master_dataset()
        return {"status": "SUCCESS", "message": f"Compiled {len(df):,} items into master database."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/scrapers")
def get_scrapers():
    """Returns registry of scrapers and their active status."""
    try:
        from scrapers import SCRAPER_REGISTRY
        scrapers_list = []
        for key, val in SCRAPER_REGISTRY.items():
            scrapers_list.append({
                "id": key,
                "name": val.get("name", key),
                "type": val.get("type", "Web Scraper"),
                "description": val.get("description", ""),
                "status": "Operational"
            })
        return scrapers_list
    except Exception as e:
        return []


@app.get("/", response_class=FileResponse)
def serve_dashboard():
    """Serves the pure HTML/CSS/JS executive B2B dashboard."""
    if os.path.exists(INDEX_HTML_PATH):
        return FileResponse(INDEX_HTML_PATH)
    raise HTTPException(status_code=404, detail="Dashboard template not found.")


if __name__ == "__main__":
    import uvicorn
    print("[+] Launching Animated PC Hardware Competitor Intelligence Dashboard on http://127.0.0.1:8000")
    uvicorn.run("dashboard:app", host="127.0.0.1", port=8000, reload=True)
