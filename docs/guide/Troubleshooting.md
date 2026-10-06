# Troubleshooting

[Guide home](Home.md) · [Installation](Quick-start.md) · [Backups](Backups-and-upgrades.md)

| Symptom | What to check |
| --- | --- |
| Container cannot write `/data` | The bind path exists on the Docker host, not just your client. Its owner is UID/GID 10001; directory mode 0700, database mode 0600. Do not fix this with privileged mode or chmod 777. |
| “Image not found” | Build/load the exact tag in Repository or `GROVE_IMAGE`. No public prebuilt image is provided. Keep `--pull=never` for a loaded Unraid image. |
| Port already allocated | Another app uses the host port. Choose a different host port; keep container port 8765 and update the WebUI URL. |
| “Forbidden” / host rejected | `ALLOWED_HOSTS` must contain the address/hostname used in your browser, without scheme or port, plus 127.0.0.1 for health checks. |
| Desktop works but phone cannot connect | 127.0.0.1 on the phone means the phone. Use the server's explicitly configured private LAN address; use trusted home Wi-Fi, not cellular/guest Wi-Fi. Check existing isolation without opening public access. |
| New empty bank after an update | Stop and inspect project name, volume and appdata path before adding/restoring anything. A new Compose project can select a different volume. Original data may still be intact. |
| Geoapify says no key | Check only file path, owner, mode and container variable. File must be a regular, non-symlink file owned by the running UID, with no group/other permissions; key text must fit the supported format. Never paste its contents into logs or issues. |
| Key configured but provider inactive | Enable global and that provider's permission in Settings, then save. Key presence alone does not enable requests. |
| Refresh is disabled or returns few results | Check permission, ZIP, cooldown, enabled sources, account quota and provider status. City coverage is regional; source limits and filtering make results incomplete. |
| Weather unavailable / too early | Use a Saturday within the 16-day horizon, valid ZIP/timezone, page-session consent and an explicit Check weather click. Verify provider availability; missing values are not zero. |
| No plan fits | Add ideas or relax limits. Check locked items, date-specific events, category caps, estimated costs and energy ceiling. An empty result can be correct. |
| Timezone error | Use an IANA name (e.g. America/Los_Angeles). Direct Python needs system timezone data; the Docker image includes it. |
| Theme differs between devices | Explicit theme preference is per browser. Use Settings → Appearance → Use device setting to reset it. |

For Compose diagnostics, run `docker compose ps` and `docker compose logs --tail 50 weekend-grove` from the same installation directory, with the same override files used for startup. For native Unraid, use the container's **Logs** menu. A healthy check verifies the local HTTP endpoint, not provider availability or your phone's connection.

Before reporting a bug, record the commit/image tag, installation route, browser and a short reproduction using generic sample data. Remove keys, tokens, real ZIP/address, local server URLs, household records, backups and private paths from any screenshot or log. Do not attach your `.env`, template export or appdata directory. Report suspected credential exposure privately; revoke/rotate with the provider and do not rewrite shared Git history without a coordinated plan.

If recovery is needed, follow [Backups and upgrades](Backups-and-upgrades.md). Do not delete data or reset a database just to clear an error.
