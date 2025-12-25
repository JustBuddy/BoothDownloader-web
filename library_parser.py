import os
import json
import glob
import re
from urllib.parse import quote

# Define the root folder for the asset library.
root_folder = "BoothDownloaderOut"
# Define the output HTML file.
output_file = "asset_library.html"

# Initialize an HTML template.
html_template = """<!doctype html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Asset Library</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
    <style>
        :root {{ --primary: #FDDA0D; --bg: #0b0b0d; --card: #16161a; --text: #ddd; --grid-size: 220px; }}
        body {{ font-family: 'Inter', sans-serif; background-color: var(--bg); color: var(--text); margin: 0; padding: 0; overflow-x: hidden; }}
        
        .top-nav {{
            position: sticky; top: 0; z-index: 1000;
            background: rgba(11, 11, 13, 0.9); backdrop-filter: blur(12px);
            border-bottom: 1px solid #222; padding: 15px 30px;
            display: flex; align-items: center; justify-content: space-between; gap: 20px;
        }}
        .nav-logo {{ color: var(--primary); font-weight: 800; font-size: 1.2rem; white-space: nowrap; }}
        
        .search-container {{ flex-grow: 1; display: flex; justify-content: center; position: relative; max-width: 500px; }}
        .search-input {{ 
            padding: 10px 45px 10px 20px; width: 100%; 
            background: #1a1a1f; border: 1px solid #333; border-radius: 8px; 
            color: white; outline: none; transition: border-color 0.3s;
        }}
        .search-input:focus {{ border-color: var(--primary); }}
        .clear-search {{
            position: absolute; right: 15px; top: 50%; transform: translateY(-50%);
            background: none; border: none; color: #666; font-size: 1.2rem;
            cursor: pointer; display: none; padding: 0; line-height: 1;
        }}
        .clear-search:hover {{ color: var(--primary); }}

        .nav-btn {{ background: #222; border: 1px solid #333; color: white; padding: 10px 18px; border-radius: 8px; cursor: pointer; font-weight: 600; position: relative; z-index: 2001; }}
        .nav-btn.active {{ border-color: var(--primary); color: var(--primary); }}
        
        /* Flyout Perimeter and Menu */
        #menuPerimeter {{ display: none; position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; z-index: 1999; }}
        .flyout-menu {{
            display: none; position: fixed; top: 75px; right: 30px; width: 320px;
            background: rgba(26, 26, 31, 0.98); backdrop-filter: blur(20px);
            border: 1px solid rgba(253, 218, 13, 0.3); z-index: 2000; padding: 25px; border-radius: 16px; 
            opacity: 0; transform: translateY(-20px); transition: 0.3s;
            pointer-events: none; box-shadow: 0 20px 60px rgba(0,0,0,0.8);
        }}
        .flyout-menu.open {{ display: block; opacity: 1; transform: translateY(0); pointer-events: all; }}

        .container {{ max-width: 1600px; margin: 40px auto; padding: 0 30px; }}
        #assetList {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(var(--grid-size), 1fr)); gap: 20px; list-style: none; padding: 0; }}
        .asset {{ background: var(--card); border: 1px solid #252525; border-radius: 12px; overflow: hidden; cursor: pointer; display: flex; flex-direction: column; height: 100%; transition: 0.3s; }}
        .asset:hover {{ border-color: var(--primary); transform: translateY(-5px); }}
        
        .image-container {{ position: relative; width: 100%; padding-top: 100%; background: #000; flex-shrink: 0; }}
        .image-thumbnail {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; transition: 0.4s; }}
        .adult-content {{ filter: blur(50px); }}
        .asset:hover .adult-content {{ filter: blur(0px); }}
        body.no-blur .adult-content {{ filter: blur(0px) !important; }}

        .content {{ padding: 15px; flex-grow: 1; display: flex; flex-direction: column; }}
        .name {{ font-weight: 600; color: #fff; line-height: 1.3; margin-bottom: 8px; font-size: 0.9rem; height: 2.6em; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }}
        .stats {{ color: #666; font-size: 0.75rem; display: flex; gap: 10px; margin-top: auto; }}
        .tag-pill {{ font-size: 0.65rem; background: #222; padding: 2px 6px; border-radius: 4px; color: #aaa; white-space: nowrap; transition: 0.2s; }}
        .modal .tag-pill {{ cursor: pointer; }}
        .modal .tag-pill:hover {{ background: var(--primary); color: #000; }}

        .modal {{ display: none; position: fixed; z-index: 3000; left: 0; top: 0; width: 100%; height: 100%; align-items: center; justify-content: center; transition: 0.3s; padding: 20px; box-sizing: border-box; }}
        .modal.visible {{ display: flex; }}
        .modal.active {{ background: rgba(0,0,0,0.95); }}
        .modal-card {{ background: #1a1a1f; width: 100%; max-width: 900px; max-height: 90vh; border: 1px solid var(--primary); border-radius: 16px; display: flex; flex-wrap: wrap; overflow-y: auto; opacity: 0; transform: scale(0.9); transition: 0.3s; }}
        .modal.active .modal-card {{ opacity: 1; transform: scale(1); }}

        .modal-side-img {{ flex: 1 1 400px; background: #000; display: flex; align-items: center; justify-content: center; min-height: 300px; }}
        .modal-side-img img {{ max-width: 100%; max-height: 100%; object-fit: contain; }}
        .modal-info {{ flex: 1 1 400px; padding: 30px; display: flex; flex-direction: column; min-width: 300px; }}
        .modal-name {{ font-size: 1.4rem; font-weight: 800; color: var(--primary); margin-bottom: 10px; }}
        .file-item {{ padding: 10px; background: #222; border-radius: 8px; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center; gap: 10px; }}
        .file-link {{ color: #fff; text-decoration: none; font-size: 0.85rem; word-break: break-all; }}
        .setting-label {{ display: block; margin: 15px 0 8px; font-size: 0.7rem; color: #555; text-transform: uppercase; font-weight: 800; }}
    </style>
</head>
<body>
    <div id="menuPerimeter" onclick="toggleMenu(event, true)"></div>
    <nav class="top-nav">
        <div class="nav-logo">Booth Asset Library</div>
        <div class="search-container">
            <input type="text" id="searchInput" class="search-input" placeholder="Search library..." onkeyup="handleSearch()">
            <button id="clearSearch" class="clear-search" onclick="clearSearch()">×</button>
        </div>
        <button id="toggleBtn" class="nav-btn" onclick="toggleMenu(event)">Options ⚙</button>
    </nav>

    <div id="flyoutMenu" class="flyout-menu">
        <span class="setting-label">Sort Order</span>
        <select id="sortOrder" onchange="sortAssets(true)" style="width:100%; padding:10px; background:#0b0b0d; color:white; border:1px solid #333; border-radius:8px; margin-bottom:15px;">
            <option value="id">Folder ID</option>
            <option value="name">Alphabetical</option>
            <option value="size">Total Size</option>
        </select>
        <span class="setting-label">Adult Filter</span>
        <select id="adultFilter" onchange="applyFilters(true)" style="width:100%; padding:10px; background:#0b0b0d; color:white; border:1px solid #333; border-radius:8px; margin-bottom:15px;">
            <option value="all">Show All</option>
            <option value="hide">Hide Adult</option>
            <option value="only">Only Adult</option>
        </select>
        <span class="setting-label">Card Width</span>
        <input type="range" id="gridRange" min="180" max="500" value="220" oninput="updateGrid(this.value)" style="width:100%; accent-color:var(--primary); margin-bottom:15px;">
        <label style="display:flex; gap:10px; cursor:pointer; font-size:0.9rem;">
            <input type="checkbox" id="blurToggle" onchange="updateBlur(this.checked)"> Disable Adult Blur
        </label>
    </div>

    <div class="container"><ul id="assetList">{assets}</ul></div>

    <div id="detailModal" class="modal" onclick="closeModal()">
        <div class="modal-card" onclick="event.stopPropagation()">
            <div class="modal-side-img"><img id="modalImg" src=""></div>
            <div class="modal-info">
                <div id="modalName" class="modal-name"></div>
                <div id="modalTags" style="display:flex; flex-wrap:wrap; gap:6px; margin-bottom:20px;"></div>
                <span class="setting-label">Binary Files</span>
                <ul id="fileList" style="list-style:none; padding:0; margin-top:10px;"></ul>
            </div>
        </div>
    </div>

    <script>
        const savedGrid = localStorage.getItem('gridSize') || '220';
        const savedBlur = localStorage.getItem('disableBlur') === 'true';
        const savedSort = localStorage.getItem('sortOrder') || 'id';
        const savedAdultFilter = localStorage.getItem('adultFilter') || 'all';
        
        updateGrid(savedGrid); updateBlur(savedBlur);
        document.getElementById('gridRange').value = savedGrid;
        document.getElementById('blurToggle').checked = savedBlur;
        document.getElementById('sortOrder').value = savedSort;
        document.getElementById('adultFilter').value = savedAdultFilter;

        function toggleMenu(e, forceClose = false) {{ 
            if(e) e.stopPropagation();
            const menu = document.getElementById('flyoutMenu');
            const btn = document.getElementById('toggleBtn');
            const perimeter = document.getElementById('menuPerimeter');
            
            if (forceClose || menu.classList.contains('open')) {{
                menu.classList.remove('open');
                btn.classList.remove('active');
                perimeter.style.display = 'none';
            }} else {{
                menu.classList.add('open');
                btn.classList.add('active');
                perimeter.style.display = 'block';
            }}
        }}

        function updateGrid(val) {{ document.documentElement.style.setProperty('--grid-size', val + 'px'); localStorage.setItem('gridSize', val); }}
        function updateBlur(d) {{ d ? document.body.classList.add('no-blur') : document.body.classList.remove('no-blur'); localStorage.setItem('disableBlur', d); }}
        function handleSearch() {{ document.getElementById("clearSearch").style.display = document.getElementById("searchInput").value ? "block" : "none"; applyFilters(); }}
        function clearSearch() {{ const i = document.getElementById("searchInput"); i.value = ""; handleSearch(); i.focus(); }}

        function applyFilters(save = false) {{
            const query = document.getElementById("searchInput").value.toLowerCase();
            const adultMode = document.getElementById("adultFilter").value;
            const items = document.getElementsByClassName("asset");
            let count = 0;
            if(save) localStorage.setItem('adultFilter', adultMode);
            for (let item of items) {{
                const isAdult = item.getAttribute('data-adult') === 'true';
                let ok = (adultMode==='all') || (adultMode==='hide' && !isAdult) || (adultMode==='only' && isAdult);
                if (ok) count++;
                item.style.display = (ok && item.getAttribute('data-search').includes(query)) ? "" : "none";
            }}
            document.getElementById("searchInput").placeholder = `Search ${{count}} items...`;
        }}

        function tagSearch(tagName) {{ const s = document.getElementById("searchInput"); s.value = tagName; closeModal(); handleSearch(); window.scrollTo({{ top: 0, behavior: 'smooth' }}); }}

        function openDetails(assetId) {{
            const item = document.querySelector(`.asset[data-id="${{assetId}}"]`);
            document.getElementById("modalImg").src = item.getAttribute('data-img');
            document.getElementById("modalName").innerText = item.getAttribute('data-name');
            const tags = JSON.parse(item.getAttribute('data-tags'));
            document.getElementById("modalTags").innerHTML = tags.map(t => `<span class="tag-pill" onclick="tagSearch('${{t.replace(/'/g, "\\\\'")}}')">${{t}}</span>`).join('');
            const files = JSON.parse(item.getAttribute('data-files'));
            document.getElementById("fileList").innerHTML = files.map(f => `
                <li class="file-item"><a class="file-link" href="${{f.path}}" target="_blank">${{f.name}}</a><span style="color:#666;font-size:0.75rem;">${{f.size}}</span></li>
            `).join('');
            const m = document.getElementById("detailModal");
            m.classList.add('visible'); setTimeout(() => m.classList.add('active'), 10);
        }}

        function closeModal() {{ const m = document.getElementById("detailModal"); m.classList.remove('active'); setTimeout(() => {{ if(!m.classList.contains('active')) m.classList.remove('visible'); }}, 300); }}

        function sortAssets(save = false) {{
            const list = document.getElementById('assetList');
            const items = Array.from(list.getElementsByClassName('asset'));
            const order = document.getElementById('sortOrder').value;
            if(save) localStorage.setItem('sortOrder', order);
            items.sort((a, b) => {{
                if (order === 'id') return parseInt(a.getAttribute('data-id')) - parseInt(b.getAttribute('data-id'));
                if (order === 'name') return a.getAttribute('data-name').toLowerCase().localeCompare(b.getAttribute('data-name').toLowerCase());
                return parseInt(b.getAttribute('data-bytes')) - parseInt(a.getAttribute('data-bytes'));
            }});
            list.innerHTML = ""; items.forEach(i => list.appendChild(i));
            applyFilters();
        }}

        document.addEventListener('keydown', e => {{ if(e.key==="Escape") {{ closeModal(); toggleMenu(null, true); }} }});
        sortAssets();
    </script>
</body>
</html>
"""

def get_readable_size(size_bytes):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024: return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f}TB"

def get_dir_contents(binary_folder):
    files = []
    if os.path.exists(binary_folder):
        for root, _, filenames in os.walk(binary_folder):
            for f in filenames:
                fp = os.path.join(root, f)
                rel = os.path.relpath(fp, start=os.getcwd())
                files.append({"name": f, "path": quote(rel), "size": get_readable_size(os.path.getsize(fp))})
    return files

def generate_asset_html(asset_id, asset_name, asset_image, binary_folder, tags, is_adult):
    total_bytes = 0
    if os.path.exists(binary_folder):
        for root, _, filenames in os.walk(binary_folder):
            for f in filenames:
                total_bytes += os.path.getsize(os.path.join(root, f))
    
    files_data = get_dir_contents(binary_folder)
    img_class = "image-thumbnail adult-content" if is_adult else "image-thumbnail"
    img_tag = f'<img class="{img_class}" src="{asset_image}">' if asset_image else '<div class="image-thumbnail" style="background:#222;display:flex;align-items:center;justify-content:center;color:#444;font-weight:800;">EMPTY</div>'
    safe_name = asset_name.replace('"', '&quot;')
    tag_html = "".join([f'<span class="tag-pill">{t}</span>' for t in tags[:3]])
    search_str = f"{asset_id} {asset_name} {' '.join(tags)}".lower().replace("'", "")
    
    return f"""
    <li class="asset" onclick="openDetails('{asset_id}')" data-id="{asset_id}" data-name="{safe_name}" 
        data-img="{asset_image}" data-bytes="{total_bytes}" data-files='{json.dumps(files_data).replace("'", "&apos;")}'
        data-tags='{json.dumps(tags).replace("'", "&apos;")}' data-adult="{str(is_adult).lower()}" 
        data-search='{search_str}'>
        <div class="image-container">{img_tag}</div>
        <div class="content">
            <div class="name">{asset_name}</div>
            <div class="stats"><span>{get_readable_size(total_bytes)}</span><span>{len(files_data)} files</span></div>
            <div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:10px;height:1.5em;overflow:hidden;">{tag_html}</div>
        </div>
    </li>
    """

asset_items = []
processed = set()
for folder in sorted(os.listdir(root_folder)):
    path = os.path.join(root_folder, folder)
    if not os.path.isdir(path) or folder in processed: continue
    jsons = glob.glob(os.path.join(path, "_BoothPage.json")) or glob.glob(os.path.join(path, "_BoothInnerHtmlList.json"))
    if not jsons: continue
    processed.add(folder)
    with open(jsons[0], 'r', encoding='utf-8') as f:
        binary = os.path.join(path, 'Binary')
        if jsons[0].endswith('_BoothPage.json'):
            data = json.load(f)
            tags = [t.get('name', '') for t in data.get('tags', [])]
            is_ad = data.get('is_adult', False) or any(x in data.get('name', '').lower() for x in ['r-18', 'r18', '精液', 'otinpo', 'otimpo'])
            asset_items.append((folder, generate_asset_html(folder, data.get('name', 'N/A'), data.get('images', [{}])[0].get('original', ''), binary, tags, is_ad)))
        else:
            data = json.load(f)
            item = data[0] if data else ""
            if item:
                name = (re.search(r'break-all\">(.*?)<\/div>', item) or re.search(r'>(.*?)<\/div>', item)).group(1)
                img = re.search(r'src=\"([^\"]+)\"', item).group(1) if 'src="' in item else ""
                asset_items.append((folder, generate_asset_html(folder, name, img, binary, [], "r-18" in name.lower())))

asset_items.sort(key=lambda x: int(x[0]) if x[0].isdigit() else 0)
output_html = html_template.format(assets="\n".join(i[1] for i in asset_items))
with open(output_file, 'w', encoding='utf-8') as f: f.write(output_html)
print("The library got updated.")