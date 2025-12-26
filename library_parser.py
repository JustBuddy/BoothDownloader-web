import os
import json
import glob
import re
import time
import sys
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed
from deep_translator import GoogleTranslator

# Configuration
ROOT_FOLDER = "BoothDownloaderOut"
OUTPUT_FILE = "asset_library.html"
CACHE_FILE = "translation_cache.json"
SKIP_TRANSLATION = False  
DEBUG_TRANSLATION = False 
MAX_WORKERS = 5 

ADULT_KEYWORDS_EN = [r"R-?18", r"adult", r"nude", r"semen", r"nsfw", r"sexual", r"erotic", r"pussy", r"dick", r"vagina", r"penis", r"otimpo", r"otinpo"]
ADULT_KEYWORDS_JP = ["精液", "だぷだぷ", "ヌード", "エロ", "クリトリス", "おまんこ", "おちんぽ", "おてぃんぽ"]

# --- Translation Logic ---
translation_cache = {}
if not SKIP_TRANSLATION and os.path.exists(CACHE_FILE):
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            translation_cache = json.load(f)
    except:
        translation_cache = {}

def contains_japanese(text):
    return bool(re.search(r'[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]', str(text)))

def is_noise(text):
    if not text or len(text.strip()) < 1: return True
    if text.isdigit(): return True
    alnum_jp = re.sub(r'[^\w\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]', '', text)
    if not alnum_jp: return True
    if len(alnum_jp) / len(text) < 0.15: return True
    return False

def translate_chunk_task(chunk_data):
    chunk_index, chunk = chunk_data
    translator = GoogleTranslator(source='auto', target='en')
    separator = " @@@ "
    try:
        clean_chunk = [t.strip() for t in chunk]
        combined = separator.join(clean_chunk)
        translated = translator.translate(combined)
        if translated:
            results = [r.strip() for r in translated.split("@@@")]
            if len(results) == len(clean_chunk):
                for original, trans in zip(chunk, results):
                    if not contains_japanese(trans):
                        translation_cache[original] = trans
                return True
            else:
                for original in chunk:
                    try:
                        res = translator.translate(original)
                        if res: translation_cache[original] = res
                    except: continue
                return True
    except Exception: pass
    return False

def bulk_translate(text_list):
    if SKIP_TRANSLATION: return
    japanese_strings = list(set(str(t).strip() for t in text_list if t and contains_japanese(t)))
    new_strings = [t for t in japanese_strings if t not in translation_cache]
    if not new_strings: return
    real_queue = [t for t in new_strings if not is_noise(t)]
    for t in new_strings:
        if is_noise(t): translation_cache[t] = t
    if not real_queue: return
    if DEBUG_TRANSLATION:
        print(f"DEBUG: {len(real_queue)} terms queued.")
        sys.exit()
    batch_size = 15
    chunks = [(i//batch_size + 1, real_queue[i:i+batch_size]) for i in range(0, len(real_queue), batch_size)]
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        list(executor.map(translate_chunk_task, chunks))
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(translation_cache, f, ensure_ascii=False, indent=2)

HTML_PART_1 = """<!doctype html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Booth Asset Library</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
    <style>
        :root { --primary: #FDDA0D; --bg: #0b0b0d; --card: #16161a; --text: #ddd; --grid-size: 220px; }
        * { box-sizing: border-box; }
        body { font-family: 'Inter', sans-serif; background-color: var(--bg); color: var(--text); margin: 0; padding: 0; overflow-x: hidden; }
        .top-nav { position: sticky; top: 0; z-index: 1000; background: rgba(11, 11, 13, 0.9); backdrop-filter: blur(12px); border-bottom: 1px solid #222; padding: 15px 30px; display: flex; align-items: center; justify-content: space-between; gap: 20px; }
        .nav-logo { color: var(--primary); font-weight: 800; font-size: 1.2rem; white-space: nowrap; }
        .search-container { flex-grow: 1; display: flex; justify-content: center; position: relative; max-width: 500px; }
        .search-input { padding: 10px 45px 10px 20px; width: 100%; background: #1a1a1f; border: 1px solid #333; border-radius: 8px; color: white; outline: none; transition: border-color 0.3s; }
        .search-input:focus { border-color: var(--primary); }
        .clear-search { position: absolute; right: 15px; top: 50%; transform: translateY(-50%); background: none; border: none; color: #666; font-size: 1.2rem; cursor: pointer; display: none; padding: 0; line-height: 1; }
        .search-input:not(:placeholder-shown) + .clear-search { display: block; }
        .nav-btn { background: #222; border: 1px solid #333; color: white; padding: 10px 18px; border-radius: 8px; cursor: pointer; font-weight: 600; position: relative; z-index: 2001; transition: all 0.3s; }
        .nav-btn.active { border-color: var(--primary); color: var(--primary); }
        #menuPerimeter { display: none; position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; z-index: 1999; }
        .flyout-menu { display: block; position: fixed; top: 75px; right: 30px; width: 320px; background: rgba(26, 26, 31, 0.98); backdrop-filter: blur(20px); border: 1px solid rgba(253, 218, 13, 0.3); z-index: 2000; padding: 25px; border-radius: 16px; box-shadow: 0 20px 60px rgba(0,0,0,0.8); opacity: 0; transform: translateY(-20px) scale(0.95); transition: opacity 0.3s, transform 0.3s, visibility 0.3s; pointer-events: none; visibility: hidden; }
        .flyout-menu.open { opacity: 1; transform: translateY(0) scale(1); pointer-events: all; visibility: visible; }
        .setting-group { margin-bottom: 25px; width: 100%; }
        .setting-label { display: block; margin: 15px 0 8px; font-size: 0.7rem; color: #555; text-transform: uppercase; font-weight: 800; }
        select, input[type=range] { width: 100%; background: #0b0b0d; color: white; border: 1px solid #333; padding: 10px; border-radius: 8px; outline: none; }
        .container { max-width: 1600px; margin: 40px auto; padding: 0 30px; }
        #assetList { display: grid; grid-template-columns: repeat(auto-fill, minmax(var(--grid-size), 1fr)); gap: 35px; list-style: none; padding: 0; }
        .asset { background: #111114; border: 1px solid #252525; border-radius: 12px; overflow: hidden; cursor: pointer; display: flex; flex-direction: column; height: 100%; transition: 0.3s; position: relative; }
        .asset:hover { border-color: var(--primary); transform: translateY(-5px); }
        .asset-id-tag { position: absolute; bottom: 8px; left: 8px; z-index: 20; background: rgba(0,0,0,0.7); color: #fff; font-size: 0.65rem; padding: 2px 6px; border-radius: 4px; font-weight: 800; backdrop-filter: blur(4px); border: 1px solid rgba(255,255,255,0.1); transition: opacity 0.3s ease; opacity: 1; }
        body.hide-ids .asset-id-tag { opacity: 0; }
        .image-container { position: relative; width: 100%; padding-top: 100%; background: #000; flex-shrink: 0; z-index: 5; overflow: hidden; border-radius: 12px 12px 0 0; }
        .image-thumbnail { position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; transition: 0.4s; z-index: 10; }
        .image-backglow { position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; filter: blur(45px) saturate(5) contrast(1.5); opacity: 0.7; z-index: 1; pointer-events: none; transform: scale(1.6); }
        .adult-content { filter: blur(50px); }
        .asset:hover .adult-content { filter: blur(0px); }
        body.no-blur .adult-content { filter: blur(0px) !important; }
        .content { padding: 15px; flex-grow: 1; display: flex; flex-direction: column; z-index: 10; position: relative; background: rgba(18, 18, 22, 0.8); backdrop-filter: blur(5px); }
        .name { font-weight: 600; color: #fff; line-height: 1.3; margin-bottom: 8px; font-size: 0.9rem; height: 2.6em; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
        .name-translated { display: block; font-size: 0.75rem; color: var(--primary); margin-top: 4px; font-weight: 400; opacity: 0.8; transition: opacity 0.3s; }
        body.hide-translations .name-translated { display: none; }
        .stats { color: #aaa; font-size: 0.75rem; display: flex; gap: 10px; margin-top: auto; font-weight: 600; }
        .tag-row { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 10px; height: 18px; overflow: hidden; }
        .tag-pill { font-size: 0.65rem; background: rgba(0,0,0,0.4); height: 18px; line-height: 18px; padding: 0 8px; border-radius: 4px; color: #fff; white-space: nowrap; border: 1px solid rgba(255,255,255,0.1); display: inline-flex; align-items: center; justify-content: center; transition: background 0.2s, color 0.2s; }
        .modal-info .tag-pill { cursor: pointer; height: 22px; font-size: 0.75rem; padding: 0 10px; }
        .modal-info .tag-pill:hover { background: var(--primary); color: #000; border-color: var(--primary); }
        .tag-pill.more-btn { background: var(--primary); color: #000; font-weight: 800; border: none; }
        .modal { display: none; position: fixed; z-index: 3000; left: 0; top: 0; width: 100%; height: 100%; align-items: center; justify-content: center; transition: 0.3s; padding: 20px; box-sizing: border-box; }
        .modal.visible { display: flex; }
        .modal.active { background: rgba(0,0,0,0.95); }
        .modal-card { background: #1a1a1f; width: 100%; max-width: 1100px; max-height: 90vh; border: 1px solid var(--primary); border-radius: 16px; display: flex; flex-direction: row; overflow: hidden; opacity: 0; transform: scale(0.9); transition: 0.3s; position: relative; }
        .modal.active .modal-card { opacity: 1; transform: scale(1); }
        .modal-carousel { flex: 0 0 50%; background: #000; display: flex; align-items: center; justify-content: center; position: relative; overflow: hidden; min-height: 350px; }
        .carousel-blur-bg { position: absolute; top: -10%; left: -10%; width: 120%; height: 120%; object-fit: cover; filter: blur(40px) brightness(0.5); opacity: 0.8; z-index: 1; transition: 0.4s; }
        .carousel-main-img { max-width: 100%; max-height: 100%; object-fit: contain; position: relative; z-index: 2; transition: 0.4s; }
        .carousel-btn { position: absolute; top: 50%; transform: translateY(-50%); z-index: 10; background: rgba(0,0,0,0.5); border: 1px solid rgba(255,255,255,0.2); color: white; padding: 15px 10px; cursor: pointer; border-radius: 4px; font-size: 1.2rem; transition: 0.2s; }
        .carousel-btn:hover { background: var(--primary); color: #000; }
        .btn-prev { left: 15px; }
        .btn-next { right: 15px; }
        .carousel-dots { position: absolute; bottom: 20px; left: 50%; transform: translateX(-50%); display: flex; gap: 8px; z-index: 10; }
        .dot { width: 8px; height: 8px; border-radius: 50%; background: rgba(255,255,255,0.3); cursor: pointer; transition: 0.2s; }
        .dot.active { background: var(--primary); transform: scale(1.3); }
        .modal-info { flex: 1; padding: 30px; display: flex; flex-direction: column; min-width: 320px; position: relative; overflow-y: auto; }
        .modal-name { font-size: 1.5rem; font-weight: 800; color: var(--primary); margin-bottom: 5px; }
        .modal-subtitle { font-size: 0.9rem; color: #777; margin-bottom: 15px; font-weight: 400; font-style: italic; display: block; }
        body.hide-translations .modal-subtitle { display: none; }
        .file-list { list-style: none; padding: 0; margin-top: 10px; flex-grow: 1; }
        .file-item { padding: 10px; background: #222; border-radius: 8px; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center; gap: 10px; }
        .file-link { color: #fff; text-decoration: none; font-size: 0.85rem; word-break: break-all; flex-grow: 1; }
        .file-link:hover { color: var(--primary); }
        
        .modal-footer { margin-top: 30px; padding-top: 20px; border-top: 1px solid #333; display: flex; justify-content: space-between; align-items: flex-end; gap: 20px; padding-bottom: 20px; flex-shrink: 0; }
        .modal-id-display { color: #555; font-size: 0.8rem; font-weight: 800; }
        .modal-actions { display: flex; gap: 20px; }
        .discrete-link { color: #555; text-decoration: none; font-size: 0.75rem; font-weight: 600; display: flex; align-items: center; gap: 6px; transition: color 0.2s; }
        .discrete-link:hover { color: var(--primary); }
        #filterNotice { display: none; background: #1a1a1f; border: 2px dashed var(--primary); border-radius: 12px; padding: 20px; align-items: center; justify-content: center; text-align: center; color: var(--primary); font-weight: 800; font-size: 0.9rem; }
        @media (max-width: 800px) { .modal-card { flex-direction: column; overflow-y: auto; } .modal-carousel { flex: 0 0 400px; width: 100%; } .modal-info { flex: none; width: 100%; overflow-y: visible; } }
    </style>
</head>
<body>
    <div id="menuPerimeter" onclick="toggleMenu(event, true)"></div>
    <nav class="top-nav">
        <div class="nav-logo" data-i18n="navTitle">Booth Asset Library</div>
        <div class="search-container">
            <input type="text" id="searchInput" class="search-input" placeholder="Search..." onkeyup="handleSearchInput()">
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
        <div class="setting-group"><span class="setting-label" data-i18n="labelWidth">Card Width</span><input type="range" id="gridRange" min="180" max="500" value="220" oninput="updateGrid(this.value)"></div>
        <div class="setting-group"><span class="setting-label" data-i18n="labelVisual">Visual Controls</span>
            <label style="display:flex; gap:10px; cursor:pointer; font-size:0.9rem; margin-bottom:10px;"><input type="checkbox" id="blurToggle" onchange="updateBlur(this.checked)"> <span data-i18n="optBlur">Disable Blur</span></label>
            <label style="display:flex; gap:10px; cursor:pointer; font-size:0.9rem; margin-bottom:10px;"><input type="checkbox" id="hideIdToggle" onchange="updateIdVisibility(this.checked)"> <span data-i18n="optHideIds">Hide IDs</span></label>
            <label style="display:flex; gap:10px; cursor:pointer; font-size:0.9rem;"><input type="checkbox" id="translateToggle" onchange="updateTranslationVisibility(this.checked)"> <span data-i18n="optTranslate">English Titles</span></label>
        </div>
    </div>
    <div class="container"><ul id="assetList">"""

HTML_PART_2 = """<li id="filterNotice"></li></ul></div>
    <div id="detailModal" class="modal" onclick="closeModal()"><div class="modal-card" onclick="event.stopPropagation()"><div class="modal-carousel" id="modalCarouselContainer"><button id="carouselPrev" class="carousel-btn btn-prev" onclick="carouselNext(-1)">❮</button><img id="modalBlurBg" class="carousel-blur-bg" src=""><img id="modalImg" class="carousel-main-img" src=""><button id="carouselNext" class="carousel-btn btn-next" onclick="carouselNext(1)">❯</button><div id="carouselDots" class="carousel-dots"></div></div><div class="modal-info"><div id="modalName" class="modal-name"></div><div id="modalSubtitle" class="modal-subtitle"></div><div id="modalTags" style="display:flex; flex-wrap:wrap; gap:6px; margin-bottom:20px;"></div><span class="setting-label" data-i18n="labelBinary">Binary Files</span><ul id="fileList" class="file-list"></ul><div class="modal-footer"><div id="modalIdDisp" class="modal-id-display"></div><div class="modal-actions"><a id="openBoothLink" href="" class="discrete-link" target="_blank"><span data-i18n="footBooth">🛒 Booth</span></a><a id="openFolderLink" href="" class="discrete-link" target="_blank"><span data-i18n="footFolder">📂 Folder</span></a></div></div></div></div></div>
    <script>
        const translations = {
            en: { navTitle: "Booth Asset Library", optionsBtn: "Options ⚙", labelLanguage: "Language", labelSort: "Sort Order", optId: "Folder ID", optNew: "Recently Added", optName: "Alphabetical", optRel: "Relevance", optSize: "Total Size", labelAdult: "Adult Filter", optAll: "Show All", optHide: "Hide Adult", optOnly: "Only Adult", labelWidth: "Card Width", labelVisual: "Visual Controls", optBlur: "Disable Blur", optHideIds: "Hide Item IDs", optTranslate: "Use Translated Titles", labelBinary: "Binary Files", footBooth: "🛒 Open on Booth", footFolder: "📂 Open Local Folder", searchPre: "Search ", searchSuf: " items...", fileSingular: "file", filePlural: "files", moreTags: "+ {n} more", hiddenResults: " (+{n} hidden by filters)" },
            de: { navTitle: "Booth Bibliothek", optionsBtn: "Optionen ⚙", labelLanguage: "Sprache", labelSort: "Sortierung", optId: "ID", optNew: "Zuletzt hinzugefügt", optName: "Alphabetisch", optRel: "Beliebtheit", optSize: "Größe", labelAdult: "Filter", optAll: "Alles", optHide: "Ausblenden", optOnly: "Nur 18+", labelWidth: "Breite", labelVisual: "Anzeige", optBlur: "Kein Fokus", optHideIds: "IDs weg", optTranslate: "Übersetzte Titel", labelBinary: "Dateien", footBooth: "🛒 Booth", footFolder: "📂 Ordner", searchPre: "Suche ", searchSuf: " Artikel...", fileSingular: "Datei", filePlural: "Dateien", moreTags: "+ {n} weitere", hiddenResults: " (+{n} durch Filter versteckt)" },
            ja: { navTitle: "Boothアセットライブラリ", optionsBtn: "設定 ⚙", labelLanguage: "言語", labelSort: "並び替え", optId: "ID", optNew: "最近追加された", optName: "名前順", optRel: "人気順", optSize: "サイズ", labelAdult: "フィルター", optAll: "すべて表示", optHide: "隠す", optOnly: "成人向けのみ", labelWidth: "幅", labelVisual: "表示", optBlur: "ぼかし解除", optHideIds: "ID非表示", optTranslate: "翻訳後の名前を表示", labelBinary: "ファイル", footBooth: "🛒 Booth", footFolder: "📂 フォルダ", searchPre: "検索：", searchSuf: " 件", fileSingular: "ファイル", filePlural: "ファイル", moreTags: "他 {n} 件", hiddenResults: " (他 {n} 件がフィルター済み)" },
            ko: { navTitle: "Booth 에셋 라이브러리", optionsBtn: "설정 ⚙", labelLanguage: "언어", labelSort: "정렬", optId: "ID", optNew: "최근 추가됨", optName: "이름순", optRel: "관련성", optSize: "용량", labelAdult: "성인 필터", optAll: "모두 표시", optHide: "성인 숨기기", optOnly: "성인 전용", labelWidth: "너비", labelVisual: "표시", optBlur: "블러 해제", optHideIds: "ID 숨기기", optTranslate: "번역 제목 사용", labelBinary: "파일", footBooth: "🛒 Booth 보기", footFolder: "📂 폴더 열기", searchPre: "검색: ", searchSuf: "개", fileSingular: "파일", filePlural: "파일", moreTags: "+ {n}개 더보기", hiddenResults: " (+{n}개 숨김)" },
            'zh-Hans': { navTitle: "Booth 资源库", optionsBtn: "选项 ⚙", labelLanguage: "语言", labelSort: "排序", optId: "ID", optNew: "最近添加", optName: "名称排序", optRel: "相关性", optSize: "大小", labelAdult: "成人过滤", optAll: "显示全部", optHide: "隐藏成人", optOnly: "仅成人", labelWidth: "宽度", labelVisual: "视觉控制", optBlur: "禁用模糊", optHideIds: "隐藏 ID", optTranslate: "显示翻译名称", labelBinary: "二进制文件", footBooth: "🛒 在 Booth 打开", footFolder: "📂 打开文件夹", searchPre: "搜索 ", searchSuf: " 个项目", fileSingular: "文件", filePlural: "文件", moreTags: "+ {n} 更多", hiddenResults: " (+{n} 个被过滤)" },
            'zh-Hant': { navTitle: "Booth 資源庫", optionsBtn: "選項 ⚙", labelLanguage: "語言", labelSort: "排序", optId: "ID", optNew: "最近添加", optName: "名稱排序", optRel: "相關性", optSize: "大小", labelAdult: "成人過濾", optAll: "顯示全部", optHide: "隱藏成人", optOnly: "僅限成人", labelWidth: "寬度", labelVisual: "視覺控制", optBlur: "禁用模糊", optHideIds: "隱藏 ID", optTranslate: "顯示翻譯名稱", labelBinary: "二進制檔案", footBooth: "🛒 在 Booth 打開", footFolder: "📂 打開資料夾", searchPre: "搜尋 ", searchSuf: " 個項目", fileSingular: "檔案", filePlural: "檔案", moreTags: "+ {n} 更多", hiddenResults: " (+{n} 個被過濾)" },
            nl: { navTitle: "Booth Bibliotheek", optionsBtn: "Opties ⚙", labelLanguage: "Taal", labelSort: "Sorteer", optId: "ID", optNew: "Onlangs toegevoegd", optName: "Alfabet", optRel: "Relevantie", optSize: "Grootte", labelAdult: "Filter", optAll: "Alles tonen", optHide: "Verbergen", optOnly: "Alleen 18+", labelWidth: "Breedte", labelVisual: "Visueel", optBlur: "Geen vervaging", optHideIds: "ID's weg", optTranslate: "Engelse titels", labelBinary: "Bestanden", footBooth: "🛒 Booth", footFolder: "📂 Map", searchPre: "Zoek in ", searchSuf: " items...", fileSingular: "bestand", filePlural: "bestanden", moreTags: "+ {n} meer", hiddenResults: " (+{n} verborgen door filters)" },
            fr: { navTitle: "Bibliothèque Booth", optionsBtn: "Options ⚙", labelLanguage: "Langue", labelSort: "Trier", optId: "ID", optNew: "Ajouté récemment", optName: "Nom", optRel: "Pertinence", optSize: "Taille", labelAdult: "Filtre", optAll: "Tout", optHide: "Masquer", optOnly: "Adulte", labelWidth: "Largeur", labelVisual: "Visuel", optBlur: "Désactiver flou", optHideIds: "Masquer IDs", optTranslate: "Titres anglais", labelBinary: "Fichiers", footBooth: "🛒 Booth", footFolder: "📂 Dossier", searchPre: "Rechercher ", searchSuf: " items...", fileSingular: "fichier", filePlural: "fichiers", moreTags: "+ {n} de plus", hiddenResults: " (+{n} masqués)" },
            es: { navTitle: "Biblioteca Booth", optionsBtn: "Opciones ⚙", labelLanguage: "Idioma", labelSort: "Orden", optId: "ID", optNew: "Más reciente", optName: "Nombre", optRel: "Relevancia", optSize: "Tamaño", labelAdult: "Filtro", optAll: "Todo", optHide: "Ocultar", optOnly: "Adultos", labelWidth: "Ancho", labelVisual: "Visual", optBlur: "Sin desenfoque", optHideIds: "Ocultar IDs", optTranslate: "Títulos inglés", labelBinary: "Archivos", footBooth: "🛒 Booth", footFolder: "📂 Carpeta", searchPre: "Buscar ", searchSuf: " items...", fileSingular: "archivo", filePlural: "archivos", moreTags: "+ {n} más", hiddenResults: " (+{n} ocultos)" },
            pt: { navTitle: "Biblioteca Booth", optionsBtn: "Opções ⚙", labelLanguage: "Idioma", labelSort: "Ordenar", optId: "ID", optNew: "Mais recentes", optName: "Nome", optRel: "Relevância", optSize: "Tamanho", labelAdult: "Filtro adulto", optAll: "Tudo", optHide: "Ocultar adultos", optOnly: "Apenas 18+", labelWidth: "Largura", labelVisual: "Visual", optBlur: "Sem flou", optHideIds: "Sem IDs", optTranslate: "Títulos inglês", labelBinary: "Arquivos", footBooth: "🛒 Booth", footFolder: "📂 Pasta", searchPre: "Pesquisar ", searchSuf: " itens...", fileSingular: "arquivo", filePlural: "arquivos", moreTags: "+ {n} mais", hiddenResults: " (+{n} ocultos)" }
        };
        let currentCarouselIndex = 0, currentImages = [];
        const getLS = (k, def) => localStorage.getItem(k) || def;
        const state = { gridSize: getLS('gridSize', '220'), disableBlur: getLS('disableBlur', 'false') === 'true', sortOrder: getLS('sortOrder', 'id'), adultFilter: getLS('adultFilter', 'all'), hideIds: getLS('hideIds', 'false') === 'true', lang: getLS('lang', 'en'), showTrans: getLS('showTrans', 'true') === 'true' };
        function init() {
            updateLanguage(state.lang); updateGrid(state.gridSize); updateBlur(state.disableBlur); updateIdVisibility(state.hideIds); updateTranslationVisibility(state.showTrans);
            document.getElementById('gridRange').value = state.gridSize; document.getElementById('blurToggle').checked = state.disableBlur; document.getElementById('sortOrder').value = state.sortOrder;
            document.getElementById('adultFilter').value = state.adultFilter; document.getElementById('hideIdToggle').checked = state.hideIds; document.getElementById('translateToggle').checked = state.showTrans;
            handleSearchInput(); sortAssets();
        }
        function updateLanguage(lang) { state.lang = lang; localStorage.setItem('lang', lang); document.getElementById('langSelect').value = lang; const t = translations[lang] || translations['en']; document.querySelectorAll('[data-i18n]').forEach(el => { el.innerText = t[el.dataset.i18n]; }); applyFilters(); }
        function toggleMenu(e, forceClose = false) { if(e) e.stopPropagation(); const menu = document.getElementById('flyoutMenu'), btn = document.getElementById('toggleBtn'), perim = document.getElementById('menuPerimeter'); const open = !forceClose && !menu.classList.contains('open'); menu.classList.toggle('open', open); btn.classList.toggle('active', open); perim.style.display = open ? 'block' : 'none'; }
        function updateGrid(v) { document.documentElement.style.setProperty('--grid-size', v + 'px'); localStorage.setItem('gridSize', v); }
        function updateBlur(v) { document.body.classList.toggle('no-blur', v); localStorage.setItem('disableBlur', v); }
        function updateIdVisibility(v) { document.body.classList.toggle('hide-ids', v); localStorage.setItem('hideIds', v); }
        function updateTranslationVisibility(v) { state.showTrans = v; localStorage.setItem('showTrans', v); const items = document.getElementsByClassName('asset'); for(let item of items) { const primaryName = item.querySelector('.name-primary'); primaryName.innerText = (v && item.dataset.nameTrans) ? item.dataset.nameTrans : item.dataset.nameOrig; } }
        function handleSearchInput() { applyFilters(); }
        function clearSearch() { const i = document.getElementById("searchInput"); i.value = ""; handleSearchInput(); i.focus(); }
        function tagSearch(tag) { const s = document.getElementById("searchInput"); s.value = tag; closeModal(); handleSearchInput(); window.scrollTo({ top: 0, behavior: 'smooth' }); }
        function applyFilters(save = false) {
            const query = document.getElementById("searchInput").value.toLowerCase();
            const mode = document.getElementById("adultFilter").value;
            const items = document.getElementsByClassName("asset"), t = translations[state.lang] || translations['en'];
            let count = 0, totalMatchesButHidden = 0;
            if(save) localStorage.setItem('adultFilter', mode);
            for (let item of items) {
                const isAdult = item.dataset.adult === 'true';
                const searchMatch = item.dataset.search.includes(query);
                const filterMatch = (mode === 'all') || (mode === 'hide' && !isAdult) || (mode === 'only' && isAdult);
                if (searchMatch && !filterMatch) totalMatchesButHidden++;
                const visible = searchMatch && filterMatch;
                if (visible) count++;
                item.style.display = visible ? "" : "none";
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
        function openDetails(id) {
            const el = document.querySelector(`.asset[data-id="${id}"]`), t = translations[state.lang] || translations['en'];
            const displayTitle = (state.showTrans && el.dataset.nameTrans) ? el.dataset.nameTrans : el.dataset.nameOrig;
            const subtitle = (state.showTrans && el.dataset.nameTrans) ? el.dataset.nameOrig : "";
            document.getElementById("modalName").innerText = displayTitle;
            document.getElementById("modalSubtitle").innerText = subtitle;
            document.getElementById("modalIdDisp").innerText = "#" + id;
            document.getElementById("openFolderLink").href = el.dataset.folder;
            document.getElementById("openBoothLink").href = el.dataset.boothUrl;
            currentImages = JSON.parse(el.dataset.allImages); currentCarouselIndex = 0; updateCarousel();
            const tags = JSON.parse(el.dataset.tags);
            const tagContainer = document.getElementById("modalTags");
            const renderTagsInternal = (list) => list.map(tg => `<span class="tag-pill" onclick="tagSearch('${tg.replace(/'/g, "\\\\'")}')">${tg}</span>`).join('');
            if (tags.length > 25) { tagContainer.innerHTML = renderTagsInternal(tags.slice(0, 20)) + `<span class="tag-pill more-btn" onclick="this.parentElement.innerHTML=window.renderTagsFull(JSON.parse(document.querySelector('.asset[data-id=\\\\'${id}\\\\\\']').dataset.tags))">${t.moreTags.replace('{n}', tags.length - 20)}</span>`; } else tagContainer.innerHTML = renderTagsInternal(tags);
            window.renderTagsFull = renderTagsInternal;
            const fileData = JSON.parse(el.dataset.files);
            fileData.sort((a, b) => b.name.toLowerCase().localeCompare(a.name.toLowerCase(), undefined, { numeric: true, sensitivity: 'base' }));
            document.getElementById("fileList").innerHTML = fileData.map(f => `<li class="file-item"><a class="file-link" href="${f.path}" target="_blank">${f.name}</a><span style="color:#aaa;font-size:0.75rem;">${f.size}</span></li>`).join('');
            const m = document.getElementById("detailModal"); m.classList.add('visible'); setTimeout(() => m.classList.add('active'), 10);
        }
        function carouselNext(dir) { if (currentImages.length <= 1) return; currentCarouselIndex = (currentCarouselIndex + dir + currentImages.length) % currentImages.length; updateCarousel(); }
        function updateCarousel() {
            const img = currentImages[currentCarouselIndex];
            const modalImg = document.getElementById("modalImg");
            const modalBlurBg = document.getElementById("modalBlurBg");
            modalImg.src = img; modalBlurBg.src = img;
            const dots = document.getElementById("carouselDots");
            if (currentImages.length > 1) { dots.style.display = "flex"; dots.innerHTML = currentImages.map((_, i) => `<div class="dot ${i === currentCarouselIndex ? 'active' : ''}" onclick="currentCarouselIndex=${i}; updateCarousel()"></div>`).join(''); document.getElementById("carouselPrev").style.display = "block"; document.getElementById("carouselNext").style.display = "block"; } else { dots.style.display = "none"; document.getElementById("carouselPrev").style.display = "none"; document.getElementById("carouselNext").style.display = "none"; }
        }
        function closeModal() { const m = document.getElementById("detailModal"); m.classList.remove('active'); setTimeout(() => { if(!m.classList.contains('active')) m.classList.remove('visible'); }, 300); }
        window.onclick = e => { const menu = document.getElementById('flyoutMenu'); const btn = document.getElementById('toggleBtn'); if (menu.classList.contains('open') && !menu.contains(e.target) && e.target !== btn) toggleMenu(null, true); };
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
                rel = os.path.relpath(fp, start=os.getcwd())
                files.append({"name": f, "path": quote(rel), "size": get_readable_size(os.path.getsize(fp))})
    return files, total_size

def is_adult_content(text):
    if re.search("|".join(ADULT_KEYWORDS_EN), text, re.IGNORECASE): return True
    return any(w in text for w in ADULT_KEYWORDS_JP)

def find_specific_local_image(folder_path, web_url):
    tokens = re.findall(r'([a-fA-Z0-9-]{15,})', web_url)
    if tokens:
        local_files = os.listdir(folder_path)
        for token in tokens:
            for f in local_files:
                if token in f: return quote(os.path.join(folder_path, f))
    return None

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
                    if path not in ordered_images:
                        ordered_images.append(path)
                        found = True
                        break
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
    
    folder_time = int(os.path.getctime(folder_path))
    safe_name, safe_trans = asset_name.replace('"', '&quot;'), name_trans.replace('"', '&quot;')
    filenames_str = " ".join([f['name'] for f in files_data])
    search_str = f"{asset_id} {asset_name} {name_trans} {' '.join(tags)} {filenames_str}".lower().replace("'", "")
    rel_folder = quote(os.path.relpath(binary_folder, start=os.getcwd()))
    return f"""
    <li class="asset" onclick="openDetails('{asset_id}')" 
        data-id="{asset_id}" data-name-orig="{safe_name}" data-name-trans="{safe_trans}" data-img="{primary_img}" 
        data-all-images='{json.dumps(all_imgs).replace("'", "&apos;")}'
        data-bytes="{total_bytes}" data-files='{json.dumps(files_data).replace("'", "&apos;")}'
        data-tags='{json.dumps(tags).replace("'", "&apos;")}' data-adult="{str(is_adult).lower()}" 
        data-search='{search_str}' data-folder="{rel_folder}" data-booth-url="{booth_url}"
        data-filecount="{len(files_data)}" data-wish="{wish_count}" data-time="{folder_time}">
        <div class="image-container"><div class="asset-id-tag">#{asset_id}</div>{img_tag}</div>
        {glow_tag}<div class="content">
            <div class="name"><span class="name-primary">{asset_name}</span></div>
            <div class="stats"><span>{get_readable_size(total_bytes)}</span><span class="file-label-dynamic"></span></div>
            <div class="tag-row">{grid_tags_html}</div>
        </div>
    </li>
    """

asset_data_list, all_strings_to_translate = [], []
for folder in sorted(os.listdir(ROOT_FOLDER)):
    path = os.path.join(ROOT_FOLDER, folder)
    if not os.path.isdir(path): continue
    jsons = glob.glob(os.path.join(path, "_BoothPage.json")) or glob.glob(os.path.join(path, "_BoothInnerHtmlList.json"))
    if not jsons: continue
    with open(jsons[0], 'r', encoding='utf-8') as f:
        if jsons[0].endswith('_BoothPage.json'):
            data = json.load(f)
            name, tags, wish = data.get('name', 'N/A'), [t.get('name', '') for t in data.get('tags', [])], data.get('wish_lists_count', 0)
            all_strings_to_translate.extend([name] + tags)
            asset_data_list.append(('json', folder, data, path, wish))
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
        i_m = re.search(r'src=\"([^\"]+)\"', item)
        img = i_m.group(1) if i_m else ""
        u_m = re.search(r'href=\"([^\"]+)\"', item)
        url = u_m.group(1) if u_m else ""
        asset_items_final.append(generate_asset_html(folder, name, [img], url, path, [], is_adult_content(name), 0))

with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    f.write(HTML_PART_1 + "\\n".join(asset_items_final) + HTML_PART_2)

print("The library got updated.")