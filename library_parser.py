import os
import json
import glob
import re
import time
import sys
from collections import Counter
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed
from deep_translator import GoogleTranslator

# Configuration
ROOT_FOLDER = "BoothDownloaderOut"
OUTPUT_FILE = "asset_library.html"
CACHE_FILE = "translation_cache.json"
FILTER_FILE = "web_data/filters.json" 
SKIP_TRANSLATION = False  
DEBUG_TRANSLATION = False 
MAX_WORKERS = 5 

# Merged keyword list
ADULT_KEYWORDS = [
    r"R-?18", r"adult", r"nude", r"semen", r"nsfw", r"sexual", r"erotic", 
    r"pussy", r"dick", r"vagina", r"penis", r"otimpo", r"otinpo",
    "精液", "だぷだぷ", "ヌード", "エロ", "クリトリス", "おまんこ", "おちんぽ", "おてぃんぽ"
]

if os.path.exists(FILTER_FILE):
    try:
        with open(FILTER_FILE, 'r', encoding='utf-8') as f:
            ext_data = json.load(f)
            if isinstance(ext_data, list):
                ADULT_KEYWORDS.extend(ext_data)
    except: pass

ADULT_KEYWORDS = list(set(ADULT_KEYWORDS))

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
    <link rel="stylesheet" href="web_data/style.css" />
    <style>
        #appLoader { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: #0b0b0d; display: flex; flex-direction: column; align-items: center; justify-content: center; z-index: 9999; transition: opacity 0.6s ease; }
        .spinner { width: 50px; height: 50px; border: 3px solid rgba(253, 218, 13, 0.1); border-radius: 50%; border-top-color: #FDDA0D; animation: spin 1s ease-in-out infinite; margin-bottom: 20px; }
        @keyframes spin { to { transform: rotate(360deg); } }
        .loader-text { color: #FDDA0D; font-family: 'Inter', sans-serif; font-weight: 800; letter-spacing: 2px; font-size: 0.8rem; text-transform: uppercase; }
        #mainWrapper { opacity: 0; transition: opacity 0.8s ease; visibility: hidden; }
        body.loaded #mainWrapper { opacity: 1; visibility: visible; }
        body.loaded #appLoader { opacity: 0; pointer-events: none; }
        .asset { min-height: 350px; position: relative; overflow: hidden; background: #111114; contain: content; }
        .skeleton-shimmer {
            position: absolute; top: 0; left: 0; width: 100%; height: 100%;
            background: linear-gradient(90deg, #111114 25%, #1a1a1f 50%, #111114 75%);
            background-size: 200% 100%; animation: shimmer 1.5s infinite linear; z-index: 1;
        }
        @keyframes shimmer { from { background-position: 200% 0; } to { background-position: -200% 0; } }
        .image-thumbnail, .image-backglow, .content { opacity: 0; transition: opacity 0.6s ease-in-out; }
        .asset.is-visible .image-thumbnail, .asset.is-visible .image-backglow, .asset.is-visible .content { opacity: 1; }
        .asset.is-visible .skeleton-shimmer { display: none; }
        .asset.is-visible .image-backglow { filter: blur(45px) saturate(5) contrast(1.5); opacity: 0.7; }
        .asset.is-visible .content { backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); }
        .stat-row { margin-bottom: 4px; display: block; }
    </style>
</head>
<body>
    <div id="appLoader">
        <div class="spinner"></div>
        <div class="loader-text">Loading Library</div>
    </div>
    <div id="mainWrapper">
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
            <div class="stats-footer">
                <div class="stat-row"><span data-i18n="statItems">Items</span>: <b id="statCount">0</b></div>
                <div class="stat-row"><span data-i18n="statSize">Total Size</span>: <b id="statSize">0B</b></div>
                <div class="stat-row"><span data-i18n="statSpent">Estimated Spent</span>: <b id="statSpent">0</b></div>
                <div class="stat-row"><span data-i18n="statUpdated">Last Updated</span>: <b id="statDate">N/A</b></div>
                <span class="setting-label" style="margin-top:10px;" data-i18n="labelTopTags">Top Tags</span>
                <div id="commonTags" class="common-tags-grid"></div>
            </div>
        </div>
        <div class="container"><ul id="assetList">"""

HTML_PART_2 = """<li id="filterNotice"></li></ul></div>
    </div>
    <div id="detailModal" class="modal" onclick="closeModal()"><div class="modal-card" onclick="event.stopPropagation()"><div class="modal-carousel" id="modalCarouselContainer"><button id="carouselPrev" class="carousel-btn btn-prev" onclick="carouselNext(-1)">❮</button><img id="modalBlurBg" class="carousel-blur-bg" src=""><img id="modalImg" class="carousel-main-img" src=""><button id="carouselNext" class="carousel-btn btn-next" onclick="carouselNext(1)">❯</button><div id="carouselDots" class="carousel-dots"></div></div><div class="modal-info"><div id="modalName" class="modal-name"></div><div id="modalSubtitle" class="modal-subtitle"></div><div id="delistedWarn" class="delisted-warning" data-i18n-html="warnDelisted"></div><div id="modalTags" style="display:flex; flex-wrap:wrap; gap:6px; margin-bottom:20px;"></div><span class="setting-label" data-i18n="labelBinary">Binary Files</span><ul id="fileList" class="file-list"></ul><div class="modal-footer"><div id="modalIdDisp" class="modal-id-display"></div><div class="modal-actions"><a id="openBoothLink" href="" class="discrete-link" target="_blank"><span data-i18n="footBooth">🛒 Booth</span></a><a id="openFolderLink" href="" class="discrete-link" target="_blank"><span data-i18n="footFolder">📂 Folder</span></a></div></div></div></div></div>
    <script>
        const translations = {
            en: { warnDelisted: "<b>⚠️ Delisted Content</b>This asset was identified as potentially unavailable on Booth. Metadata support and detailed information are limited.", navTitle: "Booth Asset Library", optionsBtn: "Options ⚙", labelLanguage: "Language", labelSort: "Sort Order", optId: "Folder ID", optNew: "Recently Added", optName: "Alphabetical", optRel: "Relevance", optSize: "Total Size", labelAdult: "Adult Filter", optAll: "Show All", optHide: "Hide Adult", optOnly: "Only Adult", labelWidth: "Card Width", labelVisual: "Visual Controls", optBlur: "Disable Blur", optHideIds: "Hide Item IDs", optTranslate: "Use Translated Titles", labelBinary: "Binary Files", footBooth: "🛒 Open on Booth", footFolder: "📂 Open Local Folder", searchPre: "Search ", searchSuf: " items...", fileSingular: "file", filePlural: "files", moreTags: "+ {n} more", hiddenResults: " (+{n} hidden by filters)", statItems: "Items", statSize: "Total Size", statSpent: "Estimated Spent", statUpdated: "Last Updated", labelTopTags: "Top Tags" },
            de: { warnDelisted: "<b>⚠️ Nicht mehr gelistet</b>Dieses Asset ist wahrscheinlich nicht mehr auf Booth verfügbar. Die Metadaten-Unterstützung ist eingeschränkt.", navTitle: "Booth Bibliothek", optionsBtn: "Optionen ⚙", labelLanguage: "Sprache", labelSort: "Sortierung", optId: "ID", optNew: "Zuletzt hinzugefügt", optName: "Alphabetisch", optRel: "Beliebtheit", optSize: "Größe", labelAdult: "Filter", optAll: "Alles", optHide: "Ausblenden", optOnly: "Nur 18+", labelWidth: "Breite", labelVisual: "Anzeige", optBlur: "Kein Fokus", optHideIds: "IDs weg", optTranslate: "Übersetzte Titel", labelBinary: "Dateien", footBooth: "🛒 Booth", footFolder: "📂 Ordner", searchPre: "Suche ", searchSuf: " Artikel...", fileSingular: "Datei", filePlural: "Dateien", moreTags: "+ {n} weitere", hiddenResults: " (+{n} durch Filter versteckt)", statItems: "アイテム数", statSize: "Gesamtgröße", statSpent: "Kosten", statUpdated: "Aktualisiert", labelTopTags: "Top Tags" },
            ja: { warnDelisted: "<b>⚠️ 公開停止アイテム</b>このアセットは現在Boothで公開されていない可能性があります。メタデータのサポートが制限されています。", navTitle: "Boothアセットライブラリ", optionsBtn: "設定 ⚙", labelLanguage: "言語", labelSort: "並び替え", optId: "ID", optNew: "最近追加された", optName: "名前順", optRel: "人気順", optSize: "サイズ", labelAdult: "フィルター", optAll: "すべて表示", optHide: "隠す", optOnly: "成人向けのみ", labelWidth: "幅", labelVisual: "表示", optBlur: "ぼかし解除", optHideIds: "ID非表示", optTranslate: "翻訳後の名前を表示", labelBinary: "ファイル", footBooth: "🛒 Booth", footFolder: "📂 フォルダ", searchPre: "検索：", searchSuf: " 件", fileSingular: "ファイル", filePlural: "ファイル", moreTags: "他 {n} 件", hiddenResults: " (他 {n} 件がフィルター済み)", statItems: "アイテム数", statSize: "合計サイズ", statSpent: "推定支出額", statUpdated: "最終更新日", labelTopTags: "人気のタグ" },
            ko: { warnDelisted: "<b>⚠️ 판매 중지된 콘텐츠</b>이 에셋은 Booth에서 더 이상 제공되지 않을 가능성이 높습니다. 메타데이터 지원이 제한적입니다.", navTitle: "Booth 에셋 라이브러리", optionsBtn: "설정 ⚙", labelLanguage: "언어", labelSort: "정렬", optId: "ID", optNew: "최근 추가됨", optName: "이름순", optRel: "관련성", optSize: "용량", labelAdult: "성인 필터", optAll: "모두 표시", optHide: "성인 숨기기", optOnly: "성인 전용", labelWidth: "너비", labelVisual: "表示", optBlur: "블러 해제", optHideIds: "ID 숨기기", optTranslate: "번역 제목 사용", labelBinary: "파일", footBooth: "🛒 Booth 보기", footFolder: "📂 폴더 열기", searchPre: "검색: ", searchSuf: "개", fileSingular: "파일", filePlural: "파일", moreTags: "+ {n}개 더보기", hiddenResults: " (+{n}개 숨김)", statItems: "항목", statSize: "총 용량", statSpent: "지출 합계", statUpdated: "업데이트 일자", labelTopTags: "인기 태그" },
            'zh-Hans': { warnDelisted: "<b>⚠️ 已下架内容</b>此资源可能已无法在 Booth 上访问。元数据支持和詳細信息有限。", navTitle: "Booth 资源库", optionsBtn: "选项 ⚙", labelLanguage: "语言", labelSort: "排序", optId: "ID", optNew: "最近添加", optName: "名称排序", optRel: "相关性", optSize: "大小", labelAdult: "成人过滤", optAll: "显示全部", optHide: "隐藏成人", optOnly: "仅成人", labelWidth: "宽度", labelVisual: "视觉控制", optBlur: "禁用模糊", optHideIds: "隐藏 ID", optTranslate: "显示翻译名称", labelBinary: "二进制文件", footBooth: "🛒 在 Booth 打开", footFolder: "📂 打开文件夹", searchPre: "搜索 ", searchSuf: " 个项目", fileSingular: "文件", filePlural: "文件", moreTags: "+ {n} 更多", hiddenResults: " (+{n} 个被过滤)", statItems: "项目", statSize: "总大小", statSpent: "预计支出", statUpdated: "最后更新", labelTopTags: "热门标签" },
            'zh-Hant': { warnDelisted: "<b>⚠️ 已下架內容</b>此資源可能已無法在 Booth 上訪問。元數據支持和詳細信息有限。", navTitle: "Booth 資源庫", optionsBtn: "選項 ⚙", labelLanguage: "語言", labelSort: "排序", optId: "ID", optNew: "最近添加", optName: "名稱排序", optRel: "相關性", optSize: "大小", labelAdult: "成人過濾", optAll: "顯示全部", optHide: "隱藏成人", optOnly: "僅限成人", labelWidth: "寬度", labelVisual: "視覺控制", optBlur: "禁用模糊", optHideIds: "隱藏 ID", optTranslate: "顯示翻譯名稱", labelBinary: "二進制檔案", footBooth: "🛒 在 Booth 打開", footFolder: "📂 打開資料夾", searchPre: "搜尋 ", searchSuf: " 個項目", fileSingular: "檔案", filePlural: "檔案", moreTags: "+ {n} 更多", hiddenResults: " (+{n} 個被過濾)", statItems: "項目", statSize: "總大小", statSpent: "預計支出", statUpdated: "最後更新", labelTopTags: "熱門標籤" },
            nl: { warnDelisted: "<b>⚠️ Verwijderde Inhoud</b>Dit item is mogelijk niet langer beschikbaar op Booth. Metadata ondersteuning is beperkt.", navTitle: "Booth Bibliotheek", optionsBtn: "Opties ⚙", labelLanguage: "Taal", labelSort: "Sorteer", optId: "ID", optNew: "Onlangs toegevoegd", optName: "Alfabet", optRel: "Relevantie", optSize: "Grootte", labelAdult: "Filter", optAll: "Alles tonen", optHide: "Verbergen", optOnly: "Alleen 18+", labelWidth: "Breedte", labelVisual: "Visueel", optBlur: "Geen vervaging", optHideIds: "ID's weg", optTranslate: "Engelse titels", labelBinary: "Bestanden", footBooth: "🛒 Booth", footFolder: "📂 Map", searchPre: "Zoek in ", searchSuf: " items...", fileSingular: "bestand", filePlural: "bestanden", moreTags: "+ {n} meer", hiddenResults: " (+{n} verborgen door filters)", statItems: "Items", statSize: "Totale grootte", statSpent: "Geschatte uitgaven", statUpdated: "Laatst bijgewerkt", labelTopTags: "Populaire tags" },
            fr: { warnDelisted: "<b>⚠️ Contenu non listé</b>Cet asset n'est probablement plus disponible sur Booth. Le support des métadonnées is limité.", navTitle: "Bibliothèque Booth", optionsBtn: "Options ⚙", labelLanguage: "Langue", labelSort: "Trier", optId: "ID", optNew: "Ajouté récemment", optName: "Nom", optRel: "Pertinence", optSize: "Taille", labelAdult: "Filtre", optAll: "Tout", optHide: "Masquer", optOnly: "Adulte", labelWidth: "Largeur", labelVisual: "Visuel", optBlur: "Déshabiller flou", optHideIds: "Masquer IDs", optTranslate: "Titres anglais", labelBinary: "Fichiers", footBooth: "🛒 Booth", footFolder: "📂 Dossier", searchPre: "Rechercher ", searchSuf: " items...", fileSingular: "fichier", filePlural: "fichiers", moreTags: "+ {n} de plus", hiddenResults: " (+{n} masqués)", statItems: "Articles", statSize: "Taille totale", statSpent: "Dépenses estimées", statUpdated: "Dernière mise à jour", labelTopTags: "Tags populaires" },
            es: { warnDelisted: "<b>⚠️ Contenido no listado</b>Es probable que este activo ya no esté disponible en Booth. El soporte de metadatos is limitado.", navTitle: "Biblioteca Booth", optionsBtn: "Opciones ⚙", labelLanguage: "Idioma", labelSort: "Orden", optId: "ID", optNew: "Más reciente", optName: "Nombre", optRel: "Relevancia", optSize: "Tamaño", labelAdult: "Filtro", optAll: "Todo", optHide: "Ocultar", optOnly: "Adultos", labelWidth: "Ancho", labelVisual: "Visual", optBlur: "Sin desenfoque", optHideIds: "Ocultar IDs", optTranslate: "Títulos inglés", labelBinary: "Archivos", footBooth: "🛒 Booth", footFolder: "📂 Carpeta", searchPre: "Buscar ", searchSuf: " items...", fileSingular: "archivo", filePlural: "archivos", moreTags: "+ {n} más", hiddenResults: " (+{n} ocultos)", statItems: "Artículos", statSize: "Tamaño total", statSpent: "Gasto estimado", statUpdated: "Última actualización", labelTopTags: "Etiquetas populares" },
            pt: { warnDelisted: "<b>⚠️ Conteúdo não listado</b>Este asset provavelmente não está mais disponible no Booth. O suporte de metadatos é limité.", navTitle: "Biblioteca Booth", optionsBtn: "Opções ⚙", labelLanguage: "Idioma", labelSort: "Ordenar", optId: "ID", optNew: "Mais recentes", optName: "Nome", optRel: "Relevância", optSize: "Tamanho", labelAdult: "Filtro adulto", optAll: "Tudo", optHide: "Ocultar adultos", optOnly: "Apenas 18+", labelWidth: "Largura", labelVisual: "Visual", optBlur: "Sem flou", optHideIds: "Sem IDs", optTranslate: "Títulos inglés", labelBinary: "Arquivos", footBooth: "🛒 Booth", footFolder: "📂 Pasta", searchPre: "Pesquisar ", searchSuf: " itens...", fileSingular: "arquivo", filePlural: "arquivos", moreTags: "+ {n} mais", hiddenResults: " (+{n} ocultos)", statItems: "Itens", statSize: "Tamanho total", statSpent: "Gasto estimado", statUpdated: "Última atualização", labelTopTags: "Tags populares" }
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

        const observerOptions = { root: null, rootMargin: '600px', threshold: 0.01 };
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
            setTimeout(() => {
                updateLanguage(state.lang); updateGrid(state.gridSize); updateBlur(state.disableBlur); updateIdVisibility(state.hideIds); updateTranslationVisibility(state.showTrans);
                document.getElementById('gridRange').value = state.gridSize; document.getElementById('blurToggle').checked = state.disableBlur; document.getElementById('sortOrder').value = state.sortOrder;
                document.getElementById('adultFilter').value = state.adultFilter; document.getElementById('hideIdToggle').checked = state.hideIds; document.getElementById('translateToggle').checked = state.showTrans;
                
                const items = document.getElementsByClassName('asset');
                let totalBytes = 0;
                const tagCounts = {};
                const spent = {};

                for(let item of items) { 
                    totalBytes += parseInt(item.dataset.bytes || 0); 
                    const tags = JSON.parse(item.dataset.tags || "[]");
                    tags.forEach(t => tagCounts[t] = (tagCounts[t] || 0) + 1);
                    const pVal = parseFloat(item.dataset.priceValue || 0);
                    const pCur = item.dataset.priceCurrency || "";
                    if (pVal > 0 && pCur) spent[pCur] = (spent[pCur] || 0) + pVal;
                    observer.observe(item);
                }

                const topTags = Object.entries(tagCounts).sort((a,b) => b[1] - a[1]).slice(0, 10);
                document.getElementById('commonTags').innerHTML = topTags.map(([tag]) => `<span class="tag-pill clickable" onclick="tagSearch('${tag.replace(/'/g, "\\\\'")}')">${tag}</span>`).join('');

                document.getElementById('statCount').innerText = items.length;
                document.getElementById('statSize').innerText = formatBytes(totalBytes);
                document.getElementById('statSpent').innerText = Object.entries(spent).map(([cur, val]) => val.toLocaleString() + " " + cur).join(" / ") || "0";
                document.getElementById('statDate').innerText = new Date().toLocaleDateString();

                handleSearchInput(); sortAssets();
                const urlParams = new URLSearchParams(window.location.search);
                const targetId = urlParams.get('id');
                if (targetId) openDetails(targetId, true);
                document.body.classList.add('loaded');
            }, 50);
        }

        window.onpopstate = (e) => {
            const urlParams = new URLSearchParams(window.location.search);
            const targetId = urlParams.get('id');
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
        function updateTranslationVisibility(v) { state.showTrans = v; localStorage.setItem('showTrans', v); const items = document.getElementsByClassName('asset'); for(let item of items) { 
            const primaryName = item.querySelector('.name-primary'); 
            primaryName.innerText = (v && item.dataset.nameTrans) ? item.dataset.nameTrans : item.dataset.nameOrig;
            const authorPrimary = item.querySelector('.author-primary');
            authorPrimary.innerText = (v && item.dataset.authorTrans) ? item.dataset.authorTrans : item.dataset.authorOrig;
        } }
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
        function openDetails(id, skipHistory = false) {
            const el = document.querySelector(`.asset[data-id="${id}"]`), t = translations[state.lang] || translations['en'];
            if(!el) return;
            const displayTitle = (state.showTrans && el.dataset.nameTrans) ? el.dataset.nameTrans : el.dataset.nameOrig;
            const displayAuthor = (state.showTrans && el.dataset.authorTrans) ? el.dataset.authorTrans : el.dataset.authorOrig;
            const subtitle = (state.showTrans && el.dataset.nameTrans) ? el.dataset.nameOrig : "";
            document.getElementById("modalName").innerText = displayTitle;
            document.getElementById("modalSubtitle").innerText = (subtitle ? subtitle + " | " : "") + displayAuthor;
            document.getElementById("modalIdDisp").innerText = "#" + id;
            document.getElementById("openFolderLink").href = el.dataset.folder;
            document.getElementById("openBoothLink").href = el.dataset.boothUrl;
            document.getElementById("delistedWarn").style.display = (el.dataset.limited === 'true') ? 'block' : 'none';
            currentImages = JSON.parse(el.dataset.allImages); currentCarouselIndex = 0; updateCarousel();
            const tags = JSON.parse(el.dataset.tags);
            const tagContainer = document.getElementById("modalTags");
            const renderTagsInternal = (list) => list.map(tg => `<span class="tag-pill clickable" onclick="tagSearch('${tg.replace(/'/g, "\\\\'")}')">${tg}</span>`).join('');
            if (tags.length > 25) { tagContainer.innerHTML = renderTagsInternal(tags.slice(0, 20)) + `<span class="tag-pill more-btn clickable" onclick="this.parentElement.innerHTML=window.renderTagsFull(JSON.parse(document.querySelector('.asset[data-id=\\\\'${id}\\\\\\']').dataset.tags))">${t.moreTags.replace('{n}', tags.length - 20)}</span>`; } else tagContainer.innerHTML = renderTagsInternal(tags);
            window.renderTagsFull = renderTagsInternal;
            const fileData = JSON.parse(el.dataset.files);
            fileData.sort((a, b) => b.name.toLowerCase().localeCompare(a.name.toLowerCase(), undefined, { numeric: true, sensitivity: 'base' }));
            document.getElementById("fileList").innerHTML = fileData.map(f => `<li class="file-item"><a class="file-link" href="${f.path}" target="_blank">${f.name}</a><span style="color:#aaa;font-size:0.75rem;">${f.size}</span></li>`).join('');
            const m = document.getElementById("detailModal"); m.classList.add('visible'); setTimeout(() => m.classList.add('active'), 10);
            document.title = baseTitle + " - #" + id;
            if (!skipHistory) { const newUrl = new URL(window.location); newUrl.searchParams.set('id', id); window.history.pushState({id: id}, '', newUrl); }
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
        function closeModal(skipHistory = false) { 
            const m = document.getElementById("detailModal"); m.classList.remove('active'); setTimeout(() => { if(!m.classList.contains('active')) m.classList.remove('visible'); }, 300);
            document.title = baseTitle;
            if (!skipHistory) { const newUrl = new URL(window.location); newUrl.searchParams.delete('id'); window.history.pushState({}, '', newUrl); }
        }
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
                rel = os.path.relpath(fp, start=os.getcwd()).replace('\\', '/')
                files.append({"name": f, "path": quote(rel), "size": get_readable_size(os.path.getsize(fp))})
    return files, total_size

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
    if match: return float(match.group(1)), match.group(2)
    return 0.0, ""

def generate_asset_html(asset_id, asset_name, author_name, web_images, booth_url, folder_path, tags, is_adult, wish_count, price_str, limited=False):
    binary_folder = os.path.join(folder_path, 'Binary')
    files_data, total_bytes = get_dir_data(binary_folder)
    all_imgs = get_all_local_images(folder_path, web_images)
    primary_img = all_imgs[0] if all_imgs else ""
    name_trans = translation_cache.get(asset_name.strip(), "")
    author_trans = translation_cache.get(author_name.strip(), "")
    price_val, price_cur = parse_price(price_str)
    grid_tags_html = "".join([f'<span class="tag-pill">{t}</span>' for t in tags[:12]])
    img_class = "image-thumbnail adult-content" if is_adult else "image-thumbnail"
    folder_time = int(os.path.getctime(folder_path))
    safe_name, safe_trans = asset_name.replace('"', '&quot;'), name_trans.replace('"', '&quot;')
    safe_author, safe_author_trans = author_name.replace('"', '&quot;'), author_trans.replace('"', '&quot;')
    filenames_str = " ".join([f['name'] for f in files_data])
    search_str = f"{asset_id} {asset_name} {name_trans} {author_name} {author_trans} {' '.join(tags)} {filenames_str}".lower().replace("'", "")
    rel_folder = quote(os.path.relpath(binary_folder, start=os.getcwd()).replace('\\', '/'))
    return f"""
    <li class="asset" onclick="openDetails('{asset_id}')" 
        data-id="{asset_id}" data-name-orig="{safe_name}" data-name-trans="{safe_trans}" 
        data-author-orig="{safe_author}" data-author-trans="{safe_author_trans}" data-img="{primary_img}" 
        data-all-images='{json.dumps(all_imgs).replace("'", "&apos;")}'
        data-bytes="{total_bytes}" data-files='{json.dumps(files_data).replace("'", "&apos;")}'
        data-tags='{json.dumps(tags).replace("'", "&apos;")}' data-adult="{str(is_adult).lower()}" 
        data-search='{search_str}' data-folder="{rel_folder}" data-booth-url="{booth_url}"
        data-filecount="{len(files_data)}" data-wish="{wish_count}" data-time="{folder_time}"
        data-price-value="{price_val}" data-price-currency="{price_cur}" data-limited="{str(limited).lower()}">
        <div class="skeleton-shimmer"></div>
        <div class="image-container"><div class="asset-id-tag">#{asset_id}</div><img class="{img_class}" loading="lazy"></div>
        <img class="image-backglow"><div class="content">
            <div class="name"><span class="name-primary">{asset_name}</span></div>
            <div class="author-label">by <b class="author-primary">{author_name}</b></div>
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
            author = data.get('shop', {}).get('name', 'N/A')
            all_strings_to_translate.extend([name, author] + tags)
            asset_data_list.append(('json', folder, (name, author, data), path, wish))
        else:
            data = json.load(f)
            item = data[0] if data else ""
            if item:
                name_m = re.search(r'break-all\">(.*?)<\/div>', item) or re.search(r'>(.*?)<\/div>', item)
                name = name_m.group(1) if name_m else "N/A"
                author_m = re.search(r'text-text-gray600 break-all\">(.*?)<\/div>', item)
                author = author_m.group(1) if author_m else "N/A"
                all_strings_to_translate.extend([name, author])
                asset_data_list.append(('limited', folder, (name, author, item), path, 0))

bulk_translate(all_strings_to_translate)
if not SKIP_TRANSLATION:
    with open(CACHE_FILE, 'w', encoding='utf-8') as f: json.dump(translation_cache, f, ensure_ascii=False, indent=2)

asset_items_final = []
for type, folder, data, path, wish in asset_data_list:
    name, author, content = data
    if type == 'json':
        web_imgs = [img.get('original', '') for img in content.get('images', [])]
        tags = [t.get('name', '') for t in content.get('tags', [])]
        asset_items_final.append(generate_asset_html(folder, name, author, web_imgs, content.get('url', ''), path, tags, content.get('is_adult', False) or is_adult_content(name), wish, content.get('price', ''), limited=False))
    else:
        i_m = re.search(r'src=\"([^\"]+)\"', content)
        img = i_m.group(1) if i_m else ""
        u_m = re.search(r'href=\"([^\"]+)\"', content)
        url = u_m.group(1) if u_m else ""
        asset_items_final.append(generate_asset_html(folder, name, author, [img], url, path, [], is_adult_content(name), 0, "", limited=True))

with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    f.write(HTML_PART_1 + "\n".join(asset_items_final) + HTML_PART_2)

print("The library got updated.")