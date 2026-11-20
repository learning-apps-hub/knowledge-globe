#!/usr/bin/env python3
"""Fetch the real clouds of the last day, one picture an hour (Explore).

Source: NOAA's Global Mosaic of Geostationary Satellite Imagery (GMGSI),
longwave infrared, one world picture an hour made from five weather
satellites (GOES East and West, two Meteosats, Himawari). Public domain (NOAA
Open Data, bucket `noaa-gmgsi-pds`). Infrared works day and night.

    ../earth-data/.venv/bin/pip install h5py     (once; beside Pillow and numpy)
    ../earth-data/.venv/bin/python scripts/build_clouds.py

Run every hour by the `knowledge-globe-clouds.timer` user unit. It writes

    earth-data/derived/clouds/clouds-<YYYYMMDDHH>.jpg     2048 x 1024, one an hour
    earth-data/derived/clouds/clouds-<YYYYMMDDHH>-4096.jpg  the newest hour only
    earth-data/derived/clouds/flow-<YYYYMMDDHH>.png        how the clouds moved in the hour after
    earth-data/derived/clouds/clouds.json                  which hours there are

and, once a day, yesterday's sea ice (scripts/build_ice.py --update).

and deletes hours older than KEEP_HOURS. The downloads (7 MB each) are not
kept. h5py is a build tool, like Pillow and numpy: the app stays stdlib-only.

What the picture is, and is not:
- The satellites measure how cold the top of whatever they see is. High, thick
  cloud is very cold and shows well. Low cloud and fog are nearly as warm as
  the ground beneath and mostly do NOT show. Cold ground (ice, mountains at
  night) is taken out by comparing each spot with the warmest ground near it.
- The motion between two hours is worked out here, not seen: each patch of
  the first picture is matched to where it looks most alike in the next one
  (within about 5 degrees). Explore slides the clouds along it between the
  hours, so they move instead of fading. Where clouds grow or melt away, the
  two pictures are still mixed.
- The satellites sit over the equator and cannot see past about 73 degrees
  north or south: the picture fades to no cloud there.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DIR = os.environ.get("KG_EARTH_DIR") or os.path.join(os.path.dirname(REPO), "earth-data")
BUCKET = "https://noaa-gmgsi-pds.s3.amazonaws.com"
AGENT = "knowledge-globe-earth-build/1.0"
KEEP_HOURS = 24
WIDTH, HEIGHT = 2048, 1024
EDGE_LAT = 72.5      # the satellites see no further
FADE_LAT = 66.0      # the picture starts fading out here
# The motion: matched on a 512 x 256 copy (0.7 degree a cell), one arrow every
# FLOW_STEP cells, stored as a 128 x 64 picture: red = east, green = south,
# 128 = still, FLOW_SCALE steps a cell.
FLOW_W, FLOW_H = 512, 256
FLOW_REACH = 7        # cells: about 5 degrees an hour, faster than any cloud
FLOW_WIN = 8          # matching patch: (2 x 8 + 1) cells, about 12 degrees
FLOW_STEP = 4
FLOW_SCALE = 16
CREDIT = {
    "what": "The real clouds of the last day, one picture an hour",
    "credit": "NOAA/NESDIS, Global Mosaic of Geostationary Satellite Imagery (GOES, Meteosat, Himawari; infrared)",
    "licence": "Public domain (NOAA)",
}


def fetch(url, tries=4):
    for attempt in range(tries):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": AGENT})
            with urllib.request.urlopen(request, timeout=120) as response:  # nosec B310
                return response.read()
        except (urllib.error.URLError, TimeoutError) as error:
            if attempt == tries - 1:
                raise
            print(f"  retry {attempt + 1}: {error}", flush=True)
            time.sleep(5 * (attempt + 1))
    return None


def hour_key(when):
    """The bucket key of the infrared picture for this hour, or None if it is not there yet."""
    prefix = f"GMGSI_LW/{when:%Y/%m/%d/%H}/"
    listing = fetch(f"{BUCKET}/?list-type=2&prefix={prefix}").decode("utf-8", "replace")
    keys = sorted(re.findall(r"<Key>([^<]+\.nc)</Key>", listing))
    return keys[-1] if keys else None


def cloud_picture(nc_path):
    """One hour's file -> cloud amount, 0..1, on a plain 4096 x 2048 lat/lon grid (north up, 180 W at the left)."""
    import h5py
    import numpy as np
    from PIL import Image, ImageFilter

    with h5py.File(nc_path, "r") as nc:
        cold = np.squeeze(nc["data"][...]).astype(np.float32)   # 0..255, brighter = colder
        flag = np.squeeze(nc["dqf"][...])
        lat = nc["lat"][:, 0].astype(np.float64)                # Mercator rows, north first
        lon = nc["lon"][0, :].astype(np.float64)
    good = (flag == 0) & (cold >= 0) & (cold < 254.5)
    # Column 0 is 180 E, then 179.93 W onward: put the columns in west-to-east order.
    order = np.argsort(lon, kind="stable")
    cold, good, lon = cold[:, order], good[:, order], lon[order]

    # The warmest thing near each spot is clear ground or sea. Find it on a
    # small copy (about 0.6 degrees a cell), spread it about 9 degrees, soften.
    block = 8
    rows, cols = cold.shape[0] // block * block, cold.shape[1] // block * block
    seen = np.where(good, cold, 255.0)[:rows, :cols]
    small = seen.reshape(rows // block, block, cols // block, block)
    small = np.percentile(small, 10, axis=(1, 3)).astype(np.float32)
    ground = Image.fromarray(np.clip(small + 0.5, 0, 255).astype(np.uint8), "L")
    ground = ground.filter(ImageFilter.MinFilter(15)).filter(ImageFilter.GaussianBlur(7))
    ground = np.asarray(ground.resize((cold.shape[1], cold.shape[0]), Image.BILINEAR), np.float32)

    # Cloud = how much colder than that ground. Very cold tops (high value)
    # count as cloud whatever the ground is.
    above = (cold - ground - 8.0) / 85.0
    high = (cold - 178.0) / 60.0
    amount = np.clip(np.maximum(above, high), 0.0, 1.0) ** 1.15 * 0.8
    amount[~good] = 0.0

    # Mercator rows -> even latitude rows.
    out_h, out_w = 2048, 4096
    lat_out = 90.0 - (np.arange(out_h) + 0.5) * 180.0 / out_h
    inside = np.abs(lat_out) <= EDGE_LAT
    row_at = np.interp(lat_out[inside], lat[::-1], np.arange(len(lat))[::-1])
    low = np.clip(np.floor(row_at).astype(int), 0, len(lat) - 2)
    part = (row_at - low)[:, None].astype(np.float32)
    rows_out = amount[low] * (1 - part) + amount[low + 1] * part
    fade = np.clip((EDGE_LAT - np.abs(lat_out[inside])) / (EDGE_LAT - FADE_LAT), 0.0, 1.0)[:, None]
    world = np.zeros((out_h, cold.shape[1]), np.float32)
    world[inside] = rows_out * fade
    picture = Image.fromarray((world * 255 + 0.5).astype(np.uint8), "L")
    return picture.resize((out_w, out_h), Image.LANCZOS)


def _box(a, r):
    """Sum over a (2r+1) square around each cell: wraps east-west, nothing past the poles."""
    import numpy as np
    c = np.concatenate([a[:, -r - 1:], a, a[:, :r]], axis=1).cumsum(1)
    a = c[:, 2 * r + 1:] - c[:, :-2 * r - 1]
    p = np.pad(a, ((r + 1, r), (0, 0))).cumsum(0)
    return p[2 * r + 1:] - p[:-2 * r - 1]


def _soften(a, size):
    """A gentle blur (wraps east-west)."""
    import numpy as np
    k = np.exp(-0.5 * (np.arange(-3 * size, 3 * size + 1) / size) ** 2)
    k /= k.sum()
    r = len(k) // 2
    b = np.concatenate([a[:, -r:], a, a[:, :r]], 1)
    b = sum(k[i] * b[:, i:i + a.shape[1]] for i in range(len(k)))
    b = np.pad(b, ((r, r), (0, 0)), mode="edge")
    return sum(k[i] * b[i:i + a.shape[0]] for i in range(len(k)))


def cloud_motion(first_path, next_path):
    """How the clouds moved from one hour's picture to the next: a 128 x 64 RGB picture (see FLOW_SCALE)."""
    import numpy as np
    from PIL import Image

    def small(path):
        with Image.open(path) as im:
            return np.asarray(im.convert("L").resize((FLOW_W, FLOW_H), Image.BOX), np.float32) / 255.0

    a, b = small(first_path), small(next_path)
    reach, side = FLOW_REACH, 2 * FLOW_REACH + 1
    steps = [(dx, dy) for dy in range(-reach, reach + 1) for dx in range(-reach, reach + 1)]
    rows = np.arange(FLOW_STEP // 2, FLOW_H, FLOW_STEP)
    cols = np.arange(FLOW_STEP // 2, FLOW_W, FLOW_STEP)
    cost = np.empty((len(steps), len(rows), len(cols)), np.float32)
    for k, (dx, dy) in enumerate(steps):
        moved = np.roll(np.roll(b, -dx, 1), -dy, 0)          # moved[y, x] = b[y + dy, x + dx]
        # How unlike, plus a little for going far, so a plain patch stays still.
        cost[k] = (_box((a - moved) ** 2, FLOW_WIN) + 0.02 * (dx * dx + dy * dy))[rows][:, cols]
    best = cost.argmin(0)
    fx = (best % side - reach).astype(np.float32)
    fy = (best // side - reach).astype(np.float32)

    # Between cells: fit a curve through the best and its two neighbours, each way.
    def between(f, stride):
        inner = np.abs(f) < reach
        lo = np.where(inner, best - stride, best)
        hi = np.where(inner, best + stride, best)
        c0 = np.take_along_axis(cost, lo[None], 0)[0]
        c1 = np.take_along_axis(cost, best[None], 0)[0]
        c2 = np.take_along_axis(cost, hi[None], 0)[0]
        bend = c0 - 2 * c1 + c2
        ok = inner & (bend > 1e-6)
        return f + np.where(ok, 0.5 * (c0 - c2) / np.where(ok, bend, 1.0), 0.0)

    fx, fy = between(fx, 1), between(fy, side)
    # Trust a patch by how much cloud pattern it has; clear sky takes its neighbours' motion.
    pattern = _box(a * a, FLOW_WIN) - _box(a, FLOW_WIN) ** 2 / (2 * FLOW_WIN + 1) ** 2
    trust = np.maximum(pattern[rows][:, cols], 0)
    trust = trust / (trust.max() + 1e-9)
    weight = _soften(trust, 1) + 1e-4
    fx, fy = _soften(fx * trust, 1) / weight, _soften(fy * trust, 1) / weight
    out = np.stack([fx, fy, np.zeros_like(fx)], -1) * FLOW_SCALE + 128
    return Image.fromarray(np.clip(np.rint(out), 0, 255).astype(np.uint8), "RGB")


def make_motions(out_dir, stamps):
    """A motion picture for every hour whose next hour is held; returns {stamp: file}."""
    flows = {}
    for first, after in zip(stamps, stamps[1:]):
        gap = dt.datetime.strptime(after, "%Y%m%d%H") - dt.datetime.strptime(first, "%Y%m%d%H")
        if gap != dt.timedelta(hours=1):
            continue          # a missed hour: the viewer fades across it
        target = os.path.join(out_dir, f"flow-{first}.png")
        pictures = [os.path.join(out_dir, f"clouds-{stamp}.jpg") for stamp in (first, after)]
        made = max(os.path.getmtime(path) for path in pictures)
        if not os.path.isfile(target) or os.path.getmtime(target) < made:
            cloud_motion(*pictures).save(target + ".part", "PNG", optimize=True)
            os.replace(target + ".part", target)
        flows[first] = f"clouds/flow-{first}.png"
    for name in os.listdir(out_dir):
        match = re.fullmatch(r"flow-(\d{10})\.png", name)
        if match and match.group(1) not in flows:
            os.remove(os.path.join(out_dir, name))
    return flows


def build(earth_dir, hours=KEEP_HOURS, force=False):
    from PIL import Image

    out_dir = os.path.join(earth_dir, "derived", "clouds")
    work_dir = os.path.join(earth_dir, "source", "gmgsi")
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(work_dir, exist_ok=True)

    now = dt.datetime.now(dt.timezone.utc).replace(minute=0, second=0, microsecond=0)
    wanted = [now - dt.timedelta(hours=back) for back in range(hours + 1)]
    made = 0
    for when in wanted:
        stamp = f"{when:%Y%m%d%H}"
        target = os.path.join(out_dir, f"clouds-{stamp}.jpg")
        if os.path.isfile(target) and not force:
            continue
        key = hour_key(when)
        if not key:
            continue          # not published yet (about 40 minutes after the hour), or a missed hour
        nc_path = os.path.join(work_dir, f"{stamp}.nc")
        with open(nc_path, "wb") as fh:
            fh.write(fetch(f"{BUCKET}/{key}"))
        try:
            big = cloud_picture(nc_path)
        finally:
            os.remove(nc_path)
        big.save(os.path.join(out_dir, f"clouds-{stamp}-4096.jpg"), quality=84, optimize=True)
        big.resize((WIDTH, HEIGHT), Image.LANCZOS).save(target + ".part", "JPEG", quality=82, optimize=True)
        os.replace(target + ".part", target)
        made += 1
        print(f"  {stamp}: made", flush=True)

    # What there is now; drop hours past the day, and every big copy but the newest.
    oldest = f"{wanted[-1]:%Y%m%d%H}"
    stamps = []
    for name in sorted(os.listdir(out_dir)):
        match = re.fullmatch(r"clouds-(\d{10})(-4096)?\.jpg", name)
        if not match:
            continue
        if match.group(1) < oldest:
            os.remove(os.path.join(out_dir, name))
        elif not match.group(2):
            stamps.append(match.group(1))
    for stamp in stamps[:-1]:
        big = os.path.join(out_dir, f"clouds-{stamp}-4096.jpg")
        if os.path.isfile(big):
            os.remove(big)
    if not stamps:
        print("No cloud pictures yet.")
        return 1
    flows = make_motions(out_dir, stamps)

    def moment(stamp):
        return f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}T{stamp[8:]}:00:00Z"

    index = dict(CREDIT)
    index["hours"] = [{"at": moment(stamp), "file": f"clouds/clouds-{stamp}.jpg",
                       **({"flow": flows[stamp]} if stamp in flows else {})} for stamp in stamps]
    index["flow"] = {"width": FLOW_W, "height": FLOW_H, "scale": FLOW_SCALE}
    index["newest"] = {"at": moment(stamps[-1]), "file": f"clouds/clouds-{stamps[-1]}-4096.jpg"}
    index["edge_latitude"] = EDGE_LAT
    part = os.path.join(out_dir, "clouds.json.part")
    with open(part, "w", encoding="utf-8") as fh:
        json.dump(index, fh, ensure_ascii=False, indent=1)
    os.replace(part, os.path.join(out_dir, "clouds.json"))
    print(f"Clouds: {made} new, {len(stamps)} hours held, {len(flows)} motions, newest {moment(stamps[-1])}")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dir", default=DEFAULT_DIR, help="the earth-data folder")
    parser.add_argument("--hours", type=int, default=KEEP_HOURS, help="how many hours back to hold")
    parser.add_argument("--force", action="store_true", help="make every hour again")
    args = parser.parse_args()
    result = build(args.dir, args.hours, args.force)
    # Once a day, the same hourly job also fetches yesterday's sea ice and any new month (Owner, 2026-11-16:
    # no new timer). A failure there never fails the clouds.
    try:
        import build_ice
        build_ice.update(args.dir)
    except Exception as error:   # network, NSIDC late, a bad file: tomorrow's run tries again
        print(f"Sea ice not updated: {error}")
    return result


if __name__ == "__main__":
    sys.exit(main())
