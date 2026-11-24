"""Generate the installable-app icons (PNG) with Pillow:  myenv\\Scripts\\python.exe tools\\make_icons.py"""
import os
from PIL import Image, ImageDraw, ImageFilter

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "weatherProject", "forecast", "static", "img", "icons")
os.makedirs(OUT, exist_ok=True)


def icon(size, safe=0.0):
    """safe = fraction of padding for maskable icons (the OS may crop to a circle)."""
    S = size * 4  # draw large, then downsample for smooth edges
    im = Image.new("RGB", (S, S))
    px = im.load()
    for y in range(S):
        for x in range(S):
            t = (x * 0.35 + y * 0.65) / S
            px[x, y] = (int(18 + 20 * t), int(34 + 62 * t), int(44 + 70 * t))
    d = ImageDraw.Draw(im)
    pad = S * safe
    u = (S - 2 * pad) / 100.0
    X = lambda v: pad + v * u

    def cloud(col):
        for cx, cy, r in ((38, 46, 15), (55, 40, 19), (72, 48, 14)):
            d.ellipse((X(cx - r), X(cy - r), X(cx + r), X(cy + r)), fill=col)
        d.rounded_rectangle((X(23), X(46), X(86), X(62)), radius=X(8) - pad, fill=col)
    cloud((255, 255, 255))
    for x0 in (36, 52, 68):
        d.line((X(x0), X(70), X(x0 - 6), X(86)), fill=(155, 210, 255), width=int(u * 5), joint="curve")
    d.ellipse((X(58), X(18), X(70), X(30)), fill=(255, 167, 38))  # a little sun behind the cloud's edge
    cloud((255, 255, 255))
    return im.resize((size, size), Image.LANCZOS)


icon(192).save(os.path.join(OUT, "icon-192.png"))
icon(512).save(os.path.join(OUT, "icon-512.png"))
icon(512, safe=0.14).save(os.path.join(OUT, "maskable-512.png"))
icon(180).save(os.path.join(OUT, "apple-touch-icon.png"))
print("icons written to", os.path.normpath(OUT))
