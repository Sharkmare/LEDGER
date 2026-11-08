# Changelog

Generated from commit subjects by `tools/changelog.py` when a release is cut. Do not edit it by hand: a subject's first word picks its heading (see CONTRIBUTING.md).

## 1.4.0 (2026-11-08)

### Added

- Add dashboard modules loaded from a modules folder at launch (`36ae8f7`)

### Changed

- Move tagGroups into its own module and test it under Node (`23721f1`)
- Move the sidebar section builder into its own module and test it (`48e5a1b`)
- Move the widget form converters into their own module and test them (`ca10e1d`)
- Move the roadmap layout math into its own module and test it (`7e3c594`)
- Move the editor list and format rules into their own tested module (`e58dbc6`)
- Share one tested HTML escape function across the pages (`03ad5a6`)
- Move the summary counts, filter choices and name colours into modules (`453abfd`)
- Move the relative time wording and wiki link matching into modules (`64bc61f`)
- Load the shared escape in Node without a second name for it (`2df0189`)
- Move the dashboard chart drawing into its own module and test it (`482c372`)
- Move page tree reordering and area descendants into a tested module (`0074b25`)
- Find area descendants whatever order the areas arrive in (`8cad28c`)
- Move the API reference schema helpers into a tested module (`72a180b`)
- Move the ticket list filter building into its own tested module (`65a21ac`)
- Move the administration form markup into its own tested module (`6ef1c98`)
- Move the knowledge base page helpers into their own tested module (`b4231f0`)
- Move the board rule chips and progress bar into a tested module (`f0a4398`)

## 1.3.0 (2026-11-07)

### Added

- Add hidden ticket types per person and a distinct Cancelled color (`e7edd9b`)
- Add hidden board columns per person for every status (`28da581`)
- Add an assignee registry with lowercase names and a personal queue (`0b8f242`)
- Add per person hidden types, hidden columns and sort on the server (`f51054e`)
- Add bulk ticket changes in the API, CLI and list view (`a2dee44`)
- Show similar open tickets when creating one, in the CLI and UI (`54b11c2`)
- Add closing rules and advisory work in progress limits (`d5402f5`)
- Add a dependency view with blocker chains and an epic critical path (`d6e72f3`)

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
