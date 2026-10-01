# Weekend Grove roadmap

## Implemented follow-up

- **Configurable cost currency — implemented and verified.** USD default; USD, CAD, EUR, GBP, AUD, and NZD supported with symbols and codes. Selection relabels costs without changing stored amounts. Previews/saved plans retain snapshot currencies. Version 3 exports preserve labels; older imports and saved plans explicitly mark a USD assumption. Mismatched-currency restore requires acknowledgment. No conversion or exchange-rate APIs. See `docs/verification.md`.

- **Distinct day planning — implemented and verified.** Saturday/Sunday sections, separate per-day category maximums, optional 30/60-minute Lazy Day blocks, locked day preservation, and version 4 schedule snapshots/export. Legacy days stay unspecified. See `docs/verification.md`.

## Before eventual Unraid deployment

The reviewed configuration and private migration/recovery procedure are in [docs/unraid.md](docs/unraid.md). Local checks run before pushes; GitHub Actions is intentionally not configured.

- Verify host storage health before an explicitly authorized deployment.
- Confirm the intended appdata bind mount, UID/GID 10001 permissions, backup/restore procedure, container health, and restart persistence on Unraid.
- Test the actual phone on the home LAN after an explicitly authorized LAN-only configuration. The PC prototype remains localhost-only now.
- Before any external access, review authentication, TLS, and access strategy. No credentials, router changes, or public exposure are configured by this prototype.

## Later usability choices

- Decide whether plan deletion and automatic backup scheduling are useful after trying the local prototype.
- Final narrow-phone and JSON file-picker UI restore checks are complete after browser/connection recovery; no feature changes were needed to close those verification gaps.
