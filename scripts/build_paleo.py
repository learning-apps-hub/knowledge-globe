#!/usr/bin/env python3
"""The Earth's past, for the opening (the intro): land, sea, ice and plants as they were.

Source: the PALEOMAP PaleoAtlas, C. R. Scotese 2016 ("PALEOMAP PaleoAtlas for GPlates and the PaleoData
Plotter Program, PALEOMAP Project"), `Scotese_PaleoAtlas_v3.zip` in Zenodo 10.5281/zenodo.5460860, CC BY 4.0
(Owner found it, 2026-11-17: "clear landscape changes in motion"). 90 painted maps, today back to 750 million
years ago: mountains, lowlands, plants, deserts, ice caps, shallow seas and the deep ocean, each 3600 x 1800.

Every map has today's borders and coasts drawn on it as thin black lines, and its file name near the south
pole; `paleo_atlas.py` takes both out (it moves today's borders back with the atlas's own plate model to find
them). Nothing older than 750 million years has a map: the viewer draws the young Earth itself and says so.

    ../earth-data/.venv/bin/python scripts/build_paleo.py [--out DIR]

`--out DIR` writes the pictures and paleo.json into DIR/paleo/ instead (a preview): prod (8110) and dev (8111)
both read earth-data/derived, so building there changes the opening on both at once.

Reads   earth-data/source/paleoatlas/Scotese_PaleoAtlas_v3.zip   (58 MB: the maps, the plate model, the borders)
Writes  earth-data/derived/paleo/paleo-<age>.v2.jpg   one per era, 2048 x 1024
        earth-data/derived/paleo/paleo.json          the list + credit + `faces` (below)
(The v1 pictures, coloured from PaleoDEM height maps, stay on disk for the `opening-v1` tag; nothing lists them.)

`faces`: how much of the Earth's face is land, seen from each longitude (every
FACE_STEP degrees from 180 W) at FACE_LAT, averaged over the eras from
FACE_FROM million years ago on. The opening starts its first act on the side
that shows the most land, so it is not a plain blue ball (Owner, 2026-11-16).
"""
import json
import os
import re
import sys
import zipfile

import numpy as np
from PIL import Image

from paleo_atlas import PlateModel, clean, read_features

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EARTH = os.environ.get("KG_EARTH_DIR") or os.path.join(os.path.dirname(REPO), "earth-data")
ATLAS = os.path.join(EARTH, "source", "paleoatlas", "Scotese_PaleoAtlas_v3.zip")

VERSION = "v2"               # in every file name: the server tells browsers to keep pictures for good
WIDTH, HEIGHT = 2048, 1024
QUALITY = 84
# The eras the opening turns through (Owner, 2026-11-16; 750 to 600 added 2026-11-17 with the atlas), oldest
# first, each with the period's name. The landscape blends from one to the next all the way through, so no gap
# may be too wide to read as motion.
ERAS = [
    (750, "Cryogenian"),
    (690, "Cryogenian, the ice Earth"),
    (600, "Ediacaran"),
    (540, "Cambrian"),
    (480, "Ordovician"),
    (420, "Silurian"),
    (360, "Devonian"),
    (300, "Carboniferous"),
    (250, "Pangaea, one land"),
    (200, "Triassic and Jurassic"),
    (150, "Jurassic"),
    (100, "Cretaceous"),
    (66, "End of the Cretaceous"),
    (30, "Oligocene"),
]
# The faces table (see the docstring). FACE_LAT must match the opening's tilt for the ages (`INTRO.tilt`).
FACE_LAT, FACE_STEP, FACE_FROM = -38, 5, 360
CREDIT = {
    "what": "The Earth's past (the opening)",
    "credit": "PALEOMAP PaleoAtlas, C. R. Scotese 2016 (Zenodo)",
    "licence": "CC BY 4.0",
    "years": "750 million years ago to now",
    "made": "Painted maps of the past by a geologist, from rocks and fossils: land, sea, ice and where plants "
            "grew. Today's borders, drawn on the maps, are taken out. Nothing is mapped before 750 million years "
            "ago, so the young Earth is drawn, not mapped.",
}
MODEL = "PALEOMAP Global Plate Model/"


def atlas_entry(names, age):
    """The atlas map for an age (its file name ends in the age, three digits)."""
    pattern = re.compile(rf"PaleoAtlas Rasters v3/[^/]*_{age:03d}\.jpg$")
    found = [n for n in names if pattern.search(n) and "__MACOSX" not in n]
    if len(found) != 1:
        sys.exit(f"Expected one atlas map for {age} Ma, found {found}")
    return found[0]


def land_of(rgb):
    """Land (and ice) where the picture is not sea-blue: the atlas paints every sea blue, shallow to deep."""
    r, g, b = (rgb[..., i].astype(np.int16) for i in range(3))
    return ~((b > r + 25) & (b + 10 >= g))


def land_seen(lands):
    """For each longitude (FACE_STEP apart, from 180 W), the share of the face seen from it that is land,
    the middle counting more (as it looks: cos^1.5), averaged over the eras given."""
    h, w = lands[0].shape
    lats = np.radians(90 - (np.arange(h) + 0.5) * 180 / h)[:, None]
    lons = np.radians((np.arange(w) + 0.5) * 360 / w - 180)[None, :]
    a = np.radians(FACE_LAT)
    shares = []
    for deg in range(-180, 180, FACE_STEP):
        seen = np.clip(np.sin(lats) * np.sin(a) + np.cos(lats) * np.cos(a) * np.cos(lons - np.radians(deg)), 0, None)
        seen = seen ** 1.5 * np.cos(lats)   # (each row's cells cover less ground towards the poles)
        shares.append(round(float(np.mean([(land * seen).sum() / seen.sum() for land in lands])), 3))
    return shares


def main():
    derived = os.path.join(EARTH, "derived")
    if "--out" in sys.argv:
        derived = os.path.abspath(sys.argv[sys.argv.index("--out") + 1])
    out_dir = os.path.join(derived, "paleo")
    if not os.path.isfile(ATLAS):
        sys.exit(f"No {ATLAS}: download Scotese_PaleoAtlas_v3.zip from Zenodo 10.5281/zenodo.5460860.")
    os.makedirs(out_dir, exist_ok=True)
    eras, lands = [], []
    with zipfile.ZipFile(ATLAS) as archive:
        names = archive.namelist()
        inside = {n.split("/")[-1]: n for n in names if MODEL in n}
        model = PlateModel(archive.read(inside["PALEOMAP_PlateModel.rot"]).decode("latin-1"))
        features = read_features(archive.read(inside["PALEOMAP_PoliticalBoundaries.gpml"]))
        for age, name in ERAS:
            with archive.open(atlas_entry(names, age)) as raw:
                picture, repainted = clean(Image.open(raw), model, features, age)
            picture = picture.resize((WIDTH, HEIGHT), Image.LANCZOS)
            file = f"paleo/paleo-{age}.{VERSION}.jpg"
            picture.save(os.path.join(derived, file), quality=QUALITY, optimize=True)
            land = land_of(np.asarray(picture))
            if age <= FACE_FROM:
                land_map = Image.fromarray(land.astype(np.float32), mode="F")
                lands.append(np.asarray(land_map.resize((360, 180), Image.BOX)))
            # Where its land is, so the opening turns that side to the viewer (mean of land directions).
            lats = np.radians(90 - (np.arange(HEIGHT) + 0.5) * 180 / HEIGHT)[:, None]
            lons = np.radians((np.arange(WIDTH) + 0.5) * 360 / WIDTH - 180)[None, :]
            weight = land * np.cos(lats)
            east = float((weight * np.cos(lats) * np.sin(lons)).sum())
            front = float((weight * np.cos(lats) * np.cos(lons)).sum())
            centre = round(float(np.degrees(np.arctan2(east, front))), 1)
            size = os.path.getsize(os.path.join(derived, file))
            print(f"{age:>4} Ma  {name:<26} land {land.mean():.0%}  lines taken out {repainted:.1%}  {size // 1024} KB")
            eras.append({"age": age, "name": name, "file": file, "lon": centre})
    faces = {"lat": FACE_LAT, "step": FACE_STEP, "from": FACE_FROM, "land": land_seen(lands)}
    index = {**CREDIT, "eras": eras, "faces": faces}
    with open(os.path.join(out_dir, "paleo.json"), "w", encoding="utf-8") as out:
        json.dump(index, out, indent=1)
    print(f"Wrote {len(eras)} eras to {out_dir}")


if __name__ == "__main__":
    main()
