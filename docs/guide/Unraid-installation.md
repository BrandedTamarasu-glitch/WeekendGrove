# Unraid installation

[Guide home](Home.md) · [Backups and upgrades](Backups-and-upgrades.md)

A native Unraid Docker template is the primary route here. Compose is an alternative if you already use it. **Choose one manager for this app.** Do not launch both against the same database or port. The native route was exercised on Unraid 7.3.2; other versions may label controls differently. No Community Applications listing or prebuilt registry image is provided.

## 1. Choose storage and an address

In Unraid, verify the actual storage device/pool is healthy, has free space and has a backup plan. Create one dedicated appdata directory there. `/mnt/CONFIRMED_POOL/appdata/weekend-grove` below describes the shape of a path; replace it with your own verified path. Do not assume a pool name or a disk number. Do not mount all appdata or an entire disk into the app.

Keep the live database on local storage. Review share placement and mover behavior; avoid copying between disk-share and user-share views of the same data. See [Unraid shares](https://docs.unraid.net/unraid-os/using-unraid-to/manage-storage/shares/).

Record these four values privately:

- Dedicated appdata path.
- Server's actual private LAN interface address (or `127.0.0.1` for a server-local trial).
- Unused host port, normally `8765`.
- Source commit and local image tag from the next step.

For a **new empty directory only**, run targeted commands from the server console, replacing the placeholder first:

```sh
mkdir -p /mnt/CONFIRMED_POOL/appdata/weekend-grove
chown 10001:10001 /mnt/CONFIRMED_POOL/appdata/weekend-grove
chmod 700 /mnt/CONFIRMED_POOL/appdata/weekend-grove
```

UID/GID `10001:10001` is the app's Linux user. The app does not implement `PUID`/`PGID`. Never recursively change all appdata permissions. For existing data, take a backup and use [migration instructions](Backups-and-upgrades.md) instead of creating an empty replacement.

## 2. Build the image

On a machine with Git and Docker, clone the repository as in [Quick start](Quick-start.md). Choose a reviewed commit from GitHub's commit history and replace `COMMIT_SHA` in both commands:

```sh
git checkout COMMIT_SHA
docker build -t weekend-grove:COMMIT_SHA .
```

Use the full commit hash to make future rollback unambiguous. A build needs internet access for public source/base packages, but does not need your data or API key.

If built on another computer, transfer the image archive privately to Unraid:

```sh
docker save -o weekend-grove-image.tar weekend-grove:COMMIT_SHA
```

On the server, in the directory holding that archive:

```sh
docker load -i weekend-grove-image.tar
docker image inspect weekend-grove:COMMIT_SHA --format '{{.Architecture}}'
```

The image architecture must match your server. A local build is not automatically cross-platform. Alternatively, build the source directly on the server using its existing trusted console and tools. No plugin installation or new SSH access is required by this guide.

## 3. Add the native container

Open **Docker → Add Container**, select advanced view if needed, and enter:

| Field | Value |
| --- | --- |
| Name | `weekend-grove` |
| Repository | `weekend-grove:COMMIT_SHA` matching your loaded image |
| Network Type | `Bridge` (not Host) |
| Privileged | Off |
| WebUI | `http://YOUR_LAN_IP:8765` with your chosen address/port |
| Console shell | Shell / `sh` |

In **Extra Parameters**, paste the following as one line **after replacing** `YOUR_LAN_IP`, `YOUR_HOST_PORT` and `/mnt/CONFIRMED_POOL/appdata/weekend-grove`:

```text
--pull=never --read-only --tmpfs /tmp --cap-drop=ALL --security-opt no-new-privileges=true --user 10001:10001 --restart unless-stopped --publish YOUR_LAN_IP:YOUR_HOST_PORT:8765/tcp --mount type=bind,src=/mnt/CONFIRMED_POOL/appdata/weekend-grove,dst=/data --env ALLOWED_HOSTS=YOUR_LAN_IP,127.0.0.1,localhost
```

Use a dedicated path without spaces for this template example. The explicit bind mount refuses a nonexistent source directory. Because the line supplies the port and `/data` mount, **do not add duplicate Port or Path rows**. Do not enter any API key here. For provider-file variables, follow [API setup](API-keys-and-discovery.md) separately.

Review the final configuration before clicking **Apply**. It should publish only the chosen private address/port, mount only the dedicated directory, run unprivileged, and use the local pinned image. The restrictions make `/app` read-only and `/tmp` temporary while `/data` remains writable. See [Unraid container management](https://docs.unraid.net/unraid-os/using-unraid-to/run-docker-containers/managing-and-customizing-containers/) for the UI.

## 4. Verify it

Wait for `healthy`, open the WebUI and add your first real idea. Restart **only this container** and check that the idea remains. Set its native **Autostart** switch On if you want it after a server boot. Do not also enable a Compose copy. A Docker health-check failure alone does not trigger a restart; `unless-stopped` restarts exited services, and deliberately stopped services stay stopped.

Try the address on a phone using home Wi-Fi. Check that you see the same data and that controls fit. This is your physical-device test; browser width checks do not replace it.

This app has no login. No port forwarding, public proxy, tunnel, host networking or network-security change is part of installation. If it cannot be reached, use [Troubleshooting](Troubleshooting.md) before changing firewall/access rules.

## Alternative: an existing Compose setup

Do not create the native template if you choose this route. Copy `.env.example` to a private `.env` and set `GROVE_IMAGE`, `GROVE_BIND_IP`, `GROVE_PORT`, `GROVE_ALLOWED_HOSTS` and `GROVE_APPDATA_PATH` to the verified values above. Do not put secrets in `.env`.

Validate before starting:

```sh
docker compose --env-file .env -f compose.yaml -f compose.unraid.yaml config
```

Confirm exactly one `/data` bind mount, the right existing path, the private interface binding and the pinned image. A blank appdata path should fail. Then start the already-built image:

```sh
docker compose --env-file .env -f compose.yaml -f compose.unraid.yaml up -d --no-build --pull never
docker compose --env-file .env -f compose.yaml -f compose.unraid.yaml ps
```

Keep using the same directory, project name and file list for later commands. Compose Manager autostart is separate from native template autostart; configure only the route you chose. There is no need to install a Compose plugin merely to follow the native route.
