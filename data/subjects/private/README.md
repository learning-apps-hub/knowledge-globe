# Private subject maps

Drop a subject map here and it behaves exactly like a public one on the LAN
app (port 8110) — same API, same viewer, same validation — but it never
reaches the public GitHub Pages site.

Enforced in three independent places (see the repo README, "Private
subjects"): the Pages build filters and then re-scans the artifact,
`tests/pages_build_test.py` asserts the same in CI, and
`scripts/publish_public.sh` strips this whole directory from the derived
`public` branch, so nothing here is ever committed to the public repo.

These files **are** versioned — in the private repo (`origin`) only. That is
the point: private content still gets history and backup.

An id used here may not also exist in `data/subjects/`; the duplicate would
silently shadow one file, so it fails at startup instead.
