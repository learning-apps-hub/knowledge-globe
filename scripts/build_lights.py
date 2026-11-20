#!/usr/bin/env python3
"""City lights through the years, for the time machine (Explore and Learn).

Real years, 1992 to 2024: "Harmonization of DMSP and VIIRS nighttime light
data from 1992-2024 at the global scale" (Li, Zhou, Zhao and Zhao; figshare
article 9828827, version 10), CC BY 4.0. One GeoTIFF a year, 30 arc-seconds,
75 N to 65 S, brightness 0 to 63 (DMSP-like units; 2014 on is VIIRS made to
match DMSP).

Made years, 1960 to 1991: there is no night picture from before 1992. These
years start from the 1992 lights and dim each country by how many people lived
there that year against 1992 (people by year from Wikidata, `data/compare.json`).
They are marked as made in the list, and the viewer says so.

The viewer does NOT swap pictures. Today's lights stay the NASA Black Marble
2016 picture (sharp, already in `pack-4096`); each year here is a FACTOR on it:
how bright that place was that year against 2016, 0 to 2, stored as factor/2 in
an 8-bit grey PNG. So the look stays the same and only where and how bright the
lights are changes.

    ../earth-data/.venv/bin/python scripts/build_lights.py

Reads   earth-data/source/nightlights/<year>.tif   (about 1 GB in all; delete after)
Keeps   earth-data/source/nightlights/means/<year>.npy  (small; so a rebuild skips the TIFFs)
Writes  earth-data/derived/lights/lights-<year>.v1.png   2048 x 1024
        earth-data/derived/lights/lights.json            the list + credit
"""
import json
import os
import sys

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EARTH = os.environ.get("KG_EARTH_DIR") or os.path.join(os.path.dirname(REPO), "earth-data")
SOURCE = os.path.join(EARTH, "source", "nightlights")
MEANS = os.path.join(SOURCE, "means")
OUT = os.path.join(EARTH, "derived", "lights")

FIRST_REAL, LAST_REAL = 1992, 2024
FIRST_MADE = 1960
MADE_STEP = 2                 # made years every 2 years (people change slowly)
VERSION = "v1"                # in every file name: the server tells browsers to keep pictures for good
REFERENCE = 2016              # the year of the Black Marble picture the viewer draws
BLOCK = 20                    # 20 x 30 arc-seconds = 1/6 degree a cell
GRID_W, GRID_H = 2160, 1080   # the whole Earth at 1/6 degree
TOP_ROWS = 90                 # 90 N to 75 N: the source has nothing there
WIDTH, HEIGHT = 2048, 1024
FLOOR = 0.6                   # brightness under which a cell counts as dark (noise in empty land)
MOST = 2.0                    # the brightest a place can be against 2016
CREDIT = {
    "what": "City lights, year by year",
    "credit": "Li, Zhou, Zhao and Zhao, Harmonization of DMSP and VIIRS nighttime light data 1992-2024 (figshare)",
    "licence": "CC BY 4.0",
    "made": "Before 1992 there is no night picture: those years start from the 1992 lights, "
            "dimmed by how many people lived in each country (Wikidata).",
}


def year_mean(year):
    """The year's brightness at 1/6 degree over the whole Earth (float32, 1080 x 2160)."""
    cached = os.path.join(MEANS, f"{year}.npy")
    if os.path.exists(cached):
        return np.load(cached)
    tif = os.path.join(SOURCE, f"{year}.tif")
    image = Image.open(tif)
    width, height = image.size                        # 43201 x 16801: one extra column and row
    small = image.convert("L")                        # 0..63 fits; frees the 2.9 GB int32 copy below
    image.close()
    del image
    grid = np.asarray(small, dtype=np.uint8)[: (height // BLOCK) * BLOCK, : (width // BLOCK) * BLOCK]
    rows, cols = grid.shape[0] // BLOCK, grid.shape[1] // BLOCK
    sums = grid.reshape(rows, BLOCK, cols, BLOCK).astype(np.uint32).sum(axis=(1, 3))
    del grid, small
    world = np.zeros((GRID_H, GRID_W), np.float32)
    world[TOP_ROWS:TOP_ROWS + rows, :cols] = sums / float(BLOCK * BLOCK)
    os.makedirs(MEANS, exist_ok=True)
    np.save(cached, world)
    return world


def soften(a):
    """A 3 x 3 box blur, round the date line."""
    padded = np.pad(a, ((1, 1), (0, 0)), mode="edge")
    padded = np.concatenate([padded[:, -1:], padded, padded[:, :1]], axis=1)
    out = np.zeros_like(a)
    for dy in range(3):
        for dx in range(3):
            out += padded[dy:dy + a.shape[0], dx:dx + a.shape[1]]
    return out / 9.0


def factor(mean, reference):
    """How bright each cell is against the reference year, 0..MOST; 1 where the reference is dark."""
    m, r = soften(mean), soften(reference)
    f = np.where(r > FLOOR, (m + 0.2) / (r + 0.2), 1.0)
    return np.clip(f, 0.0, MOST).astype(np.float32)


def save_factor(f, name):
    picture = Image.fromarray(f, "F").resize((WIDTH, HEIGHT), Image.BILINEAR)
    grey = np.clip(np.asarray(picture) / MOST * 255.0 + 0.5, 0, 255).astype(np.uint8)
    path = os.path.join(OUT, name)
    Image.fromarray(grey, "L").save(path, optimize=True)
    return os.path.getsize(path)


def country_codes():
    """The area code of each 1/6-degree cell, from the area picture the viewer uses."""
    geo = json.load(open(os.path.join(EARTH, "derived", "geo.v2.json"), encoding="utf-8"))
    picture = Image.open(os.path.join(EARTH, "derived", "areas-4096.v2.png")).convert("RGB")
    picture = picture.resize((GRID_W, GRID_H), Image.NEAREST)
    rgb = np.asarray(picture, np.int32)
    codes = rgb[..., 0] + 256 * rgb[..., 1]
    return codes, {area["code"]: area["id"] for area in geo["areas"]}


def people_by_year():
    compare = json.load(open(os.path.join(REPO, "data", "compare.json"), encoding="utf-8"))["compare"]
    people = {}
    for topic, facts in compare.items():
        for fact in facts:
            if fact.get("key") == "people" and fact.get("by_year"):
                people[topic] = {int(y): float(v) for y, v in fact["by_year"].items() if float(v) > 0}
    return people


def near(table, year):
    """The value for the year, or the nearest year that has one."""
    if year in table:
        return table[year]
    return table[min(table, key=lambda y: abs(y - year))]


def main():
    os.makedirs(OUT, exist_ok=True)
    years, sizes = [], 0
    reference = year_mean(REFERENCE)
    first = None
    for year in range(FIRST_REAL, LAST_REAL + 1):
        mean = year_mean(year)
        f = factor(mean, reference)
        if year == FIRST_REAL:
            first = f
        name = f"lights-{year}.{VERSION}.png"
        sizes += save_factor(f, name)
        years.append({"year": year, "file": f"lights/{name}"})
        print(year, "real", flush=True)

    codes, ids = country_codes()
    people = people_by_year()
    # Every country's nearest value each year: summing only the countries that
    # report a year made the world ratio jump (1970 0.74, 1972 0.66).
    world_first = sum(near(table, FIRST_REAL) for table in people.values())
    made = []
    for year in range(FIRST_MADE, FIRST_REAL, MADE_STEP):
        everyone = min(1.0, sum(near(table, year) for table in people.values()) / world_first)
        scale = np.full(codes.shape, everyone, np.float32)   # sea, ice and places with no count
        for code, topic in ids.items():
            table = people.get(topic)
            if table:
                scale[codes == code] = min(1.0, near(table, year) / near(table, FIRST_REAL))
        f = first * scale
        name = f"lights-{year}.{VERSION}.png"
        sizes += save_factor(f, name)
        made.append({"year": year, "file": f"lights/{name}", "made": True})
        print(year, "made", round(everyone, 2), flush=True)

    index = dict(CREDIT, reference=REFERENCE, most=MOST, years=made + years)
    with open(os.path.join(OUT, "lights.json"), "w", encoding="utf-8") as out:
        json.dump(index, out, indent=1)
    print(f"{len(made) + len(years)} pictures, {sizes / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
