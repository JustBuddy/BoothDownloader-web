import os
import json
import glob
import re
import sys
import binascii
import logging
import traceback
from urllib.parse import quote, unquote
from concurrent.futures import ThreadPoolExecutor, as_completed
from deep_translator import GoogleTranslator
from PIL import Image

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# Configuration
ROOT_FOLDER = "BoothDownloaderOut"
OUTPUT_FILE = "asset_library.html"
CACHE_FILE = "web_data/cache/translation_cache.json"
DESC_CACHE_FILE = "web_data/cache/descriptions_cache.json"
THUMB_META_FILE = "web_data/cache/thumbnail_meta.json"
FILTER_FILE = "web_data/filters.json"
L18N_FILE = "web_data/l18n.json"
ALIAS_FILE = "web_data/alias.json"
SKIP_TRANSLATION = False
MAX_TRANSLATION_WORKERS = 5
MAX_OPTIMIZATION_WORKERS = 16

# Database Cache Settings
DATABASE_JS_FILE = "web_data/cache/database.js"
GLOBAL_META_FILE = "web_data/cache/global_metadata.json"

# Thumbnail Optimization
OPTIMIZE_THUMBNAILS = True
OPTIMIZE_GALLERY = False 
THUMBNAIL_SIZE = (256, 256)
IMG_OUT_DIR = "web_data/img"
GALLERY_OUT_DIR = "web_data/img/gallery"

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

# Purely cosmetic: these strings will be stripped from the English UI display
STRINGS_TO_REMOVE = ["Original 3D Model", "Avatar", "3D Model", "[]", "Original 3D : ", "Original 3D", "[PhysBones compatible]", "(PB compatible)", "[PB compatible]", " /"]

logger.info(f"--- Starting Library Generation ---")

# Ensure directories exist
if not os.path.exists("web_data"): os.makedirs("web_data")
if not os.path.exists("web_data/cache"): os.makedirs("web_data/cache")
if OPTIMIZE_THUMBNAILS and not os.path.exists(IMG_OUT_DIR): os.makedirs(IMG_OUT_DIR)
if OPTIMIZE_GALLERY and not os.path.exists(GALLERY_OUT_DIR): os.makedirs(GALLERY_OUT_DIR)

# Force re-translation if caches are missing
FORCE_TRANSLATION = False
if not SKIP_TRANSLATION:
    if not os.path.exists(CACHE_FILE) or not os.path.exists(DESC_CACHE_FILE):
        logger.warning("Translation cache files missing. Forcing full re-translation.")
        FORCE_TRANSLATION = True

# Load External Filters
ADULT_KEYWORDS = []
if os.path.exists(FILTER_FILE):
    try:
        with open(FILTER_FILE, 'r', encoding='utf-8') as f:
            ext_data = json.load(f)
            if isinstance(ext_data, list): ADULT_KEYWORDS.extend(ext_data)
    except Exception:
        logger.error(f"Error loading {FILTER_FILE}:\n{traceback.format_exc()}")
ADULT_KEYWORDS = list(set(ADULT_KEYWORDS))

# Load Aliases
alias_data = {}
if os.path.exists(ALIAS_FILE):
    try:
        with open(ALIAS_FILE, 'r', encoding='utf-8') as f:
            alias_data = json.load(f)
    except Exception:
        logger.error(f"Could not load alias.json:\n{traceback.format_exc()}")

# Load Caches
translation_cache = {}
if os.path.exists(CACHE_FILE):
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f: translation_cache = json.load(f)
    except Exception: pass

description_cache = {}
if os.path.exists(DESC_CACHE_FILE):
    try:
        with open(DESC_CACHE_FILE, 'r', encoding='utf-8') as f: description_cache = json.load(f)
    except Exception: pass

# Clean Error 504 from caches
error_ids = set()
def cleanup_translation_errors():
    global translation_cache, description_cache
    to_delete_short = [k for k, v in translation_cache.items() if "Error 504" in str(v)]
    for k in to_delete_short: del translation_cache[k]
    
    to_delete_desc = [k for k, v in description_cache.items() if "Error 504" in str(v)]
    for k in to_delete_desc: 
        del description_cache[k]
        error_ids.add(k) 

cleanup_translation_errors()

thumb_meta = {}
if os.path.exists(THUMB_META_FILE):
    try:
        with open(THUMB_META_FILE, 'r', encoding='utf-8') as f: thumb_meta = json.load(f)
    except Exception: pass

global_meta = {}
if os.path.exists(GLOBAL_META_FILE):
    try:
        with open(GLOBAL_META_FILE, 'r', encoding='utf-8') as f: global_meta = json.load(f)
    except Exception: pass

existing_database = {}
if os.path.exists(DATABASE_JS_FILE):
    try:
        with open(DATABASE_JS_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
            json_str = content.replace("window.BOOTH_DATABASE = ", "").rstrip(";")
            db_list = json.loads(json_str)
            existing_database = {item['id']: item for item in db_list}
            for item in db_list:
                if "Error 504" in str(item.get('nameTrans', '')) or "Error 504" in str(item.get('authorTrans', '')):
                    error_ids.add(item['id'])
    except Exception: pass

l18n_data = {"languages": {"en": "English"}, "translations": {"en": {}}}
if os.path.exists(L18N_FILE):
    try:
        with open(L18N_FILE, 'r', encoding='utf-8') as f: l18n_data = json.load(f)
    except Exception: logger.error(f"Could not load l18n.json:\n{traceback.format_exc()}")

def contains_japanese(text): return bool(re.search(r'[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]', str(text)))

def translate_single_text(text):
    if not text or not contains_japanese(text) or SKIP_TRANSLATION: return text
    try: return GoogleTranslator(source='auto', target='en').translate(text)
    except Exception: return text

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
            logger.info(f"[{label}] {percent:.1f}% ({current}/{total})")

def calculate_crc32(filepath):
    crc = 0
    try:
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b''):
                crc = binascii.crc32(chunk, crc)
        return "%08X" % (crc & 0xFFFFFFFF)
    except Exception:
        return None

def get_optimized_thumb(asset_id, original_path, crc):
    if not original_path or not os.path.exists(original_path): return ""
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
            return quote(thumb_path.replace('\\', '/')), crc
    except Exception:
        logger.error(f"Failed to optimize thumb {original_path}:\n{traceback.format_exc()}")
        return quote(original_path.replace('\\', '/')), None

def get_optimized_gallery_img(asset_id, original_path, crc):
    if not original_path or not os.path.exists(original_path): return ""
    file_name = os.path.basename(original_path)
    opt_name = f"{asset_id}_{crc}_{os.path.splitext(file_name)[0]}.webp"
    opt_path = os.path.join(GALLERY_OUT_DIR, opt_name)
    if os.path.exists(opt_path): return quote(opt_path.replace('\\', '/'))
    try:
        with Image.open(original_path) as img:
            img.save(opt_path, "WEBP", optimize=True, quality=85)
            return quote(opt_path.replace('\\', '/'))
    except Exception:
        return quote(original_path.replace('\\', '/'))

HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Booth Asset Library</title>
    <link rel="icon" type="image/svg+xml" href="web_data/favicon.svg">
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
                <label style="display:flex; gap:10px; cursor:pointer; font-size:0.85rem; margin-top:8px; align-items:center;"><input type="checkbox" id="sortInvert" onchange="sortAssets(true)"> <span data-i18n="optInvert">Invert Order</span></label>
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
    <script src="__DATABASE_FILE_INJECT_POINT__"></script>
    <script>
        const l18n = __L18N_INJECT_POINT__;
        const translations = l18n.translations;
        const STRINGS_TO_REMOVE = __REMOVABLES_INJECT_POINT__;
        const database = window.BOOTH_DATABASE || [];
        let currentCarouselIndex = 0, currentImages = [];
        const baseTitle = "Booth Asset Library";
        const getLS = (k, def) => localStorage.getItem(k) || def;
        const state = { gridSize: getLS('gridSize', '220'), disableBlur: getLS('disableBlur', 'false') === 'true', sortOrder: getLS('sortOrder', 'id'), sortInvert: getLS('sortInvert', 'false') === 'true', adultFilter: getLS('adultFilter', 'all'), typeFilter: getLS('typeFilter', 'all'), hideIds: getLS('hideIds', 'false') === 'true', lang: getLS('lang', 'en'), showTrans: getLS('showTrans', 'true') === 'true' };
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
            document.getElementById('gridRange').value = state.gridSize; document.getElementById('blurToggle').checked = state.disableBlur; document.getElementById('sortOrder').value = state.sortOrder; document.getElementById('sortInvert').checked = state.sortInvert;
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
        function cleanUIName(name, isAvatar) {
            if (!name || !isAvatar) return name || "";
            let cleaned = name;
            STRINGS_TO_REMOVE.forEach(s => {
                const escaped = s.replace(/[.*+?^${}()|[\]\\\/]/g, '\\$&');
                cleaned = cleaned.replace(new RegExp(escaped, 'gi'), '');
            });
            return cleaned.trim();
        }
        function updateTranslationVisibility(v) { 
            state.showTrans = v; localStorage.setItem('showTrans', v);
            const t = translations[state.lang] || translations['en'];
            database.forEach(item => {
                const el = document.getElementById('asset-' + item.id);
                if (!el) return;
                const rawName = (v && item.nameTrans) ? item.nameTrans : item.nameOrig;
                el.querySelector('.name-primary').innerText = v ? cleanUIName(rawName, item.isAvatar) : rawName;
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
                if (item) {
                    const rawModalName = (v && item.nameTrans) ? item.nameTrans : item.nameOrig;
                    document.getElementById("modalName").innerText = v ? cleanUIName(rawModalName, item.isAvatar) : rawModalName;
                    document.getElementById('modalDesc').innerHTML = formatDescription((v && item.descTrans) ? item.descTrans : item.descOrig);
                }
            }
        }
        function formatDescription(text) {
            if (!text) return "";
            const urlRegex = /(https?:\/\/[^\s\n]+)/g;
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
            const list = document.getElementById('assetList'), order = document.getElementById('sortOrder').value, invert = document.getElementById('sortInvert').checked;
            if(save) { localStorage.setItem('sortOrder', order); localStorage.setItem('sortInvert', invert); state.sortInvert = invert; }
            const sorted = [...database].sort((a, b) => {
                let res = 0;
                if (order === 'id') res = isNaN(a.id) || isNaN(b.id) ? a.id.localeCompare(b.id) : parseInt(a.id) - parseInt(b.id);
                else if (order === 'new') res = b.timestamp - a.timestamp;
                else if (order === 'rel') res = b.wishCount - a.wishCount;
                else if (order === 'size') res = b.bytes - a.bytes;
                else {
                    const nA = (state.showTrans && a.nameTrans) ? a.nameTrans : a.nameOrig;
                    const nB = (state.showTrans && b.nameTrans) ? b.nameTrans : b.nameOrig;
                    res = nA.toLowerCase().localeCompare(nB.toLowerCase());
                }
                return invert ? res * -1 : res;
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
            const rawTitle = (state.showTrans && item.nameTrans) ? item.nameTrans : item.nameOrig;
            const authorDisp = (state.showTrans && item.authorTrans) ? item.authorTrans : item.authorOrig;
            document.getElementById("modalName").innerText = state.showTrans ? cleanUIName(rawTitle, item.isAvatar) : rawTitle;
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
                    const rawTargetName = (state.showTrans && target.nameTrans) ? target.nameTrans : target.nameOrig;
                    const n = state.showTrans ? cleanUIName(rawTargetName, target.isAvatar) : rawTargetName;
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
                if(!viewer.classList.contains('active')) viewer.remove('visible');
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
                fp = os.path.join(root, f); size = os.path.getsize(fp); total_size += size
                rel = os.path.relpath(fp, start=os.getcwd()).replace('\\', '/')
                files.append({"name": f, "path": quote(rel), "size": get_readable_size(size)})
    return files, total_size

def get_dir_fingerprint(binary_folder):
    if not os.path.exists(binary_folder): return ""
    fingerprint = []
    for root, _, filenames in os.walk(binary_folder):
        for f in filenames:
            fp = os.path.join(root, f)
            fingerprint.append(f"{f}:{os.path.getsize(fp)}")
    return "|".join(sorted(fingerprint))

def get_image_folder_size(folder_path):
    total_size = 0
    for f in os.listdir(folder_path):
        if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif')): total_size += os.path.getsize(os.path.join(folder_path, f))
    return total_size

def is_adult_content(text): return bool(re.search("|".join(ADULT_KEYWORDS), str(text), re.IGNORECASE))

def get_all_local_images(asset_id, folder_path, web_urls=None):
    if web_urls is None: web_urls = []
    local_files = sorted([f for f in os.listdir(folder_path) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif'))])
    ordered_images = []; used_files = set()
    for url in web_urls:
        if not url: continue
        tokens = re.findall(r'([a-fA-Z0-9-]{15,})', url)
        found = False
        for token in tokens:
            for f in local_files:
                if token in f: ordered_images.append(quote(os.path.join(folder_path, f).replace('\\', '/'))); used_files.add(f); found = True; break
            if found: break
        if not found: ordered_images.append(url)
    for f in local_files:
        if f not in used_files: ordered_images.append(quote(os.path.join(folder_path, f).replace('\\', '/')))
    return ordered_images

def parse_price(price_str):
    if not price_str or "free" in str(price_str).lower(): return 0.0, "FREE"
    if isinstance(price_str, (int, float)): return float(price_str), "JPY"
    clean = str(price_str).replace(',', '').replace('¥', '')
    match = re.search(r'([\d.]+)\s*([A-Z]*)', clean)
    return (float(match.group(1)), (match.group(2) or "JPY")) if match else (0.0, "JPY")

def create_asset_data(asset_id, asset_name, author_name, web_images, booth_url, folder_path, tags, is_adult, wish_count, price_str, limited=False, description="", is_avatar=False, related_links=None):
    if limited and "⚙Unlisted" not in tags: tags.append("⚙Unlisted")
    if is_adult and "⚙Adult" not in tags: tags.append("⚙Adult")
    vrc_av = re.search(r'(https://vrchat\.com/home/avatar/avtr_[a-f0-9-]+)', description)
    vrc_wr = re.search(r'(https://vrchat\.com/home/(?:world/|launch\?worldId=)wrld_[a-f0-9-]+)', description)
    if (vrc_av or vrc_wr) and "⚙Preview" not in tags: tags.append("⚙Preview")
    binary_folder = os.path.join(folder_path, 'Binary'); files, total_bytes = get_dir_data(binary_folder)
    img_bytes, all_imgs = get_image_folder_size(folder_path), get_all_local_images(asset_id, folder_path, web_images)
    name_trans, author_trans = translation_cache.get(asset_name.strip(), ""), translation_cache.get(author_name.strip(), "")
    price_val, price_cur = parse_price(price_str)
    search_blob = f"{asset_id} {asset_name} {name_trans} {author_name} {author_trans} {' '.join(tags)}".lower()
    return { 
        "id": asset_id, "nameOrig": asset_name, "nameTrans": name_trans, "authorOrig": author_name, "authorTrans": author_trans, 
        "gridThumb": all_imgs[0] if all_imgs else "", "allImages": all_imgs, "bytes": total_bytes, "imgBytes": img_bytes, 
        "fileCount": len(files), "files": files, "tags": tags, "adult": is_adult, "searchBlob": search_blob, 
        "folder": quote(os.path.relpath(binary_folder, start=os.getcwd()).replace('\\', '/')), "boothUrl": booth_url, 
        "wishCount": wish_count, "timestamp": int(os.path.getctime(folder_path)), "priceValue": price_val, 
        "priceCurrency": price_cur, "limited": limited, "descOrig": description, "descTrans": description_cache.get(asset_id, ""), 
        "vrcAvatarLink": vrc_av.group(1) if vrc_av else "", "vrcWorldLink": vrc_wr.group(1) if vrc_wr else "", 
        "isAvatar": is_avatar, "links": related_links or [] 
    }

def get_avatar_search_profile(asset_id, orig_name, trans_name, tags):
    search_terms, groups = set(), set()
    all_ctx = (orig_name + " " + (trans_name or "") + " " + " ".join(tags)).lower()
    for g in BODY_GROUPS:
        if g.lower() in all_ctx: groups.add(g.lower())
    alias = alias_data.get(str(asset_id))
    if alias:
        for a in (alias if isinstance(alias, list) else [alias]): search_terms.add(str(a).lower())
    def add_val(cand):
        cleaned = re.sub(r'Original 3D Model|3D Model|Avatar|Ver\..*|#\w+|chan|kun|vrc|quest|pc|compatible|set', '', cand, flags=re.IGNORECASE).strip()
        if len(cleaned) > 2 and cleaned.lower() not in FORBIDDEN_NAMES: search_terms.add(cleaned.lower())
    if trans_name:
        add_val(trans_name)
        for q in re.findall(r"['\"\[「](.*?)['\"\]\"「」]", trans_name): add_val(q)
    for part in re.findall(r'[a-zA-Z0-9]{3,}', orig_name):
        if part.lower() not in FORBIDDEN_NAMES: search_terms.add(part.lower())
    return {"names": list(search_terms), "groups": list(groups)}

def check_english_match(asset_info, profile):
    title, tags, vars = asset_info
    ctx = (title + " " + " ".join(tags) + " " + " ".join(vars)).lower()
    for group in profile.get("groups", []):
        if group in ctx: return True
    blob = re.sub(r'[^a-zA-Z0-9]', ' ', ctx).lower().replace('ou', 'o')
    for term in profile.get("names", []):
        norm = re.sub(r'[^a-zA-Z0-9]', ' ', term).lower().replace('ou', 'o').strip()
        if norm and len(norm) > 2 and re.search(r'\b' + re.escape(norm) + r'\b', blob): return True
    return False

asset_data_list, short_strings_to_translate, desc_tasks, avatar_profiles = [], [], {}, {}
current_folders = sorted(os.listdir(ROOT_FOLDER))
new_global_meta = {}
dirty_ids = set()

deleted_ids = [k for k in global_meta if k not in current_folders]
if deleted_ids:
    logger.info(f"[Cleanup] Removing {len(deleted_ids)} items...")
    for d_id in deleted_ids:
        existing_database.pop(d_id, None)
        description_cache.pop(d_id, None)
        thumb_meta.pop(d_id, None)
        t_path = os.path.join(IMG_OUT_DIR, f"{d_id}_thumb.webp")
        if os.path.exists(t_path): os.remove(t_path)
        for f in glob.glob(os.path.join(GALLERY_OUT_DIR, f"{d_id}_*")):
            try: os.remove(f)
            except OSError: pass
    try:
        with open(DESC_CACHE_FILE, 'w', encoding='utf-8') as f: json.dump(description_cache, f, ensure_ascii=False, indent=2)
        with open(THUMB_META_FILE, 'w', encoding='utf-8') as f: json.dump(thumb_meta, f)
    except Exception:
         logger.error(f"Failed to save cache during cleanup:\n{traceback.format_exc()}")

logger.info(f"[Build] Identifying updates...")
for folder in current_folders:
    path = os.path.join(ROOT_FOLDER, folder)
    mtime = os.path.getmtime(path)
    binary_path = os.path.join(path, "Binary")
    files_fingerprint = get_dir_fingerprint(binary_path)
    
    meta_entry = global_meta.get(folder, {})
    if isinstance(meta_entry, (int, float)): meta_entry = {"time": meta_entry, "files": ""}
    
    needs_update = (FORCE_TRANSLATION or 
                    folder not in global_meta or 
                    meta_entry.get("time") < mtime or 
                    meta_entry.get("files") != files_fingerprint or
                    folder not in existing_database or 
                    folder in error_ids)
    
    new_global_meta[folder] = {"time": mtime, "files": files_fingerprint}
    
    if not needs_update: continue
    dirty_ids.add(folder)
    manual_json = os.path.join(path, "item_descriptor.json")
    
    if os.path.exists(manual_json):
        try:
            with open(manual_json, 'r', encoding='utf-8') as f:
                data = json.load(f)
                name, author, desc = data.get('name', 'N/A'), data.get('author', 'N/A'), data.get('description', '')
                tags = data.get('tags', [])
                short_strings_to_translate.extend([name, author] + tags)
                asset_data_list.append(('custom', folder, (name, author, data, desc), path, data.get('wish_count', 0), data.get('is_avatar', False)))
                if not SKIP_TRANSLATION and desc and (FORCE_TRANSLATION or folder not in description_cache or folder in error_ids) and contains_japanese(desc): 
                    desc_tasks[folder] = desc
        except Exception:
            logger.error(f"Failed to process {manual_json}:\n{traceback.format_exc()}")
        continue

    jsons = glob.glob(os.path.join(path, "_BoothPage.json")) or glob.glob(os.path.join(path, "_BoothInnerHtmlList.json"))
    if not jsons: continue
    try:
        with open(jsons[0], 'r', encoding='utf-8') as f:
            if jsons[0].endswith('_BoothPage.json'):
                data = json.load(f)
                name, author, desc = data.get('name', 'N/A'), data.get('shop', {}).get('name', 'N/A'), data.get('description', '')
                tags = [t.get('name', '') for t in data.get('tags', [])]
                short_strings_to_translate.extend([name, author] + tags)
                cat = data.get('category', {})
                is_av = cat.get('id') == 208 or cat.get('name') in ["3D Characters", "3Dキャラクター", "3D캐릭터"] if cat else False
                asset_data_list.append(('json', folder, (name, author, data, desc), path, data.get('wish_lists_count', 0), is_av))
                if not SKIP_TRANSLATION and desc and (FORCE_TRANSLATION or folder not in description_cache or folder in error_ids) and contains_japanese(desc): 
                    desc_tasks[folder] = desc
            else:
                data = json.load(f)
                item = data[0] if data else ""
                if item:
                    n_m, a_m = (re.search(r'break-all\">(.*?)<\/div>', item) or re.search(r'>(.*?)<\/div>', item)), re.search(r'text-text-gray600 break-all\">(.*?)<\/div>', item)
                    name, author = n_m.group(1) if n_m else "N/A", a_m.group(1) if a_m else "N/A"
                    short_strings_to_translate.extend([name, author])
                    asset_data_list.append(('limited', folder, (name, author, item, ""), path, 0, False))
    except Exception:
        logger.error(f"Failed to process {jsons[0]}:\n{traceback.format_exc()}")

if not SKIP_TRANSLATION:
    new_strs = [t for t in list(set(str(t).strip() for t in short_strings_to_translate if t and contains_japanese(t))) if t not in translation_cache]
    if new_strs:
        logger.info(f"[Translate] Processing {len(new_strs)} terms...")
        with ThreadPoolExecutor(max_workers=MAX_TRANSLATION_WORKERS) as ex_trans:
            futures_trans = {ex_trans.submit(lambda x: (x, GoogleTranslator(source='auto', target='en').translate(x)), term): term for term in new_strs}
            for i, f in enumerate(as_completed(futures_trans)): 
                try:
                    orig, trans = f.result()
                    translation_cache[orig] = trans
                except Exception:
                    logger.error(f"Translation failed for term:\n{traceback.format_exc()}")
                print_progress(i+1, len(new_strs), "Translate")
        try:
            with open(CACHE_FILE, 'w', encoding='utf-8') as f: json.dump(translation_cache, f, ensure_ascii=False, indent=2)
        except Exception:
             logger.error(f"Failed to save translation cache:\n{traceback.format_exc()}")

logger.info("[Relate] Building Avatar Profiles...")
for item_id, item in existing_database.items():
    if item['isAvatar']:
        avatar_profiles[item_id] = get_avatar_search_profile(item_id, item['nameOrig'], item['nameTrans'], item['tags'])

for atype, folder, data, path, wish, is_avatar in asset_data_list:
    if is_avatar:
        tags_source = []
        if atype == 'json': tags_source = [t.get('name', '') for t in data[2].get('tags', [])]
        elif atype == 'custom': tags_source = data[2].get('tags', [])
        avatar_profiles[folder] = get_avatar_search_profile(folder, data[0], translation_cache.get(data[0].strip(), ""), tags_source)

logger.info("[Relate] Scanning for relationships...")
relation_map = {item_id: {'avatars': [], 'assets': []} for item_id in set(list(existing_database.keys()) + [a[1] for a in asset_data_list])}

for item_id in relation_map:
    item_info, is_av, content = None, False, {}
    found_in_new = False
    for a_type, a_folder, a_data, a_path, a_wish, a_is_av in asset_data_list:
        if a_folder == item_id:
            found_in_new, is_av, name, author, content, desc = True, a_is_av, *a_data
            t_name = (translation_cache.get(name.strip(), "") or name).lower()
            if a_type == 'json':
                t_tags = [(translation_cache.get(t.get('name', ''), '') or t.get('name', '')).lower() for t in content.get('tags', [])]
                t_vars = [(translation_cache.get(v.get('name', ''), '') or v.get('name', '')).lower() for v in content.get('variations', []) if v.get('name')]
            elif a_type == 'custom': t_tags, t_vars = [t.lower() for t in content.get('tags', [])], []
            else: t_tags, t_vars = [], []
            item_info = (t_name, t_tags, t_vars)
            break
    if not found_in_new and item_id in existing_database:
        db_item = existing_database[item_id]
        item_info, is_av = ((db_item.get('nameTrans') or db_item['nameOrig']).lower(), [t.lower() for t in db_item['tags']], []), db_item['isAvatar']

    if not item_info: continue
    if found_in_new and 'related_booth_ids' in content:
        for target_id in [str(x) for x in content['related_booth_ids']]:
            if target_id == item_id: continue
            if is_av:
                relation_map[item_id]['assets'].append(target_id)
                if target_id in relation_map: relation_map[target_id]['avatars'].append(item_id)
            else:
                relation_map[item_id]['avatars'].append(target_id)
                if target_id in relation_map: relation_map[target_id]['assets'].append(item_id)
    if not is_av:
        for av_id, profile in avatar_profiles.items():
            if av_id != item_id and check_english_match(item_info, profile):
                relation_map[item_id]['avatars'].append(av_id)
                if av_id in relation_map: relation_map[av_id]['assets'].append(item_id)

assets_to_avatar = {k: sorted(list(set(v['avatars']))) for k, v in relation_map.items() if v['avatars']}
avatar_to_assets = {k: sorted(list(set(v['assets']))) for k, v in relation_map.items() if v['assets']}

if desc_tasks:
    logger.info(f"[Translate] Processing descriptions...")
    with ThreadPoolExecutor(max_workers=MAX_TRANSLATION_WORKERS) as ex_desc:
        f_to_f = {ex_desc.submit(translate_single_text, text): f for f, text in desc_tasks.items()}
        for i, f in enumerate(as_completed(f_to_f)):
            try: description_cache[f_to_f[f]] = f.result()
            except Exception: logger.error(f"Description translation failed:\n{traceback.format_exc()}")
            print_progress(i+1, len(desc_tasks), "Translate")
    try:
        with open(DESC_CACHE_FILE, 'w', encoding='utf-8') as f: json.dump(description_cache, f, ensure_ascii=False, indent=2)
    except Exception: logger.error(f"Failed to save description cache:\n{traceback.format_exc()}")

logger.info(f"[Build] Compiling Database...")
for atype, folder, data, path, wish, is_avatar in asset_data_list:
    links = avatar_to_assets.get(folder, []) if is_avatar else assets_to_avatar.get(folder, [])
    name, author, content, desc = data
    if atype == 'json': existing_database[folder] = create_asset_data(folder, name, author, [img.get('original', '') for img in content.get('images', [])], content.get('url', ''), path, [t.get('name', '') for t in content.get('tags', [])], content.get('is_adult', False) or is_adult_content(name), wish, content.get('price', ''), description=desc, is_avatar=is_avatar, related_links=links)
    elif atype == 'custom': existing_database[folder] = create_asset_data(folder, name, author, [], "", path, content.get('tags', []), content.get('is_adult', False) or is_adult_content(name), wish, content.get('price', 0), description=desc, is_avatar=is_avatar, related_links=links)
    else:
        i_m, u_m = re.search(r'src=\"([^\"]+)\"', content), re.search(r'href=\"([^\"]+)\"', content)
        existing_database[folder] = create_asset_data(folder, name, author, [i_m.group(1) if i_m else ""], u_m.group(1) if u_m else "", path, [], is_adult_content(name), 0, "", limited=True, related_links=links)

for item_id in existing_database:
    if item_id not in dirty_ids:
        item = existing_database[item_id]
        new_links = avatar_to_assets.get(item_id, []) if item['isAvatar'] else assets_to_avatar.get(item_id, [])
        if set(new_links) != set(item.get('links', [])): item['links'] = new_links

if OPTIMIZE_THUMBNAILS or OPTIMIZE_GALLERY:
    thumb_tasks, gallery_tasks, scan_list = [], [], list(existing_database.values())
    logger.info(f"[Optimize] Scanning {len(scan_list)} items for changes...")
    def scan_item(item):
        t_task, g_tasks = None, []
        if OPTIMIZE_THUMBNAILS:
            cur_thumb = unquote(item['gridThumb']).replace('/', os.sep)
            if cur_thumb.startswith('web_data') and not os.path.exists(cur_thumb):
                orig_folder = os.path.join(ROOT_FOLDER, item['id'])
                local_files = [f for f in os.listdir(orig_folder) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif'))]
                if local_files: cur_thumb = os.path.join(orig_folder, local_files[0])
            if os.path.exists(cur_thumb) and not cur_thumb.startswith('web_data'):
                crc = calculate_crc32(cur_thumb)
                if crc and (thumb_meta.get(item['id']) != crc or not os.path.exists(os.path.join(IMG_OUT_DIR, f"{item['id']}_thumb.webp"))): t_task = (item, cur_thumb, crc)
                else: item['gridThumb'] = quote(os.path.join(IMG_OUT_DIR, f"{item['id']}_thumb.webp").replace('\\', '/'))
        if OPTIMIZE_GALLERY:
            new_gal, orig_folder = [], os.path.join(ROOT_FOLDER, item['id'])
            local_srcs = sorted([f for f in os.listdir(orig_folder) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif'))])
            for img_path in item['allImages']:
                img_path_unquoted = unquote(img_path)
                local_p = img_path_unquoted.replace('/', os.sep)
                if 'web_data/img/gallery' in img_path_unquoted:
                    if os.path.exists(local_p): new_gal.append(img_path); continue
                    else:
                        match = re.search(rf"{item['id']}_[A-F0-9]+_(.*)\.webp", os.path.basename(local_p))
                        orig_fn_part = match.group(1) if match else None; found_src = False
                        for src_f in local_srcs:
                            if orig_fn_part and src_f.startswith(orig_fn_part): local_p, found_src = os.path.join(orig_folder, src_f), True; break
                        if not found_src: continue
                if os.path.exists(local_p) and not local_p.startswith('web_data'):
                    crc = calculate_crc32(local_p)
                    if not crc: continue
                    file_name = os.path.basename(local_p)
                    opt_path = os.path.join(GALLERY_OUT_DIR, f"{item['id']}_{crc}_{os.path.splitext(file_name)[0]}.webp")
                    if not os.path.exists(opt_path): g_tasks.append((item, local_p, crc, len(new_gal))); new_gal.append(img_path)
                    else: new_gal.append(quote(opt_path.replace('\\', '/')))
                else: new_gal.append(img_path)
            item['allImages'] = new_gal
        return t_task, g_tasks

    with ThreadPoolExecutor(max_workers=MAX_OPTIMIZATION_WORKERS) as ex_scan:
        f_scan = [ex_scan.submit(scan_item, it) for it in scan_list]
        for i, f in enumerate(as_completed(f_scan)):
            try:
                t, g = f.result()
                if t: thumb_tasks.append(t)
                gallery_tasks.extend(g)
            except Exception: logger.error(f"Error scanning item:\n{traceback.format_exc()}")
            print_progress(i+1, len(scan_list), "Scan")

    with ThreadPoolExecutor(max_workers=MAX_OPTIMIZATION_WORKERS) as ex_opt:
        if thumb_tasks:
            logger.info(f"[Optimize] Updating {len(thumb_tasks)} thumbnails...")
            f_thumbs = {ex_opt.submit(get_optimized_thumb, t[0]['id'], t[1], t[2]): t for t in thumb_tasks}
            for i, f in enumerate(as_completed(f_thumbs)):
                try:
                    res, crc = f.result()
                    item = f_thumbs[f][0]
                    item['gridThumb'] = res
                    if crc: thumb_meta[item['id']] = crc
                except Exception: logger.error(f"Thumbnail optimization failed:\n{traceback.format_exc()}")
                print_progress(i+1, len(thumb_tasks), "Optimize")
            try:
                with open(THUMB_META_FILE, 'w', encoding='utf-8') as f: json.dump(thumb_meta, f)
            except Exception: logger.error(f"Failed to save thumbnail meta:\n{traceback.format_exc()}")
        if gallery_tasks:
            logger.info(f"[Optimize] Processing {len(gallery_tasks)} gallery images...")
            f_gal = {ex_opt.submit(get_optimized_gallery_img, g[0]['id'], g[1], g[2]): g for g in gallery_tasks}
            for i, f in enumerate(as_completed(f_gal)):
                try:
                    res = f.result()
                    item, _, _, idx = f_gal[f]
                    item['allImages'][idx] = res
                except Exception: logger.error(f"Gallery optimization failed:\n{traceback.format_exc()}")
                print_progress(i+1, len(gallery_tasks), "Optimize")

keys_to_remove = [k for k in existing_database if k not in current_folders]
for k in keys_to_remove: del existing_database[k]

try:
    with open(DATABASE_JS_FILE, 'w', encoding='utf-8') as f: 
        f.write("window.BOOTH_DATABASE = "); json.dump(list(existing_database.values()), f, ensure_ascii=False); f.write(";")
    with open(GLOBAL_META_FILE, 'w', encoding='utf-8') as f: json.dump(new_global_meta, f)
    final_html = (HTML_TEMPLATE
                  .replace("__L18N_INJECT_POINT__", json.dumps(l18n_data, ensure_ascii=False))
                  .replace("__REMOVABLES_INJECT_POINT__", json.dumps(STRINGS_TO_REMOVE, ensure_ascii=False))
                  .replace("__DATABASE_FILE_INJECT_POINT__", DATABASE_JS_FILE))
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f: f.write(final_html)
    logger.info(f"--- Library Updated Successfully ({len(existing_database)} items) ---")
except Exception: logger.error(f"Critical failure saving database:\n{traceback.format_exc()}")