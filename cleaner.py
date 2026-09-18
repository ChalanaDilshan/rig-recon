"""
cleaner.py - Competitor Pricing Intelligence Data Normalization Engine

Standardizes:
- Titles: Removes badges ('Sale', 'New', 'Out of Stock'), SKU IDs, duplicated category prefixes.
- Prices: Extracts clean numerical LKR prices from irregular currency strings (installments, ranges, LKR/Rs formatting).
- Categories: Maps raw categories and product titles to standard 9 hardware buckets:
  ['GPU', 'CPU', 'Motherboard', 'RAM', 'Storage', 'PSU', 'Casing', 'Laptop', 'Monitor']
- Stock Status: Normalized to Enum: ['In Stock', 'Out of Stock', 'Available / On Order'].
- URLs: Canonical full URLs.
- Date: ISO-8601 YYYY-MM-DD.
"""

import re
from datetime import datetime
from typing import Optional, Tuple
from urllib.parse import urljoin, unquote

# Normalized Category Standards
VALID_CATEGORIES = [
    "GPU",
    "CPU",
    "Motherboard",
    "RAM",
    "Storage",
    "PSU",
    "Casing",
    "Laptop",
    "Monitor",
    "Accessories / Other"
]

# Canonical Store Names
STORE_MAPPINGS = {
    "nanotek": "Nanotek",
    "techzone": "Techzone",
    "mdcomputers": "MD Computers",
    "md_computers": "MD Computers",
    "chamacomputers": "Chama Computers",
    "chama": "Chama Computers",
    "gamestreet": "Game Street",
    "game_street": "Game Street",
    "mskcomputers": "MSK Computers",
    "msk": "MSK Computers",
    "pcbuilders": "PC Builders",
    "tulip": "Tulip Computers",
    "tulipcom": "Tulip Computers",
    "redlinetech": "Redline Technologies",
    "redline": "Redline Technologies",
    "redtech": "Red Tech",
    "red_tech": "Red Tech",
    "gallelaptop": "Galle Laptop",
    "galle": "Galle Laptop"
}

# ---------------------------------------------------------------------------
# Precompiled Regular Expressions for Performance and ReDoS Protection:
# Prevents repeated regex parsing and eliminates catastrophic backtracking on untrusted scraped text.
# ---------------------------------------------------------------------------
RE_PRICE_INSTALLMENT = re.compile(r"\bor\s+\d+\s*[xX]", re.IGNORECASE)
RE_NUM_EXTRACT = re.compile(r"[\d,]+(?:\.\d{1,2})?")

RE_LEAKED_CART_PRICE = re.compile(r"[\d,]+(?:\.\d{2})?\s*\+\s*Add to Cart.*$", re.IGNORECASE)
RE_LEAKED_CART = re.compile(r"\bAdd to Cart\b.*$", re.IGNORECASE)
RE_SKU_PREFIX = re.compile(r"^\d{4,6}\s*-\s*")
RE_STOCK_BADGE = re.compile(r"^(?:In Stock|Out of Stock|Sale|New|Hot|Special Offer|Featured)\s*[-:]?\s*", re.IGNORECASE)
RE_WHITESPACE = re.compile(r"\s+")

# ReDoS-hardened: bounded length scan [^,\n]{0,50} instead of unbounded .*? to prevent cross-line backtracking
RE_PC_INDICATOR = re.compile(r'\b(?:rtx|gtx|rx\s*\d{3,4})\b[^,\n]{0,50}\b(?:pc|desktop)\b', re.IGNORECASE)
RE_MOBO_CHIPSET = re.compile(r"\b(?:b550|b650|b760|b660|z790|z690|x670|x870|a520|a620|h610|h510)\b", re.IGNORECASE)
RE_SCREEN_SIZE = re.compile(r'\b(?:13\.3|14(?:\.0)?|15\.6|16(?:\.0|\.1)?|17(?:\.3)?|18)\s*(?:["\'”″]|inch|-inch|\s*(?:fhd|qhd|wqxga|oled|ips))\b', re.IGNORECASE)
RE_MOBILE_CPU = re.compile(r'\b(?:\d{4,5}(?:h|hx)|core\s*7\s*240h|ultra\s*[579][-\s]\d{3}h|ryzen\s*[3579]\s*[-]?\d{4}(?:hs|hx|u)|ryzen\s*ai\s*9\s*hx\d{3}|8845hs|8945hs|8645hs|7840hs|7940hs|7735hs|7535hs|7445hs)\b', re.IGNORECASE)
# De-duplicated alternations to eliminate NFA branch ambiguity
RE_MOBILE_GPU = re.compile(r'\b(?:rtx\s*4070\s*8gb|rtx\s*4050|rtx\s*3050\s*4gb|rtx\s*2050|rtx\s*5050)\b', re.IGNORECASE)
RE_GPU_MODEL = re.compile(r"\b(?:rtx|gtx|radeon rx|geforce|arc a)\s*\d{3,4}", re.IGNORECASE)
RE_RAM_SPECS_1 = re.compile(r"\b(?:16gb|8gb|32gb|64gb|4gb)\s*(?:ddr4|ddr5|ddr3)\b", re.IGNORECASE)
RE_RAM_SPECS_2 = re.compile(r"\b(?:ddr4|ddr5|ddr3)\s*(?:16gb|8gb|32gb|64gb|4gb)\b", re.IGNORECASE)


def clean_price(raw_price: Optional[str]) -> Tuple[Optional[float], str]:
    """
    Cleans raw price strings into a numeric float and a standardized raw string.
    Handles:
    - 'Rs. 185,000.00' -> 185000.0
    - '1,569,000 LKR' -> 1569000.0
    - 'LKR 65,000.00' -> 65000.0
    - 'Rs:500.00Rs:1,000.00or 3 XRs:186.67with' -> 500.0
    - 'N/A' / None -> None
    """
    if not raw_price:
        return None, "N/A"

    raw_str = str(raw_price).strip()
    if raw_str.upper() in ["N/A", "NAN", "NONE", "CONTACT FOR PRICE", "OUT OF STOCK", ""]:
        return None, "N/A"

    # Step 1: Remove installment noise like 'or 3 XRs:186.67with'
    cleaned = RE_PRICE_INSTALLMENT.split(raw_str)[0].strip()

    # Step 2: Handle concatenated prices -> extract first valid number
    num_matches = RE_NUM_EXTRACT.findall(cleaned)

    for match in num_matches:
        digits_only = match.replace(",", "")
        try:
            val = float(digits_only)
            if val >= 50:
                return val, raw_str
        except ValueError:
            continue

    return None, raw_str


def clean_title(title: Optional[str], raw_category: Optional[str] = None) -> str:
    """
    Cleans product title by removing:
    - Leading badges ('In Stock', 'Out of Stock', 'Sale', 'New')
    - Catalog SKU codes (e.g., '21279-')
    - Leaked button / price texts
    - Redundant category prefix concatenated to title
    """
    if not title:
        return "Unknown Product"

    # Truncate untrusted input string to safe bound (500 chars)
    cleaned = str(title).strip()[:500]

    # Remove leaked trailing price + Add to Cart text
    cleaned = RE_LEAKED_CART_PRICE.sub("", cleaned).strip()
    cleaned = RE_LEAKED_CART.sub("", cleaned).strip()

    # Remove leading SKU codes like '21279-'
    cleaned = RE_SKU_PREFIX.sub("", cleaned).strip()

    # Remove repeated category prefixes
    prefixes_to_strip = [
        "Graphics Card", "Graphic Card", "Processor", "Motherboard",
        "Memory RAM", "RAM", "Power Supply", "Storage", "Casing",
        "Monitor", "Laptops", "Laptop", "Mouse", "Keyboard"
    ]
    for prefix in prefixes_to_strip:
        if cleaned.lower().startswith(prefix.lower()):
            remainder = cleaned[len(prefix):].strip()
            if remainder and (remainder[0].isupper() or remainder[0].isdigit()):
                cleaned = remainder
                break

    # Remove leading stock/promo badges
    cleaned = RE_STOCK_BADGE.sub("", cleaned).strip()

    # Clean double spaces
    cleaned = RE_WHITESPACE.sub(" ", cleaned).strip()

    return cleaned if cleaned else "Unknown Product"


def normalize_category(raw_category: Optional[str], title: Optional[str] = None) -> str:
    """
    Hierarchical, high-precision category classification.
    Prevents complete systems (Laptops, Prebuilts) from being misclassified as components
    (RAM, CPU, GPU, Storage) due to listed specifications, and prevents monitors/motherboards/GPUs
    from being misclassified as laptops.
    """
    raw_cat = str(raw_category or "").strip().lower()[:100]
    # Bound untrusted title string length (300 chars) to prevent ReDoS on unconstrained text
    t = str(title or "").strip().lower()[:300]

    # 1. System Accessories & Parts Exclusion (e.g., GPU Holders, Laptop Bags, Cables, Mounts)
    accessory_markers = [
        "keyboard for", "charger for", "battery for", "adapter for", "laptop bag",
        "laptop sleeve", "laptop stand", "cooling pad", "thermal paste", "heatsink paste",
        "mouse pad", "sata cable", "aux cable", "usb cable", "hdmi cable", "extension cable",
        "cmos battery", "fan hub", "gpu holder", "graphics card holder", "riser cable", 
        "monitor arm", "wall mount", "screen protector", "cleaning kit", "cable management",
        "support bracket", "gpu bracket", "anti-sag", "wingwall", "desk arm", "monitor mount"
    ]
    if any(m in t for m in accessory_markers):
        return "Accessories / Other"

    # 2. Specifically Check Laptop / Notebook Memory / SODIMM RAM (before Laptop machine check)
    if any(m in t for m in ["laptop memory", "laptop ram", "notebook memory", "notebook ram", "so-dimm", "sodimm", "so dimm"]):
        return "RAM"

    # 3. Prebuilt Desktop Systems & Workstations (Must be checked BEFORE GPU/CPU/Laptop)
    # E.g. "CORE I5 2ND GEN USED GAMING PC - GTX 650 1GB VGA", "Intel Core i7 14th Gen RTX 4060 PC"
    prebuilt_indicators = [
        "gaming pc", "desktop pc", "custom pc", "prebuilt", "used pc", "brand new pc", 
        "build pc", "pc build", "all in one", "all-in-one", "aio pc", "desktop computer", 
        "workstation pc", "pba systems", "desktop workstation", "mini pc", "branded pc"
    ]
    is_pc_system = (
        any(m in t for m in prebuilt_indicators) or
        (t.endswith(" pc") and any(k in t for k in ["ryzen", "core", "intel", "amd", "rtx", "gtx", "gen"])) or
        bool(RE_PC_INDICATOR.search(t))
    )
    is_pc_excluded_part = any(comp in t for comp in [
        "casing", "pc case", "chassis", "power supply", "psu", "for pc build only",
        "pc speaker", "pc camera", "pc headset", "fan", "cooler"
    ])
    if is_pc_system and not is_pc_excluded_part:
        return "Accessories / Other"
    if any(m in raw_cat for m in ["desktop workstation", "pba systems", "all in one", "all-in-one", "aio pc", "prebuilt pc", "gaming desktop", "custom pc"]):
        return "Accessories / Other"

    has_laptop_chassis_word = any(k in t for k in ["laptop", "notebook", "macbook", "ultrabook", "chromebook"])

    # 4. Monitor Check (Must be checked BEFORE Laptop screen check!)
    # E.g. "Lenovo Legion 24-10 Gaming Monitor", "MSI MAG 272F FHD IPS Monitor"
    is_monitor = any(m in raw_cat for m in ["monitor", "monitors", "display"]) or any(m in t for m in ["monitor", "monitors", "gaming monitor", "curved monitor", "ips monitor", "led monitor"])
    if is_monitor and not has_laptop_chassis_word:
        return "Monitor"

    # 5. Motherboard Check (Must be checked BEFORE Laptop to prevent ASUS ROG "Crosshair" etc. from becoming Laptop)
    is_mobo = any(m in raw_cat for m in ["motherboard", "motherboards", "mainboard"]) or any(m in t for m in ["motherboard", "mainboard", "mobo"])
    if is_mobo and not has_laptop_chassis_word:
        return "Motherboard"
    if RE_MOBO_CHIPSET.search(t) and any(
        x in t for x in ["wifi", "plus", "pro", "gaming", "aorus", "tomahawk", "steel legend", "prime", "ax"]
    ) and not has_laptop_chassis_word:
        return "Motherboard"

    # 6. System-Level Products: Laptop (High Precedence)
    # Check raw category first
    if any(m in raw_cat for m in ["laptop", "laptops", "notebook", "notebooks", "macbook"]):
        return "Laptop"

    # Specific Laptop Brand Series & Model Lines
    laptop_brand_models = [
        "laptop", "notebook", "ultrabook", "macbook", "chromebook",
        # ASUS
        "rog zephyrus", "zephyrus", "zenbook", "vivobook", "expertbook",
        "rog strix g15", "rog strix g16", "rog strix g17", "rog strix g18", "rog strix scar",
        "strix g15", "strix g16", "strix g17", "strix g18", "strix scar", "rog flow", "rog ally",
        "tuf gaming a14", "tuf gaming a15", "tuf gaming a16", "tuf gaming f15", "tuf gaming f16", "tuf gaming f17",
        "tuf a14", "tuf a15", "tuf a16", "tuf f15", "tuf f16", "tuf 15", "tuf gaming fx", "tuf gaming fa",
        "fa506", "fa507", "fx506", "fx507", "fa401", "fx401", "v3607", "fx608", "fx610",
        # HP
        "victus", "omen 14", "omen 15", "omen 16", "omen 17", "pavilion gaming",
        "spectre x360", "spectre", "envy 13", "envy 14", "envy 15", "envy 16", "probook", "elitebook", "zbook",
        # LENOVO
        "loq", "legion 5", "legion 7", "legion pro", "legion slim", "ideapad", "thinkpad", "thinkbook", "yoga slim", "yoga pro", "yoga 7", "yoga 9",
        # MSI
        "katana", "cyborg", "msi crosshair", "crosshair 15", "crosshair 16", "crosshair 17",
        "sword", "pulse", "msi stealth", "stealth 14", "stealth 15", "stealth 16", "stealth 17", "raider", "vector",
        "titan gt", "thin 15", "thin gf", "modern 14", "modern 15", "bravo 15", "alpha 15", "delta 15",
        # ACER
        "acer nitro", "nitro 5", "nitro 16", "nitro 17", "nitro v", "predator helios", "predator triton",
        "aspire 3", "aspire 5", "aspire 7", "aspire lite", "aspire go", "swift go", "swift x", "swift 3", "swift 5",
        "extensa", "travelmate",
        # DELL
        "alienware m15", "alienware m16", "alienware m18", "dell g15", "dell g16", "inspiron 14", "inspiron 15", "inspiron 16",
        "xps 13", "xps 14", "xps 15", "xps 16", "latitude", "vostro"
    ]
    if any(m in t for m in laptop_brand_models):
        return "Laptop"

    # Mobile Screen Size Indicators: e.g. 15.6", 14", 16", 17.3", 18", 15.6 inch, FHD 144Hz, WQXGA
    has_screen = bool(RE_SCREEN_SIZE.search(t))
    has_display_phrase = any(x in t for x in ["fhd ips", "wqxga 240hz", "wqxga 165hz", "oled 3k", "oled 240hz", "fhd 144hz", "144hz display", "ips display", "thin bezel display"])

    # Mobile CPU Processor Suffixes: e.g. 13620H, 14650HX, 8845HS, 8945HS, 7735HS, Ultra 7, Ultra 9
    has_mobile_cpu = bool(RE_MOBILE_CPU.search(t))

    # Explicit Mobile-Only GPU designations: e.g. RTX 4070 8GB mobile, RTX 4050, RTX 3050 4GB, RTX 2050, RTX 5050
    # Note: RTX 3050 6GB is a desktop card, so only 4GB is mobile-only.
    has_mobile_gpu = bool(RE_MOBILE_GPU.search(t))

    # Combined system specs (RAM + NVMe/SSD + CPU/GPU)
    has_multi_spec = (
        ("nvme" in t or "ssd" in t or "m.2" in t) and
        ("ram" in t or "ddr4" in t or "ddr5" in t) and
        ("rtx" in t or "gtx" in t or "radeon" in t or "intel" in t or "ryzen" in t or "core" in t)
    )

    if (has_screen or has_display_phrase or has_mobile_cpu or (has_mobile_gpu and has_multi_spec) or (has_multi_spec and (has_screen or has_mobile_cpu))):
        is_desktop_component = any(x in t for x in [
            "desktop casing", "desktop power supply", "desktop processor", "motherboard",
            "gaming motherboard", "pc casing"
        ])
        is_desktop_gpu = (
            any(g in t for g in ["graphics card", "graphic card", "vga card", "gddr6x", "gddr7"]) and
            not (has_screen or has_mobile_cpu or any(m in t for m in ["nitro v", "victus", "cyborg", "katana", "loq", "legion", "tuf fa", "tuf fx"]))
        )
        if not is_desktop_component and not is_desktop_gpu:
            return "Laptop"

    # 7. Explicit Desktop Graphics Card Check
    has_gpu_indicator = any(g in t for g in ["graphics card", "graphic card", "vga card", "gddr6x", "gddr7"])
    has_gpu_vendor = any(v in t for v in ["zotac", "palit", "inno3d", "sapphire", "powercolor", "xfx", "pny", "galax", "gainward", "windforce", "twin edge", "eagle oc"])
    if (has_gpu_indicator or has_gpu_vendor) and not has_laptop_chassis_word and not (has_screen or has_mobile_cpu):
        return "GPU"

    # 8. GPU (Graphics Card)
    if any(m in raw_cat for m in ["graphic card", "graphics card", "gpu", "vga", "video card"]):
        return "GPU"
    if any(m in t for m in ["graphics card", "graphic card", "video card", "vga card"]):
        return "GPU"
    if RE_GPU_MODEL.search(t):
        if not any(x in t for x in ["holder", "bracket", "cooler", "waterblock", "riser", "support"]):
            return "GPU"

    # 9. CPU (Processors)
    if any(m in raw_cat for m in ["processor", "processors", "cpu"]):
        return "CPU"
    if any(m in t for m in [
        "desktop processor", "tray processor", "intel core", "amd ryzen",
        "ryzen 3", "ryzen 5", "ryzen 7", "ryzen 9", "threadripper"
    ]):
        if not any(x in t for x in ["cooler", "liquid", "fan", "waterblock"]):
            return "CPU"

    # 10. RAM (Memory Modules)
    if any(m in raw_cat for m in ["memory", "ram"]):
        return "RAM"
    if any(m in t for m in ["desktop memory", "dimm ddr", "ddr4 ram", "ddr5 ram", "ddr3 ram", "rgb ram", "udimm", "u-dimm"]):
        return "RAM"
    if RE_RAM_SPECS_1.search(t) or RE_RAM_SPECS_2.search(t):
        return "RAM"
    if any(brand in t for brand in ["fury beast", "corsair vengeance", "xpg lancer", "t-force delta", "g.skill ripjaws", "trident z"]):
        if not any(comp in t for comp in ["casing", "cooler", "psu", "motherboard", "ssd"]):
            return "RAM"

    # 11. Storage (SSD & HDD)
    if any(m in raw_cat for m in ["storage", "ssd", "hdd", "hard drive"]):
        return "Storage"
    if any(m in t for m in [
        "nvme m.2", "m.2 nvme", "m.2 ssd", "sata ssd", "solid state drive",
        "internal hdd", "external hdd", "internal hard drive", "barracuda", "ironwolf", "wd blue", "wd black"
    ]):
        return "Storage"

    # 12. PSU (Power Supply)
    if any(m in raw_cat for m in ["power supply", "power supplies", "psu"]):
        return "PSU"
    if any(m in t for m in ["power supply", "power supplies", "80 plus", "modular psu"]):
        return "PSU"

    # 13. Casing
    if any(m in raw_cat for m in ["casing", "cases", "chassis"]):
        return "Casing"
    if any(m in t for m in ["pc case", "gaming case", "computer case", "mid tower", "mini tower", "full tower", "chassis"]):
        return "Casing"

    # 14. Monitor (fallback)
    if any(m in raw_cat for m in ["monitor", "monitors", "display"]):
        return "Monitor"
    if any(m in t for m in ["gaming monitor", "ips monitor", "curved monitor", "led monitor", "fhd monitor", "144hz monitor", "165hz monitor", "240hz monitor"]):
        return "Monitor"

    return "Accessories / Other"


def normalize_stock(stock: Optional[str]) -> str:
    """
    Normalizes stock descriptions into standard Enum:
    ['In Stock', 'Out of Stock', 'Available / On Order']
    """
    if not stock:
        return "Available / On Order"

    stock_str = str(stock).strip().lower()

    if any(k in stock_str for k in [
        "out of stock", "outofstock", "sold out", "unavailable", "0 in stock"
    ]):
        return "Out of Stock"

    if any(k in stock_str for k in [
        "in stock", "instock", "available now", "ready to ship", "add to cart"
    ]):
        return "In Stock"

    if any(k in stock_str for k in [
        "available", "on order", "pre-order", "preorder", "call for availability",
        "check site", "system only"
    ]):
        return "Available / On Order"

    return "In Stock"


def normalize_store_name(identifier: str) -> str:
    """Extracts canonical store name from filename or URL identifier."""
    id_lower = str(identifier).lower()
    for key, name in STORE_MAPPINGS.items():
        if key in id_lower:
            return name
    return identifier.replace("_", " ").title()


def clean_record(raw_record: dict, default_store: str = "Unknown Store") -> dict:
    """
    Transforms any raw scraped dictionary into the uniform pipeline schema:
    - Source_Store: str
    - Category: str
    - Title: str
    - Raw_Price: str
    - Cleaned_Price_LKR: float | None
    - Stock_Status: str
    - Product_URL: str
    - Scraped_Date: str (YYYY-MM-DD)
    """
    store = raw_record.get("Source_Store") or raw_record.get("Store") or default_store
    store = normalize_store_name(store)

    raw_title = raw_record.get("Title") or raw_record.get("Product_Name") or ""
    raw_category = raw_record.get("Category") or ""
    raw_price_str = raw_record.get("Price") or raw_record.get("Raw_Price") or ""
    raw_stock = raw_record.get("Stock") or raw_record.get("Stock_Status") or ""
    raw_url = raw_record.get("URL") or raw_record.get("Product_URL") or ""
    scraped_date = raw_record.get("Scraped_Date") or datetime.now().strftime("%Y-%m-%d")

    cleaned_title = clean_title(raw_title, raw_category)
    category = normalize_category(raw_category, cleaned_title)
    cleaned_price, standardized_raw_price = clean_price(raw_price_str)
    stock_status = normalize_stock(raw_stock)

    clean_url = str(raw_url).strip()
    if clean_url:
        clean_url = unquote(clean_url)

    return {
        "Source_Store": store,
        "Category": category,
        "Title": cleaned_title,
        "Raw_Price": standardized_raw_price,
        "Cleaned_Price_LKR": cleaned_price,
        "Stock_Status": stock_status,
        "Product_URL": clean_url,
        "Scraped_Date": scraped_date
    }
