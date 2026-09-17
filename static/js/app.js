/**
 * Sri Lanka PC Hardware Competitor Pricing Intelligence
 * Pure Vanilla JavaScript Application (Zero Framework Dependencies)
 * Handles state management, dynamic DOM rendering, async API polling, and UX interactions.
 */

// ============================================================================
// Application Configuration & State
// ============================================================================

const CONFIG = {
  // Auto-detect if running on GitHub Pages, file protocol, or local backend
  isGitHubPages: window.location.hostname.includes('github.io') || window.location.protocol === 'file:',
  apiBase: (window.location.protocol.startsWith('http') && !window.location.hostname.includes('github.io')) ? '' : 'http://127.0.0.1:8000',
  staticDataBase: 'data',
  defaultCompare: 'RTX 4060',
  debounceDelay: 280,
  toastDuration: 4000
};

const state = {
  activeTab: 'catalog',
  viewMode: 'grid', // 'grid' | 'table'
  // Catalog filters
  query: '',
  store: 'All',
  category: 'All',
  stock: 'All',
  sort: 'price_asc',
  page: 1,
  limit: 48,
  // Cached datasets
  allProducts: null, // Full catalog for client-side search & filtering
  metrics: null,
  productsData: { items: [], total: 0, total_pages: 1 },
  compareData: null,
  scrapers: [],
  scrapersPayload: null,
  scraperFilter: 'all',
  scraperQuery: '',
  selectedProduct: null,
  isApiOnline: true,
  isStaticMode: false
};

// ============================================================================
// DOM Elements Cache
// ============================================================================

const elements = {
  // Navigation tabs
  tabBtns: document.querySelectorAll('.tab-btn'),
  tabContents: document.querySelectorAll('.tab-content'),
  viewGridBtn: document.getElementById('viewGridBtn'),
  viewTableBtn: document.getElementById('viewTableBtn'),
  syncDbBtn: document.getElementById('syncDbBtn'),
  systemStatusBadge: document.getElementById('systemStatusBadge'),

  // KPIs
  kpiTotalSkus: document.getElementById('kpiTotalSkus'),
  kpiActiveStores: document.getElementById('kpiActiveStores'),
  kpiInStockRate: document.getElementById('kpiInStockRate'),
  kpiStockProgress: document.getElementById('kpiStockProgress'),
  kpiCategories: document.getElementById('kpiCategories'),

  // Catalog tab
  catalogSearch: document.getElementById('catalogSearch'),
  storeFilter: document.getElementById('storeFilter'),
  categoryFilter: document.getElementById('categoryFilter'),
  stockToggleBtns: document.querySelectorAll('.stock-toggle-btn'),
  sortSelect: document.getElementById('sortSelect'),
  resetFiltersBtn: document.getElementById('resetFiltersBtn'),
  resultsCount: document.getElementById('resultsCount'),
  catalogGrid: document.getElementById('catalogGrid'),
  catalogTableContainer: document.getElementById('catalogTableContainer'),
  catalogTableBody: document.getElementById('catalogTableBody'),
  paginationWrapper: document.getElementById('paginationWrapper'),
  exportCsvBtn: document.getElementById('exportCsvBtn'),

  // Compare tab
  compareInput: document.getElementById('compareInput'),
  compareSubmitBtn: document.getElementById('compareSubmitBtn'),
  compareChips: document.getElementById('compareChips'),
  compareResultsArea: document.getElementById('compareResultsArea'),

  // Stores & Categories tabs
  storesGridContainer: document.getElementById('storesGridContainer'),
  categoryTableBody: document.getElementById('categoryTableBody'),

  // Scraper Fleet Health & Monitoring Hub
  scraperGrid: document.getElementById('scraperGrid'),
  recompileTriggerBtn: document.getElementById('recompileTriggerBtn'),
  fleetStatusPill: document.getElementById('fleetStatusPill'),
  fleetOperationalValue: document.getElementById('fleetOperationalValue'),
  fleetOperationalSub: document.getElementById('fleetOperationalSub'),
  fleetSkusValue: document.getElementById('fleetSkusValue'),
  fleetRawPayloadSub: document.getElementById('fleetRawPayloadSub'),
  fleetEnginesValue: document.getElementById('fleetEnginesValue'),
  fleetScheduleSub: document.getElementById('fleetScheduleSub'),
  scraperSearch: document.getElementById('scraperSearch'),
  scraperFilterPills: document.querySelectorAll('.scraper-filter-pill'),
  scraperTelemetryTableBody: document.getElementById('scraperTelemetryTableBody'),
  countAllScrapers: document.getElementById('countAllScrapers'),
  countOpScrapers: document.getElementById('countOpScrapers'),
  countPwScrapers: document.getElementById('countPwScrapers'),
  countHttpScrapers: document.getElementById('countHttpScrapers'),

  // Modal & Toast
  productModal: document.getElementById('productModal'),
  modalCloseBtn: document.getElementById('modalCloseBtn'),
  modalBody: document.getElementById('modalBody'),
  toastContainer: document.getElementById('toastContainer')
};

// ============================================================================
// Formatters & Utility Functions
// ============================================================================

function formatLKR(amount) {
  if (amount === null || amount === undefined || isNaN(amount)) return 'Price on Request';
  return 'Rs. ' + Math.round(Number(amount)).toLocaleString('en-US');
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function debounce(func, delay) {
  let timeoutId;
  return function (...args) {
    clearTimeout(timeoutId);
    timeoutId = setTimeout(() => func.apply(this, args), delay);
  };
}

function showToast(message, type = 'info') {
  if (!elements.toastContainer) return;
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;

  const iconSvg = type === 'success' 
    ? `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2"><path d="M20 6 9 17l-5-5"/></svg>`
    : `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#00f2fe" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`;

  toast.innerHTML = `
    <div style="display:flex;align-items:center;gap:0.6rem;">
      ${iconSvg}
      <span>${escapeHtml(message)}</span>
    </div>
  `;

  elements.toastContainer.appendChild(toast);

  setTimeout(() => {
    toast.classList.add('removing');
    setTimeout(() => toast.remove(), 300);
  }, CONFIG.toastDuration);
}

// ============================================================================
// API Client Layer with Fallback Resilience
// ============================================================================

// ============================================================================
// Data Layer: Hybrid API Client & Client-Side Static Intelligence
// Supports both live FastAPI server and 100% static hosting on GitHub Pages
// ============================================================================

async function ensureAllProductsLoaded() {
  if (state.allProducts && state.allProducts.length > 0) {
    return state.allProducts;
  }
  try {
    const res = await fetch(`${CONFIG.staticDataBase}/products.json`);
    if (!res.ok) throw new Error(`Could not load products.json (${res.status})`);
    state.allProducts = await res.json();
    return state.allProducts;
  } catch (e) {
    console.error('[Static Data] Error loading products catalog:', e);
    return [];
  }
}

async function fetchJson(endpoint, options = {}) {
  // If hosted on GitHub Pages or file protocol, run client-side intelligence
  if (CONFIG.isGitHubPages) {
    state.isStaticMode = true;
    updateOnlineBadge(true, true);
    return await handleStaticQuery(endpoint);
  }

  const url = `${CONFIG.apiBase}${endpoint}`;
  try {
    const res = await fetch(url, options);
    if (!res.ok) {
      throw new Error(`HTTP Error ${res.status}: ${res.statusText}`);
    }
    state.isApiOnline = true;
    state.isStaticMode = false;
    updateOnlineBadge(true, false);
    return await res.json();
  } catch (err) {
    console.warn(`[API] Could not connect to ${url}, falling back to static data:`, err);
    state.isApiOnline = false;
    state.isStaticMode = true;
    updateOnlineBadge(true, true);
    return await handleStaticQuery(endpoint);
  }
}

async function handleStaticQuery(endpoint) {
  // 1. Metrics Endpoint
  if (endpoint.startsWith('/api/metrics')) {
    try {
      const res = await fetch(`${CONFIG.staticDataBase}/metrics.json`);
      if (res.ok) return await res.json();
    } catch (e) {
      console.warn('[Static] Failed to load metrics.json:', e);
    }
  }

  // 2. Products Endpoint
  if (endpoint.startsWith('/api/products')) {
    const products = await ensureAllProductsLoaded();
    const urlObj = new URL('http://dummy.local' + endpoint);
    const q = (urlObj.searchParams.get('q') || '').trim().toLowerCase();
    const category = urlObj.searchParams.get('category') || 'All';
    const store = urlObj.searchParams.get('store') || 'All';
    const stock = urlObj.searchParams.get('stock') || 'All';
    const sort = urlObj.searchParams.get('sort') || 'price_asc';
    const page = parseInt(urlObj.searchParams.get('page') || '1', 10);
    const limit = parseInt(urlObj.searchParams.get('limit') || '48', 10);

    let filtered = products;

    if (q) {
      const keywords = q.split(/\s+/).filter(Boolean);
      filtered = filtered.filter(item => {
        const title = (item.Title || '').toLowerCase();
        return keywords.every(kw => title.includes(kw));
      });
    }

    if (category && category !== 'All') {
      filtered = filtered.filter(item => item.Category === category);
    }

    if (store && store !== 'All') {
      filtered = filtered.filter(item => item.Source_Store === store);
    }

    if (stock && stock !== 'All') {
      filtered = filtered.filter(item => item.Stock_Status === stock);
    }

    // Sorting
    filtered = filtered.slice().sort((a, b) => {
      const priceA = a.Cleaned_Price_LKR != null ? a.Cleaned_Price_LKR : Infinity;
      const priceB = b.Cleaned_Price_LKR != null ? b.Cleaned_Price_LKR : Infinity;

      if (sort === 'price_asc') return priceA - priceB;
      if (sort === 'price_desc') return (b.Cleaned_Price_LKR || 0) - (a.Cleaned_Price_LKR || 0);
      if (sort === 'title_asc') return (a.Title || '').localeCompare(b.Title || '');
      if (sort === 'title_desc') return (b.Title || '').localeCompare(a.Title || '');
      return priceA - priceB;
    });

    const total = filtered.length;
    const offset = (page - 1) * limit;
    const pageItems = filtered.slice(offset, offset + limit);

    return {
      items: pageItems,
      total: total,
      page: page,
      limit: limit,
      total_pages: Math.max(1, Math.ceil(total / limit))
    };
  }

  // 3. Price Comparison Endpoint
  if (endpoint.startsWith('/api/compare')) {
    const products = await ensureAllProductsLoaded();
    const urlObj = new URL('http://dummy.local' + endpoint);
    const model = (urlObj.searchParams.get('model') || '').trim();
    const category = urlObj.searchParams.get('category');

    const keywords = model.toLowerCase().split(/\s+/).filter(Boolean);
    const isGpuQuery = keywords.some(k => ['rtx', 'gtx', 'rx', 'radeon', 'geforce'].some(gpu => k.includes(gpu)))
      && !keywords.some(k => ['laptop', 'notebook'].includes(k));

    let results = products.filter(item => {
      if (item.Cleaned_Price_LKR == null || item.Cleaned_Price_LKR <= 0) return false;
      const title = (item.Title || '').toLowerCase();
      const matchesKeywords = keywords.every(kw => title.includes(kw));
      if (!matchesKeywords) return false;

      if (category && category !== 'All') {
        return item.Category === category;
      } else if (isGpuQuery) {
        return item.Category === 'GPU';
      }
      return true;
    });

    results.sort((a, b) => a.Cleaned_Price_LKR - b.Cleaned_Price_LKR);

    if (results.length === 0) {
      return {
        query: model,
        matches: 0,
        results: [],
        cheapest: null,
        min_price: 0,
        max_price: 0,
        avg_price: 0,
        savings_lkr: 0,
        savings_pct: 0
      };
    }

    const cheapest = results[0];
    const prices = results.map(r => r.Cleaned_Price_LKR);
    const min_p = Math.min(...prices);
    const max_p = Math.max(...prices);
    const avg_p = Math.round(prices.reduce((s, p) => s + p, 0) / prices.length);
    const savings_lkr = Math.round(max_p - min_p);
    const savings_pct = max_p > 0 ? Math.round((savings_lkr / max_p) * 1000) / 10 : 0;

    const decoratedResults = results.map(r => {
      const diff = Math.round(r.Cleaned_Price_LKR - min_p);
      const pct = min_p > 0 ? Math.round((diff / min_p) * 1000) / 10 : 0;
      return {
        ...r,
        diff_from_cheapest_lkr: diff,
        diff_pct: pct
      };
    });

    return {
      query: model,
      matches: results.length,
      cheapest: cheapest,
      min_price: min_p,
      max_price: max_p,
      avg_price: avg_p,
      savings_lkr: savings_lkr,
      savings_pct: savings_pct,
      results: decoratedResults
    };
  }

  // 4. Scrapers Registry Endpoint
  if (endpoint.startsWith('/api/scrapers')) {
    try {
      const res = await fetch(`${CONFIG.staticDataBase}/scrapers.json`);
      if (res.ok) return await res.json();
    } catch (e) {
      console.warn('[Static] Failed to load scrapers.json:', e);
    }
  }

  return {};
}

function updateOnlineBadge(online, isStatic = false) {
  if (!elements.systemStatusBadge) return;
  if (isStatic) {
    elements.systemStatusBadge.innerHTML = `
      <span class="pulsing-dot" style="background:#00f2fe;box-shadow:0 0 10px #00f2fe;"></span>
      <span>GitHub Pages Intel</span>
    `;
    elements.systemStatusBadge.style.borderColor = 'rgba(0, 242, 254, 0.4)';
  } else if (online) {
    elements.systemStatusBadge.innerHTML = `
      <span class="pulsing-dot"></span>
      <span>API Connected</span>
    `;
    elements.systemStatusBadge.style.borderColor = 'rgba(16, 185, 129, 0.4)';
  } else {
    elements.systemStatusBadge.innerHTML = `
      <span class="pulsing-dot" style="background:#f59e0b;box-shadow:0 0 10px #f59e0b;"></span>
      <span>Offline Preview</span>
    `;
    elements.systemStatusBadge.style.borderColor = 'rgba(245, 158, 11, 0.4)';
  }
}

// ============================================================================
// UI Renderers: Metrics & Top-Level KPIs
// ============================================================================

async function loadMetrics() {
  const data = await fetchJson('/api/metrics');
  state.metrics = data;

  if (elements.kpiTotalSkus && data.total_skus !== undefined) {
    animateCounter(elements.kpiTotalSkus, data.total_skus);
  }
  if (elements.kpiActiveStores && data.active_stores !== undefined) {
    animateCounter(elements.kpiActiveStores, data.active_stores);
  }
  if (elements.kpiInStockRate && data.in_stock_rate !== undefined) {
    elements.kpiInStockRate.innerText = `${data.in_stock_rate}%`;
    if (elements.kpiStockProgress) {
      elements.kpiStockProgress.style.width = `${Math.min(100, data.in_stock_rate)}%`;
    }
  }
  if (elements.kpiCategories && data.total_categories !== undefined) {
    animateCounter(elements.kpiCategories, data.total_categories);
  }

  // Populate Filter Dropdowns
  populateFilters(data);

  // Render Stores Breakdown Tab & Category Taxonomy Tab
  renderStoresTab(data.stores || []);
  renderCategoriesTab(data.categories || []);
}

function animateCounter(element, targetVal) {
  const duration = 1000;
  const startTime = performance.now();
  const startVal = 0;

  function update(currentTime) {
    const elapsed = currentTime - startTime;
    const progress = Math.min(elapsed / duration, 1);
    // Smooth easeOutQuad
    const current = Math.floor(startVal + (targetVal - startVal) * (1 - (1 - progress) * (1 - progress)));
    element.innerText = current.toLocaleString('en-US');
    if (progress < 1) {
      requestAnimationFrame(update);
    } else {
      element.innerText = targetVal.toLocaleString('en-US');
    }
  }
  requestAnimationFrame(update);
}

function populateFilters(data) {
  if (elements.storeFilter && data.stores) {
    const currentVal = elements.storeFilter.value;
    elements.storeFilter.innerHTML = `<option value="All">All Competitor Stores (${data.stores.length})</option>`;
    data.stores.forEach(s => {
      const opt = document.createElement('option');
      opt.value = s.Source_Store;
      opt.textContent = `${s.Source_Store} (${s.total.toLocaleString()} SKUs)`;
      elements.storeFilter.appendChild(opt);
    });
    elements.storeFilter.value = currentVal || 'All';
  }

  if (elements.categoryFilter && data.categories) {
    const currentVal = elements.categoryFilter.value;
    elements.categoryFilter.innerHTML = `<option value="All">All Hardware Categories (${data.categories.length})</option>`;
    data.categories.forEach(c => {
      const opt = document.createElement('option');
      opt.value = c.Category;
      opt.textContent = `${c.Category} (${c.count.toLocaleString()})`;
      elements.categoryFilter.appendChild(opt);
    });
    elements.categoryFilter.value = currentVal || 'All';
  }
}

// ============================================================================
// UI Renderers: Catalog Grid & Table
// ============================================================================

async function loadProducts() {
  renderLoadingState();

  const params = new URLSearchParams({
    page: state.page,
    limit: state.limit,
    sort: state.sort
  });

  if (state.query.trim()) params.set('q', state.query.trim());
  if (state.store !== 'All') params.set('store', state.store);
  if (state.category !== 'All') params.set('category', state.category);
  if (state.stock !== 'All') params.set('stock', state.stock);

  const data = await fetchJson(`/api/products?${params.toString()}`);
  state.productsData = data;

  // Update counts
  if (elements.resultsCount) {
    elements.resultsCount.innerHTML = `Showing <span class="results-count-bold">${(data.items || []).length.toLocaleString()}</span> of <span class="results-count-bold">${(data.total || 0).toLocaleString()}</span> live indexed hardware products`;
  }

  if (!data.items || data.items.length === 0) {
    renderEmptyState();
    return;
  }

  if (state.viewMode === 'grid') {
    renderProductGrid(data.items);
  } else {
    renderProductTable(data.items);
  }

  renderPagination(data.page, data.total_pages);
}

function renderLoadingState() {
  if (state.viewMode === 'grid') {
    elements.catalogGrid.style.display = 'grid';
    elements.catalogTableContainer.style.display = 'none';
    elements.catalogGrid.innerHTML = Array(12).fill(0).map(() => `
      <div class="product-card skeleton" style="height: 240px;"></div>
    `).join('');
  } else {
    elements.catalogGrid.style.display = 'none';
    elements.catalogTableContainer.style.display = 'block';
    elements.catalogTableBody.innerHTML = Array(8).fill(0).map(() => `
      <tr>
        <td colspan="6"><div class="skeleton" style="height: 32px; width: 100%;"></div></td>
      </tr>
    `).join('');
  }
}

function renderEmptyState() {
  const emptyHtml = `
    <div style="grid-column: 1/-1; text-align: center; padding: 4rem 1rem; color: var(--text-muted);">
      <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="margin-bottom: 1rem; opacity: 0.5;">
        <circle cx="11" cy="11" r="8"></circle>
        <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
      </svg>
      <h3 style="font-size: 1.15rem; color: var(--text-primary); margin-bottom: 0.5rem;">No Matching Hardware Found</h3>
      <p style="font-size: 0.85rem; max-width: 420px; margin: 0 auto 1.5rem auto;">
        No products matched your active filters for search "${escapeHtml(state.query)}". Try broadening your search or resetting filters.
      </p>
      <button class="btn btn-glass" onclick="resetFilters()">Reset All Filters</button>
    </div>
  `;

  if (state.viewMode === 'grid') {
    elements.catalogGrid.innerHTML = emptyHtml;
  } else {
    elements.catalogTableBody.innerHTML = `<tr><td colspan="6">${emptyHtml}</td></tr>`;
  }
  if (elements.paginationWrapper) elements.paginationWrapper.innerHTML = '';
}

function renderProductGrid(items) {
  elements.catalogGrid.style.display = 'grid';
  elements.catalogTableContainer.style.display = 'none';

  elements.catalogGrid.innerHTML = items.map((item, index) => {
    const isInStock = item.Stock_Status === 'In Stock';
    const stockClass = isInStock ? 'in-stock' : 'out-of-stock';
    const store = item.Source_Store || 'Unknown Vendor';
    const priceText = formatLKR(item.Cleaned_Price_LKR);
    const category = item.Category || 'Hardware';
    const hasUrl = item.Product_URL && item.Product_URL.startsWith('http');

    return `
      <div class="product-card" data-index="${index}">
        <div>
          <div class="product-card-top">
            <span class="store-badge" data-store="${escapeHtml(store)}">${escapeHtml(store)}</span>
            <span class="stock-pill ${stockClass}">
              <span style="width:5px;height:5px;border-radius:50%;background:currentColor;"></span>
              ${escapeHtml(item.Stock_Status || 'Unknown')}
            </span>
          </div>
          <span class="category-tag">${escapeHtml(category)}</span>
          <h4 class="product-title" title="${escapeHtml(item.Title)}">${escapeHtml(item.Title)}</h4>
        </div>

        <div class="product-card-bottom">
          <div class="price-box">
            <span class="price-label">Market Price</span>
            <span class="price-val">${priceText}</span>
          </div>
          <div class="card-actions">
            <button class="btn-icon-action" title="Compare this model" onclick="quickCompare('${escapeHtml(item.Title.replace(/'/g, "\\'"))}', '${escapeHtml(category)}')">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 3h5v5"/><path d="M8 21H3v-5"/><path d="M21 3 14 10"/><path d="M3 21l7-7"/></svg>
            </button>
            ${hasUrl ? `
              <a href="${escapeHtml(item.Product_URL)}" target="_blank" rel="noopener noreferrer" class="btn-icon-action" title="Visit Store Page">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
              </a>
            ` : ''}
          </div>
        </div>
      </div>
    `;
  }).join('');
}

function renderProductTable(items) {
  elements.catalogGrid.style.display = 'none';
  elements.catalogTableContainer.style.display = 'block';

  elements.catalogTableBody.innerHTML = items.map(item => {
    const isInStock = item.Stock_Status === 'In Stock';
    const stockClass = isInStock ? 'in-stock' : 'out-of-stock';
    const hasUrl = item.Product_URL && item.Product_URL.startsWith('http');

    return `
      <tr>
        <td style="width: 140px;">
          <span class="store-badge" data-store="${escapeHtml(item.Source_Store)}">${escapeHtml(item.Source_Store)}</span>
        </td>
        <td>
          <div style="font-weight: 600; color: var(--text-primary); line-height: 1.35;">${escapeHtml(item.Title)}</div>
          <div style="font-size: 0.72rem; color: var(--text-muted); margin-top: 0.2rem;">${escapeHtml(item.Category || 'Hardware')}</div>
        </td>
        <td style="width: 120px;">
          <span class="stock-pill ${stockClass}">${escapeHtml(item.Stock_Status || 'Unknown')}</span>
        </td>
        <td style="width: 150px; text-align: right;">
          <span style="font-family: var(--font-mono); font-weight: 700; color: var(--accent-cyan); font-size: 1rem;">
            ${formatLKR(item.Cleaned_Price_LKR)}
          </span>
        </td>
        <td style="width: 100px; text-align: center;">
          <div style="display: inline-flex; gap: 0.4rem;">
            <button class="btn-icon-action" title="Compare" onclick="quickCompare('${escapeHtml(item.Title.replace(/'/g, "\\'"))}', '${escapeHtml(item.Category || '')}')">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 3h5v5"/><path d="M8 21H3v-5"/><path d="M21 3 14 10"/><path d="M3 21l7-7"/></svg>
            </button>
            ${hasUrl ? `
              <a href="${escapeHtml(item.Product_URL)}" target="_blank" rel="noopener noreferrer" class="btn-icon-action" title="Visit Store Page">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
              </a>
            ` : ''}
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

function renderPagination(currentPage, totalPages) {
  if (!elements.paginationWrapper) return;
  if (totalPages <= 1) {
    elements.paginationWrapper.innerHTML = '';
    return;
  }

  let html = `
    <div style="font-size: 0.8rem; color: var(--text-muted); font-family: var(--font-mono);">
      Page ${currentPage} of ${totalPages}
    </div>
    <div class="pagination-controls">
      <button class="page-btn" ${currentPage === 1 ? 'disabled' : ''} onclick="goToPage(1)" title="First Page">«</button>
      <button class="page-btn" ${currentPage === 1 ? 'disabled' : ''} onclick="goToPage(${currentPage - 1})" title="Previous Page">‹</button>
  `;

  // Dynamic window of page numbers
  const maxButtons = 5;
  let startPage = Math.max(1, currentPage - 2);
  let endPage = Math.min(totalPages, startPage + maxButtons - 1);
  if (endPage - startPage < maxButtons - 1) {
    startPage = Math.max(1, endPage - maxButtons + 1);
  }

  for (let p = startPage; p <= endPage; p++) {
    html += `
      <button class="page-btn ${p === currentPage ? 'active' : ''}" onclick="goToPage(${p})">${p}</button>
    `;
  }

  html += `
      <button class="page-btn" ${currentPage === totalPages ? 'disabled' : ''} onclick="goToPage(${currentPage + 1})" title="Next Page">›</button>
      <button class="page-btn" ${currentPage === totalPages ? 'disabled' : ''} onclick="goToPage(${totalPages})" title="Last Page">»</button>
    </div>
  `;

  elements.paginationWrapper.innerHTML = html;
}

function goToPage(page) {
  state.page = page;
  loadProducts();
  window.scrollTo({ top: 380, behavior: 'smooth' });
}

// ============================================================================
// UI Renderers: Cross-Store Comparison Matrix
// ============================================================================

async function runPriceComparison(modelQuery, category = null) {
  if (!modelQuery || !modelQuery.trim()) return;
  const query = modelQuery.trim();
  state.compareQuery = query;

  if (elements.compareInput) elements.compareInput.value = query;

  // Update active chip state
  document.querySelectorAll('.chip-btn').forEach(chip => {
    chip.classList.toggle('active', chip.dataset.model.toLowerCase() === query.toLowerCase());
  });

  if (elements.compareResultsArea) {
    elements.compareResultsArea.innerHTML = `
      <div style="padding: 3rem; text-align: center; color: var(--text-muted);">
        <div class="skeleton" style="height: 120px; width: 100%; max-width: 600px; margin: 0 auto 1.5rem auto; border-radius: var(--radius-lg);"></div>
        <p>Analyzing competitor prices for "${escapeHtml(query)}" across all vendors...</p>
      </div>
    `;
  }

  let endpoint = `/api/compare?model=${encodeURIComponent(query)}`;
  if (category && category !== 'All') {
    endpoint += `&category=${encodeURIComponent(category)}`;
  }
  const data = await fetchJson(endpoint);
  state.compareData = data;
  renderCompareResults(data);
}

function renderCompareResults(data) {
  if (!elements.compareResultsArea) return;

  if (!data.results || data.results.length === 0) {
    elements.compareResultsArea.innerHTML = `
      <div style="text-align: center; padding: 3rem 1rem; color: var(--text-muted);">
        <h4 style="font-size: 1.1rem; color: var(--text-primary); margin-bottom: 0.5rem;">No exact match for "${escapeHtml(data.query)}"</h4>
        <p style="font-size: 0.85rem; max-width: 450px; margin: 0 auto 1.5rem auto;">
          Try searching for standard GPU/CPU family keywords such as <strong>RTX 4060</strong>, <strong>Ryzen 7600</strong>, <strong>i5 13400</strong>, or <strong>DDR5</strong>.
        </p>
      </div>
    `;
    return;
  }

  const cheapest = data.cheapest || data.results[0];
  const savingsText = data.savings_lkr > 0 ? formatLKR(data.savings_lkr) : 'Rs. 0';
  const savingsPct = data.savings_pct || 0;

  let html = `
    <div class="compare-analysis-grid">
      <!-- Best Deal Spotlight Card -->
      <div class="best-deal-card">
        <div class="best-deal-ribbon">Lowest Price</div>
        <div class="deal-vendor">${escapeHtml(cheapest.Source_Store)}</div>
        <div class="deal-title">${escapeHtml(cheapest.Title)}</div>
        <div class="deal-price">${formatLKR(cheapest.Cleaned_Price_LKR)}</div>
        <div style="margin-top: 1rem; display: flex; gap: 0.75rem;">
          ${cheapest.Product_URL ? `
            <a href="${escapeHtml(cheapest.Product_URL)}" target="_blank" rel="noopener noreferrer" class="btn btn-primary btn-sm">
              Buy from ${escapeHtml(cheapest.Source_Store)}
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
            </a>
          ` : ''}
        </div>
      </div>

      <!-- Price Spread & Potential Savings Card -->
      <div class="savings-card">
        <div>
          <div style="display: flex; justify-content: space-between; align-items: baseline;">
            <span style="font-size: 0.76rem; text-transform: uppercase; color: var(--text-muted); font-weight: 600;">Maximum Price Spread</span>
            <span style="font-size: 0.75rem; color: var(--accent-emerald); font-weight: 700;">Save up to ${savingsPct}%</span>
          </div>
          <div style="font-family: var(--font-mono); font-size: 1.85rem; font-weight: 800; color: var(--text-primary); margin: 0.35rem 0;">
            ${savingsText}
          </div>
          <div style="font-size: 0.8rem; color: var(--text-secondary);">
            Price range from ${formatLKR(data.min_price)} to ${formatLKR(data.max_price)} (Avg: ${formatLKR(data.avg_price)})
          </div>
        </div>

        <div class="price-spread-bar-wrapper">
          <div class="spread-bar-header">
            <span>Cheapest: ${escapeHtml(cheapest.Source_Store)}</span>
            <span>Spread: ${savingsPct}%</span>
          </div>
          <div class="spread-track">
            <div class="spread-fill" style="width: 100%;"></div>
          </div>
        </div>
      </div>
    </div>

    <!-- Comparative Table -->
    <div class="catalog-table-wrapper" style="margin-top: 1.5rem;">
      <table class="data-table">
        <thead>
          <tr>
            <th>Store Vendor</th>
            <th>Catalog Product Title</th>
            <th>Stock Status</th>
            <th style="text-align: right;">Price (LKR)</th>
            <th style="text-align: right;">Vs. Lowest</th>
            <th style="text-align: center;">Store Link</th>
          </tr>
        </thead>
        <tbody>
  `;

  data.results.forEach((item, i) => {
    const isLowest = i === 0;
    const diffVal = item.diff_from_cheapest_lkr || 0;
    const diffPct = item.diff_pct || 0;
    const diffLabel = isLowest ? `<span style="color:var(--accent-emerald);font-weight:700;">BEST DEAL</span>` : `+${formatLKR(diffVal)} (+${diffPct}%)`;
    const stockClass = item.Stock_Status === 'In Stock' ? 'in-stock' : 'out-of-stock';

    html += `
      <tr style="${isLowest ? 'background: rgba(16, 185, 129, 0.05);' : ''}">
        <td><span class="store-badge" data-store="${escapeHtml(item.Source_Store)}">${escapeHtml(item.Source_Store)}</span></td>
        <td style="font-weight: 500;">${escapeHtml(item.Title)}</td>
        <td><span class="stock-pill ${stockClass}">${escapeHtml(item.Stock_Status)}</span></td>
        <td style="text-align: right; font-family: var(--font-mono); font-weight: 700; color: ${isLowest ? '#34d399' : 'var(--text-primary)'}; font-size: 0.95rem;">
          ${formatLKR(item.Cleaned_Price_LKR)}
        </td>
        <td style="text-align: right; font-family: var(--font-mono); font-size: 0.8rem; color: ${isLowest ? '#34d399' : 'var(--text-muted)'};">
          ${diffLabel}
        </td>
        <td style="text-align: center;">
          ${item.Product_URL ? `
            <a href="${escapeHtml(item.Product_URL)}" target="_blank" rel="noopener noreferrer" class="btn-icon-action" style="margin: 0 auto;" title="Visit Product Page">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
            </a>
          ` : '-'}
        </td>
      </tr>
    `;
  });

  html += `
        </tbody>
      </table>
    </div>
  `;

  elements.compareResultsArea.innerHTML = html;
}

// ============================================================================
// UI Renderers: Stores Intelligence & Category Taxonomy Tabs
// ============================================================================

function renderStoresTab(stores) {
  if (!elements.storesGridContainer) return;

  if (!stores || stores.length === 0) {
    elements.storesGridContainer.innerHTML = `<div style="color:var(--text-muted);">No store data available.</div>`;
    return;
  }

  elements.storesGridContainer.innerHTML = stores.map(store => {
    const rate = store.in_stock_rate !== undefined ? store.in_stock_rate : 0;
    const rateColor = rate >= 70 ? '#10b981' : rate >= 50 ? '#f59e0b' : '#f43f5e';

    return `
      <div class="store-intel-card">
        <div>
          <div class="store-intel-header">
            <h3 class="store-intel-name">${escapeHtml(store.Source_Store)}</h3>
            <span class="store-badge" data-store="${escapeHtml(store.Source_Store)}">Active Vendor</span>
          </div>

          <div class="store-stats-row">
            <div class="store-stat-box">
              <div class="store-stat-label">Total Indexed SKUs</div>
              <div class="store-stat-val">${(store.total || 0).toLocaleString()}</div>
            </div>
            <div class="store-stat-box">
              <div class="store-stat-label">In Stock SKUs</div>
              <div class="store-stat-val" style="color: ${rateColor};">${(store.in_stock || 0).toLocaleString()}</div>
            </div>
          </div>

          <div style="margin-bottom: 0.5rem;">
            <div style="display: flex; justify-content: space-between; font-size: 0.74rem; color: var(--text-secondary); margin-bottom: 0.35rem;">
              <span>Stock Availability Health</span>
              <span style="font-weight: 700; color: ${rateColor};">${rate}%</span>
            </div>
            <div class="progress-track">
              <div class="progress-bar" style="width: ${Math.min(100, rate)}%; background: ${rateColor};"></div>
            </div>
          </div>
        </div>

        <div style="margin-top: 1.25rem; padding-top: 0.85rem; border-top: 1px solid rgba(255,255,255,0.05); display: flex; justify-content: space-between; align-items: center;">
          <button class="btn btn-glass btn-sm" onclick="filterByStore('${escapeHtml(store.Source_Store)}')">
            Filter Catalog by Store
          </button>
        </div>
      </div>
    `;
  }).join('');
}

function renderCategoriesTab(categories) {
  if (!elements.categoryTableBody) return;

  if (!categories || categories.length === 0) {
    elements.categoryTableBody.innerHTML = `<tr><td colspan="5" style="text-align:center;color:var(--text-muted);">No categories available.</td></tr>`;
    return;
  }

  elements.categoryTableBody.innerHTML = categories.map(cat => {
    return `
      <tr>
        <td style="font-weight: 600; font-size: 0.95rem;">
          <a href="javascript:void(0)" onclick="filterByCategory('${escapeHtml(cat.Category)}')" style="color: var(--text-primary); text-decoration: none;">
            ${escapeHtml(cat.Category)}
          </a>
        </td>
        <td style="text-align: right; font-family: var(--font-mono); font-weight: 600;">
          ${(cat.count || 0).toLocaleString()}
        </td>
        <td style="text-align: right; font-family: var(--font-mono); font-weight: 700; color: var(--accent-cyan);">
          ${formatLKR(cat.avg_price)}
        </td>
        <td style="text-align: right; font-family: var(--font-mono); font-size: 0.85rem; color: var(--text-muted);">
          ${formatLKR(cat.min_price)}
        </td>
        <td style="text-align: right; font-family: var(--font-mono); font-size: 0.85rem; color: var(--text-muted);">
          ${formatLKR(cat.max_price)}
        </td>
      </tr>
    `;
  }).join('');
}

// ============================================================================
// UI Renderers: Web Scraper Fleet Health & Monitoring Dashboard
// ============================================================================

async function loadScrapers() {
  const data = await fetchJson('/api/scrapers');
  state.scrapersPayload = data || {};
  state.scrapers = Array.isArray(data) ? data : (data.scrapers || []);
  renderScrapersHealthDashboard();
}

function renderScrapersHealthDashboard() {
  const payload = state.scrapersPayload || {};
  const fleet = payload.fleet || {};
  const allScrapers = state.scrapers || [];

  // 1. Render Top Fleet Overview KPIs
  if (elements.fleetOperationalValue) {
    const opCount = fleet.operational_scrapers != null ? fleet.operational_scrapers : allScrapers.filter(s => (s.telemetry?.total_skus || 0) > 0).length;
    const totalCount = fleet.total_scrapers || allScrapers.length || 11;
    elements.fleetOperationalValue.textContent = `${opCount} / ${totalCount} Stores`;
  }
  if (elements.fleetOperationalSub) {
    const rate = fleet.operational_rate != null ? fleet.operational_rate : Math.round((8 / 11) * 1000) / 10;
    elements.fleetOperationalSub.textContent = `${rate}% Active Coverage`;
  }
  if (elements.fleetSkusValue) {
    const skus = fleet.total_harvested_skus != null ? fleet.total_harvested_skus : allScrapers.reduce((acc, s) => acc + (s.telemetry?.total_skus || 0), 0);
    elements.fleetSkusValue.textContent = Number(skus).toLocaleString('en-US');
  }
  if (elements.fleetRawPayloadSub) {
    elements.fleetRawPayloadSub.textContent = `${fleet.total_raw_data_formatted || '1.55 MB'} Raw Store Payloads`;
  }
  if (elements.fleetEnginesValue) {
    const pw = fleet.playwright_engines != null ? fleet.playwright_engines : allScrapers.filter(s => s.is_playwright).length;
    const http = fleet.http_engines != null ? fleet.http_engines : allScrapers.length - pw;
    elements.fleetEnginesValue.textContent = `${pw} Browser • ${http} HTTP`;
  }
  if (elements.fleetScheduleSub && fleet.schedule) {
    elements.fleetScheduleSub.textContent = fleet.schedule;
  }

  // Update filter pill counters
  const opScrapersCount = allScrapers.filter(s => (s.telemetry?.total_skus || 0) > 0).length;
  const pwScrapersCount = allScrapers.filter(s => s.is_playwright).length;
  const httpScrapersCount = allScrapers.length - pwScrapersCount;

  if (elements.countAllScrapers) elements.countAllScrapers.textContent = allScrapers.length;
  if (elements.countOpScrapers) elements.countOpScrapers.textContent = opScrapersCount;
  if (elements.countPwScrapers) elements.countPwScrapers.textContent = pwScrapersCount;
  if (elements.countHttpScrapers) elements.countHttpScrapers.textContent = httpScrapersCount;

  // 2. Filter scrapers based on active filter and search query
  let filtered = allScrapers.slice();

  if (state.scraperFilter === 'operational') {
    filtered = filtered.filter(s => (s.telemetry?.total_skus || 0) > 0);
  } else if (state.scraperFilter === 'playwright') {
    filtered = filtered.filter(s => s.is_playwright);
  } else if (state.scraperFilter === 'http') {
    filtered = filtered.filter(s => !s.is_playwright);
  }

  if (state.scraperQuery) {
    const q = state.scraperQuery.toLowerCase().trim();
    filtered = filtered.filter(s => 
      (s.name || '').toLowerCase().includes(q) ||
      (s.engine || '').toLowerCase().includes(q) ||
      (s.type || '').toLowerCase().includes(q) ||
      (s.description || '').toLowerCase().includes(q)
    );
  }

  // 3. Render Scraper Health Cards
  if (elements.scraperGrid) {
    if (filtered.length === 0) {
      elements.scraperGrid.innerHTML = `
        <div style="grid-column: 1 / -1; padding: 3rem; text-align: center; color: var(--text-muted);">
          <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="margin-bottom: 0.75rem; opacity: 0.5;"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <p style="font-size: 0.95rem; margin: 0;">No scrapers matching "<strong>${escapeHtml(state.scraperQuery)}</strong>"</p>
        </div>
      `;
    } else {
      elements.scraperGrid.innerHTML = filtered.map(s => {
        const t = s.telemetry || {};
        const initials = (s.name || 'SC').split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();
        const statusBadge = s.status_badge || (t.total_skus > 0 ? 'healthy' : 'idle');
        const statusLabel = s.status || (t.total_skus > 0 ? 'Operational' : 'Standby / Ready');
        const totalSkusStr = (t.total_skus || 0).toLocaleString('en-US');
        const inStockRate = t.in_stock_rate != null ? t.in_stock_rate : 0;
        const inStockSkusStr = (t.in_stock_skus || 0).toLocaleString('en-US');
        const rawSize = t.raw_size_formatted || '0 B';
        const lastScraped = t.last_scraped || 'No Runs';
        const sharePct = t.market_share_pct || 0;

        return `
          <div class="scraper-card">
            <div>
              <div class="scraper-card-top">
                <div class="scraper-card-store">
                  <div class="scraper-store-avatar">${escapeHtml(initials)}</div>
                  <div>
                    <div class="scraper-card-title">
                      <span>${escapeHtml(s.name)}</span>
                    </div>
                    ${s.url ? `
                      <a href="${escapeHtml(s.url)}" target="_blank" rel="noopener noreferrer" class="scraper-card-url" title="Visit ${escapeHtml(s.name)} storefront">
                        <span>${escapeHtml(s.url.replace(/^https?:\/\/(www\.)?/, ''))}</span>
                        <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
                      </a>
                    ` : ''}
                  </div>
                </div>
                <div style="display: flex; flex-direction: column; align-items: flex-end; gap: 0.35rem;">
                  <span class="scraper-status-pill ${statusBadge}">
                    <span class="scraper-status-dot ${statusBadge}"></span>
                    <span>${escapeHtml(statusLabel)}</span>
                  </span>
                  <span class="store-tech-pill" style="font-size: 0.68rem;">${escapeHtml(s.engine || s.type)}</span>
                </div>
              </div>

              <p style="font-size: 0.78rem; color: var(--text-secondary); line-height: 1.45; margin: 1rem 0 0.85rem;">
                ${escapeHtml(s.description || 'Automated price and inventory scraper')}
              </p>

              <!-- Metrics Mini-Grid -->
              <div class="scraper-stats-grid">
                <div class="scraper-stat-item">
                  <span class="scraper-stat-label">Harvested SKUs</span>
                  <span class="scraper-stat-value" style="color: #00f2fe;">${totalSkusStr}</span>
                  <span style="font-size: 0.68rem; color: var(--text-muted);">${sharePct}% market share</span>
                </div>
                <div class="scraper-stat-item">
                  <span class="scraper-stat-label">In-Stock Rate</span>
                  <span class="scraper-stat-value" style="color: #10b981;">${inStockRate}%</span>
                  <span style="font-size: 0.68rem; color: var(--text-muted);">${inStockSkusStr} available</span>
                </div>
                <div class="scraper-stat-item">
                  <span class="scraper-stat-label">Raw Store Payload</span>
                  <span class="scraper-stat-value">${escapeHtml(rawSize)}</span>
                  <span style="font-size: 0.68rem; color: var(--text-muted);">${t.raw_file_count || 0} CSV batch(es)</span>
                </div>
                <div class="scraper-stat-item">
                  <span class="scraper-stat-label">Last Ingested</span>
                  <span class="scraper-stat-value" style="font-size: 0.85rem; font-weight: 600;">${escapeHtml(lastScraped)}</span>
                  <span style="font-size: 0.68rem; color: var(--text-muted);">${t.categories_count || 0} hardware classes</span>
                </div>
              </div>
            </div>

            <!-- Card Actions -->
            <div class="scraper-card-footer">
              <span style="font-family: var(--font-mono); font-size: 0.7rem; color: var(--text-muted);">
                ${t.primary_raw_file ? escapeHtml(t.primary_raw_file) : 'No raw dataset'}
              </span>
              <div style="display: flex; gap: 0.5rem;">
                ${t.total_skus > 0 ? `
                  <button class="btn btn-glass btn-sm" onclick="filterByStore('${escapeHtml(s.name)}')">
                    View Catalog (${totalSkusStr})
                  </button>
                ` : `
                  <button class="btn btn-glass btn-sm" disabled style="opacity: 0.5;">Standby</button>
                `}
              </div>
            </div>
          </div>
        `;
      }).join('');
    }
  }

  // 4. Render Deep Telemetry Matrix Table
  if (elements.scraperTelemetryTableBody) {
    elements.scraperTelemetryTableBody.innerHTML = allScrapers.map(s => {
      const t = s.telemetry || {};
      const statusBadge = s.status_badge || (t.total_skus > 0 ? 'healthy' : 'idle');
      const statusLabel = s.status || (t.total_skus > 0 ? 'Operational' : 'Standby');
      const totalSkusStr = (t.total_skus || 0).toLocaleString('en-US');
      const inStockRate = t.in_stock_rate != null ? t.in_stock_rate : 0;
      const rawSize = t.raw_size_formatted || '0 B';
      const lastScraped = t.last_scraped || 'Never';

      return `
        <tr>
          <td>
            <div style="display: flex; align-items: center; gap: 0.6rem;">
              <strong>${escapeHtml(s.name)}</strong>
              ${s.url ? `
                <a href="${escapeHtml(s.url)}" target="_blank" rel="noopener noreferrer" style="color: var(--text-muted);" title="Visit Website">
                  <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
                </a>
              ` : ''}
            </div>
          </td>
          <td>
            <span class="store-tech-pill" style="font-size: 0.72rem;">${escapeHtml(s.engine || s.type)}</span>
          </td>
          <td>
            <span class="scraper-status-pill ${statusBadge}">
              <span class="scraper-status-dot ${statusBadge}"></span>
              <span>${escapeHtml(statusLabel)}</span>
            </span>
          </td>
          <td style="text-align: right; font-family: var(--font-mono); font-weight: 700; color: #00f2fe;">
            ${totalSkusStr}
          </td>
          <td style="text-align: right; font-family: var(--font-mono); font-weight: 600; color: #10b981;">
            ${inStockRate}%
          </td>
          <td style="text-align: right; font-family: var(--font-mono); font-size: 0.82rem; color: var(--text-muted);">
            ${escapeHtml(rawSize)}
          </td>
          <td style="font-family: var(--font-mono); font-size: 0.8rem; color: var(--text-secondary);">
            ${escapeHtml(lastScraped)}
          </td>
          <td style="text-align: center;">
            ${t.total_skus > 0 ? `
              <button class="btn btn-glass btn-sm" onclick="filterByStore('${escapeHtml(s.name)}')">View</button>
            ` : '-'}
          </td>
        </tr>
      `;
    }).join('');
  }
}

async function triggerDatabaseMerge() {
  if (state.isStaticMode || CONFIG.isGitHubPages) {
    showToast('Static Mode (GitHub Pages): Catalog updates run automatically via scheduled GitHub Actions workflow.', 'info');
    return;
  }

  showToast('Initiating Master Dataset compilation and SQLite indexing...', 'info');
  if (elements.recompileTriggerBtn) {
    elements.recompileTriggerBtn.disabled = true;
    elements.recompileTriggerBtn.innerHTML = `
      <svg class="animate-spin" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="animation: spin 1s linear infinite;"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
      Compiling Master DB...
    `;
  }
  if (elements.syncDbBtn) {
    elements.syncDbBtn.disabled = true;
    elements.syncDbBtn.style.opacity = '0.6';
  }

  try {
    const res = await fetchJson('/api/trigger-merge', { method: 'POST' });
    showToast(res.message || 'Master database compiled successfully!', 'success');
    await loadMetrics();
    await loadProducts();
  } catch (err) {
    showToast('Compilation completed or running in background.', 'info');
    await loadMetrics();
  } finally {
    if (elements.recompileTriggerBtn) {
      elements.recompileTriggerBtn.disabled = false;
      elements.recompileTriggerBtn.innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/><path d="M16 21h5v-5"/></svg>
        Re-Index & Compile Master Database
      `;
    }
    if (elements.syncDbBtn) {
      elements.syncDbBtn.disabled = false;
      elements.syncDbBtn.style.opacity = '1';
    }
  }
}

// ============================================================================
// Navigation & Tab Switching
// ============================================================================

function switchTab(tabId) {
  state.activeTab = tabId;

  // Update Tab Buttons
  elements.tabBtns.forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === tabId);
  });

  // Update Content Panels
  elements.tabContents.forEach(content => {
    content.classList.toggle('active', content.id === `tab-${tabId}`);
  });

  // Lazy-load or refresh tab specific data
  if (tabId === 'compare' && !state.compareData) {
    runPriceComparison(CONFIG.defaultCompare);
  } else if (tabId === 'scrapers' && (!state.scrapers || state.scrapers.length === 0)) {
    loadScrapers();
  }
}

function filterByStore(storeName) {
  state.store = storeName;
  if (elements.storeFilter) elements.storeFilter.value = storeName;
  state.page = 1;
  switchTab('catalog');
  loadProducts();
}

function filterByCategory(categoryName) {
  state.category = categoryName;
  if (elements.categoryFilter) elements.categoryFilter.value = categoryName;
  state.page = 1;
  switchTab('catalog');
  loadProducts();
}

function quickCompare(productTitle, category = null) {
  // Extract a clean search token from the product title
  // e.g. "MSI GeForce RTX 4060 Ventus 2X" -> "RTX 4060"
  let token = productTitle;
  const match = productTitle.match(/(RTX\s*\d{4}|RX\s*\d{4}|i[3579]-?\d{4,5}|Ryzen\s*[3579]\s*\d{4}|DDR[45]|1TB|2TB)/i);
  if (match) {
    token = match[0];
  } else {
    token = productTitle.split(' ').slice(0, 3).join(' ');
  }

  switchTab('compare');
  runPriceComparison(token, category);
}

function resetFilters() {
  state.query = '';
  state.store = 'All';
  state.category = 'All';
  state.stock = 'All';
  state.sort = 'price_asc';
  state.page = 1;

  if (elements.catalogSearch) elements.catalogSearch.value = '';
  if (elements.storeFilter) elements.storeFilter.value = 'All';
  if (elements.categoryFilter) elements.categoryFilter.value = 'All';
  if (elements.sortSelect) elements.sortSelect.value = 'price_asc';

  elements.stockToggleBtns.forEach(btn => {
    btn.classList.toggle('active', btn.dataset.val === 'All');
  });

  loadProducts();
  showToast('Filters reset to default view', 'info');
}

// ============================================================================
// Data Export (CSV)
// ============================================================================

function exportToCsv() {
  const items = state.productsData.items || [];
  if (items.length === 0) {
    showToast('No items to export', 'info');
    return;
  }

  const headers = ['Source_Store', 'Category', 'Title', 'Cleaned_Price_LKR', 'Stock_Status', 'Product_URL'];
  const rows = items.map(item => [
    `"${(item.Source_Store || '').replace(/"/g, '""')}"`,
    `"${(item.Category || '').replace(/"/g, '""')}"`,
    `"${(item.Title || '').replace(/"/g, '""')}"`,
    item.Cleaned_Price_LKR || '',
    `"${(item.Stock_Status || '').replace(/"/g, '""')}"`,
    `"${(item.Product_URL || '').replace(/"/g, '""')}"`
  ]);

  const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
  const encodedUri = encodeURI(csvContent);
  const link = document.createElement('a');
  link.setAttribute('href', encodedUri);
  link.setAttribute('download', `sri_lanka_pc_market_${Date.now()}.csv`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  showToast(`Exported ${items.length} products to CSV!`, 'success');
}

// ============================================================================
// Event Listeners & Bootstrapping
// ============================================================================

function setupEventListeners() {
  // Tab buttons
  elements.tabBtns.forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

  // View mode toggles
  if (elements.viewGridBtn) {
    elements.viewGridBtn.addEventListener('click', () => {
      state.viewMode = 'grid';
      elements.viewGridBtn.classList.add('active');
      elements.viewTableBtn.classList.remove('active');
      renderProductGrid(state.productsData.items || []);
    });
  }
  if (elements.viewTableBtn) {
    elements.viewTableBtn.addEventListener('click', () => {
      state.viewMode = 'table';
      elements.viewTableBtn.classList.add('active');
      elements.viewGridBtn.classList.remove('active');
      renderProductTable(state.productsData.items || []);
    });
  }

  // Catalog search input (debounced)
  if (elements.catalogSearch) {
    elements.catalogSearch.addEventListener('input', debounce((e) => {
      state.query = e.target.value;
      state.page = 1;
      loadProducts();
    }, CONFIG.debounceDelay));
  }

  // Dropdown filters
  if (elements.storeFilter) {
    elements.storeFilter.addEventListener('change', (e) => {
      state.store = e.target.value;
      state.page = 1;
      loadProducts();
    });
  }

  if (elements.categoryFilter) {
    elements.categoryFilter.addEventListener('change', (e) => {
      state.category = e.target.value;
      state.page = 1;
      loadProducts();
    });
  }

  if (elements.sortSelect) {
    elements.sortSelect.addEventListener('change', (e) => {
      state.sort = e.target.value;
      state.page = 1;
      loadProducts();
    });
  }

  // Stock status buttons
  elements.stockToggleBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      elements.stockToggleBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.stock = btn.dataset.val;
      state.page = 1;
      loadProducts();
    });
  });

  // Reset button
  if (elements.resetFiltersBtn) {
    elements.resetFiltersBtn.addEventListener('click', resetFilters);
  }

  // Export CSV
  if (elements.exportCsvBtn) {
    elements.exportCsvBtn.addEventListener('click', exportToCsv);
  }

  // Compare input & quick chips
  if (elements.compareSubmitBtn) {
    elements.compareSubmitBtn.addEventListener('click', () => {
      runPriceComparison(elements.compareInput.value);
    });
  }
  if (elements.compareInput) {
    elements.compareInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        runPriceComparison(elements.compareInput.value);
      }
    });
  }

  // Recompile Database button
  if (elements.recompileTriggerBtn) {
    elements.recompileTriggerBtn.addEventListener('click', triggerDatabaseMerge);
  }
  if (elements.syncDbBtn) {
    elements.syncDbBtn.addEventListener('click', triggerDatabaseMerge);
  }

  // Scraper Fleet Filters & Search
  if (elements.scraperSearch) {
    elements.scraperSearch.addEventListener('input', debounce((e) => {
      state.scraperQuery = e.target.value;
      renderScrapersHealthDashboard();
    }, 200));
  }

  if (elements.scraperFilterPills) {
    elements.scraperFilterPills.forEach(pill => {
      pill.addEventListener('click', () => {
        elements.scraperFilterPills.forEach(p => p.classList.remove('active'));
        pill.classList.add('active');
        state.scraperFilter = pill.dataset.filter || 'all';
        renderScrapersHealthDashboard();
      });
    });
  }

  // Keyboard Shortcuts: '/' focuses search, 'Esc' closes modals, '1'-'5' switches tabs
  window.addEventListener('keydown', (e) => {
    if (e.key === '/' && document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'SELECT') {
      e.preventDefault();
      if (state.activeTab === 'compare') {
        elements.compareInput?.focus();
      } else {
        elements.catalogSearch?.focus();
      }
    } else if (e.key === 'Escape') {
      if (elements.productModal?.classList.contains('active')) {
        elements.productModal.classList.remove('active');
      }
    } else if (e.altKey && ['1', '2', '3', '4', '5'].includes(e.key)) {
      e.preventDefault();
      const tabMap = { '1': 'catalog', '2': 'compare', '3': 'stores', '4': 'categories', '5': 'scrapers' };
      switchTab(tabMap[e.key]);
    }
  });
}

// Quick chip click handler
window.setCompareChip = function(model) {
  runPriceComparison(model);
};

window.quickCompare = quickCompare;
window.filterByStore = filterByStore;
window.filterByCategory = filterByCategory;
window.resetFilters = resetFilters;
window.goToPage = goToPage;

// Application Initialization
async function initApp() {
  setupEventListeners();
  await loadMetrics();
  await loadProducts();
}

document.addEventListener('DOMContentLoaded', initApp);
