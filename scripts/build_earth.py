#!/usr/bin/env python3
"""Fetch and derive the realistic Earth's picture layers (Explore preview).

The big files are NOT in git. They live in a server data folder that both the
dev and prod trees read (`KG_EARTH_DIR`, default `../earth-data` beside the
repo). This script is the only thing that writes there:

    earth-data/source/    one-time downloads, kept for good
    earth-data/derived/   what the app serves at /earth/<file>

Run it once on a new server, and again when a layer is added:

    python3 -m venv ../earth-data/.venv
    ../earth-data/.venv/bin/pip install Pillow numpy
    ../earth-data/.venv/bin/python scripts/build_earth.py

Fetching needs only the standard library; deriving needs Pillow and numpy
(build tools, not app dependencies: the app itself stays stdlib-only).

Every source is public domain or free to use. Each layer's credit and year are written to
`derived/manifest.json`, which the app shows beside the globe.
"""
import argparse
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DIR = os.environ.get("KG_EARTH_DIR") or os.path.join(os.path.dirname(REPO), "earth-data")

# Bump when a derived file's recipe changes: the file name changes with it, so
# browsers that cached the old one for good fetch the new one.
VERSION = "v1"

NASA = "https://assets.science.nasa.gov/content/dam/science/esd/eo/images"
EOIMG = "https://eoimages.gsfc.nasa.gov/images/imagerecords"
NE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson"

SOURCES = {
    "day": {
        "file": "bmng-200408-topo-bathy-21600.jpg",
        "urls": [
            f"{NASA}/bmng/bmng-topography-bathymetry/august/world.topo.bathy.200408.3x21600x10800.jpg",
            f"{EOIMG}/73000/73776/world.topo.bathy.200408.3x21600x10800.jpg",
        ],
        "credit": "NASA Earth Observatory, Blue Marble: Next Generation (R. Stöckli)",
        "what": "Land, sea floor and ice, cloud-free",
        "years": "August 2004",
        "licence": "Public domain (NASA)",
    },
    "night": {
        "file": "black-marble-2016-3km.jpg",
        "urls": [
            f"{NASA}/imagerecords/144000/144898/BlackMarble_2016_3km.jpg",
            f"{EOIMG}/144000/144898/BlackMarble_2016_3km.jpg",
        ],
        "credit": "NASA Earth Observatory, Black Marble (J. Stevens, M. Román; Suomi NPP VIIRS)",
        "what": "City lights at night",
        "years": "2016",
        "licence": "Public domain (NASA)",
    },
    "clouds": {
        "file": "clouds-2002-8192.tif",
        "urls": [
            f"{EOIMG}/57000/57747/cloud_combined_8192.tif",
            # NASA's own file, as kept by the Internet Archive, for when the NASA host is unreachable.
            "https://web.archive.org/web/20231230035002id_/"
            "https://eoimages.gsfc.nasa.gov/images/imagerecords/57000/57747/cloud_combined_8192.tif",
        ],
        "credit": "NASA Earth Observatory, Blue Marble clouds (R. Stöckli; MODIS)",
        "what": "One real day of cloud cover",
        "years": "2001–2002 composite",
        "licence": "Public domain (NASA)",
    },
    "land": {
        "file": "ne_10m_land.geojson",
        "urls": [f"{NE}/ne_10m_land.geojson"],
        "credit": "Natural Earth",
        "what": "Coastlines (which parts are sea)",
        "years": "v5.1.2",
        "licence": "Public domain (Natural Earth)",
    },
    "lakes": {
        "file": "ne_10m_lakes.geojson",
        "urls": [f"{NE}/ne_10m_lakes.geojson"],
    },
    "shelves": {
        "file": "ne_10m_antarctic_ice_shelves_polys.geojson",
        "urls": [f"{NE}/ne_10m_antarctic_ice_shelves_polys.geojson"],
    },
    "stars": {
        "file": "bsc5-catalog.gz",
        "urls": [
            "https://cdsarc.cds.unistra.fr/ftp/V/50/catalog.gz",
            # The same CDS file on its Harvard mirror (the Strasbourg host times out from this server).
            "https://vizier.cfa.harvard.edu/ftp/cats/V/50/catalog.gz",
        ],
        "credit": "Yale Bright Star Catalogue, 5th edition (D. Hoffleit, W. H. Warren Jr.), via CDS",
        "what": "Every star the eye can see (to magnitude 6.5): place, brightness, colour",
        "years": "Positions for the year 2000",
        "licence": "Free to use (CDS / NASA ADC)",
    },
    "moon": {
        "file": "lroc-color-poles-2k.tif",
        "urls": [
            "https://svs.gsfc.nasa.gov/vis/a000000/a004700/a004720/lroc_color_poles_2k.tif",
            "https://web.archive.org/web/2023id_/"
            "https://svs.gsfc.nasa.gov/vis/a000000/a004700/a004720/lroc_color_poles_2k.tif",
        ],
        "credit": "NASA Scientific Visualization Studio, CGI Moon Kit (E. Wright; LRO camera)",
        "what": "The Moon's surface",
        "years": "LRO, 2009 onward",
        "licence": "Public domain (NASA)",
    },
}

SEA_W, SEA_H = 720, 360   # the sea-room grid the page reads: half a degree a cell
SEA_UNIT = 0.25           # one grey level = a quarter of a degree from the nearest land


def log(message):
    print(message, flush=True)


# ---------- fetch ----------

def _remote_size(url):
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "earth-layer-build/1.0"})
    with urllib.request.urlopen(request, timeout=40) as response:  # nosec B310 - fixed https sources
        return int(response.headers.get("Content-Length") or 0)


def _download(url, target):
    """Download with resume: a dropped connection carries on where it stopped."""
    part = target + ".part"
    total = _remote_size(url)
    for attempt in range(1, 9):
        have = os.path.getsize(part) if os.path.exists(part) else 0
        if total and have >= total:
            break
        headers = {"User-Agent": "earth-layer-build/1.0"}
        if have:
            headers["Range"] = f"bytes={have}-"
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=60) as response:  # nosec B310 - fixed https sources
                if have and response.status != 206:
                    have = 0  # the host ignored the range: start again
                with open(part, "ab" if have else "wb") as out:
                    while True:
                        chunk = response.read(1 << 20)
                        if not chunk:
                            break
                        out.write(chunk)
            if not total:
                break
        except (urllib.error.URLError, OSError, ValueError) as error:
            log(f"    attempt {attempt}: {error}")
            time.sleep(min(30, 3 * attempt))
    size = os.path.getsize(part) if os.path.exists(part) else 0
    if not size or (total and size != total):
        raise OSError(f"incomplete download ({size} of {total} bytes)")
    os.replace(part, target)


def fetch(source_dir):
    os.makedirs(source_dir, exist_ok=True)
    for name, source in SOURCES.items():
        target = os.path.join(source_dir, source["file"])
        if os.path.exists(target) and os.path.getsize(target) > 0:
            log(f"  have   {source['file']}")
            continue
        for url in source["urls"]:
            log(f"  fetch  {source['file']}  <-  {url.split('/')[2]}")
            try:
                _download(url, target)
                break
            except (urllib.error.URLError, OSError, ValueError) as error:
                log(f"    failed: {error}")
        else:
            raise SystemExit(f"Could not fetch the '{name}' source from any of its addresses.")


# ---------- derive ----------

def _rings(path):
    """Every polygon in a GeoJSON file as (outer ring, [holes]), in degrees."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    for feature in data["features"]:
        geometry = feature["geometry"]
        if not geometry:
            continue
        polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
        for polygon in polygons:
            yield polygon[0], polygon[1:]


def _land_mask(source_dir, width, height):
    """255 where there is land (or shelf ice), 0 where there is water."""
    from PIL import Image, ImageDraw

    def to_px(ring):
        return [((lon + 180.0) / 360.0 * width, (90.0 - lat) / 180.0 * height) for lon, lat, *_ in ring]

    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    for name, fill in (("land", 255), ("shelves", 255), ("lakes", 0)):
        for outer, holes in _rings(os.path.join(source_dir, SOURCES[name]["file"])):
            draw.polygon(to_px(outer), fill=fill)
            for hole in holes:
                draw.polygon(to_px(hole), fill=255 - fill)
    return mask


def _sea_room(land_small):
    """For each cell, how far the nearest land is, in degrees along the globe."""
    import numpy as np

    land = np.asarray(land_small) > 0
    height, width = land.shape
    lat = np.radians(90.0 - (np.arange(height) + .5) * 180.0 / height)
    lon = np.radians((np.arange(width) + .5) * 360.0 / width - 180.0)
    # Only land cells that touch water can be the nearest land to anything.
    edge = land & ~(np.roll(land, 1, 1) & np.roll(land, -1, 1)
                    & np.vstack([land[:1], land[:-1]]) & np.vstack([land[1:], land[-1:]]))
    rows, cols = np.nonzero(edge)
    coast = np.stack([np.cos(lat[rows]) * np.cos(lon[cols]), np.cos(lat[rows]) * np.sin(lon[cols]),
                      np.sin(lat[rows])], 1).astype(np.float32)
    room = np.zeros((height, width), np.float32)
    cos_lon, sin_lon = np.cos(lon), np.sin(lon)
    for row in range(height):
        cells = np.stack([math.cos(lat[row]) * cos_lon, math.cos(lat[row]) * sin_lon,
                          np.full(width, math.sin(lat[row]))], 1).astype(np.float32)
        nearest = (cells @ coast.T).max(1)
        room[row] = np.degrees(np.arccos(np.clip(nearest, -1, 1)))
    room[land] = 0
    return room


def derive(source_dir, out_dir, parts=("earth", "sky")):
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        raise SystemExit("Deriving needs Pillow and numpy: see the top of this file.")
    Image.MAX_IMAGE_PIXELS = None
    os.makedirs(out_dir, exist_ok=True)
    files = {}

    def src(name):
        return os.path.join(source_dir, SOURCES[name]["file"])

    def save(image, name, **options):
        path = os.path.join(out_dir, name)
        image.save(path, **options)
        log(f"  wrote  {name}  {os.path.getsize(path) / 1e6:.2f} MB")
        return name

    if "sky" in parts:
        files.update(_derive_sky(source_dir, out_dir, save, Image))
    if "earth" not in parts:
        _write_manifest(out_dir, files)
        return

    # Day colour. 4K is the light version served everywhere; 8K is kept for
    # desktop zoom (Owner's decision, 2026-11-12).
    day = Image.open(src("day"))
    day.draft("RGB", (10800, 5400))
    day = day.convert("RGB")
    for width in (8192, 4096):
        day = day.resize((width, width // 2), Image.LANCZOS)
        files[f"day{width}"] = save(day, f"day-{width}.{VERSION}.jpg", quality=88, optimize=True, progressive=True)
    del day

    # Night lights: only the light itself. The source also paints faint land
    # and sea so it can stand alone; here the day picture does that job.
    night = Image.open(src("night")).convert("RGB").resize((4096, 2048), Image.LANCZOS)
    rgb = np.asarray(night, np.float32)
    glow = np.maximum(rgb[..., 0], rgb[..., 1]) - rgb[..., 2] * .92 - 5.0
    lights = np.clip(glow / 150.0, 0, 1) ** .8
    del night, rgb, glow

    clouds = Image.open(src("clouds")).convert("L").resize((4096, 2048), Image.LANCZOS)
    cloud = np.asarray(clouds, np.float32) / 255.0
    del clouds

    # Water, for the sun's glint and for keeping pins off the land. Drawn big
    # and shrunk, so the coast is smooth.
    land_big = _land_mask(source_dir, 8192, 4096)
    water = 1.0 - np.asarray(land_big.resize((4096, 2048), Image.LANCZOS), np.float32) / 255.0

    # One picture, three jobs: red = city lights, green = clouds, blue = water.
    # A phone then holds two big pictures in memory, not four.
    pack = np.stack([lights, cloud, water], 2)
    pack_image = Image.fromarray((np.clip(pack, 0, 1) * 255 + .5).astype(np.uint8), "RGB")
    files["pack4096"] = save(pack_image, f"pack-4096.{VERSION}.jpg", quality=90, subsampling=0, optimize=True)
    del pack, pack_image, lights, cloud, water

    # Sea room: how far each half-degree cell is from the nearest land. A cell
    # counts as land if any land touches it, so a pin never rests on a coast.
    land_small = land_big.resize((SEA_W * 4, SEA_H * 4), Image.NEAREST).reduce(4)
    land_any = Image.fromarray((np.asarray(land_small) > 0).astype(np.uint8) * 255, "L")
    room = _sea_room(land_any)
    sea = Image.fromarray(np.clip(np.round(room / SEA_UNIT), 0, 255).astype(np.uint8), "L")
    files["sea"] = save(sea, f"sea-{SEA_W}.{VERSION}.png", optimize=True)

    _write_manifest(out_dir, files)


LAYERS = ("day", "night", "clouds", "land", "stars", "moon")


def _write_manifest(out_dir, files):
    """Merge into the existing manifest, so deriving one part keeps the others."""
    path = os.path.join(out_dir, "manifest.json")
    old = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            old = json.load(fh)
    manifest = {
        "version": VERSION,
        "files": {**old.get("files", {}), **files},
        "sea": {"width": SEA_W, "height": SEA_H, "unit_degrees": SEA_UNIT},
        "layers": [
            {key: SOURCES[name][key] for key in ("what", "credit", "years", "licence")}
            for name in LAYERS
        ],
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    log("  wrote  manifest.json")


def _derive_sky(source_dir, out_dir, save, Image):
    """The stars as a small list, and the Moon's surface picture."""
    import gzip
    files = {}

    # Yale Bright Star Catalogue, fixed-width (CDS V/50 ReadMe). Each star is
    # four numbers: right ascension and declination in degrees (J2000),
    # visual magnitude, B-V colour (0.6 = Sun-like when the catalogue has none).
    stars = []
    with gzip.open(os.path.join(source_dir, SOURCES["stars"]["file"]), "rt", encoding="ascii") as fh:
        for line in fh:
            line = line.rstrip("\n").ljust(114)
            if not line[75:77].strip() or not line[102:107].strip():
                continue   # a few entries are novae or galaxies with no position or magnitude
            ra = (int(line[75:77]) + int(line[77:79]) / 60 + float(line[79:83]) / 3600) * 15
            dec = int(line[84:86]) + int(line[86:88]) / 60 + int(line[88:90]) / 3600
            if line[83] == "-":
                dec = -dec
            bv = float(line[109:114]) if line[109:114].strip() else 0.6
            stars.append([round(ra, 3), round(dec, 3), float(line[102:107]), bv])
    stars.sort(key=lambda star: star[2])   # brightest first, so a phone can stop early
    name = f"stars.{VERSION}.json"
    with open(os.path.join(out_dir, name), "w", encoding="utf-8") as fh:
        json.dump({"fields": ["ra", "dec", "mag", "bv"], "stars": stars}, fh, separators=(",", ":"))
    log(f"  wrote  {name}  {len(stars)} stars  {os.path.getsize(os.path.join(out_dir, name)) / 1e6:.2f} MB")
    files["stars"] = name

    # The Moon is small on screen: 2K is plenty.
    moon = Image.open(os.path.join(source_dir, SOURCES["moon"]["file"])).convert("RGB")
    moon = moon.resize((2048, 1024), Image.LANCZOS)
    files["moon"] = save(moon, f"moon-2048.{VERSION}.jpg", quality=86, optimize=True, progressive=True)
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--data", default=DEFAULT_DIR, help=f"data folder (default: {DEFAULT_DIR})")
    parser.add_argument("--only", choices=("fetch", "derive", "sky"),
                        help="run one half; 'sky' re-derives only the stars and the Moon")
    args = parser.parse_args()
    source_dir = os.path.join(args.data, "source")
    out_dir = os.path.join(args.data, "derived")
    if args.only not in ("derive", "sky"):
        log(f"Sources -> {source_dir}")
        fetch(source_dir)
    if args.only != "fetch":
        log(f"Derived -> {out_dir}")
        derive(source_dir, out_dir, ("sky",) if args.only == "sky" else ("earth", "sky"))
    total = sum(os.path.getsize(os.path.join(root, name))
                for root, _, names in os.walk(args.data) if ".venv" not in root for name in names)
    log(f"Earth data on disk: {total / 1e9:.2f} GB (budget: 6 GB)")


if __name__ == "__main__":
    sys.exit(main())
