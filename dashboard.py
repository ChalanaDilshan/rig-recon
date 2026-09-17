"""
dashboard.py - Executive B2B Competitor Pricing Intelligence Dashboard
FastAPI + SQLite + Pure HTML/CSS/JS Frontend
"""

import os
import time
import sqlite3
import threading
from collections import defaultdict
from typing import Optional, List
import pandas as pd
from fastapi import FastAPI, Query, HTTPException, Request, Header
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from merger import compile_master_dataset, DB_PATH, MASTER_CSV_PATH

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
INDEX_HTML_PATH = os.path.join(TEMPLATES_DIR, "index.html")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

app = FastAPI(title="Sri Lanka PC Hardware Market Intelligence")

# ---------------------------------------------------------------------------
# Network & IP Utilities:
# ---------------------------------------------------------------------------
LOOPBACK_IPS = {"127.0.0.1", "::1", "localhost", "testclient"}


def get_client_ip(request: Request) -> str:
    """Extracts client IP, respecting X-Forwarded-For if deployed behind a proxy."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # First entry in X-Forwarded-For is the originating client IP
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def escape_like(s: str) -> str:
    r"""Escapes SQLite LIKE wildcards (% and _) as well as the escape character (\)."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ---------------------------------------------------------------------------
# Security & CORS Hardening:
# Strict origin parsing from env; credentials explicitly False to guarantee
# compliance with W3C / fetch standards (wildcard cannot combine with credentials=True).
# ---------------------------------------------------------------------------
raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000,http://localhost:3000")
allowed_origins_list = [o.strip() for o in raw_origins.split(",") if o.strip()]
is_wildcard = "*" in allowed_origins_list

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if is_wildcard else allowed_origins_list,
    allow_credentials=False,  # Enforce False: prevents illegal wildcard + credential combination
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Rate Limiting & Concurrency State:
# Sliding-window rate limiter per IP with automatic memory cleanup to prevent memory exhaustion,
# plus concurrency locks for database synchronization.
# ---------------------------------------------------------------------------
rate_limit_records = defaultdict(lambda: defaultdict(list))
rate_limit_lock = threading.Lock()
last_rate_limit_cleanup: float = 0.0
RATE_LIMIT_CLEANUP_INTERVAL = 300.0  # Prune every 5 minutes

merge_lock = threading.Lock()
last_merge_timestamp: float = 0.0
MERGE_COOLDOWN_SECONDS = 30
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")


def check_rate_limit(ip: str, bucket: str, limit: int, window_seconds: int = 60) -> bool:
    """
    Sliding window rate limit checker per IP with memory leak prevention.
    Periodically purges inactive IPs from rate_limit_records.
    """
    global last_rate_limit_cleanup
    now = time.time()
    with rate_limit_lock:
        # Memory cleanup: purge stale IP buckets if interval passed or table exceeds 1000 IPs
        if now - last_rate_limit_cleanup > RATE_LIMIT_CLEANUP_INTERVAL or len(rate_limit_records) > 1000:
            stale_cutoff = now - 600.0  # Inactive for > 10 minutes
            stale_ips = []
            for recorded_ip, buckets in list(rate_limit_records.items()):
                empty_buckets = []
                for b_name, timestamps in list(buckets.items()):
                    fresh = [t for t in timestamps if t > stale_cutoff]
                    if not fresh:
                        empty_buckets.append(b_name)
                    else:
                        buckets[b_name] = fresh
                for b_name in empty_buckets:
                    del buckets[b_name]
                if not buckets:
                    stale_ips.append(recorded_ip)
            for s_ip in stale_ips:
                del rate_limit_records[s_ip]
            last_rate_limit_cleanup = now

        timestamps = rate_limit_records[ip][bucket]
        cutoff = now - window_seconds
        valid_timestamps = [t for t in timestamps if t > cutoff]
        if len(valid_timestamps) >= limit:
            rate_limit_records[ip][bucket] = valid_timestamps
            return False
        valid_timestamps.append(now)
        rate_limit_records[ip][bucket] = valid_timestamps
        return True


@app.middleware("http")
async def rate_limiting_middleware(request: Request, call_next):
    """Protects all application and API endpoints from abusive traffic and DoS attacks."""
    client_ip = get_client_ip(request)
    path = request.url.path

    # Root / UI rate limit: 60 req/min
    if path in ("/", "/index.html"):
        if not check_rate_limit(client_ip, "ui_root", limit=60, window_seconds=60):
            return JSONResponse(
                status_code=429,
                content={"error": "Too Many Requests", "detail": "UI request limit exceeded. Please wait a moment."},
                headers={"Retry-After": "30"}
            )

    # API endpoints rate limiting
    if path.startswith("/api/"):
        # General API limit: 120 req/min
        if not check_rate_limit(client_ip, "general_api", limit=120, window_seconds=60):
            return JSONResponse(
                status_code=429,
                content={"error": "Too Many Requests", "detail": "API rate limit exceeded. Please wait a moment."},
                headers={"Retry-After": "60"}
            )

        # Specific limit for product search: 60 req/min
        if path.startswith("/api/products"):
            if not check_rate_limit(client_ip, "products_search", limit=60, window_seconds=60):
                return JSONResponse(
                    status_code=429,
                    content={"error": "Too Many Requests", "detail": "Product catalog search rate limit reached. Please wait."},
                    headers={"Retry-After": "30"}
                )

        # Specific limit for heavy LIKE comparison searches (/api/compare): 45 req/min
        if path.startswith("/api/compare"):
            if not check_rate_limit(client_ip, "compare_api", limit=45, window_seconds=60):
                return JSONResponse(
                    status_code=429,
                    content={"error": "Too Many Requests", "detail": "Price comparison query limit reached. Please wait."},
                    headers={"Retry-After": "30"}
                )

    return await call_next(request)


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
        # Sanitize length, escape SQL LIKE wildcards (% and _), and bound max keywords
        sanitized_q = q[:100].strip()
        keywords = sanitized_q.split()[:8]
        for kw in keywords:
            conditions.append("Title LIKE ? ESCAPE '\\'")
            params.append(f"%{escape_like(kw)}%")

    if category and category != "All":
        conditions.append("Category = ?")
        params.append(category[:50])

    if store and store != "All":
        conditions.append("Source_Store = ?")
        params.append(store[:50])

    if stock and stock != "All":
        conditions.append("Stock_Status = ?")
        params.append(stock[:50])

    if min_price is not None:
        conditions.append("Cleaned_Price_LKR >= ?")
        params.append(max(0.0, float(min_price)))

    if max_price is not None:
        conditions.append("Cleaned_Price_LKR <= ?")
        params.append(max(0.0, float(max_price)))

    where_clause = " AND ".join(conditions)

    # Count total
    count_sql = f"SELECT COUNT(*) FROM market_products WHERE {where_clause}"
    cursor.execute(count_sql, params)
    total_items = cursor.fetchone()[0]

    # Strictly whitelist sort options to ensure SQL safety
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
    model: str = Query(..., min_length=2, max_length=80, description="Model to compare, e.g. 'RTX 4060'"),
    category: Optional[str] = Query(None, description="Optional category filter (e.g. 'GPU', 'Laptop', 'CPU')")
):
    """Cross-store price comparison matrix with comparative savings calculation."""
    conn = get_db()
    cursor = conn.cursor()

    # Sanitize, escape SQL LIKE wildcards (% and _), and bound keywords
    sanitized_model = model[:80].strip()
    keywords = sanitized_model.split()[:6]
    conditions = ["Title LIKE ? ESCAPE '\\'"] * len(keywords)
    params = [f"%{escape_like(kw)}%" for kw in keywords]

    if category and category != "All":
        conditions.append("Category = ?")
        params.append(category[:50])
    else:
        # If user searches for a GPU model like 'RTX 4060', exclude Laptops and Prebuilt PCs unless specifically asked
        m_lower = sanitized_model.lower()
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
            "query": sanitized_model,
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
        "query": sanitized_model,
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
def trigger_merge(
    request: Request,
    x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key")
):
    """
    Triggers cleaner + merger to refresh database.
    Hardened against DoS with:
    1. Localhost-only restriction for unauthenticated calls (rejects remote calls if no ADMIN_API_KEY).
    2. Mandatory ADMIN_API_KEY verification for remote/external requests.
    3. Concurrency lock (prevents overlapping builds).
    4. Minimum cooldown period between runs.
    5. Per-IP rate limiting (2 requests per 5 minutes).
    """
    global last_merge_timestamp
    client_ip = get_client_ip(request)

    # 1. Access Control: Loopback vs Remote
    is_loopback = client_ip in LOOPBACK_IPS

    if not is_loopback:
        # Remote request - strictly require configured ADMIN_API_KEY
        if not ADMIN_API_KEY:
            raise HTTPException(
                status_code=403,
                detail="Forbidden: Master database compilation is restricted to localhost. Set ADMIN_API_KEY to allow authenticated remote rebuilds."
            )
        if x_admin_key != ADMIN_API_KEY:
            raise HTTPException(
                status_code=401,
                detail="Unauthorized: Valid X-Admin-Key header is required for remote database compilation."
            )
    else:
        # Localhost request: if key was provided and ADMIN_API_KEY is set, ensure it is not invalid
        if ADMIN_API_KEY and x_admin_key and x_admin_key != ADMIN_API_KEY:
            raise HTTPException(
                status_code=401,
                detail="Unauthorized: Invalid X-Admin-Key provided."
            )

    # 2. Rate limiting on merge endpoint: max 2 requests per 5 minutes per IP
    if not check_rate_limit(client_ip, "merge_api", limit=2, window_seconds=300):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Database compilation can only be requested up to twice every 5 minutes."
        )

    # 3. Check cooldown
    now = time.time()
    if now - last_merge_timestamp < MERGE_COOLDOWN_SECONDS:
        remaining = int(MERGE_COOLDOWN_SECONDS - (now - last_merge_timestamp))
        raise HTTPException(
            status_code=429,
            detail=f"Cooldown active. Please wait {remaining} seconds before re-triggering database compilation."
        )

    # Non-blocking concurrency lock to ensure single compilation at a time
    acquired = merge_lock.acquire(blocking=False)
    if not acquired:
        raise HTTPException(
            status_code=409,
            detail="A master database compilation is currently in progress. Please wait."
        )

    try:
        df = compile_master_dataset()
        last_merge_timestamp = time.time()
        return {
            "status": "SUCCESS",
            "message": f"Compiled {len(df):,} items into master database.",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Compilation error: {str(e)}")
    finally:
        merge_lock.release()


@app.get("/api/scrapers")
def get_scrapers():
    """Returns comprehensive health, telemetry, and catalog statistics for all scrapers."""
    try:
        from export_static import get_scraper_telemetry
        return get_scraper_telemetry(DB_PATH)
    except Exception as e:
        scrapers_json_path = os.path.join(os.path.dirname(__file__), "data", "scrapers.json")
        if os.path.exists(scrapers_json_path):
            import json
            with open(scrapers_json_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"fleet": {}, "scrapers": []}


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
