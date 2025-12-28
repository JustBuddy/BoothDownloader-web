# BoothDownloader-web

A high-performance local web gallery generator for your [BoothDownloader](https://github.com/Myrkie/BoothDownloader) library. Organize, search, and preview your VRChat assets and Booth items with a modern, responsive interface.

[**View Live Demo**](https://justbuddy.github.io/BoothDownloader-web/demo/asset_library.html)

![Preview](https://splash.buddyworks.wtf/LwpinegQ.png)
![Preview2](https://splash.buddyworks.wtf/InNbMlYH.png)

## Features
- **Auto-Translation:** Automatically translates Japanese titles, authors, and tags to English via Google Translate (cached locally).
- **Smart Filtering:** Built-in NSFW/Adult content filter and tag-based searching.
- **VRChat Integration:** Detects and links public VRChat Avatars (`avtr_`) and Worlds (`wrld_`) directly from item descriptions.
- **Asset Optimization:** Generates WebP thumbnails for lightning-fast loading.
- **Detailed Stats:** Track total library size, image storage, and estimated investment across different currencies.
- **Multilingual UI:** Support for English, Japanese, Korean, Chinese, German, French, and more.

## Installation & Requirements
1. Install Python 3.
2. Install dependencies:
   ```bash
   pip install deep-translator Pillow
   ```

## Usage
1. **Critical:** Ensure `AutoZip` is set to `false` in your `BDConfig.json` (BoothDownloader must keep folders extracted).
2. Place `library_parser.py` in the same directory as your `BoothDownloaderOut` folder.
3. Run the script:
   ```bash
   python library_parser.py
   ```
4. Open `asset_library.html` in your browser.

## Configuration
The following variables can be adjusted at the top of the script:
- `ROOT_FOLDER`: Location of your assets (default: `BoothDownloaderOut`).
- `MAX_WORKERS`: Number of parallel threads for translation (default: `5`).
- `OPTIMIZE_THUMBNAILS`: Set to `False` to skip WebP generation.
- `SKIP_TRANSLATION`: Toggle AI translation services.

## Disclaimer
- **USE LOCALLY ONLY:** This tool is designed for private library management.
- **NO DOWNLOADER:** This script cannot download assets. It only parses items you already legally own and have downloaded via BoothDownloader.
- **Liability:** I am not responsible for any misuse or data issues.

## Contributing
Feel free to submit Pull Requests for translations, UI improvements or bug fixes. Please maintain the existing color palette (Inter font, dark aesthetic, yellow accents).