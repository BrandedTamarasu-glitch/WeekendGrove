# Discover: first local version

Discover lives inside Weekend Grove. Suggestions remain in a review inbox until Save adds one to the ordinary idea bank. Dismiss persists across refreshes. Existing ideas are never reseeded or overwritten by discovery.

## Setup and behavior

- ZIP starts blank. Choose a five-digit US ZIP, local radius (default 30 miles), and optional day-trip radius (default 100 miles). Both are configurable up to 150 miles.
- Distances approximate a straight line between the chosen ZIP center and the venue ZIP center. They are not driving distance, travel time, or precise address distance.
- Public lookup consent and weekly refresh both start off. Saving settings alone does not run a lookup. Refresh now requires consent. Weekly scheduling defaults to Thursday 08:00 in the configurable timezone; choose and save the intended timezone before enabling.
- A persisted job tracks start/completion, next run, additions, and skipped records. A database lease prevents duplicate workers. Missed schedules catch up once after downtime. Manual refresh is limited to once every five minutes. No retry loop on provider failures.
- Only the city community-events source below is enabled. Other regions, restaurants, and places have no discovery provider in this release. Empty results do not imply no nearby options.
- Suggestions include source URL, checked date, event date/time, distance, and Local/Day trip label. Cost, visit duration, effort, family/teen suitability and accessibility remain unknown unless the user supplies details. Check the original event page before attending.
- Choose an actual Saturday in the planner. An event can only be placed on a matching unexpired Saturday/Sunday, including locked suggestions and plan saving. Historical snapshots keep their original dates. The planner does not resolve clock-time conflicts or travel routes.
- Changing ZIP changes future refreshes. Inbox history and saved ideas retain their original distance estimates. Saved ideas are user-owned; later source refreshes do not rewrite them. Source cancellations or rescheduling after saving require checking the original listing.

## Verified sources and outbound disclosure

1. [Zippopotam.us](https://docs.zippopotam.us/docs/getting-started/): HTTPS `api.zippopotam.us/us/{ZIP}`. Receives the selected ZIP and the public venue ZIP. Coordinates are cached in SQLite for 30 days. This free API uses GeoNames data; show attribution to [GeoNames](https://www.geonames.org/), [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/). No API key.
2. [City of Stanwood subscriptions](https://stanwoodwa.org/iCalendar.aspx): the Events category's published HTTPS iCalendar feed, `https://stanwoodwa.org/common/modules/iCalendar/iCalendar.aspx?catID=27&feed=calendar`. The city receives a generic feed request only when the source's venue ZIP falls within range. Only individual occurrences with a recognized venue ZIP and usable dates enter the inbox. Recurrences, cancelled records, missing locations and unsupported dates are skipped. Attribution and the original event link are displayed; descriptions and images are not copied.

Both providers see the server's public IP. Ideas, saved plans, household details, ages and health information are never sent. The local interface stays on its existing host/port. External services are queried by the Python server; the browser does not load external scripts or images.

Validated October 5, 2026 with the actual bounded client: a generic example ZIP returned one place; the Events feed returned six occurrences. Public Overpass probes returned 406/504 or timeout; no places adapter is enabled. Visit Skagit Valley returned 403 to a direct read and is not integrated. No bot blocking was bypassed.

## Implementation and limits

Python standard library only: `urllib.parse`, `http.client`, `ssl`, `socket`, `zoneinfo`, threads and SQLite. The Dockerfile installs Debian `tzdata` and `ca-certificates` for reliable timezone/TLS support; no new Python package, account, credential, sidecar or host cron job is needed. A scheduler thread checks persisted state every 30 seconds but performs no external work while disabled.

Only hardcoded provider endpoints are fetched. HTTPS is certificate-verified, resolved IPs must all be public, the selected IP is pinned to the TLS connection, and redirects are rejected. DNS, socket time, total refresh time, response size (1 MiB), event count (500), lookahead (90 days), and stored inbox history (1,000 records) are bounded. Responses render as escaped plain text. Settings changes invalidate the active job; no subsequent requests or candidate writes occur after permission revocation is observed. An already-sent request cannot be recalled.

The initial source is intentionally regional. New providers need successful direct validation, appropriate attribution/terms, offline parser tests, bounded requests, and updated user-facing disclosure before enabling. Do not silently substitute a blocked provider or an unapproved credentialed service.

## Storage, migration, and recovery

On first upgrade, existing databases without provenance get `before-upgrade-v5.sqlite3` using SQLite's backup API before schema changes. The existing bind mount and user IDs stay the same. Take a fresh off-server backup before any production upgrade as well.

Version 5 JSON preserves idea provenance, dated plan snapshots, discovery preferences and Save/Dismiss decisions. Versions 1–4 still import. Restore validates the complete file before a transactional additive merge. Existing records and decisions win. A separate checkbox can restore discovery preferences, always with consent and weekly refresh disabled. Operational job leases and ZIP caches are not in JSON; the full SQLite backup retains them. Treat database backup restoration as operational recovery: review discovery consent/scheduling before starting a restored service.

No automated deletion occurs at the history limit; the status reports that new records were withheld. JSON remains subject to the existing 2 MiB restore limit; use full database backups for larger banks.

## Local verification

Run `python3 -m unittest discover -s tests -v`, `python3 -m compileall -q server.py discovery.py`, `node --check static/app.js`, `node --check static/discovery.js`, and `git diff --check` locally. Tests use temporary databases and mocked providers; HTTP integration uses localhost only. GitHub Actions is not configured.

Before production: review the local preview, approve the exact outbound data/providers above, back up live state, build/test the updated image, then apply a pinned image update without changing the existing LAN binding or storage. A container build has not been validated on this workstation because Docker is unavailable.
