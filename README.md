# LEDGER

A small ticket tracker and knowledge base for solo developers and small teams: tickets, boards, planning, dashboards, pages and a catalogue of tools, with a command line for all of it. One Python process, one SQLite file, no dependencies beyond the Python standard library. No accounts, no cloud, no build step.

## Run it

```bash
python -m ledger.server
```

Python 3.10 or newer. Nothing to install. Ranked search uses SQLite's full-text engine when the build has it (standard builds do) and falls back to plain matching when not.

Open http://127.0.0.1:6680/. The server listens on loopback only. Data lives in `data/ledger.db`, a SQLite file in write-ahead mode. Stop the server and copy `ledger.db` to back up (while it runs, recent commits sit in `ledger.db-wal`, so copy that and `ledger.db-shm` too). A fresh database starts with an organisation name, five ticket templates and two dashboards.

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

- **Tickets** have a title, description, type, status, priority, assignee, tags, parent, area, iteration, estimate, start and due date, links, comments, open questions and a history that records who changed what. Types: task, bug, feature, epic, story, spike, chore. Statuses: backlog, todo, in_progress, in_review, blocked, done, cancelled. An epic shows progress over everything under it. A ticket moves to done only with a comment on it (the counts or the result), either one it already has or `comment` in the same PATCH; A ticket also cannot move to done while an open ticket (not done or cancelled) has a `blocks` link to it; the refusal names the blockers. Cancelling and creating a ticket directly in done are not affected.
- **Work in progress limits** are advisory. `GET /api/wip` returns the limits and the current count per status, `PUT /api/wip/<status>` with `{"limit": 3}` sets one (0 or null clears it) and only in_progress, in_review and blocked may have a limit. Nothing is ever refused: a board column over its limit shows `count / limit` with a red tint.
- **Dependencies** come from `blocks` links. The ticket drawer has a Dependencies section (hidden when there is nothing to show) listing the tickets that block it and the tickets it blocks, however far along the chain, indented by distance with status pills; an epic or any ticket with sub-tickets also shows its critical path, the longest chain of open sub-tickets linked by `blocks`, as `A -> B -> C`. `GET /api/tickets/<KEY>/dependencies` and `python ledger_cli.py deps KEY` return the same.
- **Open questions** are questions a ticket cannot move without. Ask one on the ticket (or when you create it); anyone can answer it in the
  drawer, where each open question has its own answer box (Ctrl+Enter posts). An answered question keeps its answer, who gave it and when, and
  can be reopened or removed. Asking, answering, reopening and removing are all written to the history. Tickets with an unanswered question show a
  `? 2` badge on cards and in the list, and the Open questions item under Work lists only those tickets. Questions are separate from comments, so
  an answer is never lost in a thread.
- **People and the queue.** Assignee names are stored lowercase, so `Ann` and `ann` are one person, and a ticket can only be assigned
  to a registered name. A new database has nobody registered; add people with `person-add NAME` or `POST /api/people`. Assigning an unknown name is
  refused and the message lists the nearest registered names and the command that registers it. A person is removed with `person-rm` or
  `DELETE /api/people/<name>`, which is refused while they have open tickets. The queue is the open tickets assigned to a person. Each row carries
  `reasons`: `assigned` always, plus `review` when the ticket is in `in_review` and `question` when it has an unanswered question; the last two label
  tickets already in the queue and never add others. A name that is not registered has an empty queue. `GET /api/queue?person=NAME` and
  `queue [--person NAME]` return it (the person defaults to the caller); the web interface shows it for the name in the profile menu as My queue in
  the navigator and as a count button in the top bar. The `unassigned` figure in stats counts open tickets only.
- **Hidden board columns** are a setting per person for every status, on every board: open the profile menu and tick the statuses to hide, for example Done
  and Cancelled. The columns are left off the ticket board, area boards and board pages, and a `Hiding Done, Cancelled` chip in the filter bar says so and clears
  them with one click. The tickets stay in list views and counts. The choice follows your name: it is kept on the server
  (see Saved view settings below) and cached in the browser.
- **Hidden ticket types** are a setting per person: open the profile menu (top right) and tick the types to hide, for example chore or spike.
  Hidden types stay out of the board and list views, area pages and board pages, and a `Hiding bug, chore` chip in the filter bar says so and clears
  them with one click. The choice follows your name, like hidden columns. The API takes `exclude_type=bug,chore` on `GET /api/tickets`, which also keeps the
  total count right.
- **Status colors** are chosen so no two statuses look alike. Cancelled is pink, apart from the grey of Backlog, so a cancelled ticket is not
  mistaken for open work; a test fails if two status colors drift too close.
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
- **Large spaces**: the tree loads one folder at a time, starts folded, and pages a long folder 200 at a time (`GET /api/kb/spaces/ID/children`). A page returns its first 100 sub-pages with the total, and its previous and next page directly. Lookups by title, parent and translation are indexed, so a category page with thousands of links opens in milliseconds. The Sub-page picker in the editor searches instead of listing every page.
- **History**: every save is a version with an author and an optional note; compare any version with the one before and restore it.
- **Trust**: verify a page to say it is still right and set when it should be looked at again. Pages past their review date are flagged and listed.
- **Find**: Ctrl K searches pages, tools and tickets at once, ranked, with matches highlighted, and jumps to any area, board, dashboard or setting. On knowledge base pages the search box in the top bar searches the knowledge base, in the space you are reading by default with one click to search every space; clearing the box returns you to where you were.

### Tools

The Tools category is a catalogue of programs and services: command line tools and scripts on this machine, and APIs and services elsewhere. A tool page shows what it is, how to run it with copy buttons, its commands, and notes. Give it an OpenAPI description and the page lists every endpoint with parameters, request and response examples, a filter, and a try-it panel.

The description can be pasted JSON, a file on this machine (`.json`, `.yaml`, `.yml`), or an address. A file or address is fetched once and cached; Fetch again refreshes it, and if a later fetch fails the cached copy stays visible with the reason. YAML is read by a small built-in reader that covers what OpenAPI files use and says so plainly when it meets something it does not support.

## Web interface

A top bar with global search, Create, refresh, shortcuts, theme and a profile menu where you set the name recorded in history. A side navigator with a filter box lists saved views, the organisation's areas and boards, projects, planning, dashboards and administration. Administration manages the organisation, projects, areas, boards, iterations, tags and templates in one place. Lists and boards sort by key (in number order, so REO-2 comes before REO-10), title, status, priority, type, assignee, estimate or updated, from the column headings or the Sort control on the tickets page and on board pages, and the choice is remembered. Filters live in the list headings: the arrow beside Status, Priority, Type, Assignee or Tags opens a menu of values, and the Status menu also hides done work. Above a board the same menus are chips. Active filters show as chips you can clear one by one or all at once. The list view has a checkbox column: tick rows (Shift-click for a range, the header box for every shown row) and a bar appears at the bottom with Move to, Priority, Assign, Add tag, Cancel (asks for an optional reason, added as a comment) and Clear. The selection survives the automatic refresh and is cleared after an action; clicking a row still opens it. There is a light and a dark theme and the page refreshes itself every few seconds. On a narrow screen the navigator slides in.

In the Create ticket dialog, typing a title of eight characters or more shows a "Similar open tickets" list under the title field after a short pause, with each ticket's key, title and status linking to it in a new tab; the list is hidden when nothing is close and never blocks creating the ticket.

Press `?` for the shortcuts: `c` create, `/` search, `s` `b` `l` for the views, `n` to show or hide the navigator, `r` refresh, `Enter` opens the focused ticket, `Esc` closes the drawer. A ticket opens directly from `http://127.0.0.1:6680/#APP-1`, and Ctrl K finds anything. The API reference with try-it-out is at `/docs`.

### Saved view settings

Hidden ticket types, hidden board columns and the list sort follow your name, not the browser. The server keeps them per name (compared in lowercase), so a second browser, a cleared browser or another machine shows the same choices once you enter your name in the profile menu. On load and whenever you change the name, the page asks the server: a value the server has wins and is copied into the browser as an offline cache; a choice that only this browser has is uploaded once, so nothing set before this feature is lost; with neither, the default applies. Changing a setting saves it to the server and the browser, and a toast says if the server refused it. If the server cannot be reached, the browser copy is used silently. Settings need a name: the `anonymous` name is refused. `GET /api/settings` returns your settings, `PUT /api/settings/<key>` with `{"value": ...}` sets one and `DELETE /api/settings/<key>` clears it. The keys are `hidden_types` (a list of ticket types), `hidden_statuses` (a list of statuses) and `sort` (`{"field": "priority", "direction": "desc"}`, with an empty field for the default order). Anything else is refused with a message.

## Command line

`ledger_cli.py` uses only the standard library. Add `--json` to any command for machine output. Set your name with `--as NAME` or `LEDGER_ACTOR`; it defaults to your system user name. Point at another server with `--base` or `LEDGER_URL`. `python ledger_cli.py --help` lists every command. `add` first asks the server for open tickets with a similar title and prints up to three of them to stderr under `Similar open tickets:` as `KEY title (score%)`, then creates the ticket anyway; `--no-similar-check` skips the lookup, and stdout and `--json` output are unchanged.

```bash
python ledger_cli.py new-project APP "My app" --tags games
python ledger_cli.py projects --tag games
python ledger_cli.py project-set APP --tags games,tools
python ledger_cli.py add APP "Login fails on empty password" --type bug --priority high --labels auth
python ledger_cli.py add APP "Crash on start" --template 1 --area "Platform" --iteration "Sprint 1" --estimate 3
python ledger_cli.py add APP "Login fails when empty" --no-similar-check
python ledger_cli.py list --project APP --open
python ledger_cli.py list -q login --area Platform
python ledger_cli.py mine
python ledger_cli.py show APP-1
python ledger_cli.py move APP-1 in_progress
python ledger_cli.py wip                      # work in progress limits and counts
python ledger_cli.py wip-set in_progress 3   # advisory limit; 0 clears it
python ledger_cli.py done APP-1 --comment "Fixed in the next release"   # refused without a comment
python ledger_cli.py bulk APP-1 APP-2 APP-3 --status done --add-label shipped --comment "Released"
python ledger_cli.py --json list --project APP --open --label stale | python ledger_cli.py bulk --keys-from - --status cancelled
python ledger_cli.py add APP "Pick a payment provider" --question "Which provider?" --question "Refunds in v1?"
python ledger_cli.py question ask APP-1 "Which currency first?"
python ledger_cli.py question list --project APP
python ledger_cli.py question answer 3 "Euro"
python ledger_cli.py list --project APP --questions
python ledger_cli.py people
python ledger_cli.py person-add ann
python ledger_cli.py queue
python ledger_cli.py queue --person ann
python ledger_cli.py list --project APP --open --exclude-type chore,spike
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
python ledger_cli.py --as ann setting-set hidden_statuses '["done","cancelled"]'
python ledger_cli.py --as ann settings
python ledger_cli.py --as ann setting-clear hidden_statuses
```

`bulk KEY KEY ...` applies `--status`, `--priority`, `--type`, `--assignee`, `--parent`, `--area`, `--iteration`, `--add-label`, `--rm-label` and `--comment` to every key (at most 200). Keys can also come from standard input with `--keys-from -`, either the output of `list --json` or one key per line. It prints `updated N, unchanged N, failed N` with one line per failed ticket and exits 1 if any ticket failed.

## HTTP API

`GET /api` lists the endpoints, `GET /api/meta` lists the allowed values, `GET /api/openapi.json` is an OpenAPI 3 description and `/docs` is an interactive reference. Requests and responses are JSON, errors are `{"error": "..."}` with a 4xx status, and writes accept an `X-Ledger-Actor` header that names who made the change. A ticket created with a `source` value, such as `github:123`, can be found again with `GET /api/tickets?source=github:123` and cannot be created twice, which makes importers safe to re-run. `GET /api/tickets` returns at most `limit` tickets (default 500) and reports the full count in the `X-Total-Count` header. `GET /api/tickets/similar?project=KEY&title=...&limit=3` returns the open tickets of that project whose title is closest to `title`, best first, each as `{key, title, status, score}` with a score from 0 to 1 and nothing below 0.55; creating a ticket is never refused because of a match.

`POST /api/tickets/bulk` with `{"keys": [...], "changes": {...}, "comment": "..."}` applies the same changes to up to 200 tickets (duplicates are ignored). `changes` takes any field a ticket edit accepts, plus `add_labels` and `remove_labels`, which adjust each ticket's own labels. The comment, if given, is added to every ticket that did not fail, including ones already at the new values. It is not atomic: the reply is `{"updated": [...], "unchanged": [...], "failed": [{"key", "error"}]}` and a failing ticket never stops the others. An empty key list, more than 200 keys, or neither changes nor a comment is refused with 400.

## Fonts

The interface uses the system font stack. To use other fonts, put a `fonts.css` in the font directory (`fonts/` next to the code, or `LEDGER_FONT_DIR`) that sets `--ledger-font-ui`, `--ledger-font-mono`, `--ledger-font-display` and `--ledger-font-icons`, with the font files beside it. An `icons.json` mapping names such as `status_done` and `type_bug` to code points adds icons. Nothing is required.

## Layout

| Path | Purpose |
|---|---|
| `ledger/store.py` | Schema, validation and ticket logic |
| `ledger/organise.py` | Organisation, areas, boards, iterations, plan and roadmap |
| `ledger/manage.py` | Tags and templates |
| `ledger/people.py` | Registered assignees and the per-person queue |
| `ledger/metrics.py` | Metrics, widgets and dashboards |
| `ledger/kb.py` | Spaces, pages, versions, search, tools and their OpenAPI descriptions |
| `ledger/web.py` | The HTTP layer: router, request and response, threaded server, test client |
| `ledger/miniyaml.py` | The YAML reader used for OpenAPI files |
| `ledger/usersettings.py` | Per-person view settings: allowed keys, validation, storage |
| `ledger/openapi.py` | The OpenAPI description |
| `ledger/similar.py` | Finds open tickets with a title close to a new one |
| `ledger/server.py` | HTTP server and API |
| `ledger/static/` | The web interface |
| `ledger_cli.py` | Command line client |
| `tools/check_commit_message.py` | The commit message check run by `.githooks/commit-msg` |
| `tests/` | Tests for the store, API, server, command line, planning, metrics, knowledge base, YAML and page renderer |

## Contributing

Release notes are in `CHANGELOG.md`. Read `CONTRIBUTING.md`. Commit messages are one short line; `git config core.hooksPath .githooks` turns on the check.

## Tests

```bash
python -m unittest discover -s tests -v
```

The last tests measure speed and print a report of what is slow; see `tests/test_zz_performance.py`.

## License

MIT. See LICENSE.
