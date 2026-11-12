// Where the real Sun, Moon and stars are, for the Explore page's Earth.
//
// Standard low-precision formulas (Astronomical Almanac, "low precision"
// section): the Sun within about 0.01°, the Moon within about 0.3°. That is
// far finer than a screen can show, and needs no data file.
//
// Directions are unit vectors in the SKY frame, the globe's own axes with the
// sky fixed: north = +y, right ascension 0 = +z, right ascension 90° = +x
// (the same way the globe counts longitude: 0 = +z, 90° east = +x).
// The page turns the sky frame into the globe's frame with skyTurn(): a star
// at right ascension α stands over longitude α − GMST.

const RAD = Math.PI / 180;
const J2000 = 2451545.0;
export const SIDEREAL_DAY = 86164.0905;   // seconds for one turn of the Earth against the stars

export const julian = (ms) => ms / 86400000 + 2440587.5;

// Greenwich mean sidereal time, in radians: how far the Earth has turned.
export function gmst(ms) {
  const d = julian(ms) - J2000;
  return (((280.46061837 + 360.98564736629 * d) % 360) + 360) % 360 * RAD;
}

// Right ascension / declination (radians) → a unit vector in the sky frame.
export function fromRaDec(ra, dec, out = [0, 0, 0]) {
  out[0] = Math.cos(dec) * Math.sin(ra);
  out[1] = Math.sin(dec);
  out[2] = Math.cos(dec) * Math.cos(ra);
  return out;
}

// Ecliptic longitude/latitude (radians) → sky-frame vector, tilting by the
// Earth's axial tilt `eps`.
function fromEcliptic(lam, beta, eps) {
  const x = Math.cos(beta) * Math.cos(lam);
  const y = Math.cos(beta) * Math.sin(lam);
  const z = Math.sin(beta);
  const eqX = x;                                        // toward the March equinox
  const eqY = y * Math.cos(eps) - z * Math.sin(eps);    // 90° east along the equator
  const eqZ = y * Math.sin(eps) + z * Math.cos(eps);    // north
  return [eqY, eqZ, eqX];
}

const tilt = (d) => (23.439 - 0.0000004 * d) * RAD;

// The Sun's direction from the Earth.
export function sunDir(ms) {
  const d = julian(ms) - J2000;
  const L = 280.460 + 0.9856474 * d;
  const g = (357.528 + 0.9856003 * d) * RAD;
  const lam = (L + 1.915 * Math.sin(g) + 0.020 * Math.sin(2 * g)) * RAD;
  return fromEcliptic(lam, 0, tilt(d));
}

// The Moon's direction from the Earth's centre.
export function moonDir(ms) {
  const d = julian(ms) - J2000;
  const T = d / 36525;
  const s = (a, b) => Math.sin((a + b * T) * RAD);
  const lam = 218.32 + 481267.881 * T
    + 6.29 * s(135.0, 477198.87) - 1.27 * s(259.3, -413335.36)
    + 0.66 * s(235.7, 890534.22) + 0.21 * s(269.9, 954397.74)
    - 0.19 * s(357.5, 35999.05) - 0.11 * s(186.5, 966404.03);
  const beta = 5.13 * s(93.3, 483202.02) + 0.28 * s(228.2, 960400.89)
    - 0.28 * s(318.3, 6003.15) - 0.17 * s(217.6, -407332.21);
  return fromEcliptic(lam * RAD, beta * RAD, tilt(d));
}

// A sky-frame vector → latitude/longitude (degrees) of the spot on Earth
// where it stands straight overhead at time `ms`.
export function overhead(vec, ms) {
  const lat = Math.asin(Math.max(-1, Math.min(1, vec[1]))) / RAD;
  let lon = (Math.atan2(vec[0], vec[2]) - gmst(ms)) / RAD;
  lon = ((lon + 540) % 360) - 180;
  return { lat, lon };
}

// How lit the Moon looks from Earth: 0 = new, 1 = full.
export function moonLit(ms) {
  const s = sunDir(ms);
  const m = moonDir(ms);
  const cos = s[0] * m[0] + s[1] * m[1] + s[2] * m[2];
  return (1 - cos) / 2;
}

// A star's colour from its B−V index (blue-white to orange), as linear RGB.
const BV_RAMP = [
  [-0.4, [0.58, 0.68, 1.00]],
  [0.0, [0.78, 0.85, 1.00]],
  [0.4, [1.00, 0.97, 0.93]],
  [0.8, [1.00, 0.90, 0.74]],
  [1.2, [1.00, 0.78, 0.56]],
  [2.0, [1.00, 0.62, 0.38]],
];
export function starColor(bv) {
  if (bv <= BV_RAMP[0][0]) return BV_RAMP[0][1];
  for (let i = 1; i < BV_RAMP.length; i += 1) {
    const [b1, c1] = BV_RAMP[i];
    if (bv <= b1) {
      const [b0, c0] = BV_RAMP[i - 1];
      const t = (bv - b0) / (b1 - b0);
      return c0.map((v, k) => v + (c1[k] - v) * t);
    }
  }
  return BV_RAMP[BV_RAMP.length - 1][1];
}
