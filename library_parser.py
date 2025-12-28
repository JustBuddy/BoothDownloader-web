import os
import json
import glob
import re
import time
import sys
from urllib.parse import quote, unquote
from concurrent.futures import ThreadPoolExecutor, as_completed
from deep_translator import GoogleTranslator
from PIL import Image

# Configuration
ROOT_FOLDER = "BoothDownloaderOut"
OUTPUT_FILE = "asset_library.html"
CACHE_FILE = "translation_cache.json"
DESC_CACHE_FILE = "web_data/descriptions.json"
FILTER_FILE = "web_data/filters.json" 
SKIP_TRANSLATION = False  
MAX_WORKERS = 5 

# Thumbnail Optimization
OPTIMIZE_THUMBNAILS = True
THUMBNAIL_SIZE = (256, 256)
IMG_OUT_DIR = "img"

# Keywords that should NEVER be considered an avatar name
FORBIDDEN_NAMES = {
    "vrchat", "vrc", "unity", "fbx", "avatar", "3d", "model", "quest", "pc", 
    "original", "character", "boy", "girl", "boy's", "girl's", "android", "human",
    "unlisted", "adult", "preview", "cloth", "clothing", "accessory", "hair",
    "eye", "texture", "physbone", "blendshape", "maya", "blender", "hotogiya"
}

print(f"--- Starting Library Generation ---")

if not os.path.exists("web_data"):
    os.makedirs("web_data")

if OPTIMIZE_THUMBNAILS and not os.path.exists(IMG_OUT_DIR):
    os.makedirs(IMG_OUT_DIR)

# Load External Filters
ADULT_KEYWORDS = [
    r"R-?18", r"adult", r"nude", r"semen", r"nsfw", r"sexual", r"erotic", 
    r"pussy", r"dick", r"vagina", r"penis", r"otimpo", r"otinpo",
    "精液", "だぷだぷ", "ヌード", "エロ", "クリトリス", "おまんこ", "おちんぽ", "おてぃんぽ"
]
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

def contains_japanese(text):
    return bool(re.search(r'[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]', str(text)))

def translate_single_text(text):
    if not text or not contains_japanese(text) or SKIP_TRANSLATION:
        return text
    try:
        return GoogleTranslator(source='auto', target='en').translate(text)
    except:
        return text

def print_progress(current, total, label="Progress"):
    percent = (current / total) * 100
    if sys.stdout.isatty():
        bar_length = 30
        done = int(bar_length * current / total)
        bar = "█" * done + "░" * (bar_length - done)
        sys.stdout.write(f"\r[Translate] {label}: |{bar}| {percent:.1f}% ({current}/{total}) ")
        sys.stdout.flush()
        if current == total:
            sys.stdout.write("\n")
    else:
        if current == 1 or current == total or current % max(1, (total // 20)) == 0:
            print(f"[Translate] {label}: {percent:.1f}% ({current}/{total})")

def bulk_translate_short_terms(text_list):
    if SKIP_TRANSLATION: return
    japanese_strings = list(set(str(t).strip() for t in text_list if t and contains_japanese(t) and len(str(t)) < 500))
    new_strings = [t for t in japanese_strings if t not in translation_cache]
    if not new_strings: return

    total = len(new_strings)
    print(f"[Translate] Queuing {total} short terms...")
    
    def translate_task(item):
        try:
            res = GoogleTranslator(source='auto', target='en').translate(item)
            return item, res
        except:
            return item, None

    completed = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_term = {executor.submit(translate_task, term): term for term in new_strings}
        for future in as_completed(future_to_term):
            original, translated = future.result()
            if translated:
                translation_cache[original] = translated
            completed += 1
            print_progress(completed, total, "Short Terms")
    
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(translation_cache, f, ensure_ascii=False, indent=2)

def get_optimized_thumb(asset_id, original_path):
    if not original_path or not os.path.exists(original_path): return ""
    if not original_path.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
        return quote(original_path.replace('\\', '/'))
    thumb_name = f"{asset_id}_thumb.webp"
    thumb_path = os.path.join(IMG_OUT_DIR, thumb_name)
    if not os.path.exists(thumb_path):
        try:
            with Image.open(original_path) as img:
                width, height = img.size
                if width != height:
                    min_dim = min(width, height)
                    img = img.crop(((width-min_dim)/2, (height-min_dim)/2, (width+min_dim)/2, (height+min_dim)/2))
                img.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
                img.save(thumb_path, "WEBP", optimize=True, quality=80)
        except: return quote(original_path.replace('\\', '/'))
    return quote(thumb_path.replace('\\', '/'))

HTML_PART_1 = """<!doctype html>
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
        
        .asset-link-view-all { 
            display: flex; 
            align-items: center; 
            justify-content: center; 
            background: rgba(253, 218, 13, 0.05); 
            border: 1px dashed #FDDA0D; 
            border-radius: 6px; 
            text-decoration: none; 
            transition: 0.2s; 
            padding: 8px;
            height: 46px;
            box-sizing: border-box;
        }
        .asset-link-view-all:hover { background: rgba(253, 218, 13, 0.15); transform: translateY(-2px); }
        .asset-link-view-all span { color: #FDDA0D; font-size: 0.65rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.5px; }
        .asset-link-grid { align-items: stretch; }
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
                <select id="langSelect" onchange="updateLanguage(this.value)">
                    <option value="de">Deutsch</option><option value="en">English</option><option value="es">Español</option><option value="fr">Français</option><option value="ja">日本語</option><option value="ko">한국어</option><option value="nl">Nederlands</option><option value="pt">Português</option><option value="zh-Hans">简体中文</option><option value="zh-Hant">繁體中文</option>
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
        <div class="container"><ul id="assetList">"""

HTML_PART_2 = """<li id="filterNotice"></li></ul></div>
    </div>
    <div id="detailModal" class="modal" onclick="closeModal()">
        <div class="modal-card" onclick="event.stopPropagation()">
            <div class="modal-carousel" id="modalCarouselContainer">
                <button id="carouselPrev" class="carousel-btn btn-prev" onclick="carouselNext(-1)">❮</button>
                <img id="modalBlurBg" class="carousel-blur-bg" src="">
                <img id="modalImg" class="carousel-main-img" src="">
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
    <script>
        const translations = {
            en: { btnDetails: "Details", labelComp: "Compatible Assets", labelDesigned: "Designed For", labelViewRel: "View All", warnDelisted: "<b>⚠️ Delisted Item</b> This asset may no longer be available on Booth.", navTitle: "Booth Asset Library", optionsBtn: "Options ⚙", labelLanguage: "Language", labelSort: "Sort Order", optId: "Folder ID", optNew: "Recently Added", optName: "A-Z Name", optRel: "Popularity", optSize: "Storage Size", labelAdult: "Content Filter", optAll: "Show Everything", optHide: "Hide Adult", optOnly: "Adult Only", labelWidth: "Card Display Width", optBlur: "Disable Blur", optHideIds: "Hide Asset IDs", optTranslate: "Show English Titles", labelBinary: "Local Files", footBooth: "🛒 View on Booth", footFolder: "📂 Open Folder", footVrcAvatar: "👤 Public Avatar", footVrcWorld: "🌐 Public World", searchPre: "Searching ", searchSuf: " assets...", fileSingular: "file", filePlural: "files", moreTags: "+ {n} others", hiddenResults: " ({n} items hidden by filter)", statItems: "Total Assets", statSize: "Library Size", statImgSize: "Graphics Size", statSpent: "Estimated Investment", statUpdated: "Last Refreshed", labelTopTags: "Frequent Tags", btnDesc: "Description" },
            ja: { btnDetails: "詳細", labelComp: "対応アセット", labelDesigned: "対応モデル", labelViewRel: "すべて見る", warnDelisted: "<b>⚠️ 公開停止</b> このアイテムは現在Boothで公開されていない可能性があります。", navTitle: "Boothアセットライブラリ", optionsBtn: "設定 ⚙", labelLanguage: "表示言語", labelSort: "並び替え", optId: "ID順", optNew: "追加日順", optName: "名前順", optRel: "人気順", optSize: "サイズ順", labelAdult: "成人向けフィルター", optAll: "すべて表示", optHide: "成人向けを隠す", optOnly: "成人向けのみ", labelWidth: "カードの幅", optBlur: "ぼかしを無効化", optHideIds: "IDを非表示", optTranslate: "翻訳された名前を表示", labelBinary: "構成ファイル", footBooth: "🛒 Boothで見る", footFolder: "📂 フォルダを開く", footVrcAvatar: "👤 パブリックアバター", footVrcWorld: "🌐 パブリックワールド", searchPre: "検索中: ", searchSuf: " 件", fileSingular: "ファイル", filePlural: "ファイル", moreTags: "他 {n} 件", hiddenResults: " ({n} 件が非表示)", statItems: "総アイテム数", statSize: "ライブラリ容量", statImgSize: "グラフィックス容量", statSpent: "推定支出合計", statUpdated: "最終更新", labelTopTags: "人気のタグ", btnDesc: "商品説明" },
            ko: { btnDetails: "상세 정보", labelComp: "호환 에셋", labelDesigned: "호환 모델", labelViewRel: "모두 보기", warnDelisted: "<b>⚠️ 판매 중지됨</b> 이 에셋은 현재 Booth에서 제공되지 않을 수 있습니다.", navTitle: "Booth 에셋 라이브러리", optionsBtn: "설정 ⚙", labelLanguage: "언어 선택", labelSort: "정렬 기준", optId: "폴더 ID", optNew: "최근 추가됨", optName: "이름순", optRel: "인기순", optSize: "용량순", labelAdult: "성인 콘텐츠 필터", optAll: "모두 보기", optHide: "성인 콘텐츠 숨기기", optOnly: "성인 콘텐츠만", labelWidth: "카드 너비", optBlur: "블러 효과 끄기", optHideIds: "항목 ID 숨기기", optTranslate: "번역된 제목 사용", labelBinary: "로컬 파일", footBooth: "🛒 Booth에서 보기", footFolder: "📂 폴더 열기", footVrcAvatar: "👤 퍼블릭 아바타", footVrcWorld: "🌐 퍼블릭 월드", searchPre: "検索結果: ", searchSuf: "개", fileSingular: "파일", filePlural: "파일", moreTags: "+ {n}개 더보기", hiddenResults: " ({n}개 필터링됨)", statItems: "총 에셋 수", statSize: "전체 용량", statImgSize: "그래픽 용량", statSpent: "예상 총 지출", statUpdated: "마지막 업데이트", labelTopTags: "가장 많이 쓰인 태그", btnDesc: "설명" },
            'zh-Hans': { btnDetails: "详细信息", labelComp: "兼容资源", labelDesigned: "设计用于", labelViewRel: "查看全部", warnDelisted: "<b>⚠️ 已下架内容</b> 此资源可能已在 Booth 停止售卖。", navTitle: "Booth 资源库", optionsBtn: "选项 ⚙", labelLanguage: "语言设置", labelSort: "排序方式", optId: "文件夹 ID", optNew: "最近添加", optName: "名称排序", optRel: "人气相关", optSize: "占用空间", labelAdult: "成人内容过滤", optAll: "显示全部内容", optHide: "隐藏成人内容", optOnly: "仅成人内容", labelWidth: "卡片显示宽度", optBlur: "禁用模糊效果", optHideIds: "隐藏资源 ID", optTranslate: "显示翻译名称", labelBinary: "本地文件", footBooth: "🛒 在 Booth 打开", footFolder: "📂 打开本地目录", footVrcAvatar: "👤 公开化身", footVrcWorld: "🌐 公开世界", searchPre: "正在搜索 ", searchSuf: " 个资源...", fileSingular: "文件", filePlural: "文件", moreTags: "+ {n} 个其他", hiddenResults: " ({n} 个已被过滤)", statItems: "资源总数", statSize: "库总大小", statImgSize: "图片大小", statSpent: "预计总支出", statUpdated: "最後更新時間", labelTopTags: "高频标签", btnDesc: "资源描述" },
            'zh-Hant': { btnDetails: "詳細資訊", labelComp: "相容資源", labelDesigned: "設計用於", labelViewRel: "查看全部", warnDelisted: "<b>⚠️ 已下架內容</b> 此資源可能已在 Booth 販售。", navTitle: "Booth 資源庫", optionsBtn: "選項 ⚙", labelLanguage: "語言設置", labelSort: "排序方式", optId: "資料夾 ID", optNew: "最近添加", optName: "名稱排序", optRel: "人氣相關", optSize: "占用空間", labelAdult: "成人內容過濾", optAll: "顯示全部內容", optHide: "隱藏成人內容", optOnly: "僅限成人內容", labelWidth: "卡片顯示寬度", optBlur: "禁用模糊效果", optHideIds: "隱藏資源 ID", optTranslate: "顯示翻譯名稱", labelBinary: "本地檔案", footBooth: "🛒 在 Booth 打開", footFolder: "📂 打開資料夾", footVrcAvatar: "👤 公開化身", footVrcWorld: "🌐 公開世界", searchPre: "正在搜尋 ", searchSuf: " 個資源...", fileSingular: "檔案", filePlural: "檔案", moreTags: "+ {n} 個其他", hiddenResults: " ({n} 個已被過濾)", statItems: "資源總數", statSize: "庫總大小", statImgSize: "圖片大小", statSpent: "預計總支出", statUpdated: "最後更新時間", labelTopTags: "高頻標籤", btnDesc: "詳細描述" },
            de: { btnDetails: "Details", labelComp: "Passendes Zubehör", labelDesigned: "Entwickelt für", labelViewRel: "Alle zeigen", warnDelisted: "<b>⚠️ Nicht mehr gelistet</b> Dieses Asset ist möglicherweise nicht mehr verfügbar.", navTitle: "Booth Bibliothek", optionsBtn: "Optionen ⚙", labelLanguage: "Sprache", labelSort: "Sortierung", optId: "Ordner ID", optNew: "Zuletzt hinzugefügt", optName: "Name (A-Z)", optRel: "Beliebtheit", optSize: "Dateigröße", labelAdult: "Filter", optAll: "Alles zeigen", optHide: "Nicht jugendfrei ausblenden", optOnly: "Nur 18+", labelWidth: "Kartenbreite", optBlur: "Kein Fokus", optHideIds: "IDs verbergen", optTranslate: "Übersetzte Titel", labelBinary: "Dateien", footBooth: "🛒 Auf Booth ansehen", footFolder: "📂 Ordner öffnen", footVrcAvatar: "👤 Avatar-Link", footVrcWorld: "🌐 Welt-Link", searchPre: "Suche ", searchSuf: " Artikel...", fileSingular: "Datei", filePlural: "Dateien", moreTags: "+ {n} weitere", hiddenResults: " ({n} durch Filter versteckt)", statItems: "Gesamtanzahl", statSize: "Binärgröße", statImgSize: "Grafikgröße", statSpent: "Voraussichtliche Kosten", statUpdated: "Aktualisiert", labelTopTags: "Häufige Tags", btnDesc: "Beschreibung" },
            nl: { btnDetails: "Details", labelComp: "Compatibele Assets", labelDesigned: "Ontworpen voor", labelViewRel: "Toon alles", warnDelisted: "<b>⚠️ Verwijderde Inhoud</b> Dit item is mogelijk nicht langer beschikbaar.", navTitle: "Booth Bibliotheek", optionsBtn: "Opties ⚙", labelLanguage: "Taal", labelSort: "Sorteren", optId: "ID", optNew: "Nieuwste eerst", optName: "Naam", optRel: "Relevantie", optSize: "Grootte", labelAdult: "Filter", optAll: "Alles tonen", optHide: "Verberg 18+", optOnly: "Alleen 18+", labelWidth: "Breedte", optBlur: "Geen vervaging", optHideIds: "ID's verbergen", optTranslate: "Vertaalde titels", labelBinary: "Bestanden", footBooth: "🛒 Bekijk op Booth", footFolder: "📂 Map openen", footVrcAvatar: "👤 Openbare Avatar", footVrcWorld: "🌐 Openbare Wereld", searchPre: "Zoek in ", searchSuf: " items...", fileSingular: "bestand", filePlural: "bestanden", moreTags: "+ {n} meer", hiddenResults: " ({n} items verborgen)", statItems: "Totaal Brass", statSize: "Totale grootte", statImgSize: "Beeldgrootte", statSpent: "Geschatte totale kosten", statUpdated: "Laatste update", labelTopTags: "Populaire tags", btnDesc: "Beschreibung" },
            fr: { btnDetails: "Détails", labelComp: "Assets Compatibles", labelDesigned: "Conçu pour", labelViewRel: "Tout voir", warnDelisted: "<b>⚠️ Contenu non listé</b> Cet asset n'est probablement plus disponible.", navTitle: "Bibliothèque Booth", optionsBtn: "Options ⚙", labelLanguage: "Langue", labelSort: "Trier par", optId: "ID du dossier", optNew: "Ajoutés récemment", optName: "Nom (A-Z)", optRel: "Popularité", optSize: "Taille totale", labelAdult: "Filtre de contenu", optAll: "Tout afficher", optHide: "Masquer Adulte", optOnly: "Adulte uniquement", labelWidth: "Largeur des cartes", optBlur: "Désactiver le flou", optHideIds: "Masquer les IDs", optTranslate: "Titres traduits", labelBinary: "Fichiers locaux", footBooth: "🛒 Voir sur Booth", footFolder: "📂 Ouvrir le dossier", footVrcAvatar: "👤 Avatar Public", footVrcWorld: "🌐 Monde Public", searchPre: "Recherche de ", searchSuf: " items...", fileSingular: "fichier", filePlural: "fichiers", moreTags: "+ {n} de plus", hiddenResults: " ({n} masqués par filtre)", statItems: "Total des assets", statSize: "Taille binaire", statImgSize: "Taille images", statSpent: "Investissement estimé", statUpdated: "Mis à jour le", labelTopTags: "Tags fréquents", btnDesc: "Description" },
            es: { btnDetails: "Details", labelComp: "Activos Compatibles", labelDesigned: "Diseñado para", labelViewRel: "Ver todo", warnDelisted: "<b>⚠️ Item no disponible</b> Es probable que este conteúdo ya no esté.", navTitle: "Biblioteca Booth", optionsBtn: "Opciones ⚙", labelLanguage: "Idioma", labelSort: "Ordenar por", optId: "ID de carpeta", optNew: "Añadidos recentemente", optName: "Nombre (A-Z)", optRel: "Relevancia", optSize: "Tamaño", labelAdult: "Filtro de conteúdo", optAll: "Mostrar todo", optHide: "Ocultar adultos", optOnly: "Solo adultos", labelWidth: "Ancho de tarjeta", optBlur: "Quitar desenfoque", optHideIds: "Ocultar IDs", optTranslate: "Títulos traducidos", labelBinary: "Archivos locales", footBooth: "🛒 Ver en Booth", footFolder: "📂 Abrir carpeta", footVrcAvatar: "👤 Avatar Público", footVrcWorld: "🌐 Mundo Público", searchPre: "Buscando ", searchSuf: " activos...", fileSingular: "archivo", filePlural: "archivos", moreTags: "+ {n} outros", hiddenResults: " ({n} ocultos)", statItems: "Activos totales", statSize: "Tamaño binario", statImgSize: "Tamaño images", statSpent: "Inversión estimada", statUpdated: "Última actualización", labelTopTags: "Etiquetas comunes", btnDesc: "Description" },
            pt: { btnDetails: "Detalhes", labelComp: "Assets Compatíveis", labelDesigned: "Projetado para", labelViewRel: "Ver todos", warnDelisted: "<b>⚠️ Conteúdo removido</b> Este asset pode não estar mais disponible.", navTitle: "Biblioteca Booth", optionsBtn: "Opções ⚙", labelLanguage: "Idioma", labelSort: "Ordenar por", optId: "ID da pasta", optNew: "Adicionados recentemente", optName: "Nombre (A-Z)", optRel: "Popularidade", optSize: "Tamanho total", labelAdult: "Filtre de conteúdo", optAll: "Mostrar tudo", optHide: "Ocultar 18+", optOnly: "Apenas 18+", labelWidth: "Largura dos cards", optBlur: "Sem desfoque", optHideIds: "Ocultar IDs", optTranslate: "Títulos traducidos", labelBinary: "Arquivos locais", footBooth: "🛒 Ver no Booth", footFolder: "📂 Abrir pasta", footVrcAvatar: "👤 Avatar Público", footVrcWorld: "🌐 Mundo Público", searchPre: "Pesquisando ", searchSuf: " itens...", fileSingular: "arquivo", filePlural: "arquivos", moreTags: "+ {n} outros", hiddenResults: " ({n} itens ocultos)", statItems: "Total de itens", statSize: "Tamanho binário", statImgSize: "Tamanho images", statSpent: "Investimento estimado", statUpdated: "Última actualización", labelTopTags: "Tags frequentes", btnDesc: "Descrição" }
        };
        let currentCarouselIndex = 0, currentImages = [];
        const baseTitle = "Booth Asset Library";
        const getLS = (k, def) => localStorage.getItem(k) || def;
        const state = { gridSize: getLS('gridSize', '220'), disableBlur: getLS('disableBlur', 'false') === 'true', sortOrder: getLS('sortOrder', 'id'), adultFilter: getLS('adultFilter', 'all'), hideIds: getLS('hideIds', 'false') === 'true', lang: getLS('lang', 'en'), showTrans: getLS('showTrans', 'true') === 'true' };
        
        function formatBytes(bytes) {
            if (bytes === 0) return '0 B';
            const k = 1024, sizes = ['B', 'KB', 'MB', 'GB', 'TB'], i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        }

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
            requestAnimationFrame(() => {
                requestAnimationFrame(() => {
                    updateLanguage(state.lang); updateGrid(state.gridSize); updateBlur(state.disableBlur); updateIdVisibility(state.hideIds); updateTranslationVisibility(state.showTrans);
                    document.getElementById('gridRange').value = state.gridSize; document.getElementById('blurToggle').checked = state.disableBlur; document.getElementById('sortOrder').value = state.sortOrder;
                    document.getElementById('adultFilter').value = state.adultFilter; document.getElementById('hideIdToggle').checked = state.hideIds; document.getElementById('translateToggle').checked = state.showTrans;
                    
                    const items = document.getElementsByClassName('asset');
                    let totalBinaryBytes = 0, totalImageBytes = 0;
                    const tagCounts = {}, spent = {};

                    for(let item of items) { 
                        totalBinaryBytes += parseInt(item.dataset.bytes || 0); 
                        totalImageBytes += parseInt(item.dataset.imgBytes || 0); 
                        const tags = JSON.parse(item.dataset.tags || "[]");
                        tags.forEach(t => tagCounts[t] = (tagCounts[t] || 0) + 1);
                        const pVal = parseFloat(item.dataset.priceValue || 0), pCur = item.dataset.priceCurrency || "";
                        if (pVal > 0 && pCur) spent[pCur] = (spent[pCur] || 0) + pVal;
                        observer.observe(item);
                    }

                    const topTags = Object.entries(tagCounts).sort((a,b) => b[1] - a[1]).slice(0, 10);
                    document.getElementById('commonTags').innerHTML = topTags.map(([tag]) => `<span class="tag-pill clickable" onclick="tagSearch('${tag.replace(/'/g, "\\\\'")}')">${tag}</span>`).join('');

                    document.getElementById('statCount').innerText = items.length;
                    document.getElementById('statSize').innerText = formatBytes(totalBinaryBytes);
                    document.getElementById('statImgSize').innerText = formatBytes(totalImageBytes);
                    document.getElementById('statSpent').innerText = Object.entries(spent).map(([cur, val]) => val.toLocaleString() + " " + cur).join(" / ") || "0";
                    document.getElementById('statDate').innerText = new Date().toLocaleDateString();

                    const urlParams = new URLSearchParams(window.location.search);
                    const queryParam = urlParams.get('q');
                    if (queryParam) {
                        document.getElementById("searchInput").value = queryParam;
                    }

                    handleSearchInput(); sortAssets();
                    const targetId = urlParams.get('id');
                    if (targetId) openDetails(targetId, true);
                    setTimeout(() => { document.body.classList.add('loaded'); }, 50);
                });
            });
        }

        window.onpopstate = (e) => {
            const urlParams = new URLSearchParams(window.location.search);
            const targetId = urlParams.get('id');
            const targetQuery = urlParams.get('q') || "";
            
            if (document.getElementById("searchInput").value !== targetQuery) {
                document.getElementById("searchInput").value = targetQuery;
                applyFilters();
            }

            if (targetId) openDetails(targetId, true); else closeModal(true);
        };

        function updateLanguage(lang) { 
            state.lang = lang; localStorage.setItem('lang', lang); 
            document.getElementById('langSelect').value = lang; 
            const t = translations[lang] || translations['en']; 
            document.querySelectorAll('[data-i18n]').forEach(el => { el.innerText = t[el.dataset.i18n]; }); 
            document.querySelectorAll('[data-i18n-html]').forEach(el => { el.innerHTML = t[el.dataset.i18nHtml]; });
            applyFilters(); 
        }
        function toggleMenu(e, forceClose = false) { if(e) e.stopPropagation(); const menu = document.getElementById('flyoutMenu'), btn = document.getElementById('toggleBtn'), perim = document.getElementById('menuPerimeter'); const open = !forceClose && !menu.classList.contains('open'); menu.classList.toggle('open', open); btn.classList.toggle('active', open); perim.style.display = open ? 'block' : 'none'; }
        function updateGrid(v) { document.documentElement.style.setProperty('--grid-size', v + 'px'); localStorage.setItem('gridSize', v); }
        function updateBlur(v) { document.body.classList.toggle('no-blur', v); localStorage.setItem('disableBlur', v); }
        function updateIdVisibility(v) { document.body.classList.toggle('hide-ids', v); localStorage.setItem('hideIds', v); }
        
        function formatDescription(text) {
            if (!text) return "";
            const urlRegex = /(https?:\\/\\/[^\\s\\n]+)/g;
            return text.replace(urlRegex, (url) => `<a href="${url}" target="_blank" onclick="event.stopPropagation()">${url}</a>`);
        }

        function updateTranslationVisibility(v) { 
            state.showTrans = v; localStorage.setItem('showTrans', v); 
            const items = document.getElementsByClassName('asset'); 
            for(let item of items) { 
                const primaryName = item.querySelector('.name-primary'); 
                primaryName.innerText = (v && item.dataset.nameTrans) ? item.dataset.nameTrans : item.dataset.nameOrig;
                const authorPrimary = item.querySelector('.author-primary');
                authorPrimary.innerText = (v && item.dataset.authorTrans) ? item.dataset.authorTrans : item.dataset.authorOrig;
            } 
            const modal = document.getElementById('detailModal');
            if (modal.classList.contains('active')) {
                const id = new URLSearchParams(window.location.search).get('id');
                const el = document.querySelector(`.asset[data-id="${id}"]`);
                if (el) {
                    const raw = (v && el.dataset.descTrans) ? el.dataset.descTrans : el.dataset.descOrig;
                    document.getElementById('modalDesc').innerHTML = formatDescription(raw);
                }
            }
        }
        function handleSearchInput() { 
            const query = document.getElementById("searchInput").value;
            const newUrl = new URL(window.location);
            if (query) newUrl.searchParams.set('q', query); else newUrl.searchParams.delete('q');
            window.history.replaceState({}, '', newUrl);
            applyFilters(); 
        }
        function clearSearch() { const i = document.getElementById("searchInput"); i.value = ""; handleSearchInput(); i.focus(); }
        
        function tagSearch(query, isAuthor = false) {
            const s = document.getElementById("searchInput");
            const finalQuery = (query.startsWith('rel:') || isAuthor) ? (isAuthor ? `author:${query}` : query) : query;
            s.value = finalQuery;
            
            const newUrl = new URL(window.location);
            newUrl.searchParams.set('q', finalQuery);
            window.history.pushState({}, '', newUrl);
            
            closeModal();
            handleSearchInput();
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }

        function applyFilters(save = false) {
            let query = document.getElementById("searchInput").value.toLowerCase();
            const mode = document.getElementById("adultFilter").value;
            const items = document.getElementsByClassName("asset"), t = translations[state.lang] || translations['en'];
            let count = 0, totalMatchesButHidden = 0;
            if(save) { state.adultFilter = mode; localStorage.setItem('adultFilter', mode); }

            const isAuthorSearch = query.startsWith('author:');
            const isRelSearch = query.startsWith('rel:');
            
            const authorQuery = isAuthorSearch ? query.replace('author:', '').trim() : '';
            const relQuery = isRelSearch ? query.replace('rel:', '').trim() : '';

            for (let item of items) {
                const isAdult = item.dataset.adult === 'true';
                const filterMatch = (mode === 'all') || (mode === 'hide' && !isAdult) || (mode === 'only' && isAdult);
                
                let searchMatch = false;
                if (isRelSearch) {
                    const links = JSON.parse(item.dataset.links || "[]");
                    searchMatch = (item.dataset.id === relQuery) || links.includes(relQuery);
                } else if (isAuthorSearch) {
                    const authorO = item.dataset.authorOrig.toLowerCase();
                    const authorT = item.dataset.authorTrans.toLowerCase();
                    searchMatch = (authorO === authorQuery) || (authorT === authorQuery) || (authorO.includes(authorQuery)) || (authorT.includes(authorQuery));
                } else {
                    searchMatch = item.dataset.search.includes(query);
                }

                if (searchMatch && !filterMatch) totalMatchesButHidden++;
                const visible = searchMatch && filterMatch;
                if (visible) { count++; item.style.display = ""; observer.observe(item); } else { item.style.display = "none"; }
                const fc = parseInt(item.dataset.filecount);
                item.querySelector('.file-label-dynamic').innerText = fc + " " + (fc === 1 ? t.fileSingular : t.filePlural);
            }
            document.getElementById("searchInput").placeholder = t.searchPre + count + t.searchSuf;
            const notice = document.getElementById("filterNotice");
            if (totalMatchesButHidden > 0) { notice.innerText = t.hiddenResults.replace('{n}', totalMatchesButHidden).trim(); notice.style.display = "flex"; } else { notice.style.display = "none"; }
        }

        function sortAssets(save = false) {
            const list = document.getElementById('assetList'), order = document.getElementById('sortOrder').value;
            if(save) localStorage.setItem('sortOrder', order);
            const items = Array.from(list.children).filter(el => el.classList.contains('asset'));
            items.sort((a, b) => {
                if (order === 'id') return parseInt(a.dataset.id) - parseInt(b.dataset.id);
                if (order === 'new') return parseInt(b.dataset.time) - parseInt(a.dataset.time);
                if (order === 'rel') return parseInt(b.dataset.wish) - parseInt(a.dataset.wish);
                if (order === 'name') {
                    const nA = (state.showTrans && a.dataset.nameTrans) ? a.dataset.nameTrans : a.dataset.nameOrig;
                    const nB = (state.showTrans && b.dataset.nameTrans) ? b.dataset.nameTrans : b.dataset.nameOrig;
                    return nA.toLowerCase().localeCompare(nB.toLowerCase());
                }
                return parseInt(b.dataset.bytes) - parseInt(a.dataset.bytes);
            });
            const notice = document.getElementById('filterNotice');
            list.innerHTML = ""; items.forEach(i => list.appendChild(i));
            list.appendChild(notice); applyFilters();
        }

        function switchTab(tabId) {
            document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            const pane = document.getElementById('pane-' + tabId);
            if (pane) pane.classList.add('active');
            const tab = document.getElementById('tab-' + tabId);
            if (tab) tab.classList.add('active');
        }
        
        function openDetails(id, skipHistory = false) {
            const el = document.querySelector(`.asset[data-id="${id}"]`), t = translations[state.lang] || translations['en'];
            if(!el) return;
            
            switchTab('details');
            document.getElementById("modalImg").src = ""; 
            document.getElementById("modalBlurBg").src = "";
            currentImages = JSON.parse(el.dataset.allImages); 
            currentCarouselIndex = 0; 
            updateCarousel();

            const displayTitle = (state.showTrans && el.dataset.nameTrans) ? el.dataset.nameTrans : el.dataset.nameOrig;
            const authorOrig = el.dataset.authorOrig;
            const authorTrans = (state.showTrans && el.dataset.authorTrans) ? el.dataset.authorTrans : authorOrig;
            
            document.getElementById("modalName").innerText = displayTitle;
            document.getElementById("modalSubtitle").innerHTML = `by <a class="modal-author-link" onclick="tagSearch('${authorOrig.replace(/'/g, "\\\\'")}', true)"><b class="author-primary">${authorTrans}</b></a>`;
            
            const meta = [];
            if (el.dataset.nameTrans && state.showTrans) meta.push(`<div class="meta-pill">${el.dataset.nameOrig}</div>`);
            meta.push(`<div class="meta-pill">${el.dataset.priceCurrency} ${parseFloat(el.dataset.priceValue).toLocaleString()}</div>`);
            document.getElementById("modalMeta").innerHTML = meta.join('');

            document.getElementById("modalIdDisp").innerText = "#" + id;
            document.getElementById("openFolderLink").href = el.dataset.folder;
            document.getElementById("openBoothLink").href = el.dataset.boothUrl;
            document.getElementById("delistedWarn").style.display = (el.dataset.limited === 'true') ? 'block' : 'none';
            
            const vrcA = el.dataset.vrcAvatarLink, vrcW = el.dataset.vrcWorldLink;
            document.getElementById("openVrcAvatarLink").style.display = vrcA ? "block" : "none";
            document.getElementById("openVrcAvatarLink").href = vrcA || "";
            document.getElementById("openVrcWorldLink").style.display = vrcW ? "block" : "none";
            document.getElementById("openVrcWorldLink").href = vrcW || "";

            const tags = JSON.parse(el.dataset.tags), tagContainer = document.getElementById("modalTags");
            tagContainer.innerHTML = tags.map(tg => `<span class="tag-pill clickable" onclick="tagSearch('${tg.replace(/'/g, "\\\\'")}')">${tg}</span>`).join('');

            const transDesc = (state.showTrans && el.dataset.descTrans) ? el.dataset.descTrans : el.dataset.descOrig;
            document.getElementById("modalDesc").innerHTML = formatDescription(transDesc || "");
            document.getElementById("tab-description").style.display = (transDesc && transDesc.trim()) ? "block" : "none";

            const isAvatar = el.dataset.isAvatar === 'true';
            const links = JSON.parse(el.dataset.links || "[]");
            const relSection = document.getElementById("relSection");
            if (links.length > 0) {
                relSection.style.display = "block";
                document.getElementById("relTitle").innerText = isAvatar ? t.labelComp : t.labelDesigned;

                let relationshipHtml = links.map(linkId => {
                    const target = document.querySelector(`.asset[data-id="${linkId}"]`);
                    if (!target) return "";
                    
                    const isTargetAdult = target.dataset.adult === 'true';
                    const mode = state.adultFilter;
                    const filterMatch = (mode === 'all') || (mode === 'hide' && !isTargetAdult) || (mode === 'only' && isTargetAdult);
                    if (!filterMatch) return "";

                    const n = (state.showTrans && target.dataset.nameTrans) ? target.dataset.nameTrans : target.dataset.nameOrig;
                    return `<a href="#" class="asset-link-item" onclick="event.preventDefault(); openDetails('${linkId}')">
                        <img class="asset-link-thumb" src="${target.dataset.img}">
                        <span class="asset-link-name">${n}</span>
                    </a>`;
                }).join('');
                
                if (relationshipHtml.trim()) {
                    relationshipHtml += `<a href="#" class="asset-link-view-all" onclick="event.preventDefault(); tagSearch('rel:${id}')"><span>${t.labelViewRel}</span></a>`;
                }

                document.getElementById("relationshipContainer").innerHTML = relationshipHtml;
                if (!relationshipHtml.trim()) relSection.style.display = "none";
            } else { relSection.style.display = "none"; }

            const fileData = JSON.parse(el.dataset.files);
            fileData.sort((a, b) => b.name.toLowerCase().localeCompare(a.name.toLowerCase(), undefined, { numeric: true, sensitivity: 'base' }));
            document.getElementById("fileList").innerHTML = fileData.map(f => `
                <li class="file-item">
                    <a class="file-link" href="${f.path}" target="_blank">${f.name}</a>
                    <span style="color:#666; font-size:0.7rem;">${f.size}</span>
                </li>`).join('');

            const m = document.getElementById("detailModal"); 
            m.classList.add('visible'); 
            setTimeout(() => m.classList.add('active'), 10);
            
            const contentContainer = document.querySelector('.tab-content-container');
            if (contentContainer) contentContainer.scrollTop = 0;

            document.title = baseTitle + " - #" + id;
            if (!skipHistory) { const newUrl = new URL(window.location); newUrl.searchParams.set('id', id); window.history.pushState({id: id}, '', newUrl); }
        }

        function carouselNext(dir) { if (currentImages.length <= 1) return; currentCarouselIndex = (currentCarouselIndex + dir + currentImages.length) % currentImages.length; updateCarousel(); }
        function updateCarousel() {
            if (!currentImages.length) return;
            const imgUrl = currentImages[currentCarouselIndex], modalImg = document.getElementById("modalImg"), modalBlurBg = document.getElementById("modalBlurBg");
            modalImg.src = imgUrl; modalBlurBg.src = imgUrl;
            const dots = document.getElementById("carouselDots");
            if (currentImages.length > 1) { dots.style.display = "flex"; dots.innerHTML = currentImages.map((_, i) => `<div class="dot ${i === currentCarouselIndex ? 'active' : ''}" onclick="currentCarouselIndex=${i}; updateCarousel()"></div>`).join(''); document.getElementById("carouselPrev").style.display = "block"; document.getElementById("carouselNext").style.display = "block"; } else { dots.style.display = "none"; document.getElementById("carouselPrev").style.display = "none"; document.getElementById("carouselNext").style.display = "none"; }
        }
        function closeModal(skipHistory = false) { 
            const m = document.getElementById("detailModal"); m.classList.remove('active'); setTimeout(() => { if(!m.classList.contains('active')) m.classList.remove('visible'); }, 300);
            document.title = baseTitle;
            if (!skipHistory) { const newUrl = new URL(window.location); newUrl.searchParams.delete('id'); window.history.pushState({}, '', newUrl); }
        }
        window.onclick = e => { const menu = document.getElementById('flyoutMenu'), btn = document.getElementById('toggleBtn'); if (menu.classList.contains('open') && !menu.contains(e.target) && e.target !== btn) toggleMenu(null, true); };
        document.addEventListener('keydown', e => { if(e.key === "Escape") { closeModal(); toggleMenu(null, true); } if(e.key === "ArrowRight") carouselNext(1); if(e.key === "ArrowLeft") carouselNext(-1); });
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
                total_size += os.path.getsize(fp)
                rel = os.path.relpath(fp, start=os.getcwd()).replace('\\', '/')
                files.append({"name": f, "path": quote(rel), "size": get_readable_size(os.path.getsize(fp))})
    return files, total_size

def get_image_folder_size(folder_path):
    total_size = 0
    for f in os.listdir(folder_path):
        if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif')):
            total_size += os.path.getsize(os.path.join(folder_path, f))
    return total_size

def is_adult_content(text):
    return bool(re.search("|".join(ADULT_KEYWORDS), str(text), re.IGNORECASE))

def get_all_local_images(folder_path, web_urls):
    local_files = [f for f in os.listdir(folder_path) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif'))]
    ordered_images = []
    for url in web_urls:
        tokens = re.findall(r'([a-fA-Z0-9-]{15,})', url)
        found = False
        for token in tokens:
            for f in local_files:
                if token in f:
                    path = quote(os.path.join(folder_path, f).replace('\\', '/'))
                    if path not in ordered_images:
                        ordered_images.append(path)
                        found = True
                        break
            if found: break
        if not found and url: ordered_images.append(url)
    for f in local_files:
        path = quote(os.path.join(folder_path, f).replace('\\', '/'))
        if path not in ordered_images: ordered_images.append(path)
    return ordered_images

def parse_price(price_str):
    if not price_str or "free" in price_str.lower(): return 0.0, "FREE"
    clean = price_str.replace(',', '').replace('¥', '')
    match = re.search(r'([\d.]+)\s*([A-Z]+)', clean)
    return (float(match.group(1)), match.group(2)) if match else (0.0, "")

def generate_asset_html(asset_id, asset_name, author_name, web_images, booth_url, folder_path, tags, is_adult, wish_count, price_str, limited=False, description="", is_avatar=False, related_links=None):
    if limited and "⚙Unlisted" not in tags:
        tags.append("⚙Unlisted")
    if is_adult and "⚙Adult" not in tags:
        tags.append("⚙Adult")
    vrc_av_match = re.search(r'(https://vrchat\.com/home/avatar/avtr_[a-f0-9-]+)', description)
    vrc_av_link = vrc_av_match.group(1) if vrc_av_match else ""
    vrc_wr_match = re.search(r'(https://vrchat\.com/home/world/wrld_[a-f0-9-]+)', description)
    vrc_wr_link = vrc_wr_match.group(1) if vrc_wr_match else ""
    if (vrc_av_link or vrc_wr_link) and "⚙Preview" not in tags:
        tags.append("⚙Preview")
    binary_folder = os.path.join(folder_path, 'Binary')
    files_data, total_bytes = get_dir_data(binary_folder)
    img_bytes, all_imgs = get_image_folder_size(folder_path), get_all_local_images(folder_path, web_images)
    primary_img = all_imgs[0] if all_imgs else ""
    grid_thumb = get_optimized_thumb(asset_id, unquote(primary_img).replace('/', os.sep)) if (OPTIMIZE_THUMBNAILS and primary_img) else primary_img
    name_trans = translation_cache.get(asset_name.strip(), "")
    author_trans = translation_cache.get(author_name.strip(), "")
    desc_trans = description_cache.get(asset_id, "")
    price_val, price_cur = parse_price(price_str)
    safe_name, safe_trans = asset_name.replace('"', '&quot;'), name_trans.replace('"', '&quot;')
    safe_author, safe_author_trans = author_name.replace('"', '&quot;'), author_trans.replace('"', '&quot;')
    safe_desc, safe_desc_trans = description.replace('"', '&quot;'), desc_trans.replace('"', '&quot;')
    search_str = f"{asset_id} {asset_name} {name_trans} {author_name} {author_trans} {' '.join(tags)}".lower().replace("'", "")
    rel_folder = quote(os.path.relpath(binary_folder, start=os.getcwd()).replace('\\', '/'))
    return f"""
    <li class="asset" onclick="openDetails('{asset_id}')" 
        data-id="{asset_id}" data-name-orig="{safe_name}" data-name-trans="{safe_trans}" 
        data-author-orig="{safe_author}" data-author-trans="{safe_author_trans}" data-img="{grid_thumb}" 
        data-all-images='{json.dumps(all_imgs).replace("'", "&apos;")}'
        data-bytes="{total_bytes}" data-img-bytes="{img_bytes}" data-files='{json.dumps(files_data).replace("'", "&apos;")}'
        data-tags='{json.dumps(tags).replace("'", "&apos;")}' data-adult="{str(is_adult).lower()}" 
        data-search='{search_str}' data-folder="{rel_folder}" data-booth-url="{booth_url}"
        data-filecount="{len(files_data)}" data-wish="{wish_count}" data-time="{int(os.path.getctime(folder_path))}"
        data-price-value="{price_val}" data-price-currency="{price_cur}" data-limited="{str(limited).lower()}"
        data-desc-orig="{safe_desc}" data-desc-trans="{safe_desc_trans}" data-vrc-avatar-link="{vrc_av_link}" data-vrc-world-link="{vrc_wr_link}"
        data-is-avatar="{str(is_avatar).lower()}" data-links='{json.dumps(related_links or [])}'>
        <div class="skeleton-shimmer"></div>
        <div class="image-container"><div class="asset-id-tag">#{asset_id}</div><img class="{'image-thumbnail adult-content' if is_adult else 'image-thumbnail'}" loading="lazy"></div>
        <img class="image-backglow"><div class="content">
            <div class="name"><span class="name-primary">{asset_name}</span></div>
            <div class="author-label">by <b class="author-primary">{author_name}</b></div>
            <div class="stats"><span>{get_readable_size(total_bytes)}</span><span class="file-label-dynamic"></span></div>
            <div class="tag-row">{"".join([f'<span class="tag-pill">{t}</span>' for t in tags[:12]])}</div>
        </div>
    </li>
    """

def is_valid_avatar_name(name):
    if not name: return False
    n = name.lower().strip()
    if n == "萌" or n == "moe": return True
    if n in FORBIDDEN_NAMES or len(n) < 2: return False
    return True

def get_base_name(name):
    if not name: return None
    en_match = re.search(r'-(.*?)-', name)
    if en_match:
        cand = en_match.group(1).strip()
        if is_valid_avatar_name(cand): return cand
    matches = re.findall(r'【(.*?)】|\[(.*?)\]|\((.*?)\)|「(.*?)」', name)
    for t in matches:
        for cand in t:
            if cand:
                cleaned = re.sub(r'オリジナル3Dモデル|3Dモデル|アバター|Ver\..*', '', cand).strip()
                if is_valid_avatar_name(cleaned): return cleaned
    core = re.sub(r'[\[(（【「].*?[\])）】」]', '', name)
    core = re.sub(r'オリジナル3Dモデル|3Dモデル|アバター|Ver\..*', '', core).strip()
    return core if is_valid_avatar_name(core) else None

def contains_avatar_name(text, av_info):
    if not text: return False
    text = text.lower()
    if av_info['trans']:
        pattern = r'\b' + re.escape(av_info['trans'].lower()) + r'\b'
        if re.search(pattern, text): return True
    orig = av_info['orig'].lower()
    if orig:
        if orig in text:
            if len(orig) == 1:
                return True 
            else:
                idx = text.find(orig)
                after = text[idx + len(orig):idx + len(orig) + 1]
                if after and after in "ろうくんちゃん": return False
                return True
    return False

print("[Scan] Reading folders...")
asset_data_list, short_strings_to_translate = [], []
desc_tasks = {}
avatars = {} 
assets_to_avatar = {} 

for folder in sorted(os.listdir(ROOT_FOLDER)):
    path = os.path.join(ROOT_FOLDER, folder)
    if not os.path.isdir(path): continue
    jsons = glob.glob(os.path.join(path, "_BoothPage.json")) or glob.glob(os.path.join(path, "_BoothInnerHtmlList.json"))
    if not jsons: continue
    with open(jsons[0], 'r', encoding='utf-8') as f:
        if jsons[0].endswith('_BoothPage.json'):
            data = json.load(f)
            name, author, desc = data.get('name', 'N/A'), data.get('shop', {}).get('name', 'N/A'), data.get('description', '')
            tags = [t.get('name', '') for t in data.get('tags', [])]
            short_strings_to_translate.extend([name, author] + tags)
            is_avatar = data.get('category', {}).get('name') == "3D Characters"
            asset_data_list.append(('json', folder, (name, author, data, desc), path, data.get('wish_lists_count', 0), is_avatar))
            if not SKIP_TRANSLATION and desc and folder not in description_cache and contains_japanese(desc):
                desc_tasks[folder] = desc
        else:
            data = json.load(f)
            item = data[0] if data else ""
            if item:
                n_m = re.search(r'break-all\">(.*?)<\/div>', item) or re.search(r'>(.*?)<\/div>', item)
                a_m = re.search(r'text-text-gray600 break-all\">(.*?)<\/div>', item)
                name, author = n_m.group(1) if n_m else "N/A", a_m.group(1) if a_m else "N/A"
                short_strings_to_translate.extend([name, author])
                asset_data_list.append(('limited', folder, (name, author, item, ""), path, 0, False))

bulk_translate_short_terms(short_strings_to_translate)

for atype, folder, data, path, wish, is_avatar in asset_data_list:
    if is_avatar:
        name = data[0]
        orig_base = get_base_name(name)
        trans_base = get_base_name(translation_cache.get(name.strip(), ""))
        if orig_base or trans_base:
            avatars[folder] = {"orig": orig_base, "trans": trans_base}

for atype, folder, data, path, wish, is_avatar in asset_data_list:
    if is_avatar: continue
    name, author, content, desc = data
    tags = variations = []
    if atype == 'json':
        tags = [t.get('name', '').lower() for t in content.get('tags', [])]
        variations = [v.get('name', '').lower() for v in content.get('variations', []) if v.get('name')]
    for av_id, av_info in avatars.items():
        matched = False
        for t in tags + variations:
            if t in FORBIDDEN_NAMES: continue
            if contains_avatar_name(t, av_info): matched = True; break
        if not matched and contains_avatar_name(name, av_info): matched = True
        if not matched and av_info['orig'] and (len(av_info['orig']) > 2 or av_info['orig'] == '萌'):
            if contains_avatar_name(desc, av_info): matched = True
        if matched:
            if folder not in assets_to_avatar: assets_to_avatar[folder] = []
            assets_to_avatar[folder].append(av_id)

avatar_to_assets = {}
for asset_id, av_list in assets_to_avatar.items():
    for av_id in av_list:
        if av_id not in avatar_to_assets: avatar_to_assets[av_id] = []
        avatar_to_assets[av_id].append(asset_id)

if desc_tasks:
    total_descs = len(desc_tasks)
    print(f"[Translate] Processing descriptions...")
    completed_descs = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_folder = {executor.submit(translate_single_text, text): folder for folder, text in desc_tasks.items()}
        for future in as_completed(future_to_folder):
            folder = future_to_folder[future]
            try:
                res = future.result()
                if res: description_cache[folder] = res
            except: pass
            completed_descs += 1
            print_progress(completed_descs, total_descs, "Descriptions")
    with open(DESC_CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(description_cache, f, ensure_ascii=False, indent=2)

print(f"[Build] Generating HTML...")
asset_items_final = []
for atype, folder, data, path, wish, is_avatar in asset_data_list:
    name, author, content, desc = data
    related_links = avatar_to_assets.get(folder, []) if is_avatar else assets_to_avatar.get(folder, [])
    if atype == 'json':
        web_imgs = [img.get('original', '') for img in content.get('images', [])]
        tags = [t.get('name', '') for t in content.get('tags', [])]
        asset_items_final.append(generate_asset_html(folder, name, author, web_imgs, content.get('url', ''), path, tags, content.get('is_adult', False) or is_adult_content(name), wish, content.get('price', ''), description=desc, is_avatar=is_avatar, related_links=related_links))
    else:
        i_m, u_m = re.search(r'src=\"([^\"]+)\"', content), re.search(r'href=\"([^\"]+)\"', content)
        img, url = i_m.group(1) if i_m else "", u_m.group(1) if u_m else ""
        asset_items_final.append(generate_asset_html(folder, name, author, [img], url, path, [], is_adult_content(name), 0, "", limited=True, related_links=related_links))

with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    f.write(HTML_PART_1 + "\n".join(asset_items_final) + HTML_PART_2)

print(f"--- Library Updated Successfully ({len(asset_items_final)} items) ---")