# Weekend Grove installation guide

Weekend Grove is a small self-hosted idea bank and weekend planner. Keep a list of possibilities, review optional nearby suggestions, and make a Saturday/Sunday plan with room to breathe.

**Start without an API key.** Ideas, planning, saved plans and backups work locally. Weather needs no key. Geoapify discovery uses your own account and private key; this project does not supply or share one.

## Pick your route

| What you want | Start here |
| --- | --- |
| Try it on one computer | [Quick start](Quick-start.md) |
| Keep it running on Unraid | [Unraid installation](Unraid-installation.md) |
| Learn the app | [Settings and everyday use](Settings-and-everyday-use.md) |
| Connect your own Geoapify account | [API keys and discovery](API-keys-and-discovery.md) |
| See the weekend forecast | [Weather](Weather.md) |
| Download/print an itinerary or configure automatic copies | [Portable itineraries and backups](../portable-itineraries-and-backups.md) |
| Move, back up or update an installation | [Backups and upgrades](Backups-and-upgrades.md) |
| Resolve an installation problem | [Troubleshooting](Troubleshooting.md) |

## Before you install

The app has **no login or user separation**. Anyone who can reach it can read and change its data. The default installation is localhost-only. Home-LAN hosting is an explicit choice for a trusted network, not public hosting. Do not use router port forwarding, a public tunnel or an internet-facing reverse proxy. Authentication, TLS and an external-access design are not included.

The planner is a prototype, not a booking system. It does not know opening hours, driving routes, event time conflicts or whether an activity suits your household. Check original listings before you go.

[Project README](https://github.com/BrandedTamarasu-glitch/WeekendGrove#readme) · [GitHub Wiki](https://github.com/BrandedTamarasu-glitch/WeekendGrove/wiki) · [MIT license](https://github.com/BrandedTamarasu-glitch/WeekendGrove/blob/main/LICENSE)
