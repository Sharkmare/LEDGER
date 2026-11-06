# LEDGER

A small ticket tracker and knowledge base for solo developers and small teams: tickets, boards, planning, dashboards, pages and a catalogue of tools, with a command line for all of it. One Python process, one SQLite file, no dependencies beyond the Python standard library. No accounts, no cloud, no build step.

## Run it

```bash
python -m ledger.server
```

Python 3.10 or newer. Nothing to install. Ranked search uses SQLite's full-text engine when the build has it (standard builds do) and falls back to plain matching when not.

Open http://127.0.0.1:6680/. The server listens on loopback only. Data lives in `data/ledger.db`, a single file you can copy to back up. A fresh database starts with an organisation name, five ticket templates and two dashboards.

| Option | Flag | Environment variable |
|---|---|---|
| Port | `--port` | `LEDGER_PORT` |
| Database file | `--database` | `LEDGER_DB` |
| Font directory | | `LEDGER_FONT_DIR` |

## How work is organised

```
Organisation
  Projects          own tickets, named APP-1, APP-2 ... (numbers are never reused)
  Areas             group related work, can nest (Platform / Tools)
    Boards          show tickets by rule, plus anything pinned to them
  Iterations        time boxes inside a project (sprints)
Tickets             any type, with a parent and sub-tickets to any depth
```

- **Tickets** have a title, description, type, status, priority, assignee, tags, parent, area, iteration, estimate, start and due date, links, comments and a history that records who changed what. Types: task, bug, feature, epic, story, spike, chore. Statuses: backlog, todo, in_progress, in_review, blocked, done, cancelled. An epic shows progress over everything under it.
- **Areas** hold boards. A ticket can sit in one area.
- **Project and area tags** group projects and top-level areas in the navigator, one foldable heading per tag (an item with several tags is listed under each). List projects with `projects --tag NAME`, and break dashboards down with the `project_tag` grouping. These are separate from ticket tags (labels).
- **Boards** belong to an area. A board holds the tickets of its area and sub-areas that match its rules, plus pinned tickets. Rules: scope (this area, or any area), project, types, priorities, tags, assignee, "under this ticket", iteration. A board can show a chosen set of status columns.
- **Iterations** have dates, a goal and a state (planned, active, done). The Plan view puts the backlog beside the iterations; drag a ticket onto one to plan it. The Roadmap lays iterations and dated epics on a timeline.
- **Tags** are free text on tickets. Register one to give it a colour and description, rename it everywhere, merge two, or delete one.
- **Templates** pre-fill the Create ticket dialog: type, priority, status, a description outline, tags, estimate.
- **Dashboards** are sets of widgets: counts with change against the previous period, breakdowns (bars or donut) by status, type, priority, assignee, tag, project, area or iteration, created and closed trends, burndown, lead and cycle time, age of open work, workload per person, velocity, overdue work. Every widget can filter by project, area, type, priority, assignee, tag and open work. Edit a dashboard to add, move, change or remove widgets, or make a new one.

## Knowledge base

Pages live in spaces. A space holds a tree of pages you can reorder by dragging, and every page is written in Markdown with a live preview.

- **Reading**: clean text with a contents list, the tickets a page mentions, the pages that link to it, previous and next page, and a Was this helpful? question that asks what was missing when the answer is no.
- **Writing**: a toolbar and shortcuts (Ctrl B, Ctrl I, Ctrl L, Ctrl S), list continuation, `[[` suggests page titles, drafts are kept in the browser until you save, and a new page can start from a template (how-to, runbook, decision record, meeting notes, reference).
- **Links**: `[[Page title]]` links to a page, and a title that does not exist yet shows as a link that creates it. `APP-12` links to a ticket, and a ticket lists the pages that mention it.
- **Translations**: a page can be a translation of another page in the same space (`translation_of` and a `locale` such as `ja` in the API). Translations stay out of page lists, the tree and the space's page count, and every page in a set shows a language bar linking the others. Pass `translations=1` to list them.
- **History**: every save is a version with an author and an optional note; compare any version with the one before and restore it.
- **Trust**: verify a page to say it is still right and set when it should be looked at again. Pages past their review date are flagged and listed.
- **Find**: Ctrl K searches pages, tools and tickets at once, ranked, with matches highlighted, and jumps to any area, board, dashboard or setting.

### Tools

The Tools category is a catalogue of programs and services: command line tools and scripts on this machine, and APIs and services elsewhere. A tool page shows what it is, how to run it with copy buttons, its commands, and notes. Give it an OpenAPI description and the page lists every endpoint with parameters, request and response examples, a filter, and a try-it panel.

The description can be pasted JSON, a file on this machine (`.json`, `.yaml`, `.yml`), or an address. A file or address is fetched once and cached; Fetch again refreshes it, and if a later fetch fails the cached copy stays visible with the reason. YAML is read by a small built-in reader that covers what OpenAPI files use and says so plainly when it meets something it does not support.

## Web interface

A top bar with global search, Create, refresh, shortcuts, theme and a profile menu where you set the name recorded in history. A side navigator with a filter box lists saved views, the organisation's areas and boards, projects, planning, dashboards and administration. Administration manages the organisation, projects, areas, boards, iterations, tags and templates in one place. Lists and boards sort by key (in number order, so REO-2 comes before REO-10), title, status, priority, type, assignee, estimate or updated, from the column headings or the Sort control on the tickets page and on board pages, and the choice is remembered. Filters live in the list headings: the arrow beside Status, Priority, Type, Assignee or Tags opens a menu of values, and the Status menu also hides done work. Above a board the same menus are chips. Active filters show as chips you can clear one by one or all at once. There is a light and a dark theme and the page refreshes itself every few seconds. On a narrow screen the navigator slides in.

Press `?` for the shortcuts: `c` create, `/` search, `s` `b` `l` for the views, `n` to show or hide the navigator, `r` refresh, `Enter` opens the focused ticket, `Esc` closes the drawer. A ticket opens directly from `http://127.0.0.1:6680/#APP-1`, and Ctrl K finds anything. The API reference with try-it-out is at `/docs`.

## Command line

`ledger_cli.py` uses only the standard library. Add `--json` to any command for machine output. Set your name with `--as NAME` or `LEDGER_ACTOR`; it defaults to your system user name. Point at another server with `--base` or `LEDGER_URL`. `python ledger_cli.py --help` lists every command.

```bash
python ledger_cli.py new-project APP "My app" --tags games
python ledger_cli.py projects --tag games
python ledger_cli.py project-set APP --tags games,tools
python ledger_cli.py add APP "Login fails on empty password" --type bug --priority high --labels auth
python ledger_cli.py add APP "Crash on start" --template 1 --area "Platform" --iteration "Sprint 1" --estimate 3
python ledger_cli.py list --project APP --open
python ledger_cli.py list -q login --area Platform
python ledger_cli.py mine
python ledger_cli.py show APP-1
python ledger_cli.py move APP-1 in_progress
python ledger_cli.py done APP-1 --comment "Fixed in the next release"
python ledger_cli.py tree APP-1

python ledger_cli.py area add Platform --tags tools
python ledger_cli.py area set 1 --tags tools
python ledger_cli.py board add Platform Bugs --types bug --labels auth
python ledger_cli.py board pin 1 APP-12
python ledger_cli.py iteration add APP "Sprint 1" 2026-11-09 2026-11-20 --goal "Ship login"
python ledger_cli.py plan APP
python ledger_cli.py roadmap --project APP
python ledger_cli.py tag rename auth login
python ledger_cli.py tag merge ui interface
python ledger_cli.py template add "Crash report" --type bug --priority high --body "Stack trace:"
python ledger_cli.py dashboard data 1
python ledger_cli.py metric group --group-by assignee --open

python ledger_cli.py kb-space add ENG Engineering
python ledger_cli.py kb-page add ENG "Deploy runbook" --template runbook --labels ops
python ledger_cli.py kb-page edit 4 --body-file notes.md --comment "Add rollback steps"
python ledger_cli.py kb-page diff 4 1 2
python ledger_cli.py kb-search deploy
python ledger_cli.py find deploy
python ledger_cli.py kb-tool add Packer --kind cli --invoke "packer build FILE" --path C:/tools/packer.exe
python ledger_cli.py kb-tool add Pets --kind api --location external --openapi-url https://pets.example.com/openapi.json
python ledger_cli.py kb-tool spec 7
```

## HTTP API

`GET /api` lists the endpoints, `GET /api/meta` lists the allowed values, `GET /api/openapi.json` is an OpenAPI 3 description and `/docs` is an interactive reference. Requests and responses are JSON, errors are `{"error": "..."}` with a 4xx status, and writes accept an `X-Ledger-Actor` header that names who made the change. A ticket created with a `source` value, such as `github:123`, can be found again with `GET /api/tickets?source=github:123` and cannot be created twice, which makes importers safe to re-run. `GET /api/tickets` returns at most `limit` tickets (default 500) and reports the full count in the `X-Total-Count` header.

## Fonts

The interface uses the system font stack. To use other fonts, put a `fonts.css` in the font directory (`fonts/` next to the code, or `LEDGER_FONT_DIR`) that sets `--ledger-font-ui`, `--ledger-font-mono`, `--ledger-font-display` and `--ledger-font-icons`, with the font files beside it. An `icons.json` mapping names such as `status_done` and `type_bug` to code points adds icons. Nothing is required.

## Layout

| Path | Purpose |
|---|---|
| `ledger/store.py` | Schema, validation and ticket logic |
| `ledger/organise.py` | Organisation, areas, boards, iterations, plan and roadmap |
| `ledger/manage.py` | Tags and templates |
| `ledger/metrics.py` | Metrics, widgets and dashboards |
| `ledger/kb.py` | Spaces, pages, versions, search, tools and their OpenAPI descriptions |
| `ledger/web.py` | The HTTP layer: router, request and response, threaded server, test client |
| `ledger/miniyaml.py` | The YAML reader used for OpenAPI files |
| `ledger/openapi.py` | The OpenAPI description |
| `ledger/server.py` | HTTP server and API |
| `ledger/static/` | The web interface |
| `ledger_cli.py` | Command line client |
| `tools/check_commit_message.py` | The commit message check run by `.githooks/commit-msg` |
| `tests/` | Tests for the store, API, server, command line, planning, metrics, knowledge base, YAML and page renderer |

## Contributing

Read `CONTRIBUTING.md`. Commit messages are one short line; `git config core.hooksPath .githooks` turns on the check.

## Tests

```bash
python -m unittest discover -s tests -v
```

The last tests measure speed and print a report of what is slow; see `tests/test_zz_performance.py`.

## License

MIT. See LICENSE.
