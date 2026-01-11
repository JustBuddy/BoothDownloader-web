import os
import json
import glob
import re
import time
import sys
import binascii
from urllib.parse import quote, unquote
from concurrent.futures import ThreadPoolExecutor, as_completed
from deep_translator import GoogleTranslator
from PIL import Image

# Configuration
ROOT_FOLDER = "BoothDownloaderOut"
OUTPUT_FILE = "asset_library.html"
DATABASE_JS_FILE = "web_data/database.js"
CACHE_FILE = "web_data/cache/translation_cache.json"
DESC_CACHE_FILE = "web_data/cache/descriptions_cache.json"
THUMB_META_FILE = "web_data/cache/thumbnail_meta.json"
GLOBAL_META_FILE = "web_data/cache/global_metadata.json"
FILTER_FILE = "web_data/filters.json"
L18N_FILE = "web_data/l18n.json"
SKIP_TRANSLATION = False
MAX_WORKERS = 5

# Thumbnail Optimization
OPTIMIZE_THUMBNAILS = True
THUMBNAIL_SIZE = (256, 256)
IMG_OUT_DIR = "web_data/img"

# Shared Body Groups (Case-insensitive)
BODY_GROUPS = ["MameFriends", "MaruBody", "+Head", "Plushead", "Bodyset2"]

# Keywords that should NEVER be considered an avatar name
FORBIDDEN_NAMES = {
    "vrchat", "vrc", "unity", "fbx", "avatar", "3d", "model", "quest", "pc",
    "original", "character", "boy", "girl", "boy's", "girl's", "android", "human",
    "unlisted", "adult", "preview", "cloth", "clothing", "accessory", "hair",
    "eye", "texture", "physbone", "blendshape", "blender",
    "mobile", "compatible", "version", "support", "sdk3", "prefab", "physbones",
    "fullset", "edition", "sf", "3dcg", "vrm", "mmd", "body", "set"
}

print(f"--- Starting Library Generation ---")

if not os.path.exists("web_data"): os.makedirs("web_data")
if not os.path.exists("web_data/cache"): os.makedirs("web_data/cache")
if OPTIMIZE_THUMBNAILS and not os.path.exists(IMG_OUT_DIR): os.makedirs(IMG_OUT_DIR)

# Load External Filters
ADULT_KEYWORDS = []
if os.path.exists(FILTER_FILE):
    try:
        with open(FILTER_FILE, 'r', encoding='utf-8') as f:
            ext_data = json.load(f)
            if isinstance(ext_data, list): ADULT_KEYWORDS.extend(ext_data)
    except: pass
ADULT_KEYWORDS = list(set(ADULT_KEYWORDS))

# Load Caches
translation_cache = {}
if os.path.exists(CACHE_FILE):
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f: translation_cache = json.load(f)
    except: pass

description_cache = {}
if os.path.exists(DESC_CACHE_FILE):
    try:
        with open(DESC_CACHE_FILE, 'r', encoding='utf-8') as f: description_cache = json.load(f)
    except: pass

thumb_meta = {}
if os.path.exists(THUMB_META_FILE):
    try:
        with open(THUMB_META_FILE, 'r', encoding='utf-8') as f: thumb_meta = json.load(f)
    except: pass

global_meta = {}
if os.path.exists(GLOBAL_META_FILE):
    try:
        with open(GLOBAL_META_FILE, 'r', encoding='utf-8') as f: global_meta = json.load(f)
    except: pass

# Load existing database for incremental updates
existing_database = {}
if os.path.exists(DATABASE_JS_FILE):
    try:
        with open(DATABASE_JS_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
            json_str = content.replace("window.BOOTH_DATABASE = ", "").rstrip(";")
            db_list = json.loads(json_str)
            existing_database = {item['id']: item for item in db_list}
    except: pass

# Load L18N Data
l18n_data = {"languages": {"en": "English"}, "translations": {"en": {}}}
if os.path.exists(L18N_FILE):
    try:
        with open(L18N_FILE, 'r', encoding='utf-8') as f: l18n_data = json.load(f)
    except Exception as e: print(f"[Error] Could not load l18n.json: {e}")

def contains_japanese(text): return bool(re.search(r'[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]', str(text)))

def translate_single_text(text):
    if not text or not contains_japanese(text) or SKIP_TRANSLATION: return text
    try: return GoogleTranslator(source='auto', target='en').translate(text)
    except: return text

def print_progress(current, total, label="Progress"):
    percent = (current / total) * 100
    if sys.stdout.isatty():
        bar_length = 30
        done = int(bar_length * current / total)
        bar = "█" * done + "░" * (bar_length - done)
        sys.stdout.write(f"\r[{label}] |{bar}| {percent:.1f}% ({current}/{total}) ")
        sys.stdout.flush()
        if current == total: sys.stdout.write("\n")
    else:
        if current == 1 or current == total or current % max(1, (total // 20)) == 0:
            print(f"[{label}] {percent:.1f}% ({current}/{total})")

def bulk_translate_short_terms(text_list):
    if SKIP_TRANSLATION: return
    japanese_strings = list(set(str(t).strip() for t in text_list if t and contains_japanese(t) and len(str(t)) < 500))
    new_strings = [t for t in japanese_strings if t not in translation_cache]
    if not new_strings: return
    total = len(new_strings)
    print(f"[Translate] Queuing {total} short terms...")
    def translate_task(item):
        try: return item, GoogleTranslator(source='auto', target='en').translate(item)
        except: return item, None
    completed = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_term = {executor.submit(translate_task, term): term for term in new_strings}
        for future in as_completed(future_to_term):
            original, translated = future.result()
            if translated: translation_cache[original] = translated
            completed += 1
            print_progress(completed, total, "Translate")
    with open(CACHE_FILE, 'w', encoding='utf-8') as f: json.dump(translation_cache, f, ensure_ascii=False, indent=2)

def calculate_crc32(filepath):
    buf = open(filepath, 'rb').read()
    return "%08X" % (binascii.crc32(buf) & 0xFFFFFFFF)

def get_optimized_thumb(asset_id, original_path, crc):
    if not original_path or not os.path.exists(original_path): return ""
    if not original_path.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')): return quote(original_path.replace('\\', '/'))
    thumb_name = f"{asset_id}_thumb.webp"
    thumb_path = os.path.join(IMG_OUT_DIR, thumb_name)
    try:
        with Image.open(original_path) as img:
            width, height = img.size
            if width != height:
                min_dim = min(width, height)
                img = img.crop(((width-min_dim)/2, (height-min_dim)/2, (width+min_dim)/2, (height+min_dim)/2))
            img.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
            img.save(thumb_path, "WEBP", optimize=True, quality=80)
            thumb_meta[asset_id] = crc
    except: return quote(original_path.replace('\\', '/'))
    return quote(thumb_path.replace('\\', '/'))

HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Booth Asset Library</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="web_data/style.css" />
    <style>
        #appLoader { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: #0b0b0d; display: flex; flex-direction: column; align-items: center; justify-content: center; z-index: 9999; transition: opacity 0.6s ease; }
        .spinner { width: 50px; height: 50px; border: 3px solid rgba(253, 218, 13, 0.1); border-radius: 50%; border-top-color: #FDDA0D; animation: spin 1s ease-in-out infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }
        #mainWrapper { opacity: 0; transition: opacity 0.8s ease; visibility: hidden; }
        body.loaded #mainWrapper { opacity: 1; visibility: visible; }
        body.loaded #appLoader { opacity: 0; pointer-events: none; }
        .asset-link-view-all { display: flex; align-items: center; justify-content: center; background: rgba(253, 218, 13, 0.05); border: 1px dashed #FDDA0D; border-radius: 6px; text-decoration: none; transition: 0.2s; padding: 8px; height: 46px; box-sizing: border-box; }
        .asset-link-view-all:hover { background: rgba(253, 218, 13, 0.15); transform: translateY(-2px); }
        .asset-link-view-all span { color: #FDDA0D; font-size: 0.65rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.5px; }
        .asset-link-grid { align-items: stretch; }
        .asset .stats { display: flex; flex-wrap: wrap; gap: 4px 8px; height: auto; min-height: 1.2rem; }
        .asset .stats span { white-space: nowrap; }
    </style>
</head>
<body>
    <div id="appLoader"><div class="spinner"></div></div>
    <div id="mainWrapper">
        <div id="menuPerimeter" onclick="toggleMenu(event, true)"></div>
        <nav class="top-nav">
            <div class="nav-logo" data-i18n="navTitle">Booth Asset Library</div>
            <div class="search-container">
                <input type="text" id="searchInput" class="search-input" placeholder="..." onkeyup="handleSearchInput()">
                <button id="clearSearch" class="clear-search" onclick="clearSearch()">×</button>
            </div>
            <button id="toggleBtn" class="nav-btn" onclick="toggleMenu(event)" data-i18n="optionsBtn">Options ⚙</button>
        </nav>
        <div id="flyoutMenu" class="flyout-menu">
            <div class="setting-group"><span class="setting-label" data-i18n="labelLanguage">Language</span>
                <select id="langSelect" onchange="updateLanguage(this.value)"></select>
            </div>
            <div class="setting-group"><span class="setting-label" data-i18n="labelType">Item Type</span>
                <select id="typeFilter" onchange="applyFilters(true)">
                    <option value="all" data-i18n="optTypeAll">All Items</option><option value="avatar" data-i18n="optTypeAvatar">Avatars</option><option value="asset" data-i18n="optTypeAsset">Assets</option>
                </select>
            </div>
            <div class="setting-group"><span class="setting-label" data-i18n="labelSort">Sort Order</span>
                <select id="sortOrder" onchange="sortAssets(true)">
                    <option value="id" data-i18n="optId">Folder ID</option><option value="new" data-i18n="optNew">Recently Added</option><option value="name" data-i18n="optName">Alphabetical</option><option value="rel" data-i18n="optRel">Relevance</option><option value="size" data-i18n="optSize">Total Size</option>
                </select>
            </div>
            <div class="setting-group"><span class="setting-label" data-i18n="labelAdult">Adult Filter</span>
                <select id="adultFilter" onchange="applyFilters(true)">
                    <option value="all" data-i18n="optAll">Show All</option><option value="hide" data-i18n="optHide">Hide Adult</option><option value="only" data-i18n="optOnly">Only Adult</option>
                </select>
            </div>
            <div class="setting-group"><span class="setting-label" data-i18n="labelWidth">Card Width</span><input type="range" id="gridRange" min="160" max="400" step="10" value="220" oninput="updateGrid(this.value)"></div>
            <div class="setting-group">
                <label style="display:flex; gap:10px; cursor:pointer; font-size:0.9rem; margin-bottom:10px;"><input type="checkbox" id="blurToggle" onchange="updateBlur(this.checked)"> <span data-i18n="optBlur">Disable Blur</span></label>
                <label style="display:flex; gap:10px; cursor:pointer; font-size:0.9rem; margin-bottom:10px;"><input type="checkbox" id="hideIdToggle" onchange="updateIdVisibility(this.checked)"> <span data-i18n="optHideIds">Hide IDs</span></label>
                <label style="display:flex; gap:10px; cursor:pointer; font-size:0.9rem;"><input type="checkbox" id="translateToggle" onchange="updateTranslationVisibility(this.checked)"> <span data-i18n="optTranslate">English Titles</span></label>
            </div>
            <div class="stats-footer">
                <div class="stat-row"><span data-i18n="statItems">Items</span>: <b id="statCount">0</b></div>
                <div class="stat-row"><span data-i18n="statSize">Binary Size</span>: <b id="statSize">0B</b></div>
                <div class="stat-row"><span data-i18n="statImgSize">Asset Graphics</span>: <b id="statImgSize">0B</b></div>
                <div class="stat-row"><span data-i18n="statSpent">Estimated Investment</span>: <b id="statSpent">0</b></div>
                <div class="stat-row"><span data-i18n="statUpdated">Last Updated</span>: <b id="statDate">N/A</b></div>
                <span class="setting-label" style="margin-top:10px;" data-i18n="labelTopTags">Top Tags</span>
                <div id="commonTags" class="common-tags-grid"></div>
            </div>
        </div>
        <div class="container"><ul id="assetList"></ul><div id="filterNotice"></div></div>
    </div>
    <div id="detailModal" class="modal" onclick="closeModal()">
        <div class="modal-card" onclick="event.stopPropagation()">
            <div class="modal-carousel" id="modalCarouselContainer">
                <button id="carouselPrev" class="carousel-btn btn-prev" onclick="carouselNext(-1)">❮</button>
                <div id="carouselBlurTrack" class="carousel-blur-track"></div>
                <div id="carouselTrack" class="carousel-track"></div>
                <button id="carouselNext" class="carousel-btn btn-next" onclick="carouselNext(1)">❯</button>
                <div id="carouselDots" class="carousel-dots"></div>
            </div>
            <div class="modal-info">
                <div class="modal-header-fixed">
                    <div id="modalName" class="modal-name"></div>
                    <div id="modalSubtitle" class="modal-subtitle"></div>
                    <div id="delistedWarn" class="delisted-warning" data-i18n-html="warnDelisted"></div>
                </div>
                <div class="modal-tabs">
                    <button id="tab-details" class="tab-btn active" onclick="switchTab('details')" data-i18n="btnDetails">Details</button>
                    <button id="tab-files" class="tab-btn" onclick="switchTab('files')" data-i18n="labelBinary">Files</button>
                    <button id="tab-description" class="tab-btn" onclick="switchTab('description')" data-i18n="btnDesc">Description</button>
                </div>
                <div class="tab-content-container">
                    <div id="pane-details" class="tab-pane active">
                        <span class="modal-section-title">Pricing & Meta</span>
                        <div class="modal-meta-row" id="modalMeta"></div>
                        <span class="modal-section-title" style="margin-top:20px;">Tags</span>
                        <div id="modalTags" style="display:flex; flex-wrap:wrap; gap:6px;"></div>
                        <div id="relSection" style="display:none; margin-top:20px;">
                            <span class="modal-section-title" id="relTitle">Relationships</span>
                            <div id="relationshipContainer" class="asset-link-grid"></div>
                        </div>
                    </div>
                    <div id="pane-files" class="tab-pane">
                        <span class="modal-section-title">Package Contents</span>
                        <ul id="fileList" class="file-list"></ul>
                    </div>
                    <div id="pane-description" class="tab-pane">
                        <div id="modalDesc" class="desc-content"></div>
                    </div>
                </div>
                <div class="modal-footer">
                    <div id="modalIdDisp" class="modal-id-display"></div>
                    <div class="modal-actions">
                        <a id="openVrcAvatarLink" href="" class="discrete-link" target="_blank" style="display:none;"><span data-i18n="footVrcAvatar">👤 Public Avatar</span></a>
                        <a id="openVrcWorldLink" href="" class="discrete-link" target="_blank" style="display:none;"><span data-i18n="footVrcWorld">🌐 Public World</span></a>
                        <a id="openBoothLink" href="" class="discrete-link" target="_blank"><span data-i18n="footBooth">🛒 Booth</span></a>
                        <a id="openFolderLink" href="" class="discrete-link" target="_blank"><span data-i18n="footFolder">📂 Folder</span></a>
                    </div>
                </div>
            </div>
        </div>
    </div>
    <div id="fullscreenImageViewer" class="fullscreen-viewer" onclick="closeFullscreenImage()">
        <img id="fullscreenImage" src="" alt="Full size preview">
    </div>
    <!-- Load local database script -->
    <script src="web_data/database.js"></script>
    <script>
        const l18n = __L18N_INJECT_POINT__;
        const translations = l18n.translations;
        const database = window.BOOTH_DATABASE || [];
        let currentCarouselIndex = 0, currentImages = [];
        const baseTitle = "Booth Asset Library";
        const getLS = (k, def) => localStorage.getItem(k) || def;
        const state = { gridSize: getLS('gridSize', '220'), disableBlur: getLS('disableBlur', 'false') === 'true', sortOrder: getLS('sortOrder', 'id'), adultFilter: getLS('adultFilter', 'all'), typeFilter: getLS('typeFilter', 'all'), hideIds: getLS('hideIds', 'false') === 'true', lang: getLS('lang', 'en'), showTrans: getLS('showTrans', 'true') === 'true' };
        const observerOptions = { root: null, rootMargin: '1000px', threshold: 0.01 };
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const el = entry.target;
                    const img = el.querySelector('.image-thumbnail');
                    const glow = el.querySelector('.image-backglow');
                    if (img && !img.src) img.src = el.dataset.img;
                    if (glow && !glow.src) glow.src = el.dataset.img;
                    el.classList.add('is-visible');
                    observer.unobserve(el);
                }
            });
        }, observerOptions);
        function init() {
            renderLibrary();
            const langSel = document.getElementById('langSelect');
            langSel.innerHTML = "";
            Object.entries(l18n.languages).forEach(([code, name]) => {
                const opt = document.createElement('option');
                opt.value = code; opt.innerText = name;
                langSel.appendChild(opt);
            });
            updateLanguage(state.lang); updateGrid(state.gridSize); updateBlur(state.disableBlur); updateIdVisibility(state.hideIds); updateTranslationVisibility(state.showTrans);
            document.getElementById('gridRange').value = state.gridSize; document.getElementById('blurToggle').checked = state.disableBlur; document.getElementById('sortOrder').value = state.sortOrder;
            document.getElementById('adultFilter').value = state.adultFilter; document.getElementById('typeFilter').value = state.typeFilter; document.getElementById('hideIdToggle').checked = state.hideIds; document.getElementById('translateToggle').checked = state.showTrans;
            calculateStats();
            const urlParams = new URLSearchParams(window.location.search);
            const queryParam = urlParams.get('q');
            if (queryParam) document.getElementById("searchInput").value = queryParam;
            handleSearchInput(); sortAssets();
            const targetId = urlParams.get('id');
            if (targetId) openDetails(targetId, true);
            setTimeout(() => { document.body.classList.add('loaded'); }, 50);
        }
        function calculateStats() {
            let totalBinaryBytes = 0, totalImageBytes = 0;
            const tagCounts = {}, spent = {};
            database.forEach(item => {
                totalBinaryBytes += item.bytes;
                totalImageBytes += item.imgBytes;
                item.tags.forEach(t => tagCounts[t] = (tagCounts[t] || 0) + 1);
                if (item.priceValue > 0 && item.priceCurrency) spent[item.priceCurrency] = (spent[item.priceCurrency] || 0) + item.priceValue;
            });
            const topTags = Object.entries(tagCounts).sort((a,b) => b[1] - a[1]).slice(0, 10);
            document.getElementById('commonTags').innerHTML = topTags.map(([tag]) => `<span class="tag-pill clickable" onclick="tagSearch('${tag.replace(/'/g, "\\\\'")}')">${tag}</span>`).join('');
            document.getElementById('statCount').innerText = database.length;
            document.getElementById('statSize').innerText = formatBytes(totalBinaryBytes);
            document.getElementById('statImgSize').innerText = formatBytes(totalImageBytes);
            document.getElementById('statSpent').innerText = Object.entries(spent).map(([cur, val]) => val.toLocaleString() + " " + cur).join(" / ") || "0";
            document.getElementById('statDate').innerText = new Date().toLocaleDateString();
        }
        function renderLibrary() {
            const list = document.getElementById('assetList');
            list.innerHTML = database.map(item => {
                const isAdult = item.adult ? 'adult-content' : '';
                return `<li class="asset" id="asset-${item.id}" onclick="openDetails('${item.id}')" data-id="${item.id}">
                    <div class="skeleton-shimmer"></div>
                    <div class="image-container">
                        <div class="asset-id-tag">#${item.id}</div>
                        ${item.adult ? '<div class="adult-badge">18+</div>' : ''}
                        <img class="image-thumbnail ${isAdult}" loading="lazy">
                    </div>
                    <img class="image-backglow"><div class="content">
                        <div class="name"><span class="name-primary"></span></div>
                        <div class="author-label">by <b class="author-primary"></b></div>
                        <div class="stats"></div>
                        <div class="tag-row"></div>
                    </div>
                </li>`;
            }).join('');
            database.forEach(item => {
                const el = document.getElementById('asset-' + item.id);
                el.dataset.img = item.gridThumb;
                observer.observe(el);
            });
        }
        function formatBytes(bytes) {
            if (bytes === 0) return '0 B';
            const k = 1024, sizes = ['B', 'KB', 'MB', 'GB', 'TB'], i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        }
        function updateLanguage(lang) { 
            state.lang = lang; localStorage.setItem('lang', lang); 
            document.getElementById('langSelect').value = lang; 
            const t = translations[lang] || translations['en']; 
            if (!t) return;
            document.querySelectorAll('[data-i18n]').forEach(el => { el.innerText = t[el.dataset.i18n]; }); 
            document.querySelectorAll('[data-i18n-html]').forEach(el => { el.innerHTML = t[el.dataset.i18nHtml]; });
            applyFilters(); 
        }
        function toggleMenu(e, forceClose = false) { if(e) e.stopPropagation(); const menu = document.getElementById('flyoutMenu'), btn = document.getElementById('toggleBtn'), perim = document.getElementById('menuPerimeter'); const open = !forceClose && !menu.classList.contains('open'); menu.classList.toggle('open', open); btn.classList.toggle('active', open); perim.style.display = open ? 'block' : 'none'; }
        function updateGrid(v) { document.documentElement.style.setProperty('--grid-size', v + 'px'); localStorage.setItem('gridSize', v); }
        function updateBlur(v) { document.body.classList.toggle('no-blur', v); localStorage.setItem('disableBlur', v); }
        function updateIdVisibility(v) { document.body.classList.toggle('hide-ids', v); localStorage.setItem('hideIds', v); }
        function updateTranslationVisibility(v) { 
            state.showTrans = v; localStorage.setItem('showTrans', v);
            const t = translations[state.lang] || translations['en'];
            database.forEach(item => {
                const el = document.getElementById('asset-' + item.id);
                if (!el) return;
                el.querySelector('.name-primary').innerText = (v && item.nameTrans) ? item.nameTrans : item.nameOrig;
                el.querySelector('.author-primary').innerText = (v && item.authorTrans) ? item.authorTrans : item.authorOrig;
                el.querySelector('.tag-row').innerHTML = item.tags.slice(0, 12).map(tg => `<span class="tag-pill">${tg}</span>`).join('');
                let statsHtml = item.bytes > 0 ? `<span>${formatBytes(item.bytes)}</span>` : "";
                if (item.fileCount > 0) statsHtml += `<span>${item.fileCount} ${item.fileCount === 1 ? t.fileSingular : t.filePlural}</span>`;
                if (item.links.length > 0) statsHtml += `<span>${item.links.length} ${item.links.length === 1 ? t.matchSingular : t.matchPlural}</span>`;
                el.querySelector('.stats').innerHTML = statsHtml;
            });
            const modal = document.getElementById('detailModal');
            if (modal.classList.contains('active')) {
                const id = new URLSearchParams(window.location.search).get('id');
                const item = database.find(d => d.id === id);
                if (item) document.getElementById('modalDesc').innerHTML = formatDescription((v && item.descTrans) ? item.descTrans : item.descOrig);
            }
        }
        function formatDescription(text) {
            if (!text) return "";
            const urlRegex = /(https?:\\/\\/[^\\s\\n]+)/g;
            return text.replace(urlRegex, (url) => `<a href="${url}" target="_blank" onclick="event.stopPropagation()">${url}</a>`);
        }
        function handleSearchInput() { 
            const query = document.getElementById("searchInput").value.toLowerCase();
            const newUrl = new URL(window.location);
            if (query) newUrl.searchParams.set('q', query); else newUrl.searchParams.delete('q');
            window.history.replaceState({}, '', newUrl);
            applyFilters(); 
        }
        function clearSearch() { const i = document.getElementById("searchInput"); i.value = ""; handleSearchInput(); i.focus(); }
        function tagSearch(query, isAuthor = false) {
            const s = document.getElementById("searchInput");
            s.value = isAuthor ? `author:${query}` : query;
            const newUrl = new URL(window.location);
            newUrl.searchParams.set('q', s.value);
            window.history.pushState({}, '', newUrl);
            closeModal();
            handleSearchInput();
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }
        function applyFilters(save = false) {
            let query = document.getElementById("searchInput").value.toLowerCase();
            const mode = document.getElementById("adultFilter").value;
            const typeMode = document.getElementById("typeFilter").value;
            const t = translations[state.lang] || translations['en'];
            if(save) { state.adultFilter = mode; state.typeFilter = typeMode; localStorage.setItem('adultFilter', mode); localStorage.setItem('typeFilter', typeMode); }
            let count = 0, hiddenCount = 0;
            const isAuthorSearch = query.startsWith('author:'), isRelSearch = query.startsWith('rel:'), isTypeSearch = query.startsWith('type:');
            const authorQuery = isAuthorSearch ? query.replace('author:', '').trim() : '';
            const relQuery = isRelSearch ? query.replace('rel:', '').trim() : '';
            const typeSearchVal = isTypeSearch ? query.replace('type:', '').trim() : '';
            database.forEach(item => {
                const el = document.getElementById('asset-' + item.id);
                const adultMatch = (mode === 'all') || (mode === 'hide' && !item.adult) || (mode === 'only' && item.adult);
                const typeMatch = (typeMode === 'all') || (typeMode === 'avatar' && item.isAvatar) || (typeMode === 'asset' && !item.isAvatar);
                let searchMatch = false;
                if (isRelSearch) searchMatch = (item.id === relQuery) || item.links.includes(relQuery);
                else if (isAuthorSearch) searchMatch = item.authorOrig.toLowerCase().includes(authorQuery) || item.authorTrans.toLowerCase().includes(authorQuery);
                else if (isTypeSearch) searchMatch = (typeSearchVal === 'avatar' ? item.isAvatar : !item.isAvatar);
                else searchMatch = item.searchBlob.includes(query);
                if (searchMatch && adultMatch && typeMatch) { el.style.display = ""; count++; }
                else { el.style.display = "none"; if (searchMatch) hiddenCount++; }
            });
            document.getElementById("searchInput").placeholder = t.searchPre + count + t.searchSuf;
            const notice = document.getElementById("filterNotice");
            if (hiddenCount > 0) { notice.innerText = t.hiddenResults.replace('{n}', hiddenCount).trim(); notice.style.display = "flex"; } else { notice.style.display = "none"; }
        }
        function sortAssets(save = false) {
            const list = document.getElementById('assetList'), order = document.getElementById('sortOrder').value;
            if(save) localStorage.setItem('sortOrder', order);
            const sorted = [...database].sort((a, b) => {
                if (order === 'id') return isNaN(a.id) || isNaN(b.id) ? a.id.localeCompare(b.id) : parseInt(a.id) - parseInt(b.id);
                if (order === 'new') return b.timestamp - a.timestamp;
                if (order === 'rel') return b.wishCount - a.wishCount;
                if (order === 'size') return b.bytes - a.bytes;
                const nA = (state.showTrans && a.nameTrans) ? a.nameTrans : a.nameOrig;
                const nB = (state.showTrans && b.nameTrans) ? b.nameTrans : b.nameOrig;
                return nA.toLowerCase().localeCompare(nB.toLowerCase());
            });
            sorted.forEach(item => list.appendChild(document.getElementById('asset-' + item.id)));
        }
        function openDetails(id, skipHistory = false) {
            const item = database.find(d => d.id === id), t = translations[state.lang] || translations['en'];
            if(!item) return;
            const track = document.getElementById("carouselTrack"), blurTrack = document.getElementById("carouselBlurTrack");
            track.style.transition = 'none'; blurTrack.style.transition = 'none';
            track.style.transform = 'translateX(0)'; blurTrack.style.transform = 'translateX(0)';
            track.innerHTML = ""; blurTrack.innerHTML = "";
            switchTab('details'); currentCarouselIndex = 0; currentImages = item.allImages; 
            const mainSlides = currentImages.map(img => `<div class="carousel-slide" onclick="openFullscreenImage('${img}')"><img src="${img}"></div>`).join('');
            const blurSlides = currentImages.map(img => `<div class="carousel-blur-slide"><img src="${img}"></div>`).join('');
            track.innerHTML = mainSlides; blurTrack.innerHTML = blurSlides;
            updateCarousel(true);
            const displayTitle = (state.showTrans && item.nameTrans) ? item.nameTrans : item.nameOrig;
            const authorDisp = (state.showTrans && item.authorTrans) ? item.authorTrans : item.authorOrig;
            document.getElementById("modalName").innerText = displayTitle;
            document.getElementById("modalSubtitle").innerHTML = `by <a class="modal-author-link" onclick="tagSearch('${item.authorOrig.replace(/'/g, "\\\\'")}', true)"><b>${authorDisp}</b></a>`;
            let metaHtml = (item.nameTrans && state.showTrans) ? `<div class="meta-pill">${item.nameOrig}</div>` : "";
            metaHtml += `<div class="meta-pill">${item.priceCurrency} ${item.priceValue.toLocaleString()}</div>`;
            document.getElementById("modalMeta").innerHTML = metaHtml;
            document.getElementById("modalIdDisp").innerText = "#" + item.id;
            document.getElementById("openFolderLink").href = item.folder;
            document.getElementById("openBoothLink").style.display = item.boothUrl ? "block" : "none";
            document.getElementById("openBoothLink").href = item.boothUrl;
            document.getElementById("delistedWarn").style.display = item.limited ? 'block' : 'none';
            document.getElementById("openVrcAvatarLink").style.display = item.vrcAvatarLink ? "block" : "none";
            document.getElementById("openVrcAvatarLink").href = item.vrcAvatarLink || "";
            document.getElementById("openVrcWorldLink").style.display = item.vrcWorldLink ? "block" : "none";
            document.getElementById("openVrcWorldLink").href = item.vrcWorldLink || "";
            document.getElementById("modalTags").innerHTML = item.tags.map(tg => `<span class="tag-pill clickable" onclick="tagSearch('${tg.replace(/'/g, "\\\\'")}')">${tg}</span>`).join('');
            document.getElementById("modalDesc").innerHTML = formatDescription((state.showTrans && item.descTrans) ? item.descTrans : item.descOrig);
            document.getElementById("tab-description").style.display = (item.descOrig) ? "block" : "none";
            const relSection = document.getElementById("relSection");
            if (item.links.length > 0) {
                relSection.style.display = "block";
                document.getElementById("relTitle").innerText = item.isAvatar ? t.labelComp : t.labelDesigned;
                let relHtml = item.links.map(linkId => {
                    const target = database.find(d => d.id === linkId);
                    if (!target) return "";
                    const n = (state.showTrans && target.nameTrans) ? target.nameTrans : target.nameOrig;
                    return `<a href="#" class="asset-link-item" onclick="event.preventDefault(); openDetails('${linkId}')">
                        <img class="asset-link-thumb" src="${target.gridThumb}">
                        <span class="asset-link-name">${n}</span>
                    </a>`;
                }).join('') + `<a href="#" class="asset-link-view-all" onclick="event.preventDefault(); tagSearch('rel:${item.id}')"><span>${t.labelViewRel}</span></a>`;
                document.getElementById("relationshipContainer").innerHTML = relHtml;
            } else relSection.style.display = "none";
            document.getElementById("fileList").innerHTML = item.files.sort((a,b) => b.name.localeCompare(a.name, undefined, {numeric:true})).map(f => `
                <li class="file-item"><a class="file-link" href="${f.path}" target="_blank">${f.name}</a><span style="color:#666; font-size:0.7rem;">${f.size}</span></li>`).join('');
            const m = document.getElementById("detailModal"); m.classList.add('visible'); setTimeout(() => m.classList.add('active'), 10);
            document.title = baseTitle + " - #" + id;
            if (!skipHistory) { const newUrl = new URL(window.location); newUrl.searchParams.set('id', id); window.history.pushState({id: id}, '', newUrl); }
        }
        function switchTab(tabId) {
            document.querySelectorAll('.tab-pane, .tab-btn').forEach(el => el.classList.remove('active'));
            document.getElementById('pane-' + tabId).classList.add('active');
            document.getElementById('tab-' + tabId).classList.add('active');
        }
        function carouselNext(dir) { if (currentImages.length <= 1) return; currentCarouselIndex = (currentCarouselIndex + dir + currentImages.length) % currentImages.length; updateCarousel(); }
        function updateCarousel(instant = false) {
            const track = document.getElementById("carouselTrack"), blurTrack = document.getElementById("carouselBlurTrack"), dots = document.getElementById("carouselDots");
            const trans = instant ? 'none' : 'transform 0.3s cubic-bezier(0.4, 0, 0.2, 1)';
            track.style.transition = trans; blurTrack.style.transition = trans;
            const offset = `translateX(-${currentCarouselIndex * 100}%)`;
            track.style.transform = offset; blurTrack.style.transform = offset;
            const showUI = currentImages.length > 1;
            document.getElementById("carouselPrev").style.display = showUI ? "block" : "none";
            document.getElementById("carouselNext").style.display = showUI ? "block" : "none";
            dots.style.display = showUI ? "flex" : "none";
            if (showUI) { dots.innerHTML = currentImages.map((_, i) => `<div class="dot ${i === currentCarouselIndex ? 'active' : ''}" onclick="currentCarouselIndex=${i}; updateCarousel()"></div>`).join(''); }
        }
        function openFullscreenImage(src) {
            const viewer = document.getElementById('fullscreenImageViewer');
            const img = document.getElementById('fullscreenImage');
            img.src = src;
            viewer.classList.add('visible');
            requestAnimationFrame(() => {
                requestAnimationFrame(() => {
                    viewer.classList.add('active');
                });
            });
        }
        function closeFullscreenImage() {
            const viewer = document.getElementById('fullscreenImageViewer');
            viewer.classList.remove('active');
            setTimeout(() => {
                if(!viewer.classList.contains('active')) viewer.classList.remove('visible');
            }, 400);
        }
        function closeModal(skipHistory = false) { 
            const m = document.getElementById("detailModal"); m.classList.remove('active'); setTimeout(() => { if(!m.classList.contains('active')) m.classList.remove('visible'); }, 300);
            document.title = baseTitle; if (!skipHistory) { const newUrl = new URL(window.location); newUrl.searchParams.delete('id'); window.history.pushState({}, '', newUrl); }
        }
        window.onpopstate = () => { const p = new URLSearchParams(window.location.search); if (p.get('id')) openDetails(p.get('id'), true); else closeModal(true); };
        document.addEventListener('keydown', e => { if(e.key === "Escape") { if(document.getElementById('fullscreenImageViewer').classList.contains('active')) closeFullscreenImage(); else { closeModal(); toggleMenu(null, true); } } if(e.key === "ArrowRight") carouselNext(1); if(e.key === "ArrowLeft") carouselNext(-1); });
        init();
    </script>
</body>
</html>
"""

def get_readable_size(size_bytes):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024: return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f}TB"

def get_dir_data(binary_folder):
    files, total_size = [], 0
    if os.path.exists(binary_folder):
        for root, _, filenames in os.walk(binary_folder):
            for f in filenames:
                fp = os.path.join(root, f)
                size = os.path.getsize(fp)
                total_size += size
                rel = os.path.relpath(fp, start=os.getcwd()).replace('\\', '/')
                files.append({"name": f, "path": quote(rel), "size": get_readable_size(size)})
    return files, total_size

def get_image_folder_size(folder_path):
    total_size = 0
    for f in os.listdir(folder_path):
        if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif')): total_size += os.path.getsize(os.path.join(folder_path, f))
    return total_size

def is_adult_content(text): return bool(re.search("|".join(ADULT_KEYWORDS), str(text), re.IGNORECASE))

def get_all_local_images(folder_path, web_urls=None):
    if web_urls is None: web_urls = []
    local_files = [f for f in os.listdir(folder_path) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif'))]
    ordered_images = []
    for url in web_urls:
        tokens = re.findall(r'([a-fA-Z0-9-]{15,})', url)
        found = False
        for token in tokens:
            for f in local_files:
                if token in f:
                    path = quote(os.path.join(folder_path, f).replace('\\', '/'))
                    if path not in ordered_images: ordered_images.append(path); found = True; break
            if found: break
        if not found and url: ordered_images.append(url)
    for f in local_files:
        path = quote(os.path.join(folder_path, f).replace('\\', '/'))
        if path not in ordered_images: ordered_images.append(path)
    return ordered_images

def parse_price(price_str):
    if not price_str or "free" in str(price_str).lower(): return 0.0, "FREE"
    if isinstance(price_str, (int, float)): return float(price_str), "JPY"
    clean = str(price_str).replace(',', '').replace('¥', '')
    match = re.search(r'([\d.]+)\s*([A-Z]*)', clean)
    if match: return float(match.group(1)), (match.group(2) or "JPY")
    return 0.0, "JPY"

def create_asset_data(asset_id, asset_name, author_name, web_images, booth_url, folder_path, tags, is_adult, wish_count, price_str, limited=False, description="", is_avatar=False, related_links=None):
    if limited and "⚙Unlisted" not in tags: tags.append("⚙Unlisted")
    if is_adult and "⚙Adult" not in tags: tags.append("⚙Adult")
    vrc_av = re.search(r'(https://vrchat\.com/home/avatar/avtr_[a-f0-9-]+)', description)
    vrc_wr = re.search(r'(https://vrchat\.com/home/(?:world/|launch\?worldId=)wrld_[a-f0-9-]+)', description)
    if (vrc_av or vrc_wr) and "⚙Preview" not in tags: tags.append("⚙Preview")
    binary_folder = os.path.join(folder_path, 'Binary')
    files, total_bytes = get_dir_data(binary_folder)
    img_bytes, all_imgs = get_image_folder_size(folder_path), get_all_local_images(folder_path, web_images)
    primary_img = all_imgs[0] if all_imgs else ""
    name_trans, author_trans = translation_cache.get(asset_name.strip(), ""), translation_cache.get(author_name.strip(), "")
    desc_trans = description_cache.get(asset_id, "")
    price_val, price_cur = parse_price(price_str)
    search_blob = f"{asset_id} {asset_name} {name_trans} {author_name} {author_trans} {' '.join(tags)}".lower()
    return { "id": asset_id, "nameOrig": asset_name, "nameTrans": name_trans, "authorOrig": author_name, "authorTrans": author_trans, "gridThumb": primary_img, "allImages": all_imgs, "bytes": total_bytes, "imgBytes": img_bytes, "fileCount": len(files), "files": files, "tags": tags, "adult": is_adult, "searchBlob": search_blob, "folder": quote(os.path.relpath(binary_folder, start=os.getcwd()).replace('\\', '/')), "boothUrl": booth_url, "wishCount": wish_count, "timestamp": int(os.path.getctime(folder_path)), "priceValue": price_val, "priceCurrency": price_cur, "limited": limited, "descOrig": description, "descTrans": desc_trans, "vrcAvatarLink": vrc_av.group(1) if vrc_av else "", "vrcWorldLink": vrc_wr.group(1) if vrc_wr else "", "isAvatar": is_avatar, "links": related_links or [] }

def get_avatar_search_profile(orig_name, trans_name, tags):
    search_terms, groups = set(), set()
    all_context = (orig_name + " " + (trans_name or "") + " " + " ".join(tags)).lower()
    for g in BODY_GROUPS:
        if g.lower() in all_context: groups.add(g.lower())
    def add_valid_candidate(cand):
        cleaned = re.sub(r'Original 3D Model|3D Model|Avatar|Ver\..*|#\w+|chan|kun|vrc|quest|pc|compatible|set', '', cand, flags=re.IGNORECASE).strip()
        if len(cleaned) > 2 and cleaned.lower() not in FORBIDDEN_NAMES: search_terms.add(cleaned.lower())
    if trans_name:
        add_valid_candidate(trans_name)
        for q in re.findall(r"['\"\[「](.*?)['\"\]」]", trans_name): add_valid_candidate(q)
    for part in re.findall(r'[a-zA-Z0-9]{3,}', orig_name):
        if part.lower() not in FORBIDDEN_NAMES: search_terms.add(part.lower())
    return {"names": list(search_terms), "groups": list(groups)}

def check_english_match(asset_info, profile):
    title, tags, vars = asset_info
    asset_context = (title + " " + " ".join(tags) + " " + " ".join(vars)).lower()
    for group in profile.get("groups", []):
        if group in asset_context: return True
    blob = re.sub(r'[^a-zA-Z0-9]', ' ', asset_context).lower().replace('ou', 'o')
    for term in profile.get("names", []):
        norm = re.sub(r'[^a-zA-Z0-9]', ' ', term).lower().replace('ou', 'o').strip()
        if norm and len(norm) > 2 and re.search(r'\b' + re.escape(norm) + r'\b', blob): return True
    return False

asset_data_list, short_strings_to_translate = [], []
desc_tasks, avatar_profiles = {}, {}

# List all current folders to detect deletions
current_folders = sorted(os.listdir(ROOT_FOLDER))
new_global_meta = {}
dirty_ids = set() # Track IDs that were actually re-processed

print(f"[Build] Identifying new or changed items...")
for folder in current_folders:
    path = os.path.join(ROOT_FOLDER, folder)
    if not os.path.isdir(path): continue
    
    mtime = os.path.getmtime(path)
    needs_update = folder not in global_meta or global_meta[folder] < mtime or folder not in existing_database
    new_global_meta[folder] = mtime

    if not needs_update:
        continue

    dirty_ids.add(folder)
    manual_json = os.path.join(path, "item_descriptor.json")
    if os.path.exists(manual_json):
        with open(manual_json, 'r', encoding='utf-8') as f:
            data = json.load(f)
            name, author, desc, tags = data.get('name', 'N/A'), data.get('author', 'N/A'), data.get('description', ''), data.get('tags', [])
            short_strings_to_translate.extend([name, author] + tags)
            is_avatar = data.get('is_avatar', False)
            asset_data_list.append(('custom', folder, (name, author, data, desc), path, data.get('wish_count', 0), is_avatar))
            if not SKIP_TRANSLATION and desc and folder not in description_cache and contains_japanese(desc): desc_tasks[folder] = desc
        continue

    jsons = glob.glob(os.path.join(path, "_BoothPage.json")) or glob.glob(os.path.join(path, "_BoothInnerHtmlList.json"))
    if not jsons: continue
    with open(jsons[0], 'r', encoding='utf-8') as f:
        if jsons[0].endswith('_BoothPage.json'):
            data = json.load(f)
            name, author, desc = data.get('name', 'N/A'), data.get('shop', {}).get('name', 'N/A'), data.get('description', '')
            tags = [t.get('name', '') for t in data.get('tags', [])]
            short_strings_to_translate.extend([name, author] + tags)
            cat = data.get('category', {})
            is_avatar = cat.get('id') == 208 or cat.get('name') in ["3D Characters", "3Dキャラクター", "3D캐릭터"]
            asset_data_list.append(('json', folder, (name, author, data, desc), path, data.get('wish_lists_count', 0), is_avatar))
            if not SKIP_TRANSLATION and desc and folder not in description_cache and contains_japanese(desc): desc_tasks[folder] = desc
        else:
            data = json.load(f)
            item = data[0] if data else ""
            if item:
                n_m, a_m = (re.search(r'break-all\">(.*?)<\/div>', item) or re.search(r'>(.*?)<\/div>', item)), re.search(r'text-text-gray600 break-all\">(.*?)<\/div>', item)
                name, author = n_m.group(1) if n_m else "N/A", a_m.group(1) if a_m else "N/A"
                short_strings_to_translate.extend([name, author])
                asset_data_list.append(('limited', folder, (name, author, item, ""), path, 0, False))

if len(dirty_ids) > 0:
    print(f"[Build] Found {len(dirty_ids)} new or updated items.")
else:
    print(f"[Build] No new or updated items found.")

bulk_translate_short_terms(short_strings_to_translate)

print("[Relate] Mapping Avatars...")
for atype, folder, data, path, wish, is_avatar in asset_data_list:
    if is_avatar:
        name, trans_name = data[0], translation_cache.get(data[0].strip(), "")
        tags = [t.get('name', '') for t in data[2].get('tags', [])] if atype == 'json' else (data[2].get('tags', []) if atype == 'custom' else [])
        avatar_profiles[folder] = get_avatar_search_profile(name, trans_name, tags)

for item_id, item in existing_database.items():
    if item['isAvatar'] and item_id not in avatar_profiles:
        avatar_profiles[item_id] = get_avatar_search_profile(item['nameOrig'], item['nameTrans'], item['tags'])

assets_to_avatar, avatar_to_assets = {}, {}

for atype, folder, data, path, wish, is_avatar in asset_data_list:
    if atype == 'custom' and 'related_booth_ids' in data[2]:
        for target_id in [str(x) for x in data[2]['related_booth_ids']]:
            if is_avatar: avatar_to_assets.setdefault(folder, []).append(target_id); assets_to_avatar.setdefault(target_id, []).append(folder)
            else: assets_to_avatar.setdefault(folder, []).append(target_id); avatar_to_assets.setdefault(target_id, []).append(folder)

    if not is_avatar:
        t_name = (translation_cache.get(data[0].strip(), "") or data[0]).lower()
        t_tags = [(translation_cache.get(t.get('name', ''), '') or t.get('name', '')).lower() for t in data[2].get('tags', [])] if atype == 'json' else ([(translation_cache.get(t.strip(), '') or t.strip()).lower() for t in data[2].get('tags', []) if t] if atype == 'custom' else [])
        t_vars = [(translation_cache.get(v.get('name', ''), '') or v.get('name', '')).lower() for v in data[2].get('variations', []) if v.get('name')] if atype == 'json' else []
        for av_id, profile in avatar_profiles.items():
            if check_english_match((t_name, t_tags, t_vars), profile): assets_to_avatar.setdefault(folder, []).append(av_id); avatar_to_assets.setdefault(av_id, []).append(folder)

for d in [assets_to_avatar, avatar_to_assets]:
    for key in d: d[key] = sorted(list(set(d[key])))

if desc_tasks:
    total_descs = len(desc_tasks)
    print(f"[Translate] Processing descriptions...")
    completed_descs = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_folder = {executor.submit(translate_single_text, text): folder for folder, text in desc_tasks.items()}
        for future in as_completed(future_to_folder):
            description_cache[future_to_folder[future]] = future.result(); completed_descs += 1; print_progress(completed_descs, total_descs, "Translate")
    with open(DESC_CACHE_FILE, 'w', encoding='utf-8') as f: json.dump(description_cache, f, ensure_ascii=False, indent=2)

print(f"[Build] Compiling Database...")
for atype, folder, data, path, wish, is_avatar in asset_data_list:
    name, author, content, desc = data
    rel = avatar_to_assets.get(folder, []) if is_avatar else assets_to_avatar.get(folder, [])
    if atype == 'json':
        existing_database[folder] = create_asset_data(folder, name, author, [img.get('original', '') for img in content.get('images', [])], content.get('url', ''), path, [t.get('name', '') for t in content.get('tags', [])], content.get('is_adult', False) or is_adult_content(name), wish, content.get('price', ''), description=desc, is_avatar=is_avatar, related_links=rel)
    elif atype == 'custom':
        existing_database[folder] = create_asset_data(folder, name, author, [], "", path, content.get('tags', []), content.get('is_adult', False) or is_adult_content(name), wish, content.get('price', 0), description=desc, is_avatar=is_avatar, related_links=rel)
    else:
        i_m, u_m = re.search(r'src=\"([^\"]+)\"', content), re.search(r'href=\"([^\"]+)\"', content)
        existing_database[folder] = create_asset_data(folder, name, author, [i_m.group(1) if i_m else ""], u_m.group(1) if u_m else "", path, [], is_adult_content(name), 0, "", limited=True, related_links=rel)

keys_to_remove = [k for k in existing_database if k not in new_global_meta]
for k in keys_to_remove: del existing_database[k]

database_output = list(existing_database.values())

if OPTIMIZE_THUMBNAILS:
    to_process = []
    # Only evaluate items that are 'dirty' (new/changed)
    for item_id in dirty_ids:
        item = existing_database.get(item_id)
        if not item or not item['gridThumb'] or item['gridThumb'].startswith('http'): continue
        
        orig_local_path = unquote(item['gridThumb']).replace('/', os.sep)
        if not os.path.exists(orig_local_path): continue
        
        t_path = os.path.join(IMG_OUT_DIR, f"{item['id']}_thumb.webp")
        crc = calculate_crc32(orig_local_path)
        
        # Optimize if thumbnail doesn't exist OR source file CRC changed
        if not os.path.exists(t_path) or thumb_meta.get(item['id']) != crc:
            to_process.append((item, orig_local_path, crc))
        else:
            item['gridThumb'] = quote(t_path.replace('\\', '/'))
    
    # For clean items, just ensure their path is correctly pointed to the existing thumb
    for item in database_output:
        if item['id'] not in dirty_ids:
            t_path = os.path.join(IMG_OUT_DIR, f"{item['id']}_thumb.webp")
            if os.path.exists(t_path):
                item['gridThumb'] = quote(t_path.replace('\\', '/'))

    if to_process:
        print(f"[Optimize] Updating {len(to_process)} thumbnails...")
        for i, (item, path, crc) in enumerate(to_process):
            item['gridThumb'] = get_optimized_thumb(item['id'], path, crc)
            print_progress(i + 1, len(to_process), "Optimize")
        with open(THUMB_META_FILE, 'w', encoding='utf-8') as f: json.dump(thumb_meta, f)

with open(DATABASE_JS_FILE, 'w', encoding='utf-8') as f:
    f.write("window.BOOTH_DATABASE = ")
    json.dump(database_output, f, ensure_ascii=False)
    f.write(";")

with open(GLOBAL_META_FILE, 'w', encoding='utf-8') as f:
    json.dump(new_global_meta, f)

final_html = HTML_TEMPLATE.replace("__L18N_INJECT_POINT__", json.dumps(l18n_data, ensure_ascii=False))
with open(OUTPUT_FILE, 'w', encoding='utf-8') as f: f.write(final_html)
print(f"--- Library Updated Successfully ({len(database_output)} items) ---")