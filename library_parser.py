import os
import json
import glob
import re
from urllib.parse import quote

# Configuration
ROOT_FOLDER = "BoothDownloaderOut"
OUTPUT_FILE = "asset_library.html"

# Keyword detection for Adult content
ADULT_KEYWORDS_EN = [
    r"R-?18", r"adult", r"nude", r"semen", r"nsfw", r"sexual", 
    r"erotic", r"pussy", r"dick", r"vagina", r"penis", r"otimpo", r"otinpo"
]
ADULT_KEYWORDS_JP = ["精液", "だぷだぷ", "ヌード", "エロ", "クリトリス", "おまんこ", "おちんぽ", "おてぃんぽ"]

HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Booth Asset Library</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
    <style>
        :root {{ --primary: #FDDA0D; --bg: #0b0b0d; --card: #16161a; --text: #ddd; --grid-size: 220px; }}
        * {{ box-sizing: border-box; }}
        body {{ font-family: 'Inter', sans-serif; background-color: var(--bg); color: var(--text); margin: 0; padding: 0; overflow-x: hidden; }}
        
        /* Navbar */
        .top-nav {{
            position: sticky; top: 0; z-index: 1000;
            background: rgba(11, 11, 13, 0.9); backdrop-filter: blur(12px);
            border-bottom: 1px solid #222; padding: 15px 30px;
            display: flex; align-items: center; justify-content: space-between; gap: 20px;
        }}
        .nav-logo {{ color: var(--primary); font-weight: 800; font-size: 1.2rem; white-space: nowrap; }}
        .search-container {{ flex-grow: 1; display: flex; justify-content: center; position: relative; max-width: 500px; }}
        .search-input {{ padding: 10px 45px 10px 20px; width: 100%; background: #1a1a1f; border: 1px solid #333; border-radius: 8px; color: white; outline: none; transition: border-color 0.3s; }}
        .search-input:focus {{ border-color: var(--primary); }}
        
        .clear-search {{ 
            position: absolute; right: 15px; top: 50%; transform: translateY(-50%); 
            background: none; border: none; color: #666; font-size: 1.2rem; 
            cursor: pointer; padding: 0; display: none; 
        }}
        .search-input:not(:placeholder-shown) + .clear-search {{ display: block; }}
        .clear-search:hover {{ color: var(--primary); }}

        .nav-btn {{ background: #222; border: 1px solid #333; color: white; padding: 10px 18px; border-radius: 8px; cursor: pointer; font-weight: 600; position: relative; z-index: 2001; }}
        .nav-btn.active {{ border-color: var(--primary); color: var(--primary); }}

        /* Flyout Menu */
        #menuPerimeter {{ display: none; position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; z-index: 1999; }}
        .flyout-menu {{
            display: none; position: fixed; top: 75px; right: 30px; width: 320px;
            background: rgba(26, 26, 31, 0.98); backdrop-filter: blur(20px);
            border: 1px solid rgba(253, 218, 13, 0.3); z-index: 2000; padding: 25px; border-radius: 16px; 
            opacity: 0; transform: translateY(-20px) scale(0.95); transition: 0.3s;
            pointer-events: none; box-shadow: 0 20px 60px rgba(0,0,0,0.8);
        }}
        .flyout-menu.open {{ display: block; opacity: 1; transform: translateY(0); pointer-events: all; }}
        .setting-group {{ margin-bottom: 25px; width: 100%; }}
        .setting-label {{ display: block; margin: 15px 0 8px; font-size: 0.7rem; color: #555; text-transform: uppercase; font-weight: 800; }}
        select {{ width: 100%; background: #0b0b0d; color: white; border: 1px solid #333; padding: 10px; border-radius: 8px; outline: none; }}
        input[type=range] {{ width: 100%; background: transparent; accent-color: var(--primary); cursor: pointer; margin: 0; display: block; }}

        /* Grid */
        .container {{ max-width: 1600px; margin: 40px auto; padding: 0 30px; }}
        #assetList {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(var(--grid-size), 1fr)); gap: 35px; list-style: none; padding: 0; }}
        .asset {{ background: #111114; border: 1px solid #252525; border-radius: 12px; overflow: hidden; cursor: pointer; display: flex; flex-direction: column; height: 100%; transition: 0.3s; position: relative; }}
        .asset:hover {{ border-color: var(--primary); transform: translateY(-5px); }}

        .image-container {{ position: relative; width: 100%; padding-top: 100%; background: #000; flex-shrink: 0; z-index: 5; overflow: hidden; border-radius: 12px 12px 0 0; }}
        .image-thumbnail {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; transition: 0.4s; z-index: 10; }}
        .image-backglow {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; filter: blur(45px) saturate(5) contrast(1.5); opacity: 0.7; z-index: 1; pointer-events: none; transform: scale(1.6); }}
        .asset-id-tag {{ position: absolute; bottom: 8px; left: 8px; z-index: 20; background: rgba(0,0,0,0.7); color: #fff; font-size: 0.65rem; padding: 2px 6px; border-radius: 4px; font-weight: 800; backdrop-filter: blur(4px); border: 1px solid rgba(255,255,255,0.1); }}
        
        body.hide-ids .asset-id-tag {{ display: none; }}
        .adult-content {{ filter: blur(50px); }}
        .asset:hover .adult-content {{ filter: blur(0px); }}
        body.no-blur .adult-content {{ filter: blur(0px) !important; }}

        .content {{ padding: 15px; flex-grow: 1; display: flex; flex-direction: column; z-index: 10; position: relative; background: rgba(18, 18, 22, 0.8); backdrop-filter: blur(5px); }}
        .name {{ font-weight: 600; color: #fff; line-height: 1.3; margin-bottom: 8px; font-size: 0.9rem; height: 2.6em; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }}
        .stats {{ color: #aaa; font-size: 0.75rem; display: flex; gap: 10px; margin-top: auto; font-weight: 600; }}
        .tag-row {{ display: flex; flex-wrap: wrap; gap: 4px; margin-top: 10px; height: 18px; overflow: hidden; }}
        .tag-pill {{ font-size: 0.65rem; background: rgba(0,0,0,0.4); height: 18px; line-height: 18px; padding: 0 8px; border-radius: 4px; color: #fff; white-space: nowrap; border: 1px solid rgba(255,255,255,0.1); display: inline-flex; align-items: center; justify-content: center; transition: background 0.2s, color 0.2s; }}

        .modal-info .tag-pill {{ cursor: pointer; height: 22px; font-size: 0.75rem; padding: 0 10px; }}
        .modal-info .tag-pill:hover {{ background: var(--primary); color: #000; border-color: var(--primary); }}

        /* Modal */
        .modal {{ display: none; position: fixed; z-index: 3000; left: 0; top: 0; width: 100%; height: 100%; align-items: center; justify-content: center; transition: 0.3s; padding: 20px; box-sizing: border-box; }}
        .modal.visible {{ display: flex; }}
        .modal.active {{ background: rgba(0,0,0,0.95); }}
        .modal-card {{ background: #1a1a1f; width: 100%; max-width: 1100px; max-height: 90vh; border: 1px solid var(--primary); border-radius: 16px; display: flex; flex-wrap: wrap; overflow-y: auto; opacity: 0; transform: scale(0.9); transition: 0.3s; position: relative; }}
        .modal.active .modal-card {{ opacity: 1; transform: scale(1); }}
        
        .modal-carousel {{ flex: 1 1 450px; background: #000; display: flex; align-items: center; justify-content: center; position: relative; overflow: hidden; min-height: 350px; }}
        .carousel-blur-bg {{ position: absolute; top: -10%; left: -10%; width: 120%; height: 120%; object-fit: cover; filter: blur(40px) brightness(0.5); opacity: 0.8; z-index: 1; transition: 0.4s; }}
        .carousel-main-img {{ max-width: 100%; max-height: 100%; object-fit: contain; position: relative; z-index: 2; transition: 0.4s; }}
        
        .carousel-btn {{ position: absolute; top: 50%; transform: translateY(-50%); z-index: 10; background: rgba(0,0,0,0.5); border: 1px solid rgba(255,255,255,0.2); color: white; padding: 15px 10px; cursor: pointer; border-radius: 4px; font-size: 1.2rem; transition: 0.2s; display: none; }}
        .carousel-btn:hover {{ background: var(--primary); color: #000; }}
        .btn-prev {{ left: 15px; }}
        .btn-next {{ right: 15px; }}
        .carousel-dots {{ position: absolute; bottom: 20px; left: 50%; transform: translateX(-50%); display: flex; gap: 8px; z-index: 10; }}
        .dot {{ width: 8px; height: 8px; border-radius: 50%; background: rgba(255,255,255,0.3); cursor: pointer; transition: 0.2s; }}
        .dot.active {{ background: var(--primary); transform: scale(1.3); }}

        .modal-info {{ flex: 1 1 400px; padding: 30px; display: flex; flex-direction: column; min-width: 320px; position: relative; padding-bottom: 60px; }}
        .modal-name {{ font-size: 1.5rem; font-weight: 800; color: var(--primary); margin-bottom: 5px; }}
        .file-list {{ list-style: none; padding: 0; margin-top: 10px; }}
        .file-item {{ padding: 10px; background: #222; border-radius: 8px; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center; gap: 10px; }}
        .file-link {{ color: #fff; text-decoration: none; font-size: 0.85rem; word-break: break-all; flex-grow: 1; }}
        .file-link:hover {{ color: var(--primary); }}
        
        .modal-footer {{ position: absolute; bottom: 20px; right: 30px; display: flex; gap: 20px; }}
        .discrete-link {{ color: #555; text-decoration: none; font-size: 0.75rem; font-weight: 600; display: flex; align-items: center; gap: 6px; transition: color 0.2s; }}
        .discrete-link:hover {{ color: var(--primary); }}
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
        <div class="setting-group">
            <span class="setting-label" data-i18n="labelLanguage">Language</span>
            <select id="langSelect" onchange="updateLanguage(this.value)">
                <option value="de">Deutsch</option>
                <option value="en">English</option>
                <option value="es">Español</option>
                <option value="fr">Français</option>
                <option value="ja">日本語</option>
                <option value="nl">Nederlands</option>
                <option value="pt">Português</option>
            </select>
        </div>
        <div class="setting-group">
            <span class="setting-label" data-i18n="labelSort">Sort Order</span>
            <select id="sortOrder" onchange="sortAssets(true)">
                <option value="id" data-i18n="optId">Folder ID</option>
                <option value="name" data-i18n="optName">Alphabetical</option>
                <option value="size" data-i18n="optSize">Total Size</option>
            </select>
        </div>
        <div class="setting-group">
            <span class="setting-label" data-i18n="labelAdult">Adult Filter</span>
            <select id="adultFilter" onchange="applyFilters(true)">
                <option value="all" data-i18n="optAll">Show All Content</option>
                <option value="hide" data-i18n="optHide">Hide Adult Content</option>
                <option value="only" data-i18n="optOnly">Only Adult Content</option>
            </select>
        </div>
        <div class="setting-group">
            <span class="setting-label" data-i18n="labelWidth">Card Width</span>
            <input type="range" id="gridRange" min="180" max="500" value="220" oninput="updateGrid(this.value)">
        </div>
        <div class="setting-group">
            <span class="setting-label" data-i18n="labelVisual">Visual Controls</span>
            <label style="display:flex; gap:10px; cursor:pointer; font-size:0.9rem; margin-bottom:10px;">
                <input type="checkbox" id="blurToggle" onchange="updateBlur(this.checked)"> <span data-i18n="optBlur">Disable Adult Blur</span>
            </label>
            <label style="display:flex; gap:10px; cursor:pointer; font-size:0.9rem;">
                <input type="checkbox" id="hideIdToggle" onchange="updateIdVisibility(this.checked)"> <span data-i18n="optHideIds">Hide Item IDs</span>
            </label>
        </div>
    </div>

    <div class="container"><ul id="assetList">{assets}</ul></div>

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
                <div id="modalName" class="modal-name"></div>
                <div id="modalIdDisp" style="color:#555; font-size:0.8rem; font-weight:800; margin-bottom:15px;"></div>
                <div id="modalTags" style="display:flex; flex-wrap:wrap; gap:6px; margin-bottom:20px;"></div>
                <span class="setting-label" data-i18n="labelBinary">Binary Files</span>
                <ul id="fileList" class="file-list"></ul>
                
                <div class="modal-footer">
                    <a id="openBoothLink" href="" class="discrete-link" target="_blank"><span data-i18n="footBooth">🛒 Open on Booth</span></a>
                    <a id="openFolderLink" href="" class="discrete-link" target="_blank"><span data-i18n="footFolder">📂 Open Local Folder</span></a>
                </div>
            </div>
        </div>
    </div>

    <script>
        const translations = {{
            en: {{
                navTitle: "Booth Asset Library", optionsBtn: "Options ⚙", labelLanguage: "Language", labelSort: "Sort Order", 
                optId: "Folder ID", optName: "Alphabetical", optSize: "Total Size", labelAdult: "Adult Filter",
                optAll: "Show All Content", optHide: "Hide Adult Content", optOnly: "Only Adult Content",
                labelWidth: "Card Width", labelVisual: "Visual Controls", optBlur: "Disable Adult Blur",
                optHideIds: "Hide Item IDs", labelBinary: "Binary Files", footBooth: "🛒 Open on Booth", 
                footFolder: "📂 Open Local Folder", searchPre: "Search ", searchSuf: " items...",
                fileSingular: "file", filePlural: "files"
            }},
            de: {{
                navTitle: "Booth Asset Bibliothek", optionsBtn: "Optionen ⚙", labelLanguage: "Sprache", labelSort: "Sortierung", 
                optId: "Ordner-ID", optName: "Alphabetisch", optSize: "Dateigröße", labelAdult: "Erwachsenenfilter",
                optAll: "Alle Inhalte anzeigen", optHide: "Inhalte ausblenden", optOnly: "Nur ab 18",
                labelWidth: "Kartenbreite", labelVisual: "Visualisierung", optBlur: "Unschärfe deaktivieren",
                optHideIds: "IDs ausblenden", labelBinary: "Dateien", footBooth: "🛒 Auf Booth öffnen", 
                footFolder: "📂 Lokalen Ordner öffnen", searchPre: "Suche ", searchSuf: " Artikel...",
                fileSingular: "Datei", filePlural: "Dateien"
            }},
            ja: {{
                navTitle: "Boothアセットライブラリ", optionsBtn: "設定 ⚙", labelLanguage: "言語", labelSort: "並び替え", 
                optId: "フォルダID", optName: "名前順", optSize: "ファイルサイズ", labelAdult: "成人向けフィルター",
                optAll: "すべてのコンテンツを表示", optHide: "成人向けを隠す", optOnly: "成人向けのみ",
                labelWidth: "カードの幅", labelVisual: "表示設定", optBlur: "ぼかしを無効化",
                optHideIds: "IDを非表示", labelBinary: "バイナリファイル", footBooth: "🛒 Boothで開く", 
                footFolder: "📂 ローカルフォルダを開く", searchPre: "検索：", searchSuf: " 件のアイテム",
                fileSingular: "ファイル", filePlural: "ファイル"
            }},
            fr: {{
                navTitle: "Bibliothèque d'actifs Booth", optionsBtn: "Options ⚙", labelLanguage: "Langue", labelSort: "Trier par", 
                optId: "ID du dossier", optName: "Alphabétique", optSize: "Taille totale", labelAdult: "Filtre adulte",
                optAll: "Tout afficher", optHide: "Masquer le contenu adulte", optOnly: "Seulement adulte",
                labelWidth: "Largeur des cartes", labelVisual: "Contrôles visuels", optBlur: "Désactiver le flou",
                optHideIds: "Masquer les IDs", labelBinary: "Fichiers binaires", footBooth: "🛒 Ouvrir sur Booth", 
                footFolder: "📂 Ouvrir le dossier", searchPre: "Rechercher ", searchSuf: " articles...",
                fileSingular: "fichier", filePlural: "fichiers"
            }},
            es: {{
                navTitle: "Biblioteca de Activos Booth", optionsBtn: "Opciones ⚙", labelLanguage: "Idioma", labelSort: "Ordenar por", 
                optId: "ID de carpeta", optName: "Alfabético", optSize: "Tamaño total", labelAdult: "Filtro de adultos",
                optAll: "Mostrar todo", optHide: "Ocultar contenido adulto", optOnly: "Solo adultos",
                labelWidth: "Ancho de tarjeta", labelVisual: "Controles visuales", optBlur: "Desactivar desenfoque",
                optHideIds: "Ocultar IDs", labelBinary: "Archivos binarios", footBooth: "🛒 Abrir en Booth", 
                footFolder: "📂 Abrir carpeta local", searchPre: "Buscar ", searchSuf: " artículos...",
                fileSingular: "archivo", filePlural: "archivos"
            }},
            pt: {{
                navTitle: "Biblioteca de Ativos Booth", optionsBtn: "Opções ⚙", labelLanguage: "Idioma", labelSort: "Ordenar por", 
                optId: "ID da pasta", optName: "Alfabético", optSize: "Tamanho total", labelAdult: "Filtro de adultos",
                optAll: "Mostrar tudo", optHide: "Ocultar conteúdo adulto", optOnly: "Apenas adultos",
                labelWidth: "Largura do cartão", labelVisual: "Controles visuais", optBlur: "Desativar desfoque",
                optHideIds: "Ocultar IDs", labelBinary: "Arquivos binários", footBooth: "🛒 Abrir no Booth", 
                footFolder: "📂 Abrir pasta local", searchPre: "Pesquisar ", searchSuf: " itens...",
                fileSingular: "arquivo", filePlural: "arquivos"
            }},
            nl: {{
                navTitle: "Booth Asset Bibliotheek", optionsBtn: "Opties ⚙", labelLanguage: "Taal", labelSort: "Sorteer op", 
                optId: "Map ID", optName: "Alfabetisch", optSize: "Bestandsgrootte", labelAdult: "Volwassen filter",
                optAll: "Alle inhoud tonen", optHide: "Volwassen inhoud verbergen", optOnly: "Alleen volwassen",
                labelWidth: "Kaartbreedte", labelVisual: "Visuele instellingen", optBlur: "Vervaging uitschakelen",
                optHideIds: "ID's verbergen", labelBinary: "Binaire bestanden", footBooth: "🛒 Openen op Booth", 
                footFolder: "📂 Lokale map openen", searchPre: "Zoek in ", searchSuf: " items...",
                fileSingular: "bestand", filePlural: "bestanden"
            }}
        }};

        let currentCarouselIndex = 0, currentImages = [];
        const getLS = (k, def) => localStorage.getItem(k) || def;
        
        const state = {{
            gridSize: getLS('gridSize', '220'),
            disableBlur: getLS('disableBlur', 'false') === 'true',
            sortOrder: getLS('sortOrder', 'id'),
            adultFilter: getLS('adultFilter', 'all'),
            hideIds: getLS('hideIds', 'false') === 'true',
            lang: getLS('lang', 'en')
        }};

        function init() {{
            updateLanguage(state.lang);
            updateGrid(state.gridSize);
            updateBlur(state.disableBlur);
            updateIdVisibility(state.hideIds);
            
            document.getElementById('gridRange').value = state.gridSize;
            document.getElementById('blurToggle').checked = state.disableBlur;
            document.getElementById('sortOrder').value = state.sortOrder;
            document.getElementById('adultFilter').value = state.adultFilter;
            document.getElementById('hideIdToggle').checked = state.hideIds;
            
            handleSearchInput();
            sortAssets();
        }}

        function updateLanguage(lang) {{
            state.lang = lang; localStorage.setItem('lang', lang);
            document.getElementById('langSelect').value = lang;
            const t = translations[lang];
            document.querySelectorAll('[data-i18n]').forEach(el => {{
                el.innerText = t[el.dataset.i18n];
            }});
            applyFilters();
        }}

        function toggleMenu(e, forceClose = false) {{
            if(e) e.stopPropagation();
            const menu = document.getElementById('flyoutMenu'), btn = document.getElementById('toggleBtn'), perim = document.getElementById('menuPerimeter');
            const open = !forceClose && !menu.classList.contains('open');
            menu.classList.toggle('open', open);
            btn.classList.toggle('active', open);
            perim.style.display = open ? 'block' : 'none';
        }}

        function updateGrid(v) {{ document.documentElement.style.setProperty('--grid-size', v + 'px'); localStorage.setItem('gridSize', v); }}
        function updateBlur(v) {{ document.body.classList.toggle('no-blur', v); localStorage.setItem('disableBlur', v); }}
        function updateIdVisibility(v) {{ document.body.classList.toggle('hide-ids', v); localStorage.setItem('hideIds', v); }}

        function handleSearchInput() {{ applyFilters(); }}
        function clearSearch() {{ const i = document.getElementById("searchInput"); i.value = ""; handleSearchInput(); i.focus(); }}
        function tagSearch(tag) {{ const s = document.getElementById("searchInput"); s.value = tag; closeModal(); applyFilters(); window.scrollTo({{ top: 0, behavior: 'smooth' }}); }}

        function applyFilters(save = false) {{
            const query = document.getElementById("searchInput").value.toLowerCase();
            const mode = document.getElementById("adultFilter").value;
            const items = document.getElementsByClassName("asset");
            const t = translations[state.lang];
            let count = 0;

            if(save) localStorage.setItem('adultFilter', mode);

            for (let item of items) {{
                const isAdult = item.dataset.adult === 'true';
                let match = (mode === 'all') || (mode === 'hide' && !isAdult) || (mode === 'only' && isAdult);
                if (match) {{
                    const visible = item.dataset.search.includes(query);
                    item.style.display = visible ? "" : "none";
                    if (visible) count++;
                }} else {{
                    item.style.display = "none";
                }}
                
                const fc = parseInt(item.dataset.filecount);
                item.querySelector('.file-label-dynamic').innerText = fc + " " + (fc === 1 ? t.fileSingular : t.filePlural);
            }}
            document.getElementById("searchInput").placeholder = t.searchPre + count + t.searchSuf;
        }}

        function sortAssets(save = false) {{
            const list = document.getElementById('assetList'), order = document.getElementById('sortOrder').value;
            if(save) localStorage.setItem('sortOrder', order);
            const items = Array.from(list.children);
            items.sort((a, b) => {{
                if (order === 'id') return parseInt(a.dataset.id) - parseInt(b.dataset.id);
                if (order === 'name') return a.dataset.name.toLowerCase().localeCompare(b.dataset.name.toLowerCase());
                return parseInt(b.dataset.bytes) - parseInt(a.dataset.bytes);
            }});
            list.innerHTML = ""; items.forEach(i => list.appendChild(i));
            applyFilters();
        }}

        function openDetails(id) {{
            const el = document.querySelector(`.asset[data-id="${{id}}"]`);
            document.getElementById("modalName").innerText = el.dataset.name;
            document.getElementById("modalIdDisp").innerText = "#" + id;
            document.getElementById("openFolderLink").href = el.dataset.folder;
            document.getElementById("openBoothLink").href = el.dataset.boothUrl;
            currentImages = JSON.parse(el.dataset.allImages);
            currentCarouselIndex = 0; updateCarousel();
            document.getElementById("modalTags").innerHTML = JSON.parse(el.dataset.tags).map(t => `<span class="tag-pill" onclick="tagSearch('${{t.replace(/'/g, "\\\\'")}}')">${{t}}</span>`).join('');
            document.getElementById("fileList").innerHTML = JSON.parse(el.dataset.files).map(f => `<li class="file-item"><a class="file-link" href="${{f.path}}" target="_blank">${{f.name}}</a><span style="color:#aaa;font-size:0.75rem;">${{f.size}}</span></li>`).join('');
            const m = document.getElementById("detailModal");
            m.classList.add('visible'); setTimeout(() => m.classList.add('active'), 10);
        }}

        function carouselNext(dir) {{ if (currentImages.length <= 1) return; currentCarouselIndex = (currentCarouselIndex + dir + currentImages.length) % currentImages.length; updateCarousel(); }}
        function updateCarousel() {{
            const img = currentImages[currentCarouselIndex];
            document.getElementById("modalImg").src = img;
            document.getElementById("modalBlurBg").src = img;
            const dots = document.getElementById("carouselDots");
            if (currentImages.length > 1) {{
                dots.style.display = "flex";
                dots.innerHTML = currentImages.map((_, i) => `<div class="dot ${{i === currentCarouselIndex ? 'active' : ''}}" onclick="currentCarouselIndex=${{i}}; updateCarousel()"></div>`).join('');
                document.getElementById("carouselPrev").style.display = "block";
                document.getElementById("carouselNext").style.display = "block";
            }} else {{
                dots.style.display = "none";
                document.getElementById("carouselPrev").style.display = "none";
                document.getElementById("carouselNext").style.display = "none";
            }}
        }}

        function closeModal() {{ const m = document.getElementById("detailModal"); m.classList.remove('active'); setTimeout(() => {{ if(!m.classList.contains('active')) m.classList.remove('visible'); }}, 300); }}
        window.onclick = e => {{ if(!document.getElementById('flyoutMenu').contains(e.target) && e.target !== document.getElementById('toggleBtn')) toggleMenu(null, true); }};
        document.addEventListener('keydown', e => {{ 
            if(e.key === "Escape") {{ closeModal(); toggleMenu(null, true); }} 
            if(e.key === "ArrowRight") carouselNext(1);
            if(e.key === "ArrowLeft") carouselNext(-1);
        }});
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
        all_local_files = os.listdir(folder_path)
        for token in tokens:
            for f in all_local_files:
                if token in f:
                    return quote(os.path.join(folder_path, f))
    valid_exts = ('.jpg', '.jpeg', '.png', '.webp', '.gif')
    for f in os.listdir(folder_path):
        if f.lower().endswith(valid_exts):
            return quote(os.path.join(folder_path, f))
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

def generate_asset_html(asset_id, asset_name, web_images, booth_url, folder_path, tags, is_adult):
    binary_folder = os.path.join(folder_path, 'Binary')
    files_data, total_bytes = get_dir_data(binary_folder)
    all_imgs = get_all_local_images(folder_path, web_images)
    primary_img = all_imgs[0] if all_imgs else ""
    img_class = "image-thumbnail adult-content" if is_adult else "image-thumbnail"
    glow_tag = f'<img class="image-backglow" src="{primary_img}">' if primary_img else ''
    img_tag = f'<img class="{img_class}" src="{primary_img}">' if primary_img else '<div class="image-thumbnail" style="background:#222;display:flex;align-items:center;justify-content:center;color:#444;font-weight:800;">EMPTY</div>'
    safe_name = asset_name.replace('"', '&quot;')
    
    # Python-side tag rendering
    tag_html = "".join([f'<span class="tag-pill">{t}</span>' for t in tags[:8]])
    
    search_str = f"{asset_id} {asset_name} {' '.join(tags)}".lower().replace("'", "")
    rel_folder = quote(os.path.relpath(binary_folder, start=os.getcwd()))

    return f"""
    <li class="asset" onclick="openDetails('{asset_id}')" 
        data-id="{asset_id}" data-name="{safe_name}" data-img="{primary_img}" 
        data-all-images='{json.dumps(all_imgs).replace("'", "&apos;")}'
        data-bytes="{total_bytes}" data-files='{json.dumps(files_data).replace("'", "&apos;")}'
        data-tags='{json.dumps(tags).replace("'", "&apos;")}' data-adult="{str(is_adult).lower()}" 
        data-search='{search_str}' data-folder="{rel_folder}" data-booth-url="{booth_url}"
        data-filecount="{len(files_data)}">
        <div class="image-container"><div class="asset-id-tag">#{asset_id}</div>{img_tag}</div>
        {glow_tag}<div class="content"><div class="name">{asset_name}</div>
        <div class="stats"><span>{get_readable_size(total_bytes)}</span><span class="file-label-dynamic"></span></div>
        <div class="tag-row">{tag_html}</div></div>
    </li>
    """

asset_items = []
processed = set()
for folder in sorted(os.listdir(ROOT_FOLDER)):
    path = os.path.join(ROOT_FOLDER, folder)
    if not os.path.isdir(path) or folder in processed: continue
    jsons = glob.glob(os.path.join(path, "_BoothPage.json")) or glob.glob(os.path.join(path, "_BoothInnerHtmlList.json"))
    if not jsons: continue
    processed.add(folder)
    with open(jsons[0], 'r', encoding='utf-8') as f:
        if jsons[0].endswith('_BoothPage.json'):
            data = json.load(f)
            w_imgs = [img.get('original', '') for img in data.get('images', [])]
            tags = [t.get('name', '') for t in data.get('tags', [])]
            b_url = data.get('url', f"https://booth.pm/items/{{folder}}")
            asset_items.append((folder, generate_asset_html(folder, data.get('name', 'N/A'), w_imgs, b_url, path, tags, data.get('is_adult', False) or is_adult_content(data.get('name', '')))))
        else:
            data = json.load(f)
            item = data[0] if data else ""
            if item:
                n_m = (re.search(r'break-all\">(.*?)<\/div>', item) or re.search(r'>(.*?)<\/div>', item))
                name = n_m.group(1) if n_m else "N/A"
                i_m = re.search(r'src=\"([^\"]+)\"', item)
                img = i_m.group(1) if i_m else ""
                u_m = re.search(r'href=\"([^\"]+)\"', item)
                url = u_m.group(1) if u_m else f"https://booth.pm/items/{{folder}}"
                asset_items.append((folder, generate_asset_html(folder, name, [img], url, path, [], is_adult_content(name))))

asset_items.sort(key=lambda x: int(x[0]) if x[0].isdigit() else 0)
final_assets_html = "\\n".join(i[1] for i in asset_items)
with open(OUTPUT_FILE, 'w', encoding='utf-8') as f: f.write(HTML_TEMPLATE.format(assets=final_assets_html))
print("The library got updated.")