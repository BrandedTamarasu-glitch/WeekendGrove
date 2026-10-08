# Portable itineraries and automatic backups

Local automated and browser checks passed. Container validation and production deployment remain pending; installation owners must approve their own backup destination and policy.

## Take a weekend with you

Choose **Download / print itinerary** beneath a generated plan or inside a saved weekend. The dialog captures that snapshot immediately; it does not save the plan, reread current ideas into an older plan, or modify any records. Optional notes belong only to this copy and are cleared when the dialog closes.

**Download itinerary** saves a single HTML file with inline styling, no scripts, no external assets and no automatic network requests. Open the file in a browser for offline reading, or use **Print / save PDF** in the app. Print output contains only the itinerary. Phone file-opening behavior depends on the device/browser; this is not a promise that every phone's file preview app renders HTML.

Dates, activities, recorded location text, estimated/known duration and cost, currency, budget and Lazy Day blocks come from the selected snapshot. Older plans with missing dates/day assignments stay explicitly unspecified. Locations are not verified street addresses. Forecasts are not exported. Directions links open Google Maps only when selected, sending that activity's recorded location; no starting location is added by this app. Map service privacy and connectivity apply after opening a link.

The file contains personal trip information. Downloading does not publish it or expose the server outside the LAN. Share it only with intended recipients. Provider facts, including Ticketmaster-derived facts, may have retention/reuse requirements; a portable copy does not resolve those obligations.

## Backup setup requires explicit choices

Scheduling and retention deletion default to **off**. Proposed form defaults are daily **03:00 UTC**, seven successful copies **only if cleanup is later approved**. These are editable suggestions, not an activated policy. The owner must choose the destination, timezone/time, retention and whether deletion is allowed before enabling it.

This scheduler requires Unix file-lock support (including the Linux container); native Windows can still use manual database downloads. The server reads `GROVE_BACKUP_DIR` for an existing, dedicated, writable absolute folder. It refuses symlink paths, the app data directory itself and a `secrets` directory. It does not create a destination or choose an external service. Native Python uses its process account; the container needs the chosen folder writable by UID/GID 10001. Do not apply broad ownership or permission changes to unrelated storage.

For a container, a backup destination must be explicitly mounted. The optional `compose.backups.yaml` requires `GROVE_BACKUP_PATH` and refuses to create a missing host folder. Review the path and mount before applying it. Native Unraid needs an equivalent separately approved mapping and environment setting. No production template changes are part of this preview.

In **Settings → Automatic database backups**, inspect the configured destination. Set daily time, IANA timezone and retention. Enabling scheduling requires its approval checkbox; cleanup requires a separate deletion authorization. Changing the settings clears those approvals. Changing the server destination pauses effective scheduling/cleanup until the new folder is approved. With cleanup off, copies accumulate without a cap; monitor free space.

**Back up now** asks before writing a database copy. If previously authorized cleanup is enabled, the confirmation also says it will run. Status shows last attempt, success, failure, active/interrupted state and cleanup warnings. Refresh status after a lost connection before retrying; a repeated manual request creates another verified copy and never overwrites an earlier one. A missing destination can still be paused in Settings.

## Consistency, ownership and failure behavior

Only SQLite's transaction-consistent backup API is used. Each temporary copy passes `PRAGMA integrity_check`, is flushed, receives a SHA-256 checksum, and is published under a unique filename before being recorded as successful. Files use mode 0600. Concurrent operations use a process/file lock. Busy or interrupted copies have a 30-second backup progress deadline. Failures preserve prior completed copies and do not run retention cleanup.

After a successful copy, explicitly approved cleanup considers only older files recorded by this feature for that exact destination, with matching names and checksums. It never selects manual downloads, migration safety copies, unrelated files or modified copies. Cleanup failures keep affected files and report a warning. A process or power interruption can leave an incomplete temporary file or an unrecorded completed file; those are not automatically deleted. Preserve and inspect them rather than assuming they are recoverable backups.

The app must be running. It checks every 30 seconds, attempts at most one due slot after downtime, and does not repeatedly retry a failed slot. Enabling/changing a schedule waits for its next due time. Spring DST gaps run after the skipped local time; a fall repeated time runs once. Restore tests should keep the isolated instance's discovery/network activity disabled.

Backup controls, approvals, checksums and status live in `backup-control.json` beside the database and are intentionally excluded from JSON and SQLite exports. Restoring only a database into a fresh instance therefore does not enable automatic backups. A full SQLite restore still retains discovery permissions and its weekly schedule: isolate it from the network while checking it. Do not copy an old backup control file into a new installation to enable scheduling.

No directory ZIP, recursive archive or API-key file copy is created. Database backups still contain entered information, discovery state and potentially retained provider facts. They are not encrypted by the app. Protect their storage separately. Same-disk backups help recover mistakes but **do not protect against disk failure**; an independent device or storage destination requires a separate owner decision and approval. No external transmission is implemented.

## Isolated recovery check

1. Keep production and its existing files untouched. Select a completed backup and preserve the original.
2. Create a new private test data directory. Copy only the selected SQLite file there as `weekend.sqlite3`; do not copy old WAL/SHM files, key files or `backup-control.json`.
3. Check `PRAGMA integrity_check` using Python/SQLite. Use the same app version, or an explicitly tested newer version, with that directory.
4. Run with network disabled and no keys. Bind a different localhost-only port if interactive inspection is needed; never point the test instance at production data. Do not start discovery scheduling against the network.
5. Compare complete JSON exports, stable identifiers, saved snapshot content, archive state, currencies and discovery decisions; restart the isolated instance and repeat. Confirm automatic backups remain disabled.
6. Stop the isolated instance. Restoring over production is a separate, explicit recovery operation requiring preservation of the current database and a compatible app image; see [Backups and upgrades](guide/Backups-and-upgrades.md).
