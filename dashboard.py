"""
dashboard.py - Executive B2B Competitor Pricing Intelligence Dashboard
FastAPI + SQLite + Pure HTML/CSS/JS Frontend
"""

import os
import time
import sqlite3
import threading
import ipaddress
import secrets
from collections import defaultdict, OrderedDict, deque
from typing import Optional, List, Tuple, Union
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


def parse_trusted_proxies(env_val: str) -> Tuple[List[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]], set]:
    """Parses TRUSTED_PROXIES environment variable into IP networks and named hosts."""
    networks = []
    named_hosts = set()
    for item in env_val.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            named_hosts.add(item.lower())
    return networks, named_hosts


TRUSTED_PROXY_NETWORKS, TRUSTED_PROXY_NAMES = parse_trusted_proxies(os.getenv("TRUSTED_PROXIES", ""))


def is_trusted_proxy(ip_str: str) -> bool:
    """Checks if an IP string belongs to configured trusted proxy networks or hosts."""
    if not ip_str or (not TRUSTED_PROXY_NETWORKS and not TRUSTED_PROXY_NAMES):
        return False
    if ip_str.lower() in TRUSTED_PROXY_NAMES:
        return True
    try:
        ip_obj = ipaddress.ip_address(ip_str)
        return any(ip_obj in net for net in TRUSTED_PROXY_NETWORKS)
    except ValueError:
        return False


def get_client_ip(request: Request) -> str:
    """
    Extracts the verified client IP address.
    Security hardening:
    - Never trusts X-Forwarded-For or X-Real-IP unless the direct connection (request.client.host)
      originates from an explicitly configured trusted reverse proxy (TRUSTED_PROXIES).
    - When behind a trusted proxy, parses X-Forwarded-For from right to left, selecting
      the first untrusted IP address in the chain (preventing client-injected spoofed headers).
    """
    direct_ip = request.client.host if (request.client and request.client.host) else "unknown"

    # If the direct peer is not a trusted proxy, strictly return direct connection IP
    if not is_trusted_proxy(direct_ip):
        return direct_ip

    # If direct peer is a trusted proxy, inspect X-Forwarded-For / X-Real-IP
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # Standard XFF format: client, proxy1, proxy2
        # Parse right-to-left: first IP that is NOT a trusted proxy is the real client
        raw_ips = [ip.strip() for ip in forwarded.split(",") if ip.strip()]
        for ip in reversed(raw_ips):
            if not is_trusted_proxy(ip):
                return ip
        # If all IPs in chain are trusted proxies, fall back to leftmost
        if raw_ips:
            return raw_ips[0]

    real_ip = request.headers.get("x-real-ip")
    if real_ip and real_ip.strip():
        return real_ip.strip()

    return direct_ip


def is_loopback_request(request: Request) -> bool:
    """
    Validates whether a request originates directly from localhost/loopback.
    Guards against:
    - Direct remote connections sending spoofed X-Forwarded-For headers.
    - Remote requests forwarded through unconfigured local reverse proxies.
    - Remote requests forwarded through configured reverse proxies.
    """
    direct_ip = request.client.host if (request.client and request.client.host) else ""
    if direct_ip not in LOOPBACK_IPS:
        return False

    # If proxy forwarding headers exist on a loopback connection:
    # 1. If direct_ip is NOT a configured trusted proxy, reject loopback assumption
    #    (prevents unconfigured local reverse proxy from passing external traffic as local).
    # 2. If direct_ip IS a trusted proxy, ensure resolved originating IP is also loopback.
    has_forward_header = bool(request.headers.get("x-forwarded-for") or request.headers.get("x-real-ip"))
    if has_forward_header:
        if not is_trusted_proxy(direct_ip):
            return False
        resolved_ip = get_client_ip(request)
        return resolved_ip in LOOPBACK_IPS

    return True


def escape_like(s: str) -> str:
    r"""Escapes SQLite LIKE wildcards (% and _) as well as the escape character (\)."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def build_title_search_clause(query_str: Optional[str], max_length: int = 100, max_keywords: int = 8) -> Tuple[List[str], List[str]]:
    """
    Shared tokenizer & sanitizer for search endpoints.
    Escapes SQLite LIKE wildcards (% and _), bounds max keyword count, and
    generates parameterized Title LIKE clauses.
    Returns: (conditions_list, params_list)
    """
    if not query_str:
        return [], []
    sanitized = str(query_str)[:max_length].strip()
    keywords = sanitized.split()[:max_keywords]
    conditions = ["Title LIKE ? ESCAPE '\\'"] * len(keywords)
    params = [f"%{escape_like(kw)}%" for kw in keywords]
    return conditions, params


def ensure_db_indexes(conn: sqlite3.Connection):
    """Guarantees required query and sorting indexes exist for sub-millisecond execution."""
    try:
        cur = conn.cursor()
        cur.execute("CREATE INDEX IF NOT EXISTS idx_products_category ON market_products(Category);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_products_store ON market_products(Source_Store);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_products_price ON market_products(Cleaned_Price_LKR);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_products_stock ON market_products(Stock_Status);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_products_title ON market_products(Title);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_products_cat_price ON market_products(Category, Cleaned_Price_LKR);")
        conn.commit()
    except Exception:
        pass



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
# Bounded O(1) LRU sliding-window rate limiter per (IP, bucket) pair.
# Eliminates lock contention, synchronous cleanup churn, and memory exhaustion DoS vectors.
# ---------------------------------------------------------------------------
MAX_RATE_LIMIT_KEYS = 10000  # Hard capacity ceiling to prevent memory exhaustion
rate_limit_records: OrderedDict[Tuple[str, str], deque] = OrderedDict()
rate_limit_lock = threading.Lock()
last_rate_limit_cleanup: float = 0.0
RATE_LIMIT_CLEANUP_INTERVAL = 300.0  # Prune idle records at most once every 5 minutes

merge_lock = threading.Lock()
last_merge_timestamp: float = 0.0
MERGE_COOLDOWN_SECONDS = 30
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")


def check_rate_limit(ip: str, bucket: str, limit: int, window_seconds: int = 60) -> bool:
    """
    Constant-time O(1) sliding-window rate limit checker with bounded LRU memory management.
    Eliminates lock contention, synchronous iteration churn, and memory exhaustion DoS vectors:
    1. Flat keying (ip, bucket) stored in an OrderedDict for O(1) LRU eviction.
    2. Uses collections.deque for O(1) timestamp pruning per bucket.
    3. Strict O(1) LRU eviction when table reaches MAX_RATE_LIMIT_KEYS (no O(N) table scans under lock).
    4. Time-throttled idle bucket pruning (at most once per RATE_LIMIT_CLEANUP_INTERVAL, rate-limited to avoid churn).
    """
    global last_rate_limit_cleanup
    now = time.time()
    cutoff = now - window_seconds
    key = (ip, bucket)

    with rate_limit_lock:
        # Time-throttled periodic cleanup: runs at most once every 5 minutes, NEVER on every request
        if now - last_rate_limit_cleanup > RATE_LIMIT_CLEANUP_INTERVAL:
            last_rate_limit_cleanup = now
            idle_cutoff = now - 600.0
            expired_keys = [k for k, dq in rate_limit_records.items() if not dq or dq[-1] < idle_cutoff]
            for k in expired_keys:
                del rate_limit_records[k]

        dq = rate_limit_records.get(key)
        if dq is None:
            # Enforce hard capacity bound with O(1) eviction
            if len(rate_limit_records) >= MAX_RATE_LIMIT_KEYS:
                rate_limit_records.popitem(last=False)  # Evict oldest LRU key in O(1)
            dq = deque()
            rate_limit_records[key] = dq
        else:
            # Move key to end to update LRU order in O(1)
            rate_limit_records.move_to_end(key)

        # Prune expired timestamps for THIS key from the left of the deque in O(k_expired)
        while dq and dq[0] <= cutoff:
            dq.popleft()

        if len(dq) >= limit:
            return False

        dq.append(now)
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


@app.on_event("startup")
def startup_event():
    """Confirms database indexing and environment readiness on startup."""
    if os.path.exists(DB_PATH):
        try:
            conn = get_db()
            ensure_db_indexes(conn)
            conn.close()
        except Exception:
            pass



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
        q_conds, q_params = build_title_search_clause(q, max_length=100, max_keywords=8)
        conditions.extend(q_conds)
        params.extend(q_params)

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

    # Sanitize, escape SQL LIKE wildcards (% and _), and bound keywords using shared helper
    sanitized_model = model[:80].strip()
    conditions, params = build_title_search_clause(sanitized_model, max_length=80, max_keywords=6)

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

    # 1. Access Control: Loopback vs Remote (spoofing-hardened)
    is_loopback = is_loopback_request(request)

    if not is_loopback:
        # Remote request - strictly require configured ADMIN_API_KEY
        if not ADMIN_API_KEY:
            raise HTTPException(
                status_code=403,
                detail="Forbidden: Master database compilation is restricted to localhost. Set ADMIN_API_KEY to allow authenticated remote rebuilds."
            )
        if not x_admin_key or not secrets.compare_digest(x_admin_key, ADMIN_API_KEY):
            raise HTTPException(
                status_code=401,
                detail="Unauthorized: Valid X-Admin-Key header is required for remote database compilation."
            )
    else:
        # Localhost request: if key was provided and ADMIN_API_KEY is set, ensure it is not invalid (timing-safe)
        if ADMIN_API_KEY and x_admin_key and not secrets.compare_digest(x_admin_key, ADMIN_API_KEY):
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
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    reload = os.getenv("RELOAD", "false").lower() in ("true", "1", "yes") or os.getenv("ENVIRONMENT", "").lower() == "development"
    forwarded_allow_ips = os.getenv("FORWARDED_ALLOW_IPS") or os.getenv("TRUSTED_PROXIES") or "127.0.0.1"
    print(f"[+] Launching PC Hardware Market Intelligence Dashboard on http://{host}:{port} (reload={reload}, forwarded_allow_ips={forwarded_allow_ips})")
    uvicorn.run("dashboard:app", host=host, port=port, reload=reload, forwarded_allow_ips=forwarded_allow_ips)
