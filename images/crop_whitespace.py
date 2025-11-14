from PIL import Image
import os
from collections import Counter, deque

script_dir = os.path.dirname(os.path.abspath(__file__))
input_folder = os.path.join(script_dir, "screenshots")  # where your raw screenshots are
output_folder = os.path.join(script_dir, "cropped_cards")  # where to save processed versions

# Tolerance for considering a pixel part of the background (0-255 per channel)
TOLERANCE = 15
os.makedirs(output_folder, exist_ok=True)

# Collect already processed (without extension differences)
existing_outputs = {os.path.splitext(f)[0].lower() for f in os.listdir(output_folder) if f.lower().endswith(".png")}

def remove_background(img, tol=TOLERANCE):
    """Make only edge-connected uniform/light background transparent.
    Internal white/off-white areas remain untouched.
    Steps:
      1. Collect corner colors as background candidates (near-white only).
      2. Flood fill from all edge pixels that match background criteria.
      3. Only pixels reached by flood fill become transparent.
      4. Crop resulting transparent border.
    """
    rgb = img.convert("RGB")
    w, h = rgb.size

    def is_near_white(pixel):
        return all(channel >= 255 - tol for channel in pixel[:3])

    corner_pixels = [
        rgb.getpixel((0, 0)),
        rgb.getpixel((w - 1, 0)),
        rgb.getpixel((0, h - 1)),
        rgb.getpixel((w - 1, h - 1)),
    ]
    # Only treat near-white corners as background candidates
    bg_candidates = {p for p in corner_pixels if is_near_white(p)}

    # If no near-white corners, skip processing (avoid removing colored edges)
    if not bg_candidates:
        return None

    rgba = rgb.convert("RGBA")
    pixels = rgba.load()

    def is_bg(pixel):
        # Corner-based near-white candidates
        for bg in bg_candidates:
            if all(abs(pixel[i] - bg[i]) <= tol for i in range(3)):
                return True
        # General near-white heuristic as fallback
        if is_near_white(pixel):
            return True
        return False

    visited = [[False]*w for _ in range(h)]
    q = deque()

    def enqueue_if_bg(x, y):
        if 0 <= x < w and 0 <= y < h and not visited[y][x]:
            if is_bg(pixels[x, y]):
                visited[y][x] = True
                q.append((x, y))

    # Seed queue with all edge pixels that satisfy background criteria
    for x in range(w):
        enqueue_if_bg(x, 0)
        enqueue_if_bg(x, h-1)
    for y in range(h):
        enqueue_if_bg(0, y)
        enqueue_if_bg(w-1, y)

    # 4-directional flood fill (use 8 if needed)
    while q:
        x, y = q.popleft()
        for nx, ny in ((x+1,y), (x-1,y), (x,y+1), (x,y-1)):
            if 0 <= nx < w and 0 <= ny < h and not visited[ny][nx]:
                if is_bg(pixels[nx, ny]):
                    visited[ny][nx] = True
                    q.append((nx, ny))

    # Apply transparency only to visited (edge-connected background) pixels
    for y in range(h):
        for x in range(w):
            if visited[y][x]:
                r, g, b, a = pixels[x, y]
                pixels[x, y] = (r, g, b, 0)

    # Trim transparent border
    alpha = rgba.split()[-1]
    bbox = alpha.getbbox()
    if bbox:
        rgba = rgba.crop(bbox)
    return rgba

# Force reprocess (ignore cache) if environment variable CROP_FORCE=1
force = os.environ.get("CROP_FORCE") == "1"

if not os.path.isdir(input_folder):
    print(f"❌ Input folder not found: {input_folder}")
else:
    files_processed = 0
    files_skipped = 0
    files_skipped_no_bg = 0
    for filename in os.listdir(input_folder):
        if filename.lower().endswith((".png", ".jpg", ".jpeg")):
            stem = os.path.splitext(filename)[0].lower()
            if stem in existing_outputs and not force:
                files_skipped += 1
                continue
            path = os.path.join(input_folder, filename)
            try:
                img = Image.open(path)
                processed = remove_background(img)
                if processed is None:
                    files_skipped_no_bg += 1
                    continue
                out_name = stem + ".png"
                processed.save(os.path.join(output_folder, out_name))
                files_processed += 1
            except Exception as e:
                print(f"⚠️ Failed processing {filename}: {e}")
    if files_processed:
        print(f"✅ Background removal complete. {files_processed} new file(s) saved to '{output_folder}'.")
    print(f"ℹ️ Skipped {files_skipped} existing file(s). Use CROP_FORCE=1 to reprocess all.")
    print(f"ℹ️ Skipped {files_skipped_no_bg} file(s) with no near-white border.")
    if files_processed == 0 and files_skipped == 0 and files_skipped_no_bg == 0:
        print("ℹ️ No image files processed.")
