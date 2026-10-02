# Prototype verification

The current iteration passed **34 tests** with `python -W error::ResourceWarning -m unittest discover -s tests`. Python compilation, `node --check static/app.js`, and `docker compose config --quiet` passed. The local Docker image build also succeeded. Docker deployment and public hosting readiness are not claimed.

Tests cover daily category caps (including zero and asymmetric limits), 200 rerolls with locked day assignments, 100 relaxation-lock rerolls, relaxation on/off without ideas, 29/30-minute boundaries, cumulative time/budget constraints, impossible locks, saved-plan HTTP restart persistence, relaxation-only saves, legacy unassigned plans, additive backup merges, malformed backup rejection, and all existing currency/persistence/security regressions.

Browser checks used only isolated synthetic data on localhost. Desktop day columns aligned side by side. At 320 × 740, category controls and day sections stacked, with no horizontal overflow. A locked Saturday relaxation block retained its day and duration after reroll. Setting all eight daily caps to zero produced a relaxation-only plan that saved correctly. A legacy synthetic import displayed Day unspecified rather than invented day assignments. No browser console warnings/errors were observed.

![Desktop day sections](images/days-desktop.jpg)

![Narrow phone planner](images/days-phone.jpg)

Currency tests and browser checks confirmed unchanged numeric amounts across relabeling, captured preview/snapshot currencies, persisted settings, strict export/import validation, and mismatch acknowledgment. The supported browser file picker verified that mismatched restore remains disabled until acknowledgment and is disabled again if acknowledgment is unchecked.

Existing local records and settings were checked for preservation before and after restart; the SQLite database and automatic safety backups passed integrity checks. Actual databases, backups, local logs, private workspace paths, and household input are excluded from this repository.

The temporary UI test server and viewport override were cleaned up. Development remains localhost-only. No Unraid, router, network/security setting, cloud service, or external deployment was modified. A real physical-phone/LAN check, Unraid volume permissions and container restart persistence remain intentionally deferred until authorized deployment. This is a prototype, without authentication or a reviewed public-access strategy.

## Deployment packaging follow-up

Local regression tests still pass: **34 tests**, with ResourceWarning treated as errors. Python/JavaScript syntax and Compose configuration checks passed. No GitHub Actions/workflow was added.

The optional `tests/container_smoke.py` passed against the built local app image on Docker 29.8.1 / Compose 5.5.1 (amd64). It validated explicit localhost binding, a single bind mount replacing the named `/data` volume, rejection of unset and nonexistent appdata paths without creating a directory, UID/GID 10001, unwritable unprepared host storage, writable temporary storage and read-only app root. Container recreation and restart preserved the complete synthetic state; the Docker health check became healthy. Consistent SQLite backup passed integrity checking. Additive JSON restore, repeated restore, fresh SQLite migration, and stopped-container recovery restored the exact synthetic idea/archive/currency/day/Lazy Day snapshot state.

Only temporary synthetic databases were used. Temporary containers/networks and files were removed after the tests. No real PC database was exported, copied, or changed. No Unraid access, plugin installation, monitoring, LAN/security configuration, registry image push, PR merge, or deployment occurred.

See [the installation/recovery plan](unraid.md), `.env.example`, and `compose.unraid.yaml`. The actual Unraid version, architecture, healthy storage path, LAN interface/port, and Compose/template availability remain unverified deployment prerequisites. Local stopped-container backup recovery is tested; compatibility of an older image with a newer database schema is not assumed, and rollback requires the matching pre-upgrade image and data backup.
