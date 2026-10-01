# Prototype verification

The current iteration passed **34 tests** with `python -W error::ResourceWarning -m unittest discover -s tests`. Python compilation, `node --check static/app.js`, and `docker compose config --quiet` passed. The local Docker image build also succeeded. Docker deployment and public hosting readiness are not claimed.

Tests cover daily category caps (including zero and asymmetric limits), 200 rerolls with locked day assignments, 100 relaxation-lock rerolls, relaxation on/off without ideas, 29/30-minute boundaries, cumulative time/budget constraints, impossible locks, saved-plan HTTP restart persistence, relaxation-only saves, legacy unassigned plans, additive backup merges, malformed backup rejection, and all existing currency/persistence/security regressions.

Browser checks used only isolated synthetic data on localhost. Desktop day columns aligned side by side. At 320 × 740, category controls and day sections stacked, with no horizontal overflow. A locked Saturday relaxation block retained its day and duration after reroll. Setting all eight daily caps to zero produced a relaxation-only plan that saved correctly. A legacy synthetic import displayed Day unspecified rather than invented day assignments. No browser console warnings/errors were observed.

![Desktop day sections](images/days-desktop.jpg)

![Narrow phone planner](images/days-phone.jpg)

Currency tests and browser checks confirmed unchanged numeric amounts across relabeling, captured preview/snapshot currencies, persisted settings, strict export/import validation, and mismatch acknowledgment. The supported browser file picker verified that mismatched restore remains disabled until acknowledgment and is disabled again if acknowledgment is unchecked.

Existing local records and settings were checked for preservation before and after restart; the SQLite database and automatic safety backups passed integrity checks. Actual databases, backups, local logs, private workspace paths, and household input are excluded from this repository.

The temporary UI test server and viewport override were cleaned up. Development remains localhost-only. No Unraid, router, network/security setting, cloud service, or external deployment was modified. A real physical-phone/LAN check, Unraid volume permissions and container restart persistence remain intentionally deferred until authorized deployment. This is a prototype, without authentication or a reviewed public-access strategy.
