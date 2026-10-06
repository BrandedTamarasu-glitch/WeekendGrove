# Backups, migration and upgrades

[Guide home](Home.md) · [Troubleshooting](Troubleshooting.md)

Your data is the most important part of the installation. Keep a fresh private backup on a different device before an upgrade or move. The app does not schedule backups for you.

## Make a backup

Open **Settings → Backups & sample ideas**:

- **Export JSON** downloads portable version 5 data: ideas, archive/demo state, saved snapshots, estimates/currency, discovery preferences and Save/Dismiss decisions.
- **Database backup** downloads a transaction-consistent SQLite copy, including operational state and ZIP caches. Use this button rather than copying a live database file by itself.

Keep both before an upgrade, labeled with the date and current image/source commit. Backups contain your entered information. Never attach them to a public issue. Provider key files are excluded from both formats; protect them separately if you need to preserve them. A copy of the whole `/data` directory can include secrets, so do not treat it like a public diagnostic bundle.

## Restore JSON without replacing existing records

1. Take a backup of the destination installation first.
2. Choose **Restore JSON backup**, select the file, and review the preview's additions/skips.
3. Existing matching records and discovery decisions win. Choose the optional estimates/currency and discovery-preferences checkboxes only if wanted. Restored discovery preferences always leave public/source permissions and weekly refresh off.
4. If currencies differ, explicitly acknowledge relabeling; numbers are never converted.
5. Choose **Add missing records**, then verify your ideas, saved snapshots and settings.

Restore is additive and atomic, not a way to undo edits or delete records. Repeat version 2–5 imports do not duplicate stable identities. Older version 1 files have weaker identity guarantees across separate exports. Versions 1–4 are still supported; older plans can have unspecified days. Files must be at most 2 MiB and within the 2,000-ideas/2,000-plans and 1,000-discovery-record limits. For a larger bank, use a full database recovery.

## Move an installation or recover a full database

Full replacement can lose newer edits. Perform it only when you intentionally want the backup state.

1. Stop the source after final edits and keep its latest consistent backup. Stop the destination app too.
2. Preserve the destination's entire existing data directory in a separate safety location. Do not overwrite it in place or mix stale `-wal`/`-shm` files with a restored database.
3. Prepare a separate dedicated destination directory and place the downloaded database there as `weekend.sqlite3`.
4. For the container, set the directory owner to `10001:10001` and mode `0700`; set the database owner likewise and mode `0600`. Target only those paths. Native Python installs use the account running Python instead.
5. Start a single app instance using that directory. Compare counts, a few records, saved plans and settings to the source. Review discovery consent and scheduling: a full SQLite restore retains them, unlike the safe-off JSON preference restore.
6. Keep the old directory and backup until verification is complete. Move/recreate private key files separately; never publish them.

## Upgrade with a rollback path

1. Read the changes and record the current commit/image tag. Export JSON and download a consistent database backup.
2. Fetch the new source and select its exact reviewed commit. Build `weekend-grove:NEW_COMMIT_SHA` before touching the running container. Keep the previous image.
3. For a native Unraid template, edit **only Repository** to the new pinned tag and Apply. Preserve storage, key-file variables, binding and security parameters.
4. For Compose, keep the same project and volume; set `GROVE_IMAGE` to the new tag and use the same file list to run `up -d --no-build --pull never`. Do not use `down --volumes`.
5. Check healthy status, open the UI, restart this container once and verify persistence. Compare a new export to your backup when no user edits occurred between them.

Schema upgrades create `before-upgrade-v2.sqlite3`, `before-upgrade-v3.sqlite3` or `before-upgrade-v5.sqlite3` as needed. These are extra safety copies, not substitutes for an off-device backup. This UI redesign itself did not add a database schema.

If an upgrade fails, stop the app and preserve its failed-upgrade data separately. Use the **matching previous image and pre-upgrade database backup** in a separate prepared directory. Do not assume an old image understands a newer schema. Switching only the image can be safe when compatibility is known, but is not a general rollback guarantee. Restore ownership and verify contents before resuming use.
