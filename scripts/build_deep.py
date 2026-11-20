#!/usr/bin/env python3
"""Deep time for the time machine: every map of the PaleoAtlas, and where each plate was, 750 million years to now.

Owner, 2026-11-17: on a phone a "Deep time" switch turns the bar to 750 million years ago → now; on bigger screens
one long bar holds deep time and the recent years. At any age the Earth shows the nearest atlas maps (cross-faded),
and the current topic's outline is moved back with the atlas's own plate model ("where Brazil was 200 million
years ago"). The opening keeps its own 14 eras (`paleo.json`, build_paleo.py); this writes a second list.

Source and cleaning as build_paleo.py: Scotese's PALEOMAP PaleoAtlas (Zenodo 10.5281/zenodo.5460860, CC BY 4.0),
today's borders and the file name taken out by paleo_atlas.py. The 14 opening eras come out byte for byte the
same file as build_paleo.py writes (same name, same cleaning), so the two lists share them.

    ../earth-data/.venv/bin/python scripts/build_deep.py [--out DIR] [--only AGE,AGE]

Writes  DIR/paleo/paleo-<age>.v2.jpg     each of the 90 maps, 2048 x 1024 (skipped when already there)
        DIR/paleo/plates-<age>.v1.png    which plate is where at that age, 1024 x 512, one byte a pixel
                                         (0 = no plate known; n = the n-th plate of `plates.ids`)
        DIR/paleo/paleo-<age>.s1.jpg     each map small, 512 x 256, and
        DIR/paleo/plates-<age>.s1.png    its plate map small, 512 x 256 (nearest): all fetched as soon as deep
                                         time can be reached, so the handle shows a map at once while dragged
                                         (Owner, 2026-11-18: the old Earth lagged, most on the phone); the full
                                         pair comes when the handle rests. Made from the full files when missing.
        DIR/paleo/deep.json              the list (age, period, files) + the plate model + credit
(DIR defaults to earth-data/derived; prod and dev both read that, so build a preview with --out first.)

How the outline goes back: the viewer reads a pixel's plate from `plates-<age>`, turns the point back to today
with that plate's turn at the age (the plate model, `plates.rows`, is sent as it is and worked out in the
browser, so the outline moves smoothly between the maps), and looks up today's area there.
The plate map is made forwards: every pixel of today's plates (PALEOMAP_PlatePolygons, present-day positions)
is moved to the age and written where it lands; one-pixel gaps between the landed pixels are closed. Where no
plate lands (sea floor gone since), there is no today to look up: nothing is lit.
"""
import json
import os
import re
import sys
import zipfile

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from build_paleo import ATLAS, EARTH, HEIGHT, MODEL, QUALITY, VERSION, WIDTH, atlas_entry
from paleo_atlas import PlateModel, clean, read_features

PLATES_VERSION = "v1"
PW, PH = 1024, 512          # the plate maps
SMALL_VERSION = "s1"
SW, SH = 512, 256           # the small pair shown while the handle moves
TODAY = (4096, 2048)        # today's plates are drawn this fine, then moved (2x per side: no gaps on landing)
# The periods (International Chronostratigraphic Chart, v2023/09), each from the age it starts, youngest first.
PERIODS = [
    (2.58, "Quaternary"), (23.03, "Neogene"), (66.0, "Paleogene"), (145.0, "Cretaceous"), (201.4, "Jurassic"),
    (251.902, "Triassic"), (298.9, "Permian"), (358.9, "Carboniferous"), (419.2, "Devonian"),
    (443.8, "Silurian"), (485.4, "Ordovician"), (538.8, "Cambrian"), (635.0, "Ediacaran"), (720.0, "Cryogenian"),
    (1000.0, "Tonian"),
]
CREDIT = {
    "what": "The Earth's past (the time machine's deep time)",
    "credit": "PALEOMAP PaleoAtlas and plate model, C. R. Scotese 2016 (Zenodo)",
    "licence": "CC BY 4.0",
    "years": "750 million years ago to now",
    "made": "Painted maps of the past by a geologist, from rocks and fossils: land, sea, ice and where plants "
            "grew; today's borders, drawn on the maps, are taken out. A place's outline is moved back with the "
            "same atlas's plate model. Periods: International Chronostratigraphic Chart 2023.",
}


def period_of(age):
    """The period an age (million years ago) falls in. A map on a boundary (66, 145 ...) is the older period's
    end, as the atlas names it (66 = 'KT Boundary', the end of the Cretaceous)."""
    for start, name in PERIODS:
        if age < start or (age == round(start) and start > 3):
            return name
    return PERIODS[-1][1]


def atlas_ages(names):
    found = sorted({int(m.group(1)) for n in names if "__MACOSX" not in n
                    for m in [re.search(r"PaleoAtlas Rasters v3/[^/]*_(\d{3})\.jpg$", n)] if m})
    return found


def unwrap(ring):
    """A ring's longitudes made continuous (no 360-degree jumps), so it can be drawn whole."""
    lat, lon = ring[:, 0], ring[:, 1].copy()
    jumps = np.diff(lon)
    lon[1:] -= 360 * np.cumsum(np.round(jumps / 360))
    return lat, lon


def today_plates(features, index):
    """Today's plate (as its index, 1..n) for each pixel of a TODAY-sized equirectangular grid."""
    w, h = TODAY
    pic = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(pic)
    for plate, _born, _gone, rings in features:
        for ring in rings:
            lat, lon = unwrap(ring)
            spans = lon.max() - lon.min()
            if spans > 350 and abs(lon[-1] - lon[0]) > 300:
                # Round a pole (Antarctica): close the ring over the pole it goes round.
                pole = 90 if lat.mean() > 0 else -90
                lon = np.concatenate([lon, [lon[-1], lon[0]]])
                lat = np.concatenate([lat, [pole, pole]])
            for shift in (-360, 0, 360):
                xy = [((x + 180 + shift) / 360 * w, (90 - y) / 180 * h) for y, x in zip(lat, lon)]
                if len(xy) > 2:
                    draw.polygon(xy, fill=index[plate])
    return np.asarray(pic)


def ground_of(picture):
    """For each pixel of a TODAY-sized grid, what the atlas's own map of today paints there: 2 land, 1 shallow
    sea (the continents' drowned edges), 0 deep ocean. Plates overlap once moved back, because each plate
    polygon carries its sea floor, and the sea floor is mostly younger than the age (Africa's South Atlantic
    floor, moved back 200 million years, lands on Brazil): where they overlap, land wins, then shallow sea."""
    rgb = np.asarray(picture.convert("RGB").resize(TODAY, Image.NEAREST)).astype(np.int16)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    sea = (b > r + 25) & (b + 10 >= g)
    deep_sea = sea & (rgb @ np.array([299, 587, 114]) < 110 * 1000)
    return np.where(~sea, 2, np.where(deep_sea, 0, 1)).astype(np.uint8)


def plate_map(today, ground, model, ids, age):
    """Which plate is where at `age`: every pixel of today's plates moved there (see ground_of for overlaps)."""
    h, w = today.shape
    lat = np.radians(90 - (np.arange(h) + .5) * 180 / h)
    lon = np.radians((np.arange(w) + .5) * 360 / w - 180)
    out = np.zeros((PH, PW), np.uint8)
    landed = []
    for n, plate in enumerate(ids, 1):
        rows, cols = np.nonzero(today == n)
        if not len(rows):
            continue
        q = model.turn(plate, age)
        if q is None:
            continue
        la, lo = lat[rows], lon[cols]
        xyz = np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)], 1)
        t = 2 * np.cross(q[1:], xyz)
        r = xyz + q[0] * t + np.cross(q[1:], t)
        y = np.clip(((90 - np.degrees(np.arcsin(np.clip(r[:, 2], -1, 1)))) / 180 * PH).astype(int), 0, PH - 1)
        x = np.clip(((np.degrees(np.arctan2(r[:, 1], r[:, 0])) + 180) / 360 * PW).astype(int), 0, PW - 1)
        landed.append((y, x, np.full(len(y), n, np.uint8), ground[rows, cols]))
    y, x, n, level = (np.concatenate(part) for part in zip(*landed))
    for rank in (0, 1, 2):
        pick = level == rank
        out[y[pick], x[pick]] = n[pick]
    # Close one-pixel gaps between landed pixels (rounding), not the real ones (sea floor since gone).
    pic = Image.fromarray(out)
    grown = np.asarray(pic.filter(ImageFilter.ModeFilter(3)))
    gap = (out == 0) & (np.asarray(Image.fromarray((out > 0).astype(np.uint8) * 255).filter(ImageFilter.BoxBlur(1)))
                        > 255 * 5 / 9)
    out[gap] = grown[gap]
    return out


def model_rows(text, ids):
    """The rotation file's rows for the plates used and every plate they move with, as
    {plate: [[age, w, x, y, z, moves-with], ...]} (quaternions, as PlateModel reads them)."""
    model = PlateModel(text)
    keep, todo = set(), list(ids)
    while todo:
        plate = todo.pop()
        if plate in keep or plate == 0:
            continue
        keep.add(plate)
        todo.extend(fixed for _a, _q, fixed in model.rows.get(plate, []))
    return {str(p): [[a, *(round(float(v), 6) for v in q), f] for a, q, f in model.rows.get(p, [])]
            for p in sorted(keep)}


def make_small(derived, era):
    """The small pair for an age, from its full map and plate map (when there and the small one is not)."""
    pairs = ((era["file"], era["small"], Image.LANCZOS), (era["plates"], era["smallPlates"], Image.NEAREST))
    for full, small, how in pairs:
        src, dst = os.path.join(derived, full), os.path.join(derived, small)
        if os.path.isfile(dst) or not os.path.isfile(src):
            continue
        picture = Image.open(src).resize((SW, SH), how)
        if dst.endswith(".jpg"):
            picture.save(dst, quality=QUALITY, optimize=True)
        else:
            picture.save(dst, optimize=True)


def main():
    derived = os.path.join(EARTH, "derived")
    if "--out" in sys.argv:
        derived = os.path.abspath(sys.argv[sys.argv.index("--out") + 1])
    only = None
    if "--only" in sys.argv:
        only = {int(v) for v in sys.argv[sys.argv.index("--only") + 1].split(",")}
    out_dir = os.path.join(derived, "paleo")
    if not os.path.isfile(ATLAS):
        sys.exit(f"No {ATLAS}: download Scotese_PaleoAtlas_v3.zip from Zenodo 10.5281/zenodo.5460860.")
    os.makedirs(out_dir, exist_ok=True)
    with zipfile.ZipFile(ATLAS) as archive:
        names = archive.namelist()
        inside = {n.split("/")[-1]: n for n in names if MODEL in n}
        rot = archive.read(inside["PALEOMAP_PlateModel.rot"]).decode("latin-1")
        model = PlateModel(rot)
        borders = read_features(archive.read(inside["PALEOMAP_PoliticalBoundaries.gpml"]))
        polygons = read_features(archive.read(inside["PALEOMAP_PlatePolygons.gpml"]))
        ids = sorted({plate for plate, *_ in polygons})
        if len(ids) > 255:
            sys.exit(f"{len(ids)} plates: the plate maps hold 255")
        index = {plate: n for n, plate in enumerate(ids, 1)}
        today = today_plates(polygons, index)
        with archive.open(atlas_entry(names, 0)) as raw:
            ground = ground_of(Image.open(raw))
        print(f"{len(ids)} plates; today's grid covered {np.mean(today > 0):.1%}")
        eras = []
        for age in atlas_ages(names):
            file = f"paleo/paleo-{age}.{VERSION}.jpg"
            plates = f"paleo/plates-{age}.{PLATES_VERSION}.png"
            eras.append({"age": age, "period": period_of(age), "file": file, "plates": plates,
                         "small": f"paleo/paleo-{age}.{SMALL_VERSION}.jpg",
                         "smallPlates": f"paleo/plates-{age}.{SMALL_VERSION}.png"})
            if only is not None and age not in only:
                continue
            path = os.path.join(derived, file)
            if not os.path.isfile(path):
                with archive.open(atlas_entry(names, age)) as raw:
                    picture, _ = clean(Image.open(raw), model, borders, age)
                picture.resize((WIDTH, HEIGHT), Image.LANCZOS).save(path, quality=QUALITY, optimize=True)
            where = plate_map(today, ground, model, ids, age)
            Image.fromarray(where).save(os.path.join(derived, plates), optimize=True)
            print(f"{age:>4} Ma  {period_of(age):<13} map {os.path.getsize(path) // 1024} KB  plates "
                  f"{os.path.getsize(os.path.join(derived, plates)) // 1024} KB, {np.mean(where > 0):.0%} covered",
                  flush=True)
    for era in eras:
        make_small(derived, era)
    index_json = {**CREDIT, "eras": eras, "plates": {"ids": ids, "rows": model_rows(rot, ids)}}
    with open(os.path.join(out_dir, "deep.json"), "w", encoding="utf-8") as out:
        json.dump(index_json, out, separators=(",", ":"))
    size = os.path.getsize(os.path.join(out_dir, "deep.json")) // 1024
    print(f"Wrote {len(eras)} ages to {out_dir}/deep.json ({size} KB)")


if __name__ == "__main__":
    main()
