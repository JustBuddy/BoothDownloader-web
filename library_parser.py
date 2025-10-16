import os
import json
import glob
import re

# Define the root folder for the asset library.
root_folder = "BoothDownloaderOut"
# Define the output HTML file.
output_file = "asset_library.html"

# Initialize an HTML template with a modern theme.
html_template = """<!doctype html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Asset Library</title>
    <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;700&display=swap" rel="stylesheet">
    <style>
        body {{ font-family: 'Roboto', sans-serif; background-color: #121212; margin: 0; padding: 20px; }}
        h1 {{ text-align: center; color: #FDDA0D; margin-bottom: 20px; }}
        .search-container {{ text-align: center; margin-bottom: 20px; }}
        .search-input {{ padding: 10px; width: 300px; border: 1px solid #ccc; border-radius: 5px; }}
        ul {{ list-style-type: none; padding: 0; color: #FFF }}
        .asset {{ 
            border: 1px solid #FDDA0D; 
            padding: 15px; 
            margin: 10px 0; 
            background-color: #1A182191; 
            border-radius: 8px; 
            box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
        }}
        .asset img {{ max-width: 100%; height: auto; border-radius: 4px; cursor: pointer; }}
        .image-thumbnail {{ width: 72px; height: 72px; object-fit: cover; margin-right: 10px; cursor: pointer; }}
        .button {{ display: inline-block; margin-top: 10px; padding: 10px 15px; background: #FDDA0D; color: black; text-decoration: none; border-radius: 5px; transition: background 0.3s; float: right; }}
        .button:hover {{ background: #FFF; }}
        .container {{ max-width: 800px; margin: auto; }}
        /* Modal styles */
        .modal {{
            display: none; 
            position: fixed; 
            z-index: 1000; 
            left: 0; 
            top: 0; 
            width: 100%; 
            height: 100%; 
            overflow: auto; 
            background-color: rgba(0,0,0,0.8);
            align-items: center; 
            justify-content: center; 
        }}
        .modal-content {{
            display: block; 
            margin: auto;
            width: auto; 
            height: auto;
        }}
        .close {{
            color: #fff; 
            position: absolute; 
            top: 15px; 
            right: 25px; 
            font-size: 35px; 
            font-weight: bold; 
            cursor: pointer;
        }}
    </style>
</head>
<body>
    <h1>Asset Library</h1>
    <div class="search-container">
        <input type="text" id="searchInput" class="search-input" placeholder="Search by name or ID..." onkeyup="filterAssets()">
    </div>
    <div class="container">
        <ul id="assetList">
            {assets}
        </ul>
    </div>

    <!-- Modal for images -->
    <div id="myModal" class="modal">
        <span class="close">&times;</span>
        <img class="modal-content" id="img01">
    </div>

    <script>
        var modal = document.getElementById("myModal");
        var img = document.getElementById("img01");
        var closeBtn = document.getElementsByClassName("close")[0];

        function openModal(src) {{
            modal.style.display = "flex";
            img.src = src;  // Set the original image source
        }}
        
        closeBtn.onclick = function() {{
            modal.style.display = "none";
        }}

        window.onclick = function(event) {{
            if (event.target == modal) {{
                modal.style.display = "none";
            }}
        }}

        function filterAssets() {{
            var input = document.getElementById("searchInput");
            var filter = input.value.toLowerCase();
            var ul = document.getElementById("assetList");
            var li = ul.getElementsByTagName("li");

            for (var i = 0; i < li.length; i++) {{
                var name = li[i].getElementsByClassName("name")[0].textContent;
                if (name.toLowerCase().indexOf(filter) > -1) {{
                    li[i].style.display = "";
                }} else {{
                    li[i].style.display = "none";
                }}
            }}
        }}
    </script>
</body>
</html>
"""

asset_items = []

# Function to generate asset HTML.
def generate_asset_html(asset_id, asset_name, asset_image, binary_folder):
    return f"""
    <li class="asset">
        <div class="name">{asset_id} - {asset_name}</div>
        {f'<img class="image-thumbnail" src="{asset_image}" alt="{asset_name}" onclick="openModal(\'{asset_image}\')">' if asset_image else '<p>N/A</p>'}
        <a href="{binary_folder}" class="button" target="_blank">Browse Files...</a>
    </li>
    """

# Extract name from HTML string using regex.
def extract_name_from_html(html_content):
    match = re.search(r'<div class="text-text-default[^>]*>(.*?)<\/div>', html_content)
    return match.group(1) if match else "Unknown Asset"

# Scan the root folder.
for folder in os.listdir(root_folder):
    folder_path = os.path.join(root_folder, folder)
    
    if os.path.isdir(folder_path):
        json_path = glob.glob(os.path.join(folder_path, "_BoothPage.json")) or glob.glob(os.path.join(folder_path, "_BoothInnerHtmlList.json"))
        
        if json_path:
            with open(json_path[0], 'r', encoding='utf-8') as json_file:
                if json_path[0].endswith('_BoothPage.json'):
                    asset_data = json.load(json_file)
                    asset_name = asset_data['name']
                    asset_images = asset_data['images']
                    
                    # Use the original image instead of the resized one
                    asset_image = asset_images[0]['original'] if asset_images else ""
                    binary_folder = os.path.join(folder_path, 'Binary')
                    
                    # Add to asset items including the ID
                    asset_items.append((folder, generate_asset_html(folder, asset_name, asset_image, binary_folder)))
                
                elif json_path[0].endswith('_BoothInnerHtmlList.json'):
                    asset_data = json.load(json_file)
                    for item in asset_data:
                        asset_name = extract_name_from_html(item)
                        # Extract the image source
                        image_start_index = item.find('src="') + 5
                        asset_image = item[image_start_index:item.find('"', image_start_index)]
                        binary_folder = os.path.join(folder_path, 'Binary')

                        # Add to asset items including the ID
                        asset_items.append((folder, generate_asset_html(folder, asset_name, asset_image, binary_folder)))

# Sort the asset_items by ID (the first element of the tuple).
asset_items.sort(key=lambda x: int(x[0]))  # Convert ID string to int for proper sorting

# Generate complete HTML.
output_assets = "\n".join(item[1] for item in asset_items)  # Use only the HTML part
output_html = html_template.format(assets=output_assets)

# Write to output HTML file.
with open(output_file, 'w', encoding='utf-8') as f:
    f.write(output_html)

print("Asset library HTML has been generated in", output_file)