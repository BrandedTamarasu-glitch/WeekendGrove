# Discover: local review version

Discover lives inside Weekend Grove. Suggestions remain in a review inbox until Save adds one to the ordinary idea bank. Dismiss persists across refreshes. Existing ideas are never reseeded or overwritten by discovery.

## Setup and behavior

- ZIP starts blank. Choose a five-digit US ZIP, local radius (default 30 miles), and optional day-trip radius (default 100 miles). Both are configurable up to 150 miles.
- Distances approximate a straight line from the chosen ZIP center to provider venue coordinates (or a venue ZIP center for the city feed). They are not driving distance, travel time, or precise address distance.
- Public lookup consent and weekly refresh both start off. Saving settings alone does not run a lookup. Refresh now requires consent. Weekly scheduling defaults to Thursday 08:00 in the configurable timezone; choose and save the intended timezone before enabling.
- A persisted job tracks start/completion, next run, additions, and skipped records. A database lease prevents duplicate workers. Missed schedules catch up once after downtime. Manual refresh is limited to once every five minutes. No retry loop on provider failures.
- The city source works without keys. Geoapify restaurants/places and Ticketmaster family-classified events are implemented but inactive until the server owner supplies keys and the user grants each provider separate permission. No credentialed live calls have been validated. Empty results do not imply no nearby options.
- Suggestions include source URL, checked date, event date/time, distance, and Local/Day trip label. Cost, visit duration, effort, family/teen suitability and accessibility remain unknown unless the user supplies details. Check the original event page before attending.
- Choose an actual Saturday in the planner. An event can only be placed on a matching unexpired Saturday/Sunday, including locked suggestions and plan saving. Historical snapshots keep their original dates. The planner does not resolve clock-time conflicts or travel routes.
- Changing ZIP changes future refreshes. Inbox history and saved ideas retain their original distance estimates. Saved ideas are user-owned; later source refreshes do not rewrite them. Source cancellations or rescheduling after saving require checking the original listing.

## Verified sources and outbound disclosure

1. [Zippopotam.us](https://docs.zippopotam.us/docs/getting-started/): HTTPS `api.zippopotam.us/us/{ZIP}`. Receives the selected ZIP and the public venue ZIP. Coordinates are cached in SQLite for 30 days. This free API uses GeoNames data; show attribution to [GeoNames](https://www.geonames.org/), [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/). No API key.
2. [City of Stanwood subscriptions](https://stanwoodwa.org/iCalendar.aspx): the Events category's published HTTPS iCalendar feed, `https://stanwoodwa.org/common/modules/iCalendar/iCalendar.aspx?catID=27&feed=calendar`. The city receives a generic feed request only when the source's venue ZIP falls within range. Only individual occurrences with a recognized venue ZIP and usable dates enter the inbox. Recurrences, cancelled records, missing locations and unsupported dates are skipped. Attribution and the original event link are displayed; descriptions and images are not copied.

All enabled providers see the server's public IP. Ideas, saved plans, household details, ages and health information are never sent. The local interface stays on its existing host/port. External services are queried by the Python server; the browser does not load external scripts or images.

Validated October 5, 2026 with the actual bounded client: a generic example ZIP returned one place; the Events feed returned six occurrences. Earlier public Overpass probes returned 406/504 or timeout; that provider is not integrated. Visit Skagit Valley returned 403 to a direct read and is not integrated. No bot blocking was bypassed.

## Implementation and limits

Python standard library only: `urllib.parse`, `http.client`, `ssl`, `socket`, `zoneinfo`, threads and SQLite. The Dockerfile installs Debian `tzdata` and `ca-certificates` for reliable timezone/TLS support; no new Python package, account, credential, sidecar or host cron job is needed. A scheduler thread checks persisted state every 30 seconds but performs no external work while disabled.

Only hardcoded provider endpoints are fetched. HTTPS is certificate-verified, resolved IPs must all be public, the selected IP is pinned to the TLS connection, and redirects are rejected. DNS, socket time, total refresh time, response size (1 MiB), event count (500), lookahead (90 days), and stored inbox history (1,000 records) are bounded. Responses render as escaped plain text. Settings changes invalidate the active job; no subsequent requests or candidate writes occur after permission revocation is observed. An already-sent request cannot be recalled.

The city source is regional. The credentialed adapters below were tested with mocked responses only. Live validation requires user-operated key setup, provider terms review and explicit outbound permission. Do not silently substitute a blocked provider or an unapproved credentialed service.

## Storage, migration, and recovery

On first upgrade, existing databases without provenance get `before-upgrade-v5.sqlite3` using SQLite's backup API before schema changes. The existing bind mount and user IDs stay the same. Take a fresh off-server backup before any production upgrade as well.

Version 5 JSON preserves idea provenance, dated plan snapshots, discovery preferences and Save/Dismiss decisions. Versions 1–4 still import. Restore validates the complete file before a transactional additive merge. Existing records and decisions win. A separate checkbox can restore discovery preferences, always with all three consent switches and weekly refresh disabled. Operational job leases and ZIP caches are not in JSON; the full SQLite backup retains them. Treat database backup restoration as operational recovery: review discovery consent/scheduling before starting a restored service.

No user ideas or decision identities are deleted at the history limit; the status reports that new records were withheld. JSON remains subject to the existing 2 MiB restore limit; use full database backups for larger banks.

## Local verification

Run `python3 -m unittest discover -s tests -v`, `python3 -m compileall -q server.py discovery.py discovery_providers.py`, `node --check static/app.js`, `node --check static/discovery.js`, and `git diff --check` locally. Tests use temporary databases and mocked providers; HTTP integration uses localhost only. GitHub Actions is not configured.

Before production: review the local preview, approve the exact outbound data/providers above, back up live state, build/test the updated image, then apply a pinned image update without changing the existing LAN binding or storage. A container build has not been validated on this workstation because Docker is unavailable.


## Optional Geoapify and Ticketmaster adapters

Geoapify receives the selected US ZIP for a postcode-only geocode, then its approximate center, the requested radius and two category groups: restaurants; museums/zoos/parks. A refresh makes at most three Geoapify requests, with at least 0.51 seconds between them, each places response limited to 20. There is no pagination or detail-call fan-out. Results must match the ZIP/country, have usable coordinates and names, and pass the local distance check. Places have no event dates or invented cost/duration. Stable provider IDs deduplicate the inbox. Linked Geoapify and OpenStreetMap attribution remains on the Discover view, and each place links to a public venue map. No raw response, description, image or contact-detail archive is kept. Normalized place facts and user decisions remain local.

References: [Geoapify geocoding](https://apidocs.geoapify.com/docs/geocoding/forward-geocoding/), [Places API](https://apidocs.geoapify.com/docs/places/), [Geoapify Places overview and attribution](https://www.geoapify.com/places-api/). These sources describe caching support; review the account plan and current terms before enabling. The implementation does not purchase service or promise a permanent free quota.

Ticketmaster receives a ZIP-center geohash, radius, US filter and a 90-day date window. One request per refresh returns at most 100 events, with `includeFamily=only`; the parser also requires an explicit family classification, an on-sale status, a definite local date/timezone, and an in-range venue. Cancelled, postponed, rescheduled, unknown-family, unknown-date and explicit adult-only records are omitted. This is incomplete coverage, not a guarantee of family/teen suitability or availability. Event duration/end time and price remain unknown. Original Ticketmaster links and attribution are shown. A successful refresh clears pending facts not returned by that bounded response without calling their absence a cancellation.

References: [Ticketmaster Discovery API](https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/), [API terms](https://developer.ticketmaster.com/support/terms-of-use/). Terms do not provide a blanket fixed retention entitlement. The app uses a conservative **24-hour inbox cache**, clearing normalized provider payloads during access and scheduler ticks while keeping content-free identities and Save/Dismiss decisions. When the app is stopped, cleanup occurs on next access/tick. Saved ideas and saved plans are explicit user snapshots and are not automatically rewritten or deleted. They may become inaccurate; check the original listing before planning. Saved snapshots still contain provider Event Content; explicit Save does not exempt them from provider terms. Retained snapshots/backups still need handling if a provider requests removal; do not activate unless the owner accepts that responsibility and applicable terms. No raw payloads, images or descriptions are archived.

New source consent defaults to off when upgrading an existing local version. Keys alone do not authorize requests. Global public-lookup permission is also required. Settings changes invalidate the in-flight token, so subsequent requests and result writes stop; a request already sent cannot be recalled. Missing or invalid keys appear as inactive, without revealing values. Exceptions, API responses and query strings are not written to job status or logs. A five-minute persisted manual cooldown and one worker lease bound repeated activity; failures are not retried automatically within a run. The existing 60-second whole-refresh and 1 MiB per-response limits apply across providers.

## Secure key setup — user operated, after an approved upgrade

Production remains on the stable image; these steps are for a later explicitly approved Discover deployment. Do not paste keys into chat, source files, Docker commands, the browser application, or `.env` files in the repository. No accounts, terms acceptance, credentials or billable plans have been created by this implementation.

1. The owner separately creates/reviews each provider account and plan on its official site and accepts any applicable terms. Start with Geoapify; Ticketmaster can remain off. Do not assume the plan is free or auto-upgrade it.
2. Use the server's existing trusted **local console** to create private secret files under `/mnt/disk2/appdata/weekend-grove/secrets`. The current Unraid management URL is plain HTTP: do not type secret values into that page. No SSH enablement, new access path or network change is required by this design. If a trusted local console is unavailable, stop for an approved secure entry route.
3. For example, run this yourself on that console. It hides input, does not put the value in shell history or a command argument, and uses the app's UID/GID. Do not screen-share or record key entry:

```bash
(
  set +x
  umask 077
  grove_dir=/mnt/disk2/appdata/weekend-grove/secrets
  [[ $EUID == 0 && -t 0 && ! -L "$grove_dir" ]] || exit 1
  install -d -m 700 -o 10001 -g 10001 "$grove_dir" || exit 1
  [[ ! -e "$grove_dir/geoapify.key" && ! -L "$grove_dir/geoapify.key" ]] || {
    printf 'Key file already exists; nothing changed.\n'; exit 1;
  }
  grove_tmp=$(mktemp "$grove_dir/.geoapify.XXXXXXXX") || exit 1
  trap 'unset grove_geo_key; rm -f -- "$grove_tmp"' EXIT
  read -r -s -p 'Geoapify key: ' grove_geo_key || exit 1
  printf '\n'
  [[ $grove_geo_key =~ ^[A-Za-z0-9_-]{8,256}$ ]] || {
    printf 'Key format was not accepted.\n'; exit 1;
  }
  printf '%s' "$grove_geo_key" > "$grove_tmp" || exit 1
  unset grove_geo_key
  chown 10001:10001 "$grove_tmp" && chmod 600 "$grove_tmp" || exit 1
  ln -- "$grove_tmp" "$grove_dir/geoapify.key" || exit 1
  printf 'Geoapify key file installed privately. Searches remain off.\n'
)
```

For Ticketmaster, repeat with `grove_ticket_key`, prompt `Ticketmaster key: ` and filename `ticketmaster.key`. Skip it if not enabling that provider. The snippet refuses an existing destination (including a symlink) and atomically links a new private file without replacing anything. It disables shell tracing before reading; input is masked, not entered as a shell command. It requires an interactive root Bash console. Do not run it in a recorded or shared terminal.

4. In the native Unraid template for the approved new image, add a **Variable** named/keyed `GEOAPIFY_API_KEY_FILE`, value `/data/secrets/geoapify.key`. For Ticketmaster add `TICKETMASTER_API_KEY_FILE`, value `/data/secrets/ticketmaster.key`. These values are file paths, not secrets. Preserve all current Extra Parameters, image pinning, LAN binding, mount and security controls. The existing `/data` mount already includes these files; no additional bind or exposed port is needed. The app accepts only regular, non-symlink files owned by its UID with no group/other permissions, and rejects oversized or malformed keys.
5. After the approved image update and scoped restart, Discover should say **key configured · permission off**. Review the exact outgoing data in Location & weekly refresh. Grant the global public-lookup permission and only the intended provider permission, save settings, then explicitly request the first refresh. Weekly refresh may remain off. Verify real provider behavior and quota before enabling any schedule.

Direct `GEOAPIFY_API_KEY` / `TICKETMASTER_API_KEY` environment variables also work for controlled deployments, but are discouraged in this installation because Unraid templates and Docker inspection can retain/reveal them. `_FILE` takes precedence and fails closed if unreadable. Secret files are excluded from app JSON exports and SQLite backups (which contain database data only). Protect and back up secrets separately if needed; never include them in a support bundle. Revoking UI permission stops later lookups; removing/revoking a provider key is the owner's separate action.
