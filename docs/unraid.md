# Unraid installation and recovery plan

This prepares a later deployment. It does not access a server, change shares/network settings, install plugins, or deploy a container. Confirm storage recovery/rebuild has completed and storage is healthy before starting. Run tests locally before publishing or deploying; no GitHub Actions or paid service is required.

## Choose these values first

| Value | What to confirm |
| --- | --- |
| `GROVE_APPDATA_PATH` | An absolute, existing directory on confirmed healthy persistent storage, dedicated to this app. The path is not chosen automatically. |
| `GROVE_IMAGE` | A locally built/loaded image tagged with the exact tested source commit, for example `weekend-grove:COMMIT_SHA`. Retain the preceding image for rollback. |
| `GROVE_BIND_IP` | For a later home-LAN deployment, the server's actual private LAN interface IP. Initially `127.0.0.1`; never use `0.0.0.0` for the host binding. |
| `GROVE_PORT` | An unused host port you confirm, initially `8765`. Container port remains `8765`. |
| `GROVE_ALLOWED_HOSTS` | The exact IP/hostnames used by browsers, comma-separated without scheme/port, plus `127.0.0.1` for the health check. Initially `localhost,127.0.0.1`. |
| Backup destination | A separate private location on healthy storage, with an additional copy off the app's storage device. Backups contain household data. |

Unraid share placement depends on the current share/pool configuration. Verify the actual backing storage, capacity, permissions, and mover behavior; do not select a disk or pool based on an old inventory. A dedicated healthy pool-backed appdata directory is a practical choice, provided its health and backup strategy are verified. Keep a live SQLite database on local Docker-host storage, not an SMB/NFS-mounted client directory. Do not move active database files. Avoid copying between user-share and disk-share views of the same data. See the current [Unraid share documentation](https://docs.unraid.net/unraid-os/using-unraid-to/manage-storage/shares/).

The shape `/mnt/CONFIRMED_POOL/appdata/weekend-grove` is a placeholder, not a selected path. `/mnt/user/appdata/weekend-grove` is also only a candidate after verifying where that share is really stored. Do not mount an entire disk, all appdata, or Docker's system directory into this container.

## Configuration prepared for review

Use the existing `compose.yaml` plus `compose.unraid.yaml`. The override replaces the `/data` named volume with the selected bind mount and requires the source directory to exist. `create_host_path: false` prevents silently making a misspelled host directory; the required variable rejects an unset path. Docker bind mounts refer to the **Docker host**, not the machine running a remote client. These behaviors follow the [Docker Compose service specification](https://docs.docker.com/reference/compose-file/services/) and [bind-mount documentation](https://docs.docker.com/engine/storage/bind-mounts/).

Copy `.env.example` to a private `.env`. It deliberately keeps localhost defaults and leaves the storage path blank. Edit only after confirming the table above. The real `.env` is ignored by Git and Docker builds.

```sh
cp .env.example .env
chmod 600 .env
# Edit .env with the confirmed image tag, path, interface IP, port and hosts.
docker compose --env-file .env -f compose.yaml -f compose.unraid.yaml config
```

Review the rendered configuration: exactly one mount at `/data`, correct existing source path, one explicit host-IP/port mapping to container `8765`, and correct allowed hosts. A blank appdata path should fail validation. No registry image pull is configured in the Unraid override.

Create only the confirmed dedicated directory if this is a new installation. On the Docker host, give it UID/GID **10001:10001** ownership and mode **0700**. The image runs as that numeric user; no `PUID`/`PGID` variables are implemented. A bind mount hides the image's pre-created `/data`, so image ownership alone does not fix host permissions. Do not recursively change permissions on all appdata or unrelated shares. If migrating a database, its file must also be readable/writable by UID 10001, normally mode 0600. Use the file manager or targeted `mkdir`/`chown`/`chmod` commands on the one chosen directory/file after checking the path.

## Image and startup, after deployment is authorized

Keep source/config separate from the database and backup directory. Use the tested commit, not a moving branch, and record it with the image tag. If building on the server later:

```sh
git checkout COMMIT_SHA
docker build -t weekend-grove:COMMIT_SHA .
```

`COMMIT_SHA` is a placeholder to replace with the reviewed commit. Building may download the official Python base image if not cached. Alternatively, build on the PC, use `docker save -o IMAGE_ARCHIVE.tar weekend-grove:COMMIT_SHA`, privately transfer that archive, and run `docker load -i IMAGE_ARCHIVE.tar` on Unraid. Confirm image/server architecture matches before transferring; a PC-built amd64 image is not automatically suitable for another architecture. No registry push is required.

Once `.env` references that loaded/built image and data permissions are ready:

```sh
docker compose --env-file .env -f compose.yaml -f compose.unraid.yaml up -d --no-build --pull never
docker compose --env-file .env -f compose.yaml -f compose.unraid.yaml ps
docker compose --env-file .env -f compose.yaml -f compose.unraid.yaml logs --tail 50 weekend-grove
```

The container has a read-only root, writable `/data` and temporary `/tmp`, dropped capabilities, and no-new-privileges. Its health check queries localhost inside the container. `restart: unless-stopped` restarts a running service after Docker restarts; a deliberately stopped service stays stopped until started. A health-check failure does not by itself trigger Docker's restart policy. Verify `healthy`, restart once, and confirm existing ideas/plans/currency remain. Do not run `down --volumes`, delete appdata, or start a second instance writing the same SQLite file.

If Compose is unavailable on the actual Unraid installation, do not install an unreviewed plugin just for this app. The equivalent Docker template values are: exact local image tag; bridge network (not host); container port 8765; selected host port bound to the confirmed private interface; dedicated host directory to `/data` read/write; `ALLOWED_HOSTS` as above; UID/GID 10001 from the image; read-only root; tmpfs `/tmp`; dropped capabilities; no-new-privileges; restart unless-stopped. Verify that the template supports the explicit host-IP binding and restrictions before launching; otherwise defer and use a reviewed Compose setup. Actual Unraid version/template behavior has not been inspected.

## Home-LAN-only access

After separately authorizing LAN access, change the localhost host binding in the private `.env` to the confirmed private LAN IP and set the corresponding allowed host(s). Use `http://CONFIRMED_LAN_IP:CONFIRMED_PORT` from a phone on home Wi-Fi, then verify the layout and data. These are placeholders, not addresses to copy literally. Keep router forwarding, tunnels, reverse-proxy publishing, and public access disabled. Do not use host networking.

The host binding selects an interface; it is not authentication or a firewall. `ALLOWED_HOSTS` validates request names, not client identity. LAN-only operation relies on the existing network isolation and absence of external forwarding; anyone on that reachable network can use the app. Verify that exposure boundary at deployment without weakening existing security. External access requires a separate authentication/TLS/access design and is out of scope.

## Migrate current PC data privately

Do this only at the agreed cutover time, after final PC edits are complete. No real-data export or transfer is performed by these preparation steps.

1. In the running PC app, choose **Database backup** and **Export JSON**. Save both to a private folder outside the source checkout, not GitHub or an image build context. The database button uses SQLite's consistent backup API while the app runs. Keep the PC installation and its original data intact.
2. Stop making edits in the PC app during cutover. Record private checksums and record counts for the backups. Verify the SQLite backup with Python's `sqlite3` `PRAGMA integrity_check` before transfer; do not print idea titles into deployment logs.
3. Privately transfer the backup to a **fresh, empty** confirmed appdata directory on Unraid. With the target container stopped/not yet created, install the database backup as `weekend.sqlite3`, give its directory and file UID/GID 10001 ownership, and use 0700/0600 permissions. Do not overwrite an existing target database. Existing target data requires a separately confirmed recovery or additive merge decision.
4. Start the selected image on that directory. Verify ideas, archived entries, plans, currencies, estimates and day/relaxation snapshots, then restart and check again. Keep the PC backup and old installation until validation is complete. Older plans remain Day unspecified; migration does not invent day choices.
5. Alternative: start an empty target and use **Restore JSON backup**, review additions/skips, select backup estimates/currency when wanted, and acknowledge any currency mismatch. This is additive and idempotent for current exports. Local numeric IDs may remap on a merge. It cannot replace newer edits with old values. Keep the SQLite backup as the exact recovery option.

Example integrity check, after replacing the path with your private backup file:

```sh
python -c "import sqlite3; db=sqlite3.connect('file:PRIVATE_BACKUP.sqlite3?mode=ro', uri=True); print(db.execute('PRAGMA integrity_check').fetchone()[0]); db.close()"
```

No database, JSON backup, `.env`, server inventory, or household record belongs in this repository. A source-code update never requires migrating the local database into Git.

## Routine backup and recovery

Before every upgrade, take both UI backups, validate the database backup, and keep a copy away from app storage. A raw copy of a live SQLite file is not the backup procedure; use the app's database backup or stop the container and back up the complete appdata directory. Keep private permissions on backup files. Do not rely on parity or automatic migration safety copies as the only backup. The app does not schedule backups or provide automatic retention.

For a full database restore, explicitly choose replacement first because it can discard changes since the backup. Stop this app's container. Make a safety copy of the complete current appdata directory, then preserve that directory under a distinct name and prepare a fresh directory at the configured path. Put the validated backup there as `weekend.sqlite3`, restore UID/GID 10001 and directory/file permissions, and start the matching image. Preserving the old directory also avoids leaving old journal/WAL sidecars beside the replacement database. Do not merge raw database files or restore over a running writer. Verify state and restart persistence before considering the recovery finished. Never remove the safety copy as part of these steps.

## Upgrade and rollback

1. Run regression/syntax/Compose checks locally; run the optional container smoke test below when packaging/storage behavior changes. Publish only source and reviewed generic docs. No GitHub Actions is needed.
2. Record the running commit/image tag, save both data backups, stop this container, and preserve its complete appdata directory. Keep the prior image available. The app's v2/v3 safety backups may be created during schema upgrades, but they supplement your pre-upgrade backup.
3. Build/load the reviewed new image with a new immutable tag. Update only `GROVE_IMAGE` in the private configuration. Start it with the same appdata bind mount; validate health, sample existing records, archive flags, settings, plans and a restart. Avoid deleting the old image or pre-upgrade data backup.
4. If validation fails, stop the new container. Preserve the post-upgrade data separately. Roll back **both** the image/config and the matching pre-upgrade database into a fresh directory. Do not assume an old image can read a newer schema, and do not apply an older additive JSON export to reverse database changes. This recovery loses post-backup edits unless separately reconciled; make that choice explicit.

An image-only rollback with a newer database is unverified. Rebuild-free recreation of the same tested image and stopped-container recovery of a matching SQLite backup are tested locally; actual Unraid filesystems, permissions and restart behavior remain deployment acceptance checks.

## Local checks and deployment acceptance

```sh
python -W error::ResourceWarning -m unittest discover -s tests
python -m compileall -q server.py tests
node --check static/app.js
docker compose config --quiet
docker build -t weekend-grove:deployment-review .
python -W error::ResourceWarning tests/container_smoke.py --image weekend-grove:deployment-review
```

The optional smoke script creates only temporary synthetic databases, publishes only localhost ports, never pulls the image, and removes its temporary containers/networks. It validates UID/GID, required bind path, recreation/restart, health, currency/day/Lazy Day snapshots, consistent database backup, additive JSON restore, full SQLite migration, and stopped-container rollback. It never reads the main PC database or contacts Unraid.

At later deployment, confirm healthy chosen storage, backup restore, UID/GID write access, one `/data` mount, intended private IP/port exposure, container health, restart persistence, real phone layout and successful private migration. No server-specific path/port or healthy device has been confirmed by this guide.
