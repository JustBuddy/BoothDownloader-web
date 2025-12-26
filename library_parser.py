import os, json, glob, re, time, sys
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor
from deep_translator import GoogleTranslator

# Configuration
ROOT_FOLDER, WEB_DATA_DIR, OUTPUT_FILE, CACHE_FILE = "BoothDownloaderOut", "web_data", "asset_library.html", "translation_cache.json"
SKIP_TRANSLATION, MAX_WORKERS = False, 5
ADULT_KEYWORDS_EN = [r"R-?18", r"adult", r"nude", r"semen", r"nsfw", r"sexual", r"erotic", r"pussy", r"dick", r"vagina", r"penis", r"otimpo", r"otinpo"]
ADULT_KEYWORDS_JP = ["精液", "だぷだぷ", "ヌード", "エロ", "クリトリス", "おまんこ", "おちんぽ", "おてぃんぽ"]

os.makedirs(WEB_DATA_DIR, exist_ok=True)

# --- Translation Logic ---
translation_cache = {}
if not SKIP_TRANSLATION and os.path.exists(CACHE_FILE):
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f: translation_cache = json.load(f)
    except: pass

def contains_japanese(text): return bool(re.search(r'[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]', str(text)))
def is_noise(text):
    if not text or len(text.strip()) < 1 or text.isdigit(): return True
    alnum_jp = re.sub(r'[^\w\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]', '', text)
    return not alnum_jp or len(alnum_jp) / len(text) < 0.15

def translate_chunk_task(chunk_data):
    chunk_index, chunk = chunk_data
    translator = GoogleTranslator(source='auto', target='en')
    separator = " @@@ "
    try:
        clean_chunk = [t.strip() for t in chunk]
        translated = translator.translate(separator.join(clean_chunk))
        if translated:
            results = [r.strip() for r in translated.split("@@@")]
            if len(results) == len(clean_chunk):
                for original, trans in zip(chunk, results):
                    if not contains_japanese(trans): translation_cache[original] = trans
                return True
            else:
                for original in chunk:
                    try:
                        res = translator.translate(original)
                        if res: translation_cache[original] = res
                    except: continue
                return True
    except: pass
    return False

def bulk_translate(text_list):
    if SKIP_TRANSLATION: return
    japanese_strings = list(set(str(t).strip() for t in text_list if t and contains_japanese(t)))
    new_strings = [t for t in japanese_strings if t not in translation_cache]
    real_queue = [t for t in new_strings if not is_noise(t)]
    for t in new_strings:
        if is_noise(t): translation_cache[t] = t
    if not real_queue: return
    batch_size = 15
    chunks = [(i//batch_size + 1, real_queue[i:i+batch_size]) for i in range(0, len(real_queue), batch_size)]
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor: list(executor.map(translate_chunk_task, chunks))

# --- Data Helpers ---
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
                total_size += os.path.getsize(fp)
                rel = os.path.relpath(fp, start=os.getcwd())
                files.append({"name": f, "path": quote(rel), "size": get_readable_size(os.path.getsize(fp))})
    return files, total_size

def is_adult_content(text):
    if re.search("|".join(ADULT_KEYWORDS_EN), text, re.IGNORECASE): return True
    return any(w in text for w in ADULT_KEYWORDS_JP)

def get_all_local_images(folder_path, web_urls):
    local_files = [f for f in os.listdir(folder_path) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif'))]
    ordered_images = []
    for url in web_urls:
        tokens = re.findall(r'([a-fA-Z0-9-]{15,})', url)
        found = False
        for token in tokens:
            for f in local_files:
                if token in f:
                    path = quote(os.path.join(folder_path, f))
                    if path not in ordered_images: ordered_images.append(path); found = True; break
            if found: break
        if not found and url: ordered_images.append(url)
    for f in local_files:
        path = quote(os.path.join(folder_path, f))
        if path not in ordered_images: ordered_images.append(path)
    return ordered_images

def generate_asset_html(asset_id, asset_name, web_images, booth_url, folder_path, tags, is_adult, wish_count):
    binary_folder = os.path.join(folder_path, 'Binary')
    files_data, total_bytes = get_dir_data(binary_folder)
    all_imgs = get_all_local_images(folder_path, web_images)
    primary_img = all_imgs[0] if all_imgs else ""
    name_trans = translation_cache.get(asset_name.strip(), "")
    grid_tags_html = "".join([f'<span class="tag-pill">{t}</span>' for t in tags[:12]])
    img_class = "image-thumbnail adult-content" if is_adult else "image-thumbnail"
    glow_tag = f'<img class="image-backglow" src="{primary_img}">' if primary_img else ''
    img_tag = f'<img class="{img_class}" src="{primary_img}">' if primary_img else '<div class="image-thumbnail" style="background:#222;display:flex;align-items:center;justify-content:center;color:#444;font-weight:800;">EMPTY</div>'
    safe_name, safe_trans = asset_name.replace('"', '&quot;'), name_trans.replace('"', '&quot;')
    filenames_str = " ".join([f['name'] for f in files_data])
    search_str = f"{asset_id} {asset_name} {name_trans} {' '.join(tags)} {filenames_str}".lower().replace("'", "")
    rel_folder = quote(os.path.relpath(binary_folder, start=os.getcwd())) if os.path.exists(binary_folder) else quote(os.path.relpath(folder_path))
    return f"""<li class="asset" onclick="openDetails('{asset_id}')" data-id="{asset_id}" data-name-orig="{safe_name}" data-name-trans="{safe_trans}" data-img="{primary_img}" data-all-images='{json.dumps(all_imgs).replace("'", "&apos;")}' data-bytes="{total_bytes}" data-files='{json.dumps(files_data).replace("'", "&apos;")}' data-tags='{json.dumps(tags).replace("'", "&apos;")}' data-adult="{str(is_adult).lower()}" data-search='{search_str}' data-folder="{rel_folder}" data-booth-url="{booth_url}" data-filecount="{len(files_data)}" data-wish="{wish_count}" data-time="{int(os.path.getctime(folder_path))}">
        <div class="image-container"><div class="asset-id-tag">#{asset_id}</div>{img_tag}</div>{glow_tag}<div class="content"><div class="name"><span class="name-primary">{asset_name}</span></div><div class="stats"><span>{get_readable_size(total_bytes)}</span><span class="file-label-dynamic"></span></div><div class="tag-row">{grid_tags_html}</div></div></li>"""

# --- Main Script ---
asset_data_list, all_strings_to_translate = [], []
for folder in sorted(os.listdir(ROOT_FOLDER)):
    path = os.path.join(ROOT_FOLDER, folder)
    if not os.path.isdir(path): continue
    jsons = glob.glob(os.path.join(path, "_BoothPage.json")) or glob.glob(os.path.join(path, "_BoothInnerHtmlList.json"))
    if not jsons: continue
    with open(jsons[0], 'r', encoding='utf-8') as f:
        if jsons[0].endswith('_BoothPage.json'):
            data = json.load(f)
            name, tags = data.get('name', 'N/A'), [t.get('name', '') for t in data.get('tags', [])]
            all_strings_to_translate.extend([name] + tags)
            asset_data_list.append(('json', folder, data, path, data.get('wish_lists_count', 0)))
        else:
            data = json.load(f)
            item = data[0] if data else ""
            if item:
                name_m = re.search(r'break-all\">(.*?)<\/div>', item) or re.search(r'>(.*?)<\/div>', item)
                name = name_m.group(1) if name_m else "N/A"
                all_strings_to_translate.append(name)
                asset_data_list.append(('html', folder, (name, item), path, 0))

bulk_translate(all_strings_to_translate)
if not SKIP_TRANSLATION:
    with open(CACHE_FILE, 'w', encoding='utf-8') as f: json.dump(translation_cache, f, ensure_ascii=False, indent=2)

asset_items_final = []
for type, folder, data, path, wish in asset_data_list:
    if type == 'json':
        web_imgs = [img.get('original', '') for img in data.get('images', [])]
        tags = [t.get('name', '') for t in data.get('tags', [])]
        asset_items_final.append(generate_asset_html(folder, data.get('name', 'N/A'), web_imgs, data.get('url', ''), path, tags, data.get('is_adult', False) or is_adult_content(data.get('name', '')), wish))
    else:
        name, item = data
        img = (re.search(r'src=\"([^\"]+)\"', item) or [None, ""])[1]
        url = (re.search(r'href=\"([^\"]+)\"', item) or [None, ""])[1]
        asset_items_final.append(generate_asset_html(folder, name, [img], url, path, [], is_adult_content(name), 0))

header = f"""<!doctype html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Booth Asset Library</title><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap" rel="stylesheet"><link rel="stylesheet" href="{WEB_DATA_DIR}/style.css"></head><body><div id="menuPerimeter" onclick="toggleMenu(event, true)"></div><nav class="top-nav"><div class="nav-logo" data-i18n="navTitle">Booth Asset Library</div><div class="search-container"><input type="text" id="searchInput" class="search-input" placeholder="Search..." onkeyup="handleSearchInput()"><button id="clearSearch" class="clear-search" onclick="clearSearch()">×</button></div><button id="toggleBtn" class="nav-btn" onclick="toggleMenu(event)" data-i18n="optionsBtn">Options ⚙</button></nav><div id="flyoutMenu" class="flyout-menu"><div class="setting-group"><span class="setting-label" data-i18n="labelLanguage">Language</span><select id="langSelect" onchange="updateLanguage(this.value)"><option value="de">Deutsch</option><option value="en">English</option><option value="es">Español</option><option value="fr">Français</option><option value="ja">日本語</option><option value="ko">한국어</option><option value="nl">Nederlands</option><option value="pt">Português</option><option value="zh-Hans">简体中文</option><option value="zh-Hant">繁體中文</option></select></div><div class="setting-group"><span class="setting-label" data-i18n="labelSort">Sort Order</span><select id="sortOrder" onchange="sortAssets(true)"><option value="id" data-i18n="optId">Folder ID</option><option value="new" data-i18n="optNew">Recently Added</option><option value="name" data-i18n="optName">Alphabetical</option><option value="rel" data-i18n="optRel">Relevance</option><option value="size" data-i18n="optSize">Total Size</option></select></div><div class="setting-group"><span class="setting-label" data-i18n="labelAdult">Adult Filter</span><select id="adultFilter" onchange="applyFilters(true)"><option value="all" data-i18n="optAll">Show All</option><option value="hide" data-i18n="optHide">Hide Adult</option><option value="only" data-i18n="optOnly">Only Adult</option></select></div><div class="setting-group"><span class="setting-label" data-i18n="labelWidth">Card Width</span><input type="range" id="gridRange" min="180" max="500" value="220" oninput="updateGrid(this.value)"></div><div class="setting-group"><span class="setting-label" data-i18n="labelVisual">Visual Controls</span><label style="display:flex; gap:10px; cursor:pointer; font-size:0.9rem; margin-bottom:10px;"><input type="checkbox" id="blurToggle" onchange="updateBlur(this.checked)"> <span data-i18n="optBlur">Disable Blur</span></label><label style="display:flex; gap:10px; cursor:pointer; font-size:0.9rem; margin-bottom:10px;"><input type="checkbox" id="hideIdToggle" onchange="updateIdVisibility(this.checked)"> <span data-i18n="optHideIds">Hide IDs</span></label><label style="display:flex; gap:10px; cursor:pointer; font-size:0.9rem;"><input type="checkbox" id="translateToggle" onchange="updateTranslationVisibility(this.checked)"> <span data-i18n="optTranslate">English Titles</span></label></div></div><div class="container"><ul id="assetList">"""

footer = f"""<li id="filterNotice"></li></ul></div><div id="detailModal" class="modal" onclick="closeModal()"><div class="modal-card" onclick="event.stopPropagation()"><div class="modal-carousel" id="modalCarouselContainer"><button id="carouselPrev" class="carousel-btn btn-prev" onclick="carouselNext(-1)">❮</button><img id="modalBlurBg" class="carousel-blur-bg" src=""><img id="modalImg" class="carousel-main-img" src=""><button id="carouselNext" class="carousel-btn btn-next" onclick="carouselNext(1)">❯</button><div id="carouselDots" class="carousel-dots"></div></div><div class="modal-info"><div id="modalName" class="modal-name"></div><div id="modalSubtitle" class="modal-subtitle"></div><div id="modalTags" style="display:flex; flex-wrap:wrap; gap:6px; margin-bottom:20px;"></div><span class="setting-label" data-i18n="labelBinary">Binary Files</span><ul id="fileList" class="file-list"></ul><div class="modal-footer"><div id="modalIdDisp" class="modal-id-display"></div><div class="modal-actions"><a id="openBoothLink" href="" class="discrete-link" target="_blank"><span data-i18n="footBooth">🛒 Booth</span></a><a id="openFolderLink" href="" class="discrete-link" target="_blank"><span data-i18n="footFolder">📂 Folder</span></a></div></div></div></div></div>
<script>
let translations = {{}};
fetch('{WEB_DATA_DIR}/i18n.json').then(r => r.json()).then(data => {{ translations = data; init(); }});
let currentCarouselIndex = 0, currentImages = [];
const getLS = (k, def) => localStorage.getItem(k) || def;
const state = {{ gridSize: getLS('gridSize', '220'), disableBlur: getLS('disableBlur', 'false') === 'true', sortOrder: getLS('sortOrder', 'id'), adultFilter: getLS('adultFilter', 'all'), hideIds: getLS('hideIds', 'false') === 'true', lang: getLS('lang', 'en'), showTrans: getLS('showTrans', 'true') === 'true' }};
function init() {{ updateLanguage(state.lang); updateGrid(state.gridSize); updateBlur(state.disableBlur); updateIdVisibility(state.hideIds); updateTranslationVisibility(state.showTrans); document.getElementById('gridRange').value = state.gridSize; document.getElementById('blurToggle').checked = state.disableBlur; document.getElementById('sortOrder').value = state.sortOrder; document.getElementById('adultFilter').value = state.adultFilter; document.getElementById('hideIdToggle').checked = state.hideIds; document.getElementById('translateToggle').checked = state.showTrans; handleSearchInput(); sortAssets(); }}
function updateLanguage(lang) {{ state.lang = lang; localStorage.setItem('lang', lang); document.getElementById('langSelect').value = lang; const t = translations[lang] || translations['en']; document.querySelectorAll('[data-i18n]').forEach(el => {{ el.innerText = t[el.dataset.i18n]; }}); applyFilters(); }}
function toggleMenu(e, forceClose = false) {{ if(e) e.stopPropagation(); const menu = document.getElementById('flyoutMenu'), btn = document.getElementById('toggleBtn'), perim = document.getElementById('menuPerimeter'); const open = !forceClose && !menu.classList.contains('open'); menu.classList.toggle('open', open); btn.classList.toggle('active', open); perim.style.display = open ? 'block' : 'none'; }}
function updateGrid(v) {{ document.documentElement.style.setProperty('--grid-size', v + 'px'); localStorage.setItem('gridSize', v); }}
function updateBlur(v) {{ document.body.classList.toggle('no-blur', v); localStorage.setItem('disableBlur', v); }}
function updateIdVisibility(v) {{ document.body.classList.toggle('hide-ids', v); localStorage.setItem('hideIds', v); }}
function updateTranslationVisibility(v) {{ state.showTrans = v; localStorage.setItem('showTrans', v); const items = document.getElementsByClassName('asset'); for(let item of items) {{ const primaryName = item.querySelector('.name-primary'); primaryName.innerText = (v && item.dataset.nameTrans) ? item.dataset.nameTrans : item.dataset.nameOrig; }} }}
function handleSearchInput() {{ applyFilters(); }}
function clearSearch() {{ const i = document.getElementById("searchInput"); i.value = ""; handleSearchInput(); i.focus(); }}
function tagSearch(tag) {{ const s = document.getElementById("searchInput"); s.value = tag; closeModal(); handleSearchInput(); window.scrollTo({{ top: 0, behavior: 'smooth' }}); }}
function applyFilters(save = false) {{
    const query = document.getElementById("searchInput").value.toLowerCase();
    const mode = document.getElementById("adultFilter").value;
    const items = document.getElementsByClassName("asset"), t = translations[state.lang] || translations['en'];
    let count = 0, totalMatchesButHidden = 0;
    if(save) localStorage.setItem('adultFilter', mode);
    for (let item of items) {{
        const isAdult = item.dataset.adult === 'true';
        const searchMatch = item.dataset.search.includes(query);
        const filterMatch = (mode === 'all') || (mode === 'hide' && !isAdult) || (mode === 'only' && isAdult);
        if (searchMatch && !filterMatch) totalMatchesButHidden++;
        const visible = searchMatch && filterMatch;
        if (visible) count++;
        item.style.display = visible ? "" : "none";
        const fc = parseInt(item.dataset.filecount);
        item.querySelector('.file-label-dynamic').innerText = fc + " " + (fc === 1 ? t.fileSingular : t.filePlural);
    }}
    document.getElementById("searchInput").placeholder = t.searchPre + count + t.searchSuf;
    const notice = document.getElementById("filterNotice");
    if (totalMatchesButHidden > 0) {{ notice.innerText = t.hiddenResults.replace('{{n}}', totalMatchesButHidden).trim(); notice.style.display = "flex"; }} else {{ notice.style.display = "none"; }}
}}
function sortAssets(save = false) {{
    const list = document.getElementById('assetList'), order = document.getElementById('sortOrder').value;
    if(save) localStorage.setItem('sortOrder', order);
    const items = Array.from(list.children).filter(el => el.classList.contains('asset'));
    items.sort((a, b) => {{
        if (order === 'id') return parseInt(a.dataset.id) - parseInt(b.dataset.id);
        if (order === 'new') return parseInt(b.dataset.time) - parseInt(a.dataset.time);
        if (order === 'rel') return parseInt(b.dataset.wish) - parseInt(a.dataset.wish);
        if (order === 'name') {{
            const nA = (state.showTrans && a.dataset.nameTrans) ? a.dataset.nameTrans : a.dataset.nameOrig;
            const nB = (state.showTrans && b.dataset.nameTrans) ? b.dataset.nameTrans : b.dataset.nameOrig;
            return nA.toLowerCase().localeCompare(nB.toLowerCase());
        }}
        return parseInt(b.dataset.bytes) - parseInt(a.dataset.bytes);
    }});
    const notice = document.getElementById('filterNotice');
    list.innerHTML = ""; items.forEach(i => list.appendChild(i));
    list.appendChild(notice); applyFilters();
}}
function openDetails(id) {{
    const el = document.querySelector(`.asset[data-id="${{id}}"]`), t = translations[state.lang] || translations['en'];
    const displayTitle = (state.showTrans && el.dataset.nameTrans) ? el.dataset.nameTrans : el.dataset.nameOrig;
    const subtitle = (state.showTrans && el.dataset.nameTrans) ? el.dataset.nameOrig : "";
    document.getElementById("modalName").innerText = displayTitle; document.getElementById("modalSubtitle").innerText = subtitle; document.getElementById("modalIdDisp").innerText = "#" + id; document.getElementById("openFolderLink").href = el.dataset.folder; document.getElementById("openBoothLink").href = el.dataset.boothUrl;
    currentImages = JSON.parse(el.dataset.allImages); currentCarouselIndex = 0; updateCarousel();
    const tags = JSON.parse(el.dataset.tags); const tagContainer = document.getElementById("modalTags");
    tagContainer.innerHTML = tags.map(tg => `<span class="tag-pill" onclick="tagSearch('${{tg.replace(/'/g, "\\\\'")}}')">${{tg}}</span>`).join('');
    const fileData = JSON.parse(el.dataset.files);
    document.getElementById("fileList").innerHTML = fileData.map(f => `<li class="file-item"><a class="file-link" href="${{f.path}}" target="_blank">${{f.name}}</a><span>${{f.size}}</span></li>`).join('');
    const m = document.getElementById("detailModal"); m.classList.add('visible'); setTimeout(() => m.classList.add('active'), 10);
}}
function closeModal() {{ const m = document.getElementById("detailModal"); m.classList.remove('active'); setTimeout(() => m.classList.remove('visible'), 300); }}
function carouselNext(dir) {{ currentCarouselIndex = (currentCarouselIndex + dir + currentImages.length) % currentImages.length; updateCarousel(); }}
function updateCarousel() {{ 
    const img = currentImages[currentCarouselIndex]; document.getElementById("modalImg").src = img; document.getElementById("modalBlurBg").src = img;
    const dots = document.getElementById("carouselDots");
    dots.innerHTML = currentImages.map((_, i) => `<div class="dot ${{i === currentCarouselIndex ? 'active' : ''}}" onclick="currentCarouselIndex=${{i}}; updateCarousel()"></div>`).join('');
}}
window.onclick = e => {{ if (e.target.id === 'menuPerimeter') toggleMenu(null, true); }};
</script></body></html>"""

with open(OUTPUT_FILE, 'w', encoding='utf-8') as f: f.write(header + "\n".join(asset_items_final) + footer)
print("Library was updated")