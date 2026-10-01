# WeekendGrove

A local, mobile-friendly family idea bank and randomized weekend planner. A prototype with no accounts, cloud services, paid dependencies, telemetry, fonts, or external assets. It uses Python’s standard library, SQLite, and plain HTML/CSS/JavaScript.

## Run locally

Requires Python 3.11 or newer (developed with 3.14).

```sh
git clone https://github.com/BrandedTamarasu-glitch/WeekendGrove.git
cd WeekendGrove
python server.py
```

Open **http://127.0.0.1:8765**. The default server listens only on localhost. Stop it with Ctrl+C. A fresh installation starts empty; “Load generic sample ideas” adds eight clearly labeled generic ideas once. No personal family or health information is in the source or seed data.

## What works

- Capture an idea with only a title and category; optionally add duration, cost, location, and energy.
- Filter Projects, Restaurants, Places, and Activities. Edit, archive, and restore ideas.
- Generate 1–6 ideas within a shared weekend time/budget limit and a maximum energy level per idea. Saturday and Sunday appear in distinct columns on desktop and stacked sections on phones.
- Set separate per-day maximums for Projects, Restaurants, Places, and Activities (0–6 each, initially 1). Maximums do not require every category or day to be filled. Locked ideas keep their day and must fit its category caps.
- Optionally include random Lazy Day time, off initially. The planner reserves up to one 30- or 60-minute relaxation block per day when it fits, before filling ideas. Blocks cost zero, consume shared weekend time, and use no category quota or idea-count slot. They can be locked, rerolled, and saved without creating database ideas.
- Lock suggestions and reroll the others. Alternatives are preferred where they fit; a small bank can repeat suggestions. No duplicates within a plan.
- Save named plan snapshots, which survive idea edits and server restarts.
- Choose USD (default), CAD, EUR, GBP, AUD, or NZD. Costs and budgets show both a symbol and code; previews and saved plans retain their captured currency.
- Export all ideas (including archived ones) and plans as JSON. Download a consistent SQLite backup.
- Adjust planning estimates for unknown duration, cost, and energy. Each preview and saved plan retains the estimates it used; blank fields stay unknown in the idea bank.
- Preview and restore JSON backups by adding missing records, without replacing existing ideas or plans. Archive only generic demos to begin with your own ideas; editing a demo makes it your own.

## Prototype assumptions

Currency starts at **USD**. Selecting another currency relabels existing idea costs, planning estimates, and the current budget; numeric amounts stay unchanged. There is no conversion or exchange-rate lookup. Existing previews and saved plans keep their captured labels. Older data had no specified currency, so it is marked **USD assumed**; saving your currency choice confirms the bank label, while older saved plans retain their visible assumption. Missing details start with estimates of **60 minutes, $20 USD, medium energy** during planning. Adjust these under “Estimates for unknown details” in the planner; saved snapshots retain their original estimates. Blank cost means unknown, while an explicit 0 means free. Energy is a ceiling per suggestion, not a cumulative energy budget. Time/cost are cumulative across the whole weekend. Enter durations that include travel and preparation if those matter. New plans store actual Saturday/Sunday assignments, though they are still suggestions rather than calendar bookings. Older saved plans did not record day assignments and remain explicitly Day unspecified. Both days share the entered weekend time and budget; there are no separate daily time limits. Category caps and the Lazy Day toggle remain in the current browser form during rerolls and are captured in saved snapshots; a fresh page starts with one per category/day and Lazy Day off. Randomized greedy selection provides a few feasible choices; it does not optimize the fullest possible plan. An empty or restrictive bank can yield fewer suggestions or no match. Locked ideas that no longer fit cause a clear error and keep the current plan visible.

Local household use is the target. There is no authentication, multi-user separation, calendar, opening hours, route planning, weather, automatic backup scheduling, or plan deletion yet. It is not verified for public hosting. Before external access, add authentication, TLS and a reviewed access strategy; do not open ports for this prototype.

## Data and restore

Default data file: `data/weekend.sqlite3`, created automatically. Override its directory with `DATA_DIR=/absolute/path`. Store that directory on persistent disk and back it up. The database is never stored inside the source or a browser’s local storage.

Use **Export JSON** for a portable backup of all ideas, archived/demo flags, saved snapshots, timestamps, and planning estimates. Use **Restore JSON backup**, choose your file, review the additions/skips, and select **Add missing records**. Restores are atomic and additive: existing records with matching stable identifiers stay unchanged, including edits made since the export. Backup estimates and bank currency are only applied if you explicitly check that option. If backup and bank currencies differ, the preview explains which label all idea costs will use and requires an explicit acknowledgment before merging; numeric amounts are never converted. Saved snapshots keep their own currencies. Restoring to a fresh database with that option checked restores the full exported content; local numeric IDs may be remapped when merging. Version 4 exports include day schedules, daily maximums, relaxation blocks, the bank currency, each saved snapshot’s currency, and assumption flags. Version 2–4 repeat restores do not duplicate records. Version 1–3 exports remain supported; version 1/2 costs explicitly assume USD, and all older day assignments remain unspecified; repeats of the exact same older file are idempotent, but separate version 1 exports can create copies because they lack stable identifiers. The importer rejects unsupported/missing fields, invalid values/references/totals, duplicate identifiers/JSON keys, and exports larger than 2 MiB or 2,000 ideas/plans each before any write.

Use **Database backup** for a transaction-consistent SQLite backup. Full database replacement is a separate, potentially destructive recovery action: stop the app, explicitly confirm replacement, make a safety copy, replace `weekend.sqlite3`, preserve ownership, and restart. This app never performs that replacement. Backups contain whatever you enter; treat them as household data. The first upgrade from the original schema creates `data/before-upgrade-v2.sqlite3` and adds stable IDs without altering existing idea fields or saved snapshots. The currency upgrade from version 2 creates `data/before-upgrade-v3.sqlite3` before adding currency metadata. Keep those safety copies until you have verified a fresh backup.

## Docker packaging and Unraid preparation

The base Compose configuration still defaults to **127.0.0.1:8765** with a persistent named volume at `/data`. `GROVE_IMAGE`, `GROVE_BIND_IP`, `GROVE_PORT`, and `GROVE_ALLOWED_HOSTS` can be set in a private `.env` copied from [.env.example](.env.example). No GitHub Actions or registry publishing is required.

For a later Unraid deployment, [the installation/recovery guide](docs/unraid.md) covers choosing healthy appdata storage, UID/GID 10001 permissions, explicit home-LAN binding, private migration of current PC records, backups, upgrades, and rollback. [compose.unraid.yaml](compose.unraid.yaml) replaces the named volume with a required existing appdata bind mount and never silently creates a missing directory. Review the rendered configuration before any deployment. No Unraid path, healthy pool, interface IP, or port is assumed.

```sh
# Default local container, after choosing to run it:
docker compose up --build -d

# Validate the future Unraid config after editing a private .env:
docker compose --env-file .env -f compose.yaml -f compose.unraid.yaml config
```

The image runs as UID/GID **10001:10001**, with a read-only root and writable `/data` and temporary `/tmp`. No deployment is performed by this repository. Do not expose this unauthenticated prototype on the internet. Read the guide before running on Unraid or replacing any database.

## Verification

```sh
python -m unittest discover -s tests -v
python -m compileall -q server.py tests
node --check static/app.js
docker compose config --quiet
# Optional isolated Docker persistence/recovery checks:
docker build -t weekend-grove:deployment-review .
python -W error::ResourceWarning tests/container_smoke.py --image weekend-grove:deployment-review
```

The latest validation passed **34 tests**, including daily category maximums, locked day preservation, Lazy Day duration/quotas, no-match constraints, snapshot restart persistence, export/restore, currency handling, and host/origin protections. Desktop and narrow-phone browser checks passed. The Docker image built locally; this does not verify an Unraid deployment. See [verification evidence](docs/verification.md) and [ROADMAP.md](ROADMAP.md) for scope and remaining deployment checks.
