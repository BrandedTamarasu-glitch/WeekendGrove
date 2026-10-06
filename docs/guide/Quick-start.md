# Quick start

[Guide home](Home.md) · [Unraid](Unraid-installation.md)

Choose **one** installation method below. Docker includes Python, timezone data and TLS certificates. A direct Python install is useful for a quick local trial.

## Requirements

- A current desktop browser. Mobile layouts have been checked at 320/390px widths; that is not a promise of testing every physical phone.
- For Docker: Git, Docker with Linux containers, and Docker Compose v2 or newer. Check `docker version` and `docker compose version` before continuing. See the official [Docker installation instructions](https://docs.docker.com/engine/install/) and [Compose quickstart](https://docs.docker.com/compose/gettingstarted/).
- For Python: Python 3.11 or newer, system timezone data and trusted CA certificates. Development and the Docker image use Python 3.14. The app has no third-party Python package requirements. On a system without IANA timezone data, install your operating system's timezone package; Docker is the simpler supported packaging route.
- Persistent local storage. Keep live SQLite data on the Docker host's local disk, not a client SMB/NFS mount. No formal minimum RAM/storage requirement or broad architecture certification has been established; leave room for data and backups.

## Option A: Docker on this computer

**1. Download the source.** Open a terminal and run:

```sh
git clone https://github.com/BrandedTamarasu-glitch/WeekendGrove.git
cd WeekendGrove
```

**2. Build and start it.** Run this from that directory:

```sh
docker compose up --build -d
docker compose ps
```

The first build downloads the official Python base image and system packages. This repository does **not** publish a ready-made registry image; `weekend-grove:local` is built on your computer. Wait for the service to become `healthy` (normally within a minute).

**3. Open [http://127.0.0.1:8765](http://127.0.0.1:8765).** A new installation is empty. Add an idea or choose **Settings → Load generic sample ideas**. No discovery lookup starts automatically.

**4. Understand where your data lives.** Compose creates a persistent named volume ending in `_grove-data`, mounted at `/data`. Rebuilding or restarting the container keeps it. Keep the same project directory/name for later Compose commands so you keep using that volume.

```sh
docker compose restart
docker compose logs --tail 50 weekend-grove
```

Use the first command to restart, the second to diagnose startup. To stop without deleting data, use `docker compose stop`. Do not use `down --volumes` or delete the volume. Set up [backups](Backups-and-upgrades.md) before entering important data.

## Option B: Python on this computer

After downloading the source in step 1, run:

```sh
python3 server.py
```

On Windows the command may be `py server.py`. Open the same localhost address and leave the terminal running. Ctrl+C stops the app. Its default database is `data/weekend.sqlite3` under the project directory; keep that directory when updating source. To store data elsewhere, set `DATA_DIR` to a private absolute directory before starting. Do not run two processes against the same data directory.

Optional provider-file support relies on POSIX file ownership and no-symlink checks; use the Linux container route for key-backed discovery rather than assuming identical native Windows behavior.

## Optional home-network access

Start locally first. For access from another device, choose the host's actual private LAN address and an unused port. Copy `.env.example` to `.env`; leave it private. Set `GROVE_BIND_IP` to that address and `GROVE_ALLOWED_HOSTS` to that address plus `localhost,127.0.0.1`. Keep `GROVE_PORT=8765` unless another service uses it. Recreate with `docker compose up -d` and browse to `http://YOUR_LAN_IP:8765` on home Wi-Fi.

`YOUR_LAN_IP` is a placeholder. Never use `0.0.0.0` for the host binding in these examples. The container's internal listener is different: it listens on all *container* interfaces so Docker can forward the selected host port. `ALLOWED_HOSTS` checks names; it is not authentication or a client-IP firewall. Do not weaken network isolation to make this app reachable.

For a server bind mount, ownership and a native Unraid template, use the [Unraid guide](Unraid-installation.md).
