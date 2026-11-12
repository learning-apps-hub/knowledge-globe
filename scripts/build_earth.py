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
    "countries": {
        "file": "ne_10m_admin_0_countries.geojson",
        "urls": [f"{NE}/ne_10m_admin_0_countries.geojson"],
        "credit": "Natural Earth",
        "what": "Countries, continents, oceans, the named lines, capitals and the biggest cities",
        "years": "v5.1.2",
        "licence": "Public domain (Natural Earth)",
    },
    "places": {
        "file": "ne_10m_populated_places_simple.geojson",
        "urls": [f"{NE}/ne_10m_populated_places_simple.geojson"],
        "credit": "Natural Earth",
        "what": "Capitals and the biggest cities",
        "years": "v5.1.2",
        "licence": "Public domain (Natural Earth)",
    },
    "lines": {
        "file": "ne_10m_geographic_lines.geojson",
        "urls": [f"{NE}/ne_10m_geographic_lines.geojson"],
        "credit": "Natural Earth",
        "what": "The Equator, the Tropics, the Polar Circles and the International Date Line",
        "years": "v5.1.2",
        "licence": "Public domain (Natural Earth)",
    },
    "oceans": {
        "file": "ne_10m_geography_marine_polys.geojson",
        "urls": [f"{NE}/ne_10m_geography_marine_polys.geojson"],
        "credit": "Natural Earth",
        "what": "The five oceans",
        "years": "v5.1.2",
        "licence": "Public domain (Natural Earth)",
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


def derive(source_dir, out_dir, parts=("earth", "sky", "geo")):
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
    if "geo" in parts:
        files.update(_derive_geo(source_dir, out_dir, save, Image))
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


LAYERS = ("day", "night", "clouds", "land", "countries", "stars", "moon")


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


# ---------- geography: countries, oceans, lines, cities ----------

AREA_W, AREA_H = 4096, 2048
TINY_PIXELS = 64      # an area drawn smaller than this gets a ring marker as well as its outline
OCEANS = [(1, "Pacific Ocean", ("North Pacific Ocean", "South Pacific Ocean")),
          (2, "Atlantic Ocean", ("North Atlantic Ocean", "South Atlantic Ocean")),
          (3, "Indian Ocean", ("INDIAN OCEAN",)),
          (4, "Southern Ocean", ("SOUTHERN OCEAN",)),
          (5, "Arctic Ocean", ("Arctic Ocean",))]
CONTINENTS = ("Africa", "Antarctica", "Asia", "Europe", "North America", "Oceania", "South America")

# Places that have their own government on the ground but are not UN members or observers (Owner's
# "Taiwan rule", APPROVALS #88 B): each lights up as its own area and its card says its status in one
# plain sentence. Wording for Owner to read, 2026-11-13; only Taiwan's was agreed word for word.
OWN_GOVERNMENT = {
    "Taiwan": "Has its own government. China claims it as part of China. The UN and most countries do not "
              "recognise it as a separate country.",
    "Kosovo": "Has its own government and declared independence from Serbia in 2008. Serbia does not accept "
              "this. Some countries recognise it and some do not.",
    "N. Cyprus": "Has its own government in the north of Cyprus. Only Turkey recognises it. Cyprus and the UN "
                 "treat the whole island as one country.",
    "Somaliland": "Has run its own government since 1991. Somalia claims it as part of Somalia. The UN does not "
                  "list it as a country.",
    "W. Sahara": "Morocco governs most of it and the Sahrawi Arab Democratic Republic the rest. Both claim it all. "
                 "The UN lists it as a territory whose future is not settled.",
}
UN_OBSERVER_OR_ODD = {"Palestine", "Israel", "Vatican", "Norway"}   # sovereign, though a field says otherwise


def _slug(text):
    import re
    import unicodedata
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _area_status(props):
    """(status, sentence). status: country | own-government | territory | disputed | unowned."""
    name, admin, sovereign, kind = props["NAME"], props["ADMIN"], props["SOVEREIGNT"], props["TYPE"]
    if name in OWN_GOVERNMENT:
        return "own-government", OWN_GOVERNMENT[name]
    if name == "Antarctica":
        return "unowned", "No country owns it. A treaty sets it aside for peace and science."
    if name in UN_OBSERVER_OR_ODD or (kind in ("Sovereign country", "Sovereignty", "Country") and admin == sovereign):
        return "country", ""
    if kind in ("Country", "Dependency") and admin != sovereign:
        return "territory", f"Belongs to {sovereign}."
    if kind == "Lease":
        return "disputed", f"Land leased by {sovereign}'s lessee; it is not a country."
    if kind == "Disputed":
        return "disputed", f"Governed by {sovereign}. Its status is disputed."
    return "disputed", "No country's claim to this area is settled."


def _fill(draw, geometry, value, to_px):
    polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
    for polygon in polygons:
        draw.polygon(to_px(polygon[0]), fill=value)
        for hole in polygon[1:]:
            draw.polygon(to_px(hole), fill=0)


def _spread_oceans(seed, water, np):
    """Natural Earth's ocean polygons are rough label shapes, not the whole sea. Grow each ocean outwards over
    every open-water pixel it can reach (land stops it), so seas and gulfs join the ocean they open into.
    Water that no ocean reaches (the Mediterranean, the Black Sea, the Caspian) stays unclaimed.
    """
    step = 2                                         # grow at half size: fast, and borders stay where the seeds met
    label = seed[::step, ::step].copy()
    free = water[::step, ::step]
    label[~free] = 0
    reach = 1
    for _ in range(6000):
        grown = label.copy()
        for axis in (0, 1):
            for shift in [d for d in range(-reach, reach + 1) if d]:
                near = np.roll(label, shift, axis)
                if axis == 0 and shift > 0:          # the poles do not wrap round
                    near[:shift] = 0
                elif axis == 0:
                    near[shift:] = 0
                take = (grown == 0) & free & (near > 0)
                grown[take] = near[take]
        if np.array_equal(grown, label):
            if reach == 1:                           # then once more, allowed to hop a narrow strait of land
                reach = 3
                continue
            break
        label = grown
    full = np.repeat(np.repeat(label, step, 0), step, 1)
    out = seed.copy()
    out[(out == 0) & water & (full > 0)] = full[(out == 0) & water & (full > 0)]
    return out


def _derive_geo(source_dir, out_dir, save, Image):
    """The area-code picture, and one small JSON of every geography fact the app needs."""
    import numpy as np
    from PIL import ImageDraw

    def load(name):
        with open(os.path.join(source_dir, SOURCES[name]["file"]), encoding="utf-8") as fh:
            return json.load(fh)["features"]

    def to_px(ring):
        return [((lon + 180.0) / 360.0 * AREA_W, (90.0 - lat) / 180.0 * AREA_H) for lon, lat, *_ in ring]

    # Countries: code = position in a fixed order (1..), so the picture and the JSON always agree.
    features = sorted(load("countries"), key=lambda f: (f["properties"]["ADM0_A3"], f["properties"]["NAME"]))
    code = Image.new("I", (AREA_W, AREA_H), 0)
    draw = ImageDraw.Draw(code)
    order = sorted(range(len(features)), key=lambda i: -_geom_area(features[i]["geometry"]))
    for i in order:                                  # big first, so an enclave drawn later stays on top
        _fill(draw, features[i]["geometry"], i + 1, to_px)
    codes = np.asarray(code, np.int32)

    # Oceans: five, each merged from Natural Earth's northern and southern halves.
    sea = Image.new("L", (AREA_W, AREA_H), 0)
    sea_draw = ImageDraw.Draw(sea)
    marine = {f["properties"]["name"]: f for f in load("oceans") if f["properties"]["featurecla"] == "ocean"}
    for number, _, names in OCEANS:
        for name in names:
            _fill(sea_draw, marine[name]["geometry"], number, to_px)
    seas = np.asarray(sea, np.uint8).copy()
    lon_grid = (np.arange(AREA_W) + .5) * 360.0 / AREA_W - 180.0
    lat_grid = 90.0 - (np.arange(AREA_H) + .5) * 180.0 / AREA_H
    seas[(seas == 3) & (lon_grid[None, :] > 147.0) & (lat_grid[:, None] < -10.0)] = 1   # Coral and Tasman seas: Pacific
    seas = _spread_oceans(seas, codes == 0, np)

    rgb = np.stack([codes & 255, codes >> 8, seas], 2).astype(np.uint8)
    areas_file = save(Image.fromarray(rgb, "RGB"), f"areas-{AREA_W}.{VERSION}.png", optimize=True)
    gap = float(np.mean((codes == 0) & (seas == 0)))
    log(f"  areas: {int(codes.max())} codes, {gap * 100:.1f}% of the picture is neither country nor ocean")

    pixels = np.bincount(codes.ravel(), minlength=len(features) + 1)
    areas, by_a3 = [], {}
    for i, feature in enumerate(features):
        props = feature["properties"]
        status, sentence = _area_status(props)
        continent = props["CONTINENT"] if props["CONTINENT"] in CONTINENTS else None
        area = {
            "code": i + 1, "id": _slug(props["ADM0_A3"] + "-" + props["NAME"]) if props["ADM0_A3"] in by_a3
            else _slug(props["NAME_EN"] or props["NAME"]),
            "name": props["NAME_EN"] or props["NAME"], "sovereign": props["SOVEREIGNT"], "status": status,
            "sentence": sentence, "continent": continent, "population": props["POP_EST"],
            "label": [round(props["LABEL_X"], 3), round(props["LABEL_Y"], 3)],
            "tiny": int(pixels[i + 1]) < TINY_PIXELS,
        }
        by_a3.setdefault(props["ADM0_A3"], area)
        areas.append(area)
    ids = [a["id"] for a in areas]
    assert len(ids) == len(set(ids)), "area ids must be unique"

    # Cities: every national capital, plus any city over five million people.
    places = []
    for feature in load("places"):
        props = feature["properties"]
        capital = props["featurecla"] in ("Admin-0 capital", "Admin-0 capital alt")
        if not (capital or props["pop_max"] >= 5_000_000):
            continue
        lon, lat = props["longitude"], props["latitude"]
        col = min(AREA_W - 1, int((lon + 180.0) / 360.0 * AREA_W))
        row = min(AREA_H - 1, int((90.0 - lat) / 180.0 * AREA_H))
        owner = int(codes[row, col]) or (by_a3[props["adm0_a3"]]["code"] if props["adm0_a3"] in by_a3 else 0)
        places.append({"name": props["name"], "lon": round(lon, 4), "lat": round(lat, 4),
                       "population": props["pop_max"], "capital": capital, "area": owner})
    places.sort(key=lambda p: (-p["population"], p["name"]))
    log(f"  places: {len(places)} ({sum(p['capital'] for p in places)} capitals)")

    # Lines: the five circles of latitude are exact numbers; the Date Line is the real, bending one.
    lines = {}
    for feature in load("lines"):
        props, geometry = feature["properties"], feature["geometry"]
        if geometry["type"] == "LineString":
            lines[_slug(props["name"])] = {"name": props["name"], "lat": round(geometry["coordinates"][0][1], 4)}
        else:
            parts = [[[round(x, 3), round(y, 3)] for x, y, *_ in part] for part in geometry["coordinates"]]
            lines["date-line"] = {"name": props["name"], "paths": parts}

    # How much of each continent's land lies north and east of the Equator and the Prime Meridian (by true area).
    weight = np.cos(np.radians(90.0 - (np.arange(AREA_H) + .5) * 180.0 / AREA_H))[:, None] * np.ones((1, AREA_W))
    north = (np.arange(AREA_H) < AREA_H // 2)[:, None] * np.ones((1, AREA_W), bool)
    east = (np.arange(AREA_W) >= AREA_W // 2)[None, :] * np.ones((AREA_H, 1), bool)
    continents = []
    for name in CONTINENTS:
        member = np.zeros(len(areas) + 1, bool)
        for area in areas:
            member[area["code"]] = area["continent"] == name
        land = member[codes]
        total = float((weight * land).sum())
        continents.append({"name": name, "north": round(float((weight * land * north).sum()) / total, 3),
                           "east": round(float((weight * land * east).sum()) / total, 3)})

    geo = {"version": VERSION, "size": [AREA_W, AREA_H], "areas": areas, "places": places, "lines": lines,
           "oceans": [{"number": n, "name": label} for n, label, _ in OCEANS], "continents": continents}
    path = os.path.join(out_dir, f"geo.{VERSION}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(geo, fh, ensure_ascii=False, separators=(",", ":"))
    log(f"  wrote  geo.{VERSION}.json  {os.path.getsize(path) / 1e3:.0f} KB")
    return {"areas": areas_file, "geo": f"geo.{VERSION}.json"}


def _geom_area(geometry):
    """Rough size in square degrees (outer rings only): just for deciding which area is drawn first."""
    polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
    total = 0.0
    for polygon in polygons:
        ring = polygon[0]
        total += abs(sum(x1 * y2 - x2 * y1 for (x1, y1, *_), (x2, y2, *_) in zip(ring, ring[1:]))) / 2
    return total


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
    parser.add_argument("--only", choices=("fetch", "derive", "sky", "geo"),
                        help="run one half; 'sky' re-derives only the stars and the Moon, "
                             "'geo' only the countries, lines and cities")
    args = parser.parse_args()
    source_dir = os.path.join(args.data, "source")
    out_dir = os.path.join(args.data, "derived")
    if args.only not in ("derive", "sky", "geo"):
        log(f"Sources -> {source_dir}")
        fetch(source_dir)
    if args.only != "fetch":
        log(f"Derived -> {out_dir}")
        parts = {"sky": ("sky",), "geo": ("geo",)}.get(args.only, ("earth", "sky", "geo"))
        derive(source_dir, out_dir, parts)
    total = sum(os.path.getsize(os.path.join(root, name))
                for root, _, names in os.walk(args.data) if ".venv" not in root for name in names)
    log(f"Earth data on disk: {total / 1e9:.2f} GB (budget: 6 GB)")


if __name__ == "__main__":
    sys.exit(main())
