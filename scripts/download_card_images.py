#!/usr/bin/env python3
"""
download_card_images.py
Usage:
  python download_card_images.py start_urls.txt
Where start_urls.txt is a newline-separated list of issuer hub pages or card product pages.

What it does:
 - crawls each URL (shallow crawl) and discovers product pages (heuristic)
 - for each product page, finds the best image (og:image, link[rel=image_src], big <img>)
 - downloads images to ./images/cards/
"""

import os, re, sys, time, urllib.parse
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

HEADERS = {"User-Agent": "rewrds-bot/1.0 (+https://rewrds.com)"}  # be polite; replace with your contact URL if desired
OUT_DIR = Path("images/cards")
OUT_DIR.mkdir(parents=True, exist_ok=True)
SESSION = requests.Session()
SESSION.headers.update(HEADERS)
SLEEP = 0.8  # polite delay

def norm_filename(issuer, card_name, ext):
    # remove unsafe chars, spaces -> underscore, lowercase
    name = f"{issuer}_{card_name}".lower()
    name = re.sub(r"[^a-z0-9_]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return f"{name}.{ext}"

def get_soup(url):
    try:
        resp = SESSION.get(url, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"[ERROR] {url} -> {e}")
        return None
    return BeautifulSoup(resp.text, "lxml"), resp.url

def guess_product_links(soup, base_url):
    """Return candidate product links found on a hub page (heuristic: contains 'card', 'apply', 'credit-card')."""
    links = set()
    for a in soup.find_all("a", href=True):
        href = urllib.parse.urljoin(base_url, a["href"])
        href_l = href.lower()
        # heuristics
        if any(tok in href_l for tok in ["/card", "credit-card", "/cards/", "/creditcards/", "/credit-cards/", "apply"]):
            links.add(href.split("#")[0])
    return list(links)

def find_best_image(soup, base_url):
    # 1) og:image
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        return urllib.parse.urljoin(base_url, og["content"])
    # 2) twitter:image
    tw = soup.find("meta", attrs={"name":"twitter:image"})
    if tw and tw.get("content"):
        return urllib.parse.urljoin(base_url, tw["content"])
    # 3) link[rel=image_src]
    link_img = soup.find("link", rel="image_src")
    if link_img and link_img.get("href"):
        return urllib.parse.urljoin(base_url, link_img["href"])
    # 4) big images with likely class names (heuristic)
    candidates = []
    for img in soup.find_all("img", src=True):
        src = urllib.parse.urljoin(base_url, img["src"])
        w = img.get("width") or 0
        h = img.get("height") or 0
        area = 0
        try:
            area = int(w) * int(h)
        except:
            area = 0
        candidates.append((area, src, img))
    # prefer largest file area or fallback to first with card-like filename
    if candidates:
        candidates.sort(reverse=True, key=lambda x: x[0])
        # prefer filenames containing 'card' or 'product'
        for _, src, img in candidates:
            if re.search(r"(card|product|art|front|face)", src, re.I):
                return src
        return candidates[0][1]
    return None

def download_image(url, out_path):
    try:
        r = SESSION.get(url, stream=True, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"[ERROR] downloading {url}: {e}")
        return False
    # get extension from content-type or url
    content_type = r.headers.get("content-type", "")
    if "image" in content_type:
        ext = content_type.split("/")[-1].split(";")[0]
        if ext == "jpeg": ext = "jpg"
    else:
        ext = os.path.splitext(urllib.parse.urlparse(url).path)[1].lstrip(".") or "png"
    final_path = out_path.with_suffix(f".{ext}")
    with open(final_path, "wb") as f:
        for chunk in r.iter_content(10240):
            f.write(chunk)
    return final_path.name

def extract_card_name_from_title(soup):
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
        # sanitize
        title = re.sub(r"[:|–|-].*$", "", title)
        return re.sub(r"\s+", "_", title).strip("_")
    return "card"

def process_url(url, issuer_hint=None, visited=set()):
    time.sleep(SLEEP)
    soup_tuple = get_soup(url)
    if not soup_tuple:
        return []
    soup, final_url = soup_tuple
    results = []
    # attempt to detect if this is a product page by looking for obvious meta tags or card naming
    page_text = soup.get_text(" ", strip=True).lower()
    is_product = "apply now" in page_text[:2000] or "rewards" in page_text[:2000] or "annual fee" in page_text[:2000]
    product_links = []
    if is_product:
        product_links = [final_url]
    else:
        # discover product links
        product_links = guess_product_links(soup, final_url)[:30]  # keep it reasonable

    for p in product_links:
        if p in visited:
            continue
        visited.add(p)
        time.sleep(SLEEP)
        s_tuple = get_soup(p)
        if not s_tuple:
            continue
        psoup, pfinal = s_tuple
        img_url = find_best_image(psoup, pfinal)
        card_name = extract_card_name_from_title(psoup)
        issuer = issuer_hint or urllib.parse.urlparse(pfinal).netloc.split(".")[-2]
        if img_url:
            fname = norm_filename(issuer, card_name, "tmp")
            local = OUT_DIR / fname
            got = download_image(img_url, OUT_DIR / f"{issuer}_{card_name}")
            if got:
                results.append((pfinal, img_url, got))
            else:
                results.append((pfinal, img_url, None))
        else:
            results.append((pfinal, None, None))
    return results

def main():
    if len(sys.argv) < 2:
        print("Usage: python download_card_images.py start_urls.txt")
        sys.exit(1)
    start_file = Path(sys.argv[1])
    if not start_file.exists():
        print("start_urls.txt not found")
        sys.exit(1)
    start_urls = [line.strip() for line in start_file.read_text().splitlines() if line.strip()]
    summary = []
    visited = set()
    for url in tqdm(start_urls, desc="Issuers"):
        try:
            res = process_url(url, issuer_hint=urllib.parse.urlparse(url).netloc.split(".")[-2], visited=visited)
            summary.extend(res)
        except Exception as e:
            print(f"[ERR] {url} -> {e}")
    # write summary
    with open("download_summary.csv", "w") as f:
        f.write("product_page,found_image_url,local_filename\n")
        for product_page, found_img, local in summary:
            f.write(f'"{product_page}","{found_img or ""}","{local or ""}"\n')
    print("Done. See images in ./images/cards/ and download_summary.csv")

if __name__ == "__main__":
    main()
