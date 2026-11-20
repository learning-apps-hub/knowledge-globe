"""Clean pictures from Scotese's PALEOMAP PaleoAtlas: take out the lines drawn on them.

Every atlas map has TODAY's political boundaries and coasts drawn on it as thin black lines (moved back to
that age with the plate model) and its file name as a tiny caption near the south pole. Neither belongs in the
past. Filters alone cannot tell those lines from the map: at young ages today's coasts sit right on the old
coasts, and anything strong enough to wipe the lines wipes real islands too. So this works out WHERE the lines
must be, from the same plate model and the same boundaries the atlas ships with
(`PALEOMAP_PlateModel.rot`, `PALEOMAP_PoliticalBoundaries.gpml`), and repaints only darkened pixels in a thin
band there, from their clean neighbours. Everything else is left exactly as drawn.

Build tool (numpy + Pillow, the earth-data venv); the app itself stays standard-library only.
"""
import math
import xml.etree.ElementTree as ET  # nosec B405 - parses only the pinned atlas zip (Zenodo 5460860)

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

NS = {"gpml": "http://www.gplates.org/gplates", "gml": "http://www.opengis.net/gml"}
BAND = 5        # px (on the 3600-wide atlas): the band round each moved-back line where it may be drawn
SHIFT = 5       # px: the most a plate's lines are nudged to sit on the drawn ones (the atlas's own rounding)
DARK = 20       # a line pixel is at least this much darker than its neighbourhood (0-255) ...
ALPHA = .3      # ... and at least this share black
SOFT = 5        # its soft edge: touching pixels at least this much darker are taken too
CAPTION = (150, 1688, 430, 1722)
# Older maps were drawn with an older plate model: their lines miss the moved-back ones by 10-30 px and bend
# (600 Ma). Those maps are smoothly painted, so from this age on a second pass also takes any near-black,
# colourless stroke anywhere (on younger maps the fine relief and the dark coast edges would be caught too).
EVERYWHERE_FROM = 300   # where the file-name caption sits on a 3600 x 1800 map


# ---------- the plate model: where each plate was at an age ----------

def _quat(lat, lon, angle):
    """Unit quaternion (w, x, y, z) for a turn of `angle` degrees about the pole at (lat, lon)."""
    la, lo, h = math.radians(lat), math.radians(lon), math.radians(angle) / 2
    s = math.sin(h)
    return np.array([math.cos(h), math.cos(la) * math.cos(lo) * s, math.cos(la) * math.sin(lo) * s, math.sin(la) * s])


def _qmul(a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return np.array([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])


def _slerp(a, b, f):
    d = float(np.dot(a, b))
    if d < 0:
        b, d = -b, -d
    if d > .9995:
        q = a + f * (b - a)
        return q / np.linalg.norm(q)
    th = math.acos(d)
    return (math.sin((1 - f) * th) * a + math.sin(f * th) * b) / math.sin(th)


class PlateModel:
    """A GPlates rotation file: each plate's turn against the plate it moves with, at listed ages."""

    def __init__(self, text):
        self.rows = {}
        for line in text.splitlines():
            p = line.split("!")[0].split()
            if len(p) < 6 or p[0] == "999":
                continue
            plate, fixed = int(p[0]), int(p[5])
            age, lat, lon, angle = (float(v) for v in p[1:5])
            self.rows.setdefault(plate, []).append((age, _quat(lat, lon, angle), fixed))
        self.memo = {}

    def turn(self, plate, age, depth=0):
        """The plate's whole turn from today to `age`, in the model's fixed frame (plate 0); None if unknown."""
        key = (plate, age)
        if key not in self.memo:
            q = np.array([1.0, 0, 0, 0]) if plate == 0 or depth > 60 else None
            if q is None:
                rows = self.rows.get(plate, [])
                for (a0, q0, f0), (a1, q1, f1) in zip(rows, rows[1:]):
                    if f0 == f1 and a0 <= age <= a1 and a1 > a0:
                        parent = self.turn(f0, age, depth + 1)
                        if parent is not None:
                            q = _qmul(parent, _slerp(q0, q1, (age - a0) / (a1 - a0)))
                        break
            self.memo[key] = q
        return self.memo[key]


def read_features(text):
    """[(plate, born, gone, [N x 2 arrays of lat, lon])] from a GPlates .gpml file."""
    out = []
    for member in ET.fromstring(text).iterfind("gml:featureMember", NS):  # nosec B314 - pinned atlas file
        feature = member[0]
        pid = feature.find(".//gpml:reconstructionPlateId//gpml:value", NS)
        born, gone = math.inf, -math.inf
        valid = feature.find(".//gpml:validTime", NS)
        if valid is not None:
            def when(el, default):
                return default if el is None or not el.text or "inf" in el.text.lower() else float(el.text)
            born = when(valid.find(".//gml:begin//gml:timePosition", NS), math.inf)
            gone = when(valid.find(".//gml:end//gml:timePosition", NS), -math.inf)
        rings = [np.array(p.text.split(), dtype=float).reshape(-1, 2) for p in feature.iter("{%s}posList" % NS["gml"])]
        if rings:
            out.append((int(pid.text) if pid is not None else 0, born, gone, rings))
    return out


def moved_back(features, model, age, width, height):
    """{plate: [N x 2 arrays of x, y pixels]}: the features as they were at `age`, split at the date line."""
    out = {}
    for plate, born, gone, rings in features:
        if not gone <= age <= born:
            continue
        q = model.turn(plate, age)
        if q is None:
            continue
        for ll in rings:
            la, lo = np.radians(ll[:, 0]), np.radians(ll[:, 1])
            xyz = np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)], 1)
            t = 2 * np.cross(q[1:], xyz)
            r = xyz + q[0] * t + np.cross(q[1:], t)
            lat = np.degrees(np.arcsin(np.clip(r[:, 2], -1, 1)))
            lon = np.degrees(np.arctan2(r[:, 1], r[:, 0]))
            xy = np.stack([(lon + 180) / 360 * width, (90 - lat) / 180 * height], 1)
            cut = np.where(np.abs(np.diff(xy[:, 0])) > width / 2)[0] + 1
            out.setdefault(plate, []).extend(p for p in np.split(xy, cut) if len(p) > 1)
    return out


# ---------- finding and repainting the lines ----------

def _filtered(a, f):
    return np.asarray(Image.fromarray(a).filter(f), dtype=np.float32)


def _grow(mask, n=1):
    for _ in range(n):
        mask = _filtered((mask * 255).astype(np.uint8), ImageFilter.MaxFilter(3)) > 0
    return mask


def darkness(rgb, size=7):
    """How much darker each pixel is than its neighbourhood with dark strokes thinner than `size` px closed
    over, and that as a share (how black it is, if it were a black stroke over the neighbourhood)."""
    lum = (rgb @ np.array([.299, .587, .114], dtype=np.float32)).clip(0, 255).astype(np.uint8)
    closed = _filtered(_filtered(lum, ImageFilter.MaxFilter(size)).astype(np.uint8), ImageFilter.MinFilter(size))
    dark = closed - lum
    return dark, dark / np.maximum(closed, 1)


def _points(runs):
    pts = []
    for p in runs:
        seg = np.diff(p, axis=0)
        n = np.maximum(1, np.ceil(np.hypot(seg[:, 0], seg[:, 1])).astype(int))
        for (x0, y0), (sx, sy), k in zip(p[:-1], seg, n):
            f = np.arange(k) / k
            pts.append(np.stack([x0 + f * sx, y0 + f * sy], 1))
    return np.concatenate(pts) if pts else np.zeros((0, 2))


def nudges(lines, dark):
    """For each plate, the small shift (at most SHIFT px each way) that puts its lines on the darkest pixels:
    the atlas was drawn with its own rounding and model version, and is off by a pixel or few, plate by plate."""
    h, w = dark.shape
    out = {}
    for plate, runs in lines.items():
        pts = _points(runs)
        if len(pts) < 40:
            continue
        best, top = (0, 0), None
        for dy in range(-SHIFT, SHIFT + 1):
            for dx in range(-SHIFT, SHIFT + 1):
                x = np.clip(np.round(pts[:, 0] + dx).astype(int), 0, w - 1)
                y = np.clip(np.round(pts[:, 1] + dy).astype(int), 0, h - 1)
                score = float(dark[y, x].mean()) - .15 * (abs(dx) + abs(dy))
                if top is None or score > top:
                    best, top = (dx, dy), score
        out[plate] = best
    return out


def fill(rgb, mask):
    """Repaint masked pixels from the outside in: each pass gives the masked pixels that touch clean ones the
    mean of those clean neighbours, so a coast crossing a line meets in the middle and stays sharp."""
    out = rgb.copy()
    known = ~mask
    h, w = known.shape
    for _ in range(60):
        todo = ~known
        if not todo.any():
            break
        kp = np.pad(known, 1).astype(np.float32)
        op = np.pad(out * known[..., None], ((1, 1), (1, 1), (0, 0)))
        num = np.zeros_like(out)
        den = np.zeros(known.shape, np.float32)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx or dy:
                    num += op[1 + dy:1 + dy + h, 1 + dx:1 + dx + w]
                    den += kp[1 + dy:1 + dy + h, 1 + dx:1 + dx + w]
        ok = todo & (den > 0)
        out[ok] = num[ok] / den[ok][:, None]
        known |= ok
    return out


def caption_mask(rgb):
    """The file name printed near the south pole (black or red letters on the map's own colours)."""
    h, w, _ = rgb.shape
    x0, y0, x1, y1 = (round(v * s) for v, s in zip(CAPTION, (w / 3600, h / 1800, w / 3600, h / 1800)))
    box = rgb[y0:y1, x0:x1]
    usual = np.median(box, axis=1, keepdims=True)
    odd = (np.abs(box - usual).max(-1) > 45) | ((box[..., 0] - box[..., 1:].max(-1)) > 60)
    mask = np.zeros((h, w), bool)
    mask[y0:y1, x0:x1] = odd
    return _grow(mask)


def clean(picture, model, features, age):
    """The atlas picture for `age` with its drawn lines and caption taken out. Returns (picture, share repainted)."""
    rgb = np.asarray(picture.convert("RGB"), dtype=np.float32)
    h, w, _ = rgb.shape
    dark, alpha = darkness(rgb)
    lines = moved_back(features, model, age, w, h)
    shift = nudges(lines, dark)
    band = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(band)
    for plate, runs in lines.items():
        dx, dy = shift.get(plate, (0, 0))
        for p in runs:
            draw.line([(x + dx, y + dy) for x, y in p], fill=255, width=BAND)
    mask = _grow((np.asarray(band) > 0) & (dark > DARK) & (alpha > ALPHA))
    for _ in range(2):
        mask |= _grow(mask) & (dark > SOFT)
    if age >= EVERYWHERE_FROM:
        # Only strokes thinner than 4 px (a closing of 5): wider dark ground, like the lowlands' dark green
        # edges, closes over nothing and is left alone.
        thin, share = darkness(rgb, 5)
        chroma = rgb.max(-1) - rgb.min(-1)
        stroke = (share > .25) & (thin > 22) & (chroma < 50)
        for _ in range(6):
            stroke |= _grow(stroke) & (thin > 8) & (share > .08)
        mask |= _grow(stroke)
    mask |= caption_mask(rgb)
    out = fill(rgb, mask)
    return Image.fromarray(out.clip(0, 255).round().astype(np.uint8)), float(mask.mean())
