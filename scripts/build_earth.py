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
AREA_BIG = 8192        # a sharper copy of the area picture, for zoomed-in light-up edges (tier A, 2026-11-13)
GEO_VERSION = "v2"     # geo JSON and area pictures; v2 = 2026-11-13 (all-questions build)
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

# Natural Earth v5.1.2 gives the Spratly Islands the English name "Wake Island" (a real, different island, which
# Natural Earth keeps inside the US Minor Outlying Islands). Found 2026-11-13.
NAME_FIX = {"Spratly Is.": "Spratly Islands"}

# Names that read with "the" in a sentence ("Belongs to the Netherlands").
THE = {"United Kingdom", "United States of America", "Netherlands", "Philippines", "Bahamas", "Gambia",
       "Maldives", "Czech Republic", "Central African Republic", "Dominican Republic", "United Arab Emirates",
       "Comoros", "Marshall Islands", "Solomon Islands", "Seychelles", "Democratic Republic of the Congo",
       "Republic of the Congo", "People's Republic of China", "Falkland Islands", "Faroe Islands",
       "Cayman Islands", "British Virgin Islands", "United States Virgin Islands", "Turks and Caicos Islands",
       "Cook Islands", "Pitcairn Islands", "Northern Mariana Islands", "Federated States of Micronesia",
       "Spratly Islands", "Cocos (Keeling) Islands", "Åland Islands", "Isle of Man", "Vatican",
       "French Southern and Antarctic Lands", "Heard Island and McDonald Islands", "Southern Patagonian Ice Field",
       "Siachen Glacier", "United Nations Buffer Zone in Cyprus", "Turkish Republic of Northern Cyprus",
       "United States Minor Outlying Islands", "British Indian Ocean Territory", "Sahrawi Arab Democratic Republic",
       "Guantanamo Bay Naval Base", "Akrotiri Sovereign Base Area", "Dhekelia Cantonment",
       "South Georgia and the South Sandwich Islands", "Bajo Nuevo Bank", "Serranilla Bank", "Scarborough Shoal"}


def _the(name):
    return f"the {name}" if name in THE else name


# Disputed and leased areas, by Natural Earth NAME: (status, the card's sentence, the country it belongs to on
# the ground, or None). Only the country that actually runs it gets a "What does it belong to?" link; the other
# claimants are named in the sentence, never drawn as owners (Owner, 2026-11-13: follow the recommendation).
# Facts as of November 2026 -- re-read when a dispute moves (BIOT: 2025 UK-Mauritius treaty).
DISPUTES = {
    "Baikonur": ("leased", "Kazakhstan rents this land to Russia, which runs a space launch site here.",
                 "Kazakhstan", "Kazakhstan rents it to Russia."),
    "USNB Guantanamo Bay": ("disputed", "Cuba rents this land to the United States, which runs a naval base here. "
                            "Cuba says the lease is not valid and wants it back.",
                            "Cuba", "Cuba rents it to the United States, and wants it back."),
    "Gibraltar": ("disputed", "Governed by the United Kingdom. Spain also claims it.",
                  "United Kingdom", "The United Kingdom governs it. Spain also claims it."),
    "Falkland Is.": ("disputed", "Governed by the United Kingdom. Argentina also claims the islands, which it calls "
                     "the Islas Malvinas.", "United Kingdom",
                     "The United Kingdom governs it. Argentina also claims it."),
    "Br. Indian Ocean Ter.": ("disputed", "Governed by the United Kingdom. Mauritius claims these islands, and in "
                              "2025 the two countries signed a treaty to hand them to Mauritius, with the UK "
                              "keeping a military base on Diego Garcia.", "United Kingdom",
                              "The United Kingdom governs it. Mauritius claims it."),
    "Siachen Glacier": ("disputed", "A high mountain glacier. India controls it; Pakistan also claims it. Their "
                        "armies have faced each other here since 1984.", "India",
                        "India controls it. Pakistan also claims it."),
    "Southern Patagonian Ice Field": ("disputed", "A great ice field on the border of Chile and Argentina. In 1998 "
                                      "they agreed how to divide most of it, but part of the line is still not "
                                      "drawn.", None, ""),
    "Brazilian I.": ("disputed", "A small river island where Brazil, Uruguay and Argentina meet. Brazil governs "
                     "it; Uruguay also claims it.", "Brazil", "Brazil governs it. Uruguay also claims it."),
    "Bir Tawil": ("disputed", "Land between Egypt and Sudan that neither country claims: each claims a different "
                  "piece of land next to it instead.", None, ""),
    "Cyprus U.N. Buffer Zone": ("disputed", "A strip between the north and the south of Cyprus, patrolled by "
                                "United Nations peacekeepers since 1974.", "Cyprus",
                                "Cyprus counts it as part of Cyprus. UN peacekeepers patrol it."),
    "Spratly Is.": ("disputed", "Small reefs and islands in the South China Sea. China, Taiwan, Vietnam, "
                    "Malaysia, the Philippines and Brunei claim some or all of them, and several hold some.",
                    None, ""),
    "Scarborough Reef": ("disputed", "A reef in the South China Sea. China, the Philippines and Taiwan all claim "
                         "it; China has kept ships there since 2012.", None, ""),
    "Bajo Nuevo Bank": ("disputed", "A small reef in the Caribbean Sea, run by Colombia. The United States also "
                        "claims it.", "Colombia", "Colombia runs it. The United States also claims it."),
    "Serranilla Bank": ("disputed", "A small reef in the Caribbean Sea, run by Colombia. The United States also "
                        "claims it.", "Colombia", "Colombia runs it. The United States also claims it."),
}


# Natural Earth (default view) draws the part of Western Sahara that Morocco holds inside Morocco's polygon, and
# "W. Sahara" as only the strip east of the sand wall. The territory's northern border is the line 27 deg 40' N,
# so every Morocco pixel south of it is drawn as Western Sahara: choosing it lights the whole territory, as its
# card sentence says (found 2026-11-13).
SAHARA_NORTH = 27 + 40 / 60


def _whole_sahara(codes, features, np):
    names = [f["properties"]["NAME"] for f in features]
    morocco, sahara = names.index("Morocco") + 1, names.index("W. Sahara") + 1
    height, width = codes.shape
    lat = 90.0 - (np.arange(height) + .5) * 180.0 / height
    south = (lat < SAHARA_NORTH)[:, None] & (codes == morocco)
    codes[south] = sahara
    return codes


def _tilt(year):
    """The Earth's axial tilt in degrees for a year (IAU 2006, enough for a picture)."""
    t = (year - 2000) / 100.0
    return 23.439291 - 0.0130042 * t


def _slug(text):
    import re
    import unicodedata
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _area_status(props):
    """(status, sentence). status: country | own-government | territory | disputed | leased | unowned."""
    name, admin, sovereign, kind = props["NAME"], props["ADMIN"], props["SOVEREIGNT"], props["TYPE"]
    if name in OWN_GOVERNMENT:
        return "own-government", OWN_GOVERNMENT[name]
    if name in DISPUTES:
        return DISPUTES[name][0], DISPUTES[name][1]
    if name == "Antarctica":
        return "unowned", "No country owns it. A treaty sets it aside for peace and science."
    if name in UN_OBSERVER_OR_ODD or (kind in ("Sovereign country", "Sovereignty", "Country") and admin == sovereign):
        return "country", ""
    if kind in ("Country", "Dependency") and admin != sovereign:
        return "territory", f"Belongs to {_the(sovereign)}."
    raise ValueError(f"{name}: disputed or leased area with no sentence in DISPUTES")


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
    codes = _whole_sahara(np.asarray(code, np.int32).copy(), features, np)

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
    areas_file = save(Image.fromarray(rgb, "RGB"), f"areas-{AREA_W}.{GEO_VERSION}.png", optimize=True)

    # The same codes drawn at 8192 (sharper edges when zoomed in). Oceans come from the 4096 picture, grown a
    # few pixels into the water the finer coast uncovers; land codes are the same numbers.
    scale = AREA_BIG / AREA_W
    big = Image.new("I", (AREA_BIG, AREA_BIG // 2), 0)
    big_draw = ImageDraw.Draw(big)
    for i in order:
        _fill(big_draw, features[i]["geometry"], i + 1, lambda ring: [(x * scale, y * scale) for x, y in to_px(ring)])
    big_codes = _whole_sahara(np.asarray(big, np.int32).copy(), features, np)
    big_seas = np.repeat(np.repeat(seas, 2, 0), 2, 1)
    big_seas[big_codes > 0] = 0
    open_water = big_codes == 0
    for _ in range(4):
        for axis, shift in ((0, 1), (0, -1), (1, 1), (1, -1)):
            near = np.roll(big_seas, shift, axis)
            take = open_water & (big_seas == 0) & (near > 0)
            big_seas[take] = near[take]
    big_rgb = np.stack([big_codes & 255, big_codes >> 8, big_seas], 2).astype(np.uint8)
    big_file = save(Image.fromarray(big_rgb, "RGB"), f"areas-{AREA_BIG}.{GEO_VERSION}.png", optimize=True)
    del big, big_codes, big_seas, big_rgb, open_water
    gap = float(np.mean((codes == 0) & (seas == 0)))
    log(f"  areas: {int(codes.max())} codes, {gap * 100:.1f}% of the picture is neither country nor ocean")

    pixels = np.bincount(codes.ravel(), minlength=len(features) + 1)
    areas, by_a3 = [], {}
    for i, feature in enumerate(features):
        props = feature["properties"]
        status, sentence = _area_status(props)
        continent = props["CONTINENT"] if props["CONTINENT"] in CONTINENTS else None
        dispute = DISPUTES.get(props["NAME"])
        area = {
            "code": i + 1, "id": _slug(props["ADM0_A3"] + "-" + props["NAME"]) if props["ADM0_A3"] in by_a3
            else _slug(NAME_FIX.get(props["NAME"]) or props["NAME_EN"] or props["NAME"]),
            "name": NAME_FIX.get(props["NAME"]) or props["NAME_EN"] or props["NAME"],
            "sovereign": props["SOVEREIGNT"], "status": status,
            "sentence": sentence, "continent": continent, "population": props["POP_EST"],
            "label": [round(props["LABEL_X"], 3), round(props["LABEL_Y"], 3)],
            "tiny": int(pixels[i + 1]) < TINY_PIXELS,
        }
        if area["name"] in THE:
            area["the"] = True                    # reads "the X" inside a sentence
        if dispute and dispute[2]:
            area["belongs"] = {"name": dispute[2], "why": dispute[3]}
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

    # Natural Earth's tropics and polar circles are rounded and do not mirror (23.5 / -23.56 / 66.55 / -66.55).
    # They really sit at the Earth's tilt, which drifts slowly: use this year's value.
    import datetime
    tilt = _tilt(datetime.date.today().year)
    for key, lat in (("tropic-of-cancer", tilt), ("tropic-of-capricorn", -tilt),
                     ("arctic-circle", 90 - tilt), ("antarctic-circle", tilt - 90)):
        if key in lines:
            lines[key]["lat"] = round(lat, 4)
    lines["prime-meridian"] = {"name": "Prime Meridian", "lon": 0.0}

    # What each line runs across: the countries (area codes) and oceans under it.
    def row_of(lat):
        return min(AREA_H - 1, max(0, int((90.0 - lat) / 180.0 * AREA_H)))

    def col_of(lon):
        return min(AREA_W - 1, max(0, int((lon + 180.0) / 360.0 * AREA_W)))

    def under(rows, cols, least=3):
        """Countries and oceans along a line of pixels. Each pixel counts once, and a country needs `least`
        pixels (~30 km) so a line grazing a border or an island's edge does not count as running across it."""
        cells = np.unique(np.stack([rows, cols], 1), axis=0)
        land = codes[cells[:, 0], cells[:, 1]]
        water = seas[cells[:, 0], cells[:, 1]]
        found, count = np.unique(land[land > 0], return_counts=True)
        wet, wet_count = np.unique(water[(land == 0) & (water > 0)], return_counts=True)
        return {"areas": sorted(int(c) for c, n in zip(found, count) if n >= least),
                "oceans": sorted(int(o) for o, n in zip(wet, wet_count) if n >= least)}

    for key, entry in lines.items():
        if "lat" in entry:
            cols = np.arange(AREA_W)
            entry["crosses"] = under(np.full(AREA_W, row_of(entry["lat"])), cols)
        elif "lon" in entry:
            rows = np.arange(AREA_H)
            entry["crosses"] = under(rows, np.full(AREA_H, col_of(entry["lon"])))
        else:
            points = []
            for part in entry["paths"]:
                for (x1, y1), (x2, y2) in zip(part, part[1:]):
                    steps = max(1, int(max(abs(x2 - x1), abs(y2 - y1)) / 0.04))
                    points += [(x1 + (x2 - x1) * k / steps, y1 + (y2 - y1) * k / steps) for k in range(steps + 1)]
            entry["crosses"] = under(np.array([row_of(y) for _, y in points]),
                                     np.array([col_of(((x + 180.0) % 360.0) - 180.0) for x, _ in points]))

    # How much of each area, continent and ocean lies north and east of the Equator and the Prime Meridian
    # (by true area on the globe, not by picture pixels).
    weight = np.cos(np.radians(90.0 - (np.arange(AREA_H) + .5) * 180.0 / AREA_H))[:, None] * np.ones((1, AREA_W))
    north = (np.arange(AREA_H) < AREA_H // 2)[:, None] * np.ones((1, AREA_W), bool)
    east = (np.arange(AREA_W) >= AREA_W // 2)[None, :] * np.ones((AREA_H, 1), bool)
    size = len(features) + 1
    total = np.bincount(codes.ravel(), weight.ravel(), size)
    in_north = np.bincount(codes.ravel(), (weight * north).ravel(), size)
    in_east = np.bincount(codes.ravel(), (weight * east).ravel(), size)
    for area in areas:
        c = area["code"]
        if total[c] > 0:
            area["north"], area["east"] = round(in_north[c] / total[c], 3), round(in_east[c] / total[c], 3)
        else:                                     # too small to draw: its label point decides
            area["north"] = 1.0 if area["label"][1] >= 0 else 0.0
            area["east"] = 1.0 if area["label"][0] >= 0 else 0.0
    ocean_water = np.where(codes == 0, seas, 0).astype(np.int32)
    o_total = np.bincount(ocean_water.ravel(), weight.ravel(), 8)
    o_north = np.bincount(ocean_water.ravel(), (weight * north).ravel(), 8)
    o_east = np.bincount(ocean_water.ravel(), (weight * east).ravel(), 8)
    ocean_share = {n: (round(o_north[n] / o_total[n], 3), round(o_east[n] / o_total[n], 3)) for n, _, _ in OCEANS}

    # An area far from any continent lies in an ocean: the ocean nearest its label point.
    for area in areas:
        if area["continent"]:
            continue
        r, c = row_of(area["label"][1]), col_of(area["label"][0])
        for reach in range(2, 200, 2):
            window = seas[max(0, r - reach):r + reach + 1, max(0, c - reach):c + reach + 1]
            found = window[window > 0]
            if found.size:
                area["ocean"] = int(np.bincount(found).argmax())
                break

    # Neighbours: two countries are next to each other when their borders share points. Natural Earth draws a
    # shared border once and uses it for both sides, so the points match exactly; a coast never does.
    owners = {}
    for i, feature in enumerate(features):
        geometry = feature["geometry"]
        polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
        for polygon in polygons:
            for ring in polygon:
                for x, y, *_ in ring:
                    owners.setdefault((round(x, 6), round(y, 6)), set()).add(i + 1)
    shared = {}
    for codes_here in owners.values():
        if len(codes_here) > 1:
            for a in codes_here:
                for b in codes_here:
                    if a < b:
                        shared[(a, b)] = shared.get((a, b), 0) + 1
    by_code = {a["code"]: a for a in areas}
    for (a, b), count in shared.items():
        if count >= 2:
            by_code[a].setdefault("next", []).append(b)
            by_code[b].setdefault("next", []).append(a)
    for area in areas:
        if "next" in area:
            area["next"].sort()
    del owners

    # Oceans whose waters meet (pixels side by side, one ocean each).
    ocean_next = set()
    for axis in (0, 1):
        a, b = seas, np.roll(seas, 1, axis)
        meet = (a > 0) & (b > 0) & (a != b)
        for x, y in zip(a[meet].ravel(), b[meet].ravel()):
            ocean_next.add((int(min(x, y)), int(max(x, y))))
    continents = []
    for name in CONTINENTS:
        member = np.zeros(len(areas) + 1, bool)
        for area in areas:
            member[area["code"]] = area["continent"] == name
        land = member[codes]
        total = float((weight * land).sum())
        continents.append({"name": name, "north": round(float((weight * land * north).sum()) / total, 3),
                           "east": round(float((weight * land * east).sum()) / total, 3)})

    oceans = []
    for n, label, _ in OCEANS:
        oceans.append({"number": n, "name": label, "north": ocean_share[n][0], "east": ocean_share[n][1],
                       "next": sorted({b for a, b in ocean_next if a == n} | {a for a, b in ocean_next if b == n})})
    geo = {"version": GEO_VERSION, "size": [AREA_W, AREA_H], "tilt": round(tilt, 4), "areas": areas,
           "places": places, "lines": lines, "oceans": oceans, "continents": continents}
    path = os.path.join(out_dir, f"geo.{GEO_VERSION}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(geo, fh, ensure_ascii=False, separators=(",", ":"))
    log(f"  wrote  geo.{GEO_VERSION}.json  {os.path.getsize(path) / 1e3:.0f} KB")
    crossed = ", ".join(f"{k} {len(v['crosses']['areas'])}+{len(v['crosses']['oceans'])}" for k, v in lines.items())
    log(f"  lines cross: {crossed}")
    log(f"  neighbours: {sum(1 for (a, b), n in shared.items() if n >= 2)} pairs; oceans meeting: {len(ocean_next)}")
    return {"areas": areas_file, "areas8192": big_file, "geo": f"geo.{GEO_VERSION}.json"}


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
