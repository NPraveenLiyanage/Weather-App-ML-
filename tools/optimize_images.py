"""
Turn the heavy background photos (22 MB of JPEG) into small responsive WebP files plus a tiny blurred preview that is
inlined in the page, so the card is never an empty black box while the photo loads.
    myenv\Scripts\python.exe tools\optimize_images.py
Originals are untouched; the new page only uses static/img/sky/.
"""
import base64, io, json, os
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "weatherProject", "forecast", "static", "img")
DST = os.path.join(SRC, "sky")
NAMES = {"clear.jpeg": "clear", "sunny.jpeg": "sunny", "cloudy.jpeg": "cloudy", "overcast.jpeg": "overcast", "mist.jpeg": "mist", "fog.jpeg": "fog",
         "drizzle.jpeg": "drizzle", "shower.jpeg": "shower", "showers.jpeg": "showers", "rain.jpeg": "rain", "moderate rain.jpg": "moderate", "thunder.jpeg": "thunder"}
def crop_to(im, aspect, vbias=0.42):
    """Centre-crop to the given width/height ratio (slightly above centre vertically: skies and horizons carry the mood)."""
    w, h = im.size
    if w / h > aspect:
        nw = round(h * aspect); x = (w - nw) // 2
        return im.crop((x, 0, x + nw, h))
    nh = round(w / aspect); y = round((h - nh) * vbias)
    return im.crop((0, y, w, y + nh))


manifest, before, after = {}, 0, 0
for fn, key in NAMES.items():
    path = os.path.join(SRC, fn)
    im = Image.open(path).convert("RGB")
    before += os.path.getsize(path)
    entry = {}
    for tag, aspect, size, q in (("l", 16 / 10, (1600, 1000), 66), ("p", 9 / 14, (800, 1244), 62)):
        out = os.path.join(DST, f"{key}-{tag}.webp")
        crop_to(im, aspect).resize(size, Image.LANCZOS).save(out, "WEBP", quality=q, method=6)
        after += os.path.getsize(out)
        entry[tag] = f"img/sky/{key}-{tag}.webp"
        entry[tag + "_kb"] = os.path.getsize(out) // 1024
    tiny = crop_to(im, 16 / 10).resize((24, 15), Image.LANCZOS).filter(ImageFilter.GaussianBlur(1))
    buf = io.BytesIO(); tiny.save(buf, "WEBP", quality=40)
    entry["lqip"] = "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode()
    manifest[key] = entry
json.dump(manifest, open(os.path.join(DST, "manifest.json"), "w"))
print(f"{len(manifest)} scenes: originals {before/1e6:.1f} MB -> all web versions {after/1e6:.2f} MB (a visit downloads ONE scene, ~{after/len(manifest)/2048:.0f} KB)")
for k, v in manifest.items():
    print(f"  {k:10s} desktop {v['l_kb']:4d} KB   phone {v['p_kb']:4d} KB")
