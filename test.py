"""
MJA — Social Media Image Fetcher
=================================
Fetches images from Instagram posts and LinkedIn, then saves them
with the exact filenames expected by actualites.html.

Requirements:
    pip install instaloader selenium pillow requests

For LinkedIn you also need ChromeDriver matching your Chrome version:
    https://googlechromelabs.github.io/chrome-for-testing/
    (or: brew install chromedriver  /  winget install chromedriver)

Usage:
    python fetch_mja_images.py

Output folder: ./mja_images/
"""

import os
import time
import shutil
import requests
import instaloader
from pathlib import Path
from PIL import Image
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ── CONFIG ──────────────────────────────────────────────────────────────────

OUTPUT_DIR = Path("mja_images")

# Instagram post shortcodes (the part after /p/ in the URL)
INSTAGRAM_POSTS = {
    "ig-gide":          "DVYMaZ0DLlD",   # Gide event       → img-cleary.jpg  (rename below)
    "ig-diplome":       "DSnL1_oDCiz",   # Remise diplômes  → img-ceremonie.jpg
}

# Final filenames for each Instagram post
# key = shortcode, value = list of output filenames (one per image in carousel)
INSTAGRAM_FILENAMES = {
    "DVYMaZ0DLlD": ["img-cleary.jpg"],       # Gide post  (img_index=1 only)
    "DSnL1_oDCiz": ["img-ceremonie.jpg"],    # Remise diplômes
}

# LinkedIn page URL (will be opened in browser for manual screenshot)
LINKEDIN_URL = (
    "https://www.linkedin.com/school/"
    "magist%C3%A8re-juriste-d'affaires---djce/posts/"
    "?feedView=all&viewAsMember=true"
)

# LinkedIn: after you log in the script waits this many seconds for you to
# scroll to the right posts before it takes screenshots.
LINKEDIN_WAIT_SECONDS = 30

# ── HELPERS ─────────────────────────────────────────────────────────────────

def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)

def convert_to_jpg(src: Path, dest: Path):
    """Convert any PIL-readable image to JPEG and save to dest."""
    with Image.open(src) as img:
        rgb = img.convert("RGB")
        rgb.save(dest, "JPEG", quality=92)
    print(f"  ✓ Saved {dest.name}")

# ── INSTAGRAM ───────────────────────────────────────────────────────────────

def fetch_instagram_posts(output_dir: Path):
    """
    Download Instagram post images using instaloader.
    Works on public profiles without login.
    If you get rate-limited, pass your IG credentials below.
    """
    print("\n── Instagram ───────────────────────────────────────────")

    L = instaloader.Instaloader(
        download_pictures=True,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        post_metadata_txt_pattern="",
        quiet=True,
    )

    # Optional: log in to avoid rate limits on private/semi-private content
    # L.login("your_instagram_username", "your_password")

    tmp_dir = output_dir / "_ig_tmp"
    ensure_dir(tmp_dir)

    for label, shortcode in INSTAGRAM_POSTS.items():
        print(f"\n  Fetching post {shortcode} ({label})…")
        try:
            post = instaloader.Post.from_shortcode(L.context, shortcode)

            # Collect all image URLs in the post (carousel support)
            image_urls = []
            if post.typename == "GraphSidecar":
                for node in post.get_sidecar_nodes():
                    if not node.is_video:
                        image_urls.append(node.display_url)
            else:
                image_urls.append(post.url)

            target_names = INSTAGRAM_FILENAMES.get(shortcode, [])

            for idx, url in enumerate(image_urls):
                if idx >= len(target_names):
                    break
                dest_name = target_names[idx]

                # Download raw file
                raw_path = tmp_dir / f"{shortcode}_{idx}.jpg"
                response = requests.get(url, timeout=30)
                response.raise_for_status()
                raw_path.write_bytes(response.content)

                # Convert & copy to output
                final_path = output_dir / dest_name
                convert_to_jpg(raw_path, final_path)

                # Also save as li- variant for the LinkedIn card thumbnail
                li_name = dest_name.replace("img-", "img-li-")
                li_path = output_dir / li_name
                shutil.copy(final_path, li_path)
                print(f"  ✓ Also copied as {li_name}")

                time.sleep(1)  # be polite to Instagram servers

        except Exception as e:
            print(f"  ✗ Failed to fetch {shortcode}: {e}")

    # Cleanup temp
    shutil.rmtree(tmp_dir, ignore_errors=True)


# ── LINKEDIN ─────────────────────────────────────────────────────────────────

def fetch_linkedin_screenshots(output_dir: Path):
    """
    Opens LinkedIn in a real Chrome window so you can log in manually.
    After LINKEDIN_WAIT_SECONDS seconds, the script scrolls through the feed
    and takes a full-page screenshot of each visible post card.

    You end up with:
        img-li-ceremonie.jpg  (first post)
        img-li-cleary.jpg     (second post)
        img-li-hcjp.jpg       (third post)

    TIP: Before the countdown ends, scroll so the 3 most relevant posts
    are visible on screen and resize the cards if needed.
    """
    print("\n── LinkedIn ────────────────────────────────────────────")
    print("  Opening Chrome. Log in and scroll to the target posts.")
    print(f"  You have {LINKEDIN_WAIT_SECONDS} seconds before screenshots are taken.\n")

    options = Options()
    # Run in a VISIBLE window so you can log in
    options.add_argument("--window-size=1280,900")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(options=options)
    driver.get(LINKEDIN_URL)

    # Countdown so you can log in and position the feed
    for remaining in range(LINKEDIN_WAIT_SECONDS, 0, -5):
        print(f"  Screenshot in {remaining}s… (scroll to your posts now)")
        time.sleep(5)

    print("  Taking screenshots…")

    # LinkedIn post card selector — grabs the main feed update containers
    try:
        wait = WebDriverWait(driver, 10)
        post_cards = driver.find_elements(
            By.CSS_SELECTOR,
            "div.feed-shared-update-v2, div.occludable-update"
        )

        li_names = ["img-li-ceremonie.jpg", "img-li-cleary.jpg", "img-li-hcjp.jpg"]

        for i, (card, name) in enumerate(zip(post_cards[:3], li_names)):
            try:
                # Scroll card into view
                driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'});", card
                )
                time.sleep(1.5)

                # Screenshot the card element
                png_path = output_dir / f"_li_raw_{i}.png"
                card.screenshot(str(png_path))

                # Crop to 16:9 for the li-card-img slot
                with Image.open(png_path) as img:
                    w, h = img.size
                    target_h = int(w * 9 / 16)
                    top = max(0, (h - target_h) // 2)
                    cropped = img.crop((0, top, w, top + target_h))
                    final_path = output_dir / name
                    cropped.convert("RGB").save(final_path, "JPEG", quality=92)
                    print(f"  ✓ Saved {name}")

                png_path.unlink()

            except Exception as e:
                print(f"  ✗ Could not screenshot card {i}: {e}")

    except Exception as e:
        print(f"  ✗ LinkedIn scraping error: {e}")
        print("  → Falling back: taking a full-page screenshot for manual crop.")
        full_path = output_dir / "linkedin_feed_full.png"
        driver.save_screenshot(str(full_path))
        print(f"  Saved full page to {full_path}. Crop manually into img-li-*.jpg.")

    finally:
        driver.quit()


# ── INSTAGRAM MOSAIC PLACEHOLDERS ────────────────────────────────────────────

def generate_placeholder_mosaic(output_dir: Path, count: int = 8):
    """
    Creates solid-colour placeholder tiles (ig-1.jpg … ig-N.jpg)
    so the HTML renders immediately even before you add real photos.
    Replace these with real event photos at any time.
    """
    print("\n── Instagram mosaic placeholders ──────────────────────")
    colours = [
        (30, 30, 30), (50, 20, 20), (20, 20, 50),
        (40, 30, 20), (20, 40, 30), (35, 35, 20),
        (25, 40, 40), (45, 25, 25),
    ]
    for i in range(1, count + 1):
        path = output_dir / f"ig-{i}.jpg"
        if not path.exists():   # don't overwrite if already placed
            colour = colours[(i - 1) % len(colours)]
            img = Image.new("RGB", (800, 800), colour)
            img.save(path, "JPEG")
            print(f"  ✓ Placeholder {path.name}")
        else:
            print(f"  – {path.name} already exists, skipping")


# ── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    ensure_dir(OUTPUT_DIR)

    print("=" * 55)
    print("  MJA Image Fetcher")
    print("=" * 55)
    print(f"  Output: {OUTPUT_DIR.resolve()}")

    # 1. Instagram posts (editorial + li- duplicates)
    fetch_instagram_posts(OUTPUT_DIR)

    # 2. LinkedIn card screenshots (requires Chrome + manual login)
    fetch_linkedin_screenshots(OUTPUT_DIR)

    # 3. Placeholder tiles for the Instagram mosaic grid
    generate_placeholder_mosaic(OUTPUT_DIR, count=8)

    print("\n" + "=" * 55)
    print("  Done! Copy everything in mja_images/ next to your HTML.")
    print("  Replace ig-1.jpg … ig-8.jpg with real event photos.")
    print("=" * 55)


if __name__ == "__main__":
    main()