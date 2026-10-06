# API keys and discovery

[Guide home](Home.md) · [Discovery settings](Settings-and-everyday-use.md) · [Troubleshooting](Troubleshooting.md)

**Bring your own key.** No maintainer key is distributed. Do not paste keys into the app, source, `.env`, a template, GitHub issues, screenshots or chat. Ordinary Ideas/Plan/Saved features work without any provider account.

| Source | Key? | Coverage and status |
| --- | --- | --- |
| City of Stanwood calendar | No | Regional public events only; not a nationwide events search. In-range supported occurrences only. |
| Geoapify | Your own | Restaurants and selected places (museums, zoos, parks). Key-file integration has been checked on a running installation; coverage and account entitlement are not guaranteed. |
| Ticketmaster | Your own, optional | Bounded family-classified event adapter with offline tests. Full credentialed live behavior and retention operations are not validated; leave off unless you have reviewed the limitations below. |
| Open-Meteo weather | No | Separate manual permission and forecast flow; see [Weather](Weather.md). |

## 1. Obtain your Geoapify key

On [Geoapify's official site](https://www.geoapify.com/get-started-with-maps-api/), create your own account, review its terms/plan and create a project. Its project settings provide an API key. Check [current pricing and quotas](https://www.geoapify.com/pricing/) and monitor usage; this app does not buy a plan or promise permanently free service. Provider restrictions must permit server-side requests from your host; browser-referrer-only keys may not work.

Keep the key private. The steps below store it in a protected file, then pass **only the file path** to the container. Never copy a real key into an example command.

## 2. Create the private file on the Docker host

Use an existing trusted **local console**, or an already-secured administrative session. Do not enter a key through an unencrypted HTTP management page. This guide does not require enabling SSH or creating another access route.

Choose a dedicated secrets directory **outside the source checkout**. For a native Unraid installation, use `secrets` inside the dedicated appdata directory you selected. For named-volume Compose, choose a separate persistent host directory; the overlay below mounts it read-only. Do not reuse a shared directory or store it in a public share.

Run the following yourself in an interactive root Bash console. It asks for the directory and masks key entry. The directory must have a real, trusted existing parent; do not use a symlinked path. The snippet creates only that one directory if missing, checks ownership/mode, and refuses to overwrite an existing key. The secret is read as input, not entered as a command or argument, so it is not put into shell history. Do not record or screen-share the session.

```bash
(
  set +x
  umask 077
  [[ $EUID == 0 && -t 0 ]] || { printf 'Use an interactive root Bash console.\n'; exit 1; }
  read -r -p 'Absolute private secrets directory: ' grove_dir || exit 1
  [[ $grove_dir == /* && $grove_dir != / && ! -L $grove_dir ]] || exit 1
  if [[ ! -e $grove_dir ]]; then
    mkdir -- "$grove_dir" && chown 10001:10001 "$grove_dir" && chmod 700 "$grove_dir" || exit 1
  fi
  [[ -d $grove_dir && $(stat -c %u "$grove_dir") == 10001 && $(stat -c %a "$grove_dir") == 700 ]] || {
    printf 'Directory must be dedicated, owned by 10001, and mode 700.\n'; exit 1;
  }
  [[ ! -e $grove_dir/geoapify.key && ! -L $grove_dir/geoapify.key ]] || {
    printf 'Key file already exists; nothing changed.\n'; exit 1;
  }
  grove_tmp=$(mktemp "$grove_dir/.geoapify.XXXXXXXX") || exit 1
  trap 'unset grove_key; rm -f -- "$grove_tmp"' EXIT
  read -r -s -p 'Geoapify key (hidden): ' grove_key || exit 1
  printf '\n'
  [[ $grove_key =~ ^[A-Za-z0-9_-]{8,256}$ ]] || { printf 'Unsupported key format.\n'; exit 1; }
  printf '%s' "$grove_key" > "$grove_tmp" || exit 1
  unset grove_key
  chown 10001:10001 "$grove_tmp" && chmod 600 "$grove_tmp" || exit 1
  ln -- "$grove_tmp" "$grove_dir/geoapify.key" || exit 1
  printf 'Private key file installed. No lookup has been enabled.\n'
)
```

The file must be regular, not a symlink, owned by UID 10001 and mode 0600. The directory is mode 0700. The app rejects malformed/oversized/unreadable files without revealing values. Do not troubleshoot by printing the file. For native Python on POSIX, use the account running Python as owner instead; the root/10001 snippet is specifically for the container.

## 3A. Connect a native Unraid template

Edit the existing Weekend Grove template. Add a **Variable** with key `GEOAPIFY_API_KEY_FILE` and value `/data/secrets/geoapify.key`. This assumes the file lives inside your appdata's `secrets` directory from step 2. The `/data` mount already exposes it to the app; do not add a new port or mount all appdata.

Apply to recreate the container, preserving the pinned image, existing storage, security parameters and LAN binding. The template holds a file path, never the key itself.

## 3B. Connect Docker Compose

For a named-volume or bind-mount Compose install, use the included `compose.providers.yaml`. In your private `.env`, add `GROVE_SECRETS_PATH` with the absolute host directory chosen in step 2. It contains `geoapify.key` and optionally `ticketmaster.key`; no secret values go in `.env`.

From the project directory, validate and recreate:

```sh
docker compose -f compose.yaml -f compose.providers.yaml config
docker compose -f compose.yaml -f compose.providers.yaml up -d --no-build
```

If you also use the Unraid bind-mount override, keep it in both commands: `-f compose.yaml -f compose.unraid.yaml -f compose.providers.yaml`. Keep this full file list for future lifecycle commands. The provider overlay mounts only the selected secrets directory at `/run/grove-secrets`, read-only, and sets the two `_FILE` paths. A missing optional Ticketmaster file leaves that provider unconfigured. A nonexistent secrets directory is an error; the mount will not create one silently.

## 4. Enable only what you want

1. Open **Settings → Discovery settings**. Geoapify should report **key configured**, but still inactive until permissions are saved.
2. Set your ZIP/radii and read the outgoing-data disclosure. Enable global public lookups and Geoapify permission. Leave Ticketmaster and weekly refresh off for the first trial.
3. Save settings, then manually refresh in **Discover**. Verify the status, original source links and your provider account usage. No results can be legitimate; do not repeatedly retry around the five-minute cooldown.
4. If useful, configure weekly refresh as described in [Everyday use](Settings-and-everyday-use.md).

Geoapify receives the ZIP for postcode geocoding, then approximate ZIP-center coordinates, search radius and category groups. A refresh makes at most three Geoapify requests; each places result is capped at 20 with no pagination. Places retain unknown cost/duration/effort until you supply them. The browser does not receive the key. All providers see the server public IP; ideas, plans and household profiles are not sent.

The regional city feed uses Zippopotam.us ZIP centers. It skips unsupported recurring/cancelled/missing-location entries. Keep displayed source links and attribution, including Geoapify/OpenStreetMap and Zippopotam.us/GeoNames. Source facts do not guarantee suitability, accessibility, availability, price or opening hours.

## Optional Ticketmaster: review before activation

Ticketmaster is not required. Its [Discovery API](https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/) adapter makes one bounded request per refresh, at most 100 events over a 90-day window. It sends approximate ZIP-center geohash, radius and US/family filters. Explicit family classification, usable dates and in-range venues are required; this still does not establish suitability for a particular age or household. Prices/durations remain unknown.

The [current API terms](https://developer.ticketmaster.com/support/terms-of-use/) restrict storage to reasonable service periods and require removal of requested Event Content within 24 hours. The app's 24-hour inbox-payload cleanup is an implementation policy, **not a blanket retention entitlement**. Content-free decision identities persist. Saved ideas, saved plans and backups still contain provider facts and are not automatically deleted or rewritten; plan deletion/removal management is incomplete. Leave this provider off until you can meet applicable retention/removal obligations. Offline tests are not full operational or legal validation.

If you decide to enable it, obtain your own developer key and repeat step 2 with the prompt/file changed to Ticketmaster / `ticketmaster.key`. For native Unraid add `TICKETMASTER_API_KEY_FILE=/data/secrets/ticketmaster.key` as a Variable; the Compose overlay already references its optional file. Enable its separate permission only after configuration and review.

## Key lifecycle

Revoking a UI permission prevents subsequent requests once observed; an already-sent request cannot be recalled. Removing a file or revoking a key with its provider is separate. To rotate, stop the app, preserve the old file privately if needed, create a replacement through a trusted masked-entry process and restart; the setup snippet intentionally refuses in-place replacement.

`_FILE` takes precedence over direct environment variables and fails closed if unreadable. Direct `GEOAPIFY_API_KEY` / `TICKETMASTER_API_KEY` variables exist for controlled deployments, but are discouraged because template exports and Docker inspection can reveal them. Secret files are excluded from app exports/database backups. Protect separate secret backups and keep them out of support bundles.
