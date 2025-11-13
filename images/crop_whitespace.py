from PIL import Image, ImageChops, ImageStat
import os

input_folder = "screenshots"        # where your raw screenshots are
output_folder = "cropped_cards"     # where to save cropped versions
tolerance = 15                      # how forgiving to be (0 = strict white only)

os.makedirs(output_folder, exist_ok=True)

def trim_whitespace(img, tol=tolerance):
    # Convert to RGB just in case it's RGBA or something else
    img = img.convert("RGB")
    bg = Image.new("RGB", img.size, img.getpixel((0, 0)))  # assume top-left pixel is background
    diff = ImageChops.difference(img, bg)
    # Enhance diff to make near-white areas count as background
    diff = ImageChops.add(diff, diff, 2.0, -tol)
    bbox = diff.getbbox()
    return img.crop(bbox) if bbox else img  # crop if difference found

for filename in os.listdir(input_folder):
    if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
        path = os.path.join(input_folder, filename)
        img = Image.open(path)
        cropped = trim_whitespace(img)
        cropped.save(os.path.join(output_folder, filename))

print("✅ Cropping complete. Check the 'cropped_cards' folder.")
