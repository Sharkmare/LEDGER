# Changelog

Generated from commit subjects by `tools/changelog.py` when a release is cut. Do not edit it by hand: a subject's first word picks its heading (see CONTRIBUTING.md).

## 1.2.0 (2026-11-06)

### Added

- Add open questions on tickets, answered from the ticket drawer (`9fc2683`)

### Changed

- Speed up writes by running the database in WAL mode (`8ad2bef`)

### Fixed

- Stop the KB tree from asking a space for another space's folders (`bb3df94`)
- Stop the KB tree refresh from re-opening folders the reader closed (`bf76d29`)
- Stop the refresh from redrawing unchanged pages and interrupting drags (`1936b18`)
- Fix the sidebar section arrows shifting when a section collapses (`3a79f9b`)

## 1.1.0 (2026-11-06)

### Added

- Add tags to projects, grouped in the navigator and in metrics (`e77dad5`)
- Add tags to areas and group the area navigator by them (`f035405`)
- Show the sort control on board pages (`36b505f`)
- Add translations to knowledge base pages, shown as a language bar (`05a671a`)

### Changed

- Collapse areas in the navigator and show section counts (`65b6293`)
- Sort lists and boards by key, status, priority and more (`a21f6fc`)
- Filter from the list headings, with chips for the active filters (`4613d0f`)
- Generate the changelog from commit subjects when a release is cut (`9460b07`)
- Index KB title and parent lookups and resolve page links in batches (`0b40d74`)
- Load KB folders on demand and bound long sub-page lists (`870888f`)
- Search the knowledge base from the top search box on KB pages (`dfc23da`)

### Fixed

- Keep scroll positions when the view refreshes (`37e012a`)
- Keep the KB tree scroll position when pages open and refresh (`1368a48`)

## 1.0.0 (2026-11-05)

No changes recorded.
