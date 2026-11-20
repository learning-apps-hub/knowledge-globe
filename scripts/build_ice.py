#!/usr/bin/env python3
"""Sea ice through the years, month by month, for the time machine (Explore and Learn).

Owner approved 2026-11-16 (real from 1979, made before; "Now" = yesterday's ice).

Sources (all NOAA@NSIDC, free to use, cite the data set):
- 1979 to now, both poles: Sea Ice Index, version 4 (G02135; Fetterer, Knowles,
  Meier, Savoie, Windnagel), monthly sea ice concentration from satellites
  (passive microwave), 25 km polar stereographic grids (EPSG 3411 / 3412).
  The daily grid of yesterday is "Now".
- 1960 to 1978, Arctic only: Gridded Monthly Sea Ice Extent and Concentration,
  1850 Onward, version 2 (G10010; Walsh, Chapman, Fetterer, Stewart), made from
  old ice charts, ship and aircraft reports: one 73 MB file, 0.25 degree grid.
- 1960 to 1978, Antarctic: there is no record. Those months are MADE: the same
  month's average over 1979 to 1988, and the list says so.

Each month is one grey PNG holding the two polar caps, 1024 x 512 (about 26 KB):
rows 0-255 are 90 N to 26 N, rows 256-511 are 26 S to 90 S (0.25 degree a row,
0.35 degree a column, from 180 W). A pixel is 0 where the ice grid has no sea
(land, ice shelves, no data, outside the grid), else 1 + concentration x 254.
The viewer paints the sea from it: the day picture (August 2004) has that
August's ice in it, which is taken away where the month has none.

    ../earth-data/.venv/bin/python scripts/build_ice.py            # every month (first time: ~0.8 GB fetched)
    ../earth-data/.venv/bin/python scripts/build_ice.py --update   # new months + yesterday (the hourly clouds job)

Reads   earth-data/source/seaice/G10010_SIBT1850_V2.zip (fetched once; delete after the build)
Writes  earth-data/derived/ice/ice-<YYYYMM>.v1.png, ice-now-<YYYYMMDD>.png, ice.json
The monthly GeoTIFFs are fetched one at a time and not kept.
"""
import argparse
import datetime as dt
import json
import os
import re
import struct
import sys
import time
import urllib.error
import urllib.request
import zipfile

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DIR = os.environ.get("KG_EARTH_DIR") or os.path.join(os.path.dirname(REPO), "earth-data")
INDEX = "https://noaadata.apps.nsidc.org/NOAA/G02135"
CHARTS = "https://noaadata.apps.nsidc.org/NOAA/G10010_V2/G10010_SIBT1850_V2.zip"
AGENT = "knowledge-globe-earth-build/1.0"
VERSION = "v1"
FIRST_MADE, FIRST_REAL = 1960, 1979
MADE_FROM = range(1979, 1989)      # the Antarctic months before 1979 = the average of these years
WIDTH, HALF = 1024, 256            # a cap: 256 rows of 0.25 degree (90 to 26), 0.35 degree columns (grid: 25 km)
STEP = 0.02                        # concentration in 2% steps (the satellites measure no finer; halves the files)
EDGE = 26.0
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
CREDIT = {
    "what": "Sea ice, month by month",
    "credit": "NOAA/NSIDC Sea Ice Index v4 (Fetterer et al.; satellites); before 1979 in the Arctic, "
              "NOAA/NSIDC Gridded Monthly Sea Ice Extent and Concentration, 1850 Onward (Walsh et al.; old ice charts)",
    "licence": "Free to use, cite the data (NOAA@NSIDC)",
    "made": "Before 1979 the Arctic ice comes from old ice charts, ship and aircraft reports; the Antarctic has "
            "no record, so its ice is made: the same month's average over 1979 to 1988.",
}
# Polar stereographic on the Hughes 1980 ellipsoid (NSIDC grids): standard parallel 70, 25 km cells.
A, E = 6378273.0, 0.081816153
GRIDS = {
    "N": {"lon0": -45.0, "x0": -3850000.0, "y0": 5850000.0, "w": 304, "h": 448, "sign": 1.0},
    "S": {"lon0": 0.0, "x0": -3950000.0, "y0": 4350000.0, "w": 316, "h": 332, "sign": -1.0},
}
CELL = 25000.0


def fetch(url, tries=4):
    for attempt in range(tries):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": AGENT})
            with urllib.request.urlopen(request, timeout=120) as response:   # nosec B310 (fixed https host)
                return response.read()
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            if attempt == tries - 1:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == tries - 1:
                raise
        time.sleep(5 * (attempt + 1))
    return None


def read_tiff(data):
    """The NSIDC GeoTIFFs: one band of uncompressed 16-bit values (Pillow cannot open 16-bit palette TIFFs)."""
    if data[:4] != b"II*\x00":
        raise ValueError("not a little-endian TIFF")
    start = struct.unpack_from("<I", data, 4)[0]
    tags = {}
    for i in range(struct.unpack_from("<H", data, start)[0]):
        tag, kind, count, value = struct.unpack_from("<HHII", data, start + 2 + i * 12)
        if kind == 3 and count == 1:
            value &= 0xFFFF
        tags[tag] = (kind, count, value)
    if tags.get(259, (3, 1, 1))[2] != 1 or tags.get(258, (3, 1, 16))[2] != 16:
        raise ValueError("expected uncompressed 16-bit")
    width, height = tags[256][2], tags[257][2]

    def many(tag):
        kind, count, value = tags[tag]
        if count == 1:
            return [value]
        size = "H" if kind == 3 else "I"
        if count * (2 if kind == 3 else 4) <= 4:
            raise ValueError("strip list held inside the tag: not expected in these files")
        return list(struct.unpack_from(f"<{count}{size}", data, value))

    raw = b"".join(data[o:o + n] for o, n in zip(many(273), many(279)))
    return np.frombuffer(raw, "<u2")[: width * height].reshape(height, width)


def cap_lat_lon(pole):
    """Latitude and longitude (degrees) of every pixel of one cap."""
    rows = (np.arange(HALF) + 0.5) * (90.0 - EDGE) / HALF
    lat = 90.0 - rows if pole == "N" else -EDGE - rows
    lon = -180.0 + (np.arange(WIDTH) + 0.5) * 360.0 / WIDTH
    return np.meshgrid(lat, lon, indexing="ij")


def grid_place(pole):
    """Where every cap pixel falls on the pole's 25 km grid (fractional column, row)."""
    g = GRIDS[pole]
    lat, lon = cap_lat_lon(pole)
    s = g["sign"]
    phi = np.radians(lat * s)
    lam = np.radians((lon - g["lon0"]) * s)
    phi_c = np.radians(70.0)

    def t_of(p):
        return np.tan(np.pi / 4 - p / 2) / ((1 - E * np.sin(p)) / (1 + E * np.sin(p))) ** (E / 2)

    m_c = np.cos(phi_c) / np.sqrt(1 - E * E * np.sin(phi_c) ** 2)
    rho = A * m_c * t_of(phi) / t_of(phi_c)
    x = s * rho * np.sin(lam)
    y = -s * rho * np.cos(lam)
    col = (x - g["x0"]) / CELL - 0.5
    row = (g["y0"] - y) / CELL - 0.5
    return col, row


PLACES = {}


def to_cap(grid, pole):
    """One pole's grid -> its cap: concentration 0..1 and whether the grid holds sea there."""
    if pole not in PLACES:
        PLACES[pole] = grid_place(pole)
    col, row = PLACES[pole]
    h, w = grid.shape
    sea = grid <= 1000
    conc = np.where(grid == 2510, 1.0, np.where(sea, grid / 1000.0, 0.0))   # the hole round the pole: ice
    sea = sea | (grid == 2510)
    c0, r0 = np.floor(col).astype(int), np.floor(row).astype(int)
    fx, fy = col - c0, row - r0
    total = np.zeros(col.shape)
    weight = np.zeros(col.shape)
    for dr, dc, k in ((0, 0, (1 - fx) * (1 - fy)), (0, 1, fx * (1 - fy)), (1, 0, (1 - fx) * fy), (1, 1, fx * fy)):
        r, c = r0 + dr, c0 + dc
        inside = (r >= 0) & (r < h) & (c >= 0) & (c < w)
        rr, cc = np.clip(r, 0, h - 1), np.clip(c, 0, w - 1)
        k = np.where(inside & sea[rr, cc], k, 0.0)
        total += k * conc[rr, cc]
        weight += k
    valid = weight > 0.5
    return np.where(valid, total / np.maximum(weight, 1e-9), 0.0), valid


def encode(conc, valid):
    conc = np.round(np.clip(conc, 0, 1) / STEP) * STEP
    return np.where(valid, 1 + np.round(conc * 254), 0).astype(np.uint8)


def decode(picture):
    a = picture.astype(np.float32)
    return np.where(a > 0, (a - 1) / 254.0, 0.0), a > 0


def save(path, north, south):
    from PIL import Image
    part = path + ".part"
    Image.fromarray(np.vstack([north, south]), "L").save(part, "PNG", optimize=True)
    os.replace(part, path)
    return os.path.getsize(path)


def nsidc(kind, pole, year, month, day=None):
    """One satellite grid as a cap, or None when NSIDC has none for it."""
    if kind == "monthly":
        url = f"{INDEX}/{'north' if pole == 'N' else 'south'}/monthly/geotiff/{month:02d}_{MONTHS[month - 1]}/" \
              f"{pole}_{year}{month:02d}_concentration_v4.0.tif"
    else:
        url = f"{INDEX}/{'north' if pole == 'N' else 'south'}/daily/geotiff/{year}/{month:02d}_{MONTHS[month - 1]}/" \
              f"{pole}_{year}{month:02d}{day:02d}_concentration_v4.0.tif"
    data = fetch(url)
    return None if data is None else encode(*to_cap(read_tiff(data), pole))


def charts_caps(earth_dir):
    """The old-chart Arctic (G10010), 1960-1978: {(year, month): north cap}."""
    import h5py
    source = os.path.join(earth_dir, "source", "seaice")
    os.makedirs(source, exist_ok=True)
    zipped = os.path.join(source, "G10010_SIBT1850_V2.zip")
    if not os.path.isfile(zipped):
        print("fetching the old ice charts (73 MB)", flush=True)
        data = fetch(CHARTS)
        with open(zipped + ".part", "wb") as fh:
            fh.write(data)
        os.replace(zipped + ".part", zipped)
    nc = os.path.join(source, "G10010_sibt1850_v2.0.nc")
    if not os.path.isfile(nc):
        with zipfile.ZipFile(zipped) as z:
            z.extract("G10010_sibt1850_v2.0.nc", source)
    caps = {}
    with h5py.File(nc, "r") as f:
        land = f["LandRegion_mask"][:] == 20
        # Its rows are 89.875 N down to 30.125 N, like ours; its columns run from 0 E: turn to 180 W first.
        lon = -180.0 + (np.arange(WIDTH) + 0.5) * 360.0 / WIDTH
        cols = np.floor(np.mod(lon, 360.0) / 0.25).astype(int)
        for year in range(FIRST_MADE, FIRST_REAL):
            for month in range(1, 13):
                grid = f["seaice_conc"][(year - 1850) * 12 + month - 1]
                sea = (grid <= 100) & ~land
                north = np.zeros((HALF, WIDTH), np.uint8)
                north[: grid.shape[0]] = encode(grid[:, cols] / 100.0, sea[:, cols])
                caps[(year, month)] = north
    return caps


def made_south(out_dir):
    """The Antarctic before 1979: each month's 1979-1988 average, as a cap."""
    from PIL import Image
    caps = {}
    for month in range(1, 13):
        total, count, seen = np.zeros((HALF, WIDTH)), 0, np.zeros((HALF, WIDTH), bool)
        for year in MADE_FROM:
            path = os.path.join(out_dir, f"ice-{year}{month:02d}.{VERSION}.png")
            if not os.path.isfile(path):
                continue
            conc, valid = decode(np.asarray(Image.open(path))[HALF:])
            total += conc
            seen |= valid
            count += 1
        if count:
            caps[month] = encode(total / count, seen)
    return caps


def months_to(today):
    """Every month from 1979 to last month."""
    year, month = FIRST_REAL, 1
    while (year, month) < (today.year, today.month):
        yield year, month
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def build_real(out_dir, today, update):
    """The satellite months not built yet. With --update only the newest few are looked for."""
    wanted = list(months_to(today))
    if update:
        wanted = wanted[-4:]
    made = 0
    for year, month in wanted:
        path = os.path.join(out_dir, f"ice-{year}{month:02d}.{VERSION}.png")
        if os.path.isfile(path):
            continue
        north = nsidc("monthly", "N", year, month)
        south = nsidc("monthly", "S", year, month)
        if north is None or south is None:
            continue           # not published yet, or a month the satellites missed (Dec 1987, Jan 1988)
        save(path, north, south)
        made += 1
        print(f"  {year}-{month:02d}", flush=True)
    return made


def build_old(out_dir, earth_dir):
    south = made_south(out_dir)
    if len(south) < 12:
        print("The 1979-1988 months are needed first (for the made Antarctic).")
        return 0
    made = 0
    for (year, month), north in sorted(charts_caps(earth_dir).items()):
        path = os.path.join(out_dir, f"ice-{year}{month:02d}.{VERSION}.png")
        if not os.path.isfile(path):
            save(path, north, south[month])
            made += 1
    return made


def build_now(out_dir, today):
    """Yesterday's ice (or the newest day of the last week) as "Now"; older days are deleted."""
    for back in range(1, 8):
        day = today - dt.timedelta(days=back)
        path = os.path.join(out_dir, f"ice-now-{day:%Y%m%d}.png")
        if os.path.isfile(path):
            break
        north = nsidc("daily", "N", day.year, day.month, day.day)
        south = nsidc("daily", "S", day.year, day.month, day.day)
        if north is not None and south is not None:
            save(path, north, south)
            print(f"  now = {day:%Y-%m-%d}", flush=True)
            break
    nows = sorted(name for name in os.listdir(out_dir) if re.fullmatch(r"ice-now-\d{8}\.png", name))
    for name in nows[:-1]:
        os.remove(os.path.join(out_dir, name))
    return nows[-1] if nows else None


def write_index(out_dir, now_name):
    months = []
    for name in sorted(os.listdir(out_dir)):
        match = re.fullmatch(r"ice-(\d{4})(\d{2})\." + VERSION + r"\.png", name)
        if match:
            year, month = int(match.group(1)), int(match.group(2))
            entry = {"year": year, "month": month, "file": f"ice/{name}"}
            if year < FIRST_REAL:
                entry["made"] = True
            months.append(entry)
    index = dict(CREDIT, first_real=FIRST_REAL, edge=EDGE, months=months)
    if now_name:
        stamp = now_name[8:16]
        index["now"] = {"day": f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:]}", "file": f"ice/{now_name}"}
    part = os.path.join(out_dir, "ice.json.part")
    with open(part, "w", encoding="utf-8") as fh:
        json.dump(index, fh, indent=1)
    os.replace(part, os.path.join(out_dir, "ice.json"))
    return len(months)


def build(earth_dir, update=False):
    out_dir = os.path.join(earth_dir, "derived", "ice")
    os.makedirs(out_dir, exist_ok=True)
    today = dt.datetime.now(dt.timezone.utc).date()
    real = build_real(out_dir, today, update)
    old = 0 if update else build_old(out_dir, earth_dir)
    now_name = build_now(out_dir, today)
    count = write_index(out_dir, now_name)
    size = sum(os.path.getsize(os.path.join(out_dir, n)) for n in os.listdir(out_dir)) / 1e6
    print(f"Sea ice: {real} new satellite months, {old} old/made, {count} months held ({size:.1f} MB), now {now_name}")
    return 0


def update(earth_dir):
    """Once a day at most (from the hourly clouds job): new months and yesterday's ice."""
    stamp = os.path.join(earth_dir, "derived", "ice", "ice.json")
    if os.path.isfile(stamp) and time.time() - os.path.getmtime(stamp) < 20 * 3600:
        return 0
    return build(earth_dir, update=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dir", default=DEFAULT_DIR, help="the earth-data folder")
    parser.add_argument("--update", action="store_true", help="only new months and yesterday")
    args = parser.parse_args()
    return build(args.dir, update=args.update)


if __name__ == "__main__":
    sys.exit(main())
