# Weekend weather

The planner can request high/low temperature (Fahrenheit), a WMO daily condition code and daily maximum precipitation probability for its selected Saturday and Sunday. Generated day cards display high/low and a condition icon plus accessible text, alongside ZIP/date/retrieval context. Icons are decorative; condition text is always present. Weather location and permission live under **Settings → Weather**, reachable from each day card. The selected weekend remains in Plan. “Rain chance” includes snow and other precipitation. It does not reroll, rank or exclude ideas. Weather is never included in saved plans, JSON exports or the database.

## Provider research — October 5, 2026

[Open-Meteo forecast documentation](https://open-meteo.com/en/docs) supports up to 16 days including today, local daily dates using an IANA timezone, `temperature_2m_max`, `temperature_2m_min` and `precipitation_probability_max`. Individual fields can be missing. Forecasts are model estimates and change; service availability is not guaranteed.

[Terms and privacy](https://open-meteo.com/en/terms): the free API is for noncommercial use (including personal home apps), requires no API key, and limits use to fewer than 10,000 calls/day, 5,000/hour and 600/minute. Data attribution is CC BY 4.0. The UI links the provider and license and notes display rounding. Commercial deployments must reassess licensing/access instead of silently using this endpoint. Provider logs may contain coordinates and IP addresses and are deleted after 90 days. No paid plan is configured.

A live contract probe used only generic Beverly Hills coordinates, never household coordinates. It confirmed Fahrenheit/percent units, the requested timezone and 16 daily entries. Offline tests and the isolated preview use generic data.

## Explicit consent and data flow

Weather is off by default and independent of Discover permissions and its weekly job. A browser-session checkbox permits only manual “Check weather” clicks. A page reload resets consent; no weather schedule is created. The endpoint requires a literal JSON boolean `consent: true`, validates ZIP, Saturday and IANA timezone before any network request, and skips all external calls for wholly past/out-of-range weekends.

Zippopotam.us receives the weather ZIP if there is no fresh (30-day) local coordinate cache entry. Open-Meteo receives rounded approximate ZIP-center latitude/longitude, selected in-range dates, forecast timezone, daily variable names and Fahrenheit unit choice. Both providers see the server public IP. No idea, saved plan, household information or credential is sent. Existing public/discovery consent is not treated as weather consent. Deployment approval must disclose this new recipient and data before enabling a real household lookup.

Requests use the existing pinned-public-DNS, certificate-verified HTTPS transport, fixed provider endpoints, no redirects, bounded responses and a 30-second overall deadline. Exceptions are sanitized. There is no arbitrary client-supplied URL and no credential needed.

## Freshness and persistence

A bounded, process-only cache holds at most 32 ZIP/timezone/weekend/local-today entries for one hour; failures are held for 60 seconds to limit retries. No stale forecast is shown after expiry or an outage. Changing date, ZIP, timezone or permission clears visible results and ignores late responses. Long-open results clear after one hour. A retrieved timestamp and location/timezone context accompany every response. Browser consent and forecasts are not stored in localStorage.

Past dates show no forecast; dates beyond local today +15 days show “too early.” A partly eligible weekend can show one day and a fallback for the other. Missing/null/nonfinite/out-of-range values are unknown, never zero. A mismatched provider timezone or units fails closed. Calendar dates and ZoneInfo handle DST rather than adding a fixed 24-hour timestamp.

The existing schema, saved data, discovery scheduler and native Unraid template are unchanged. No migration required. Docker copies the new weather module. Household weather lookups require the separate in-app permission and an explicit Check weather action.

## Integrated day-card verification

Open-Meteo’s documented WMO code mapping supplies sunny/cloudy/fog/drizzle/rain/snow/thunderstorm conditions, including freezing precipitation and hail. Unknown or missing codes show “Condition unknown”; they are never inferred from rain probability. The daily weather code represents the most severe condition of the day, not a promise of constant conditions.

Only generated plans receive live weather slots. Rerolling, locking ideas and repeated generation reuse the current matching forecast without any automatic provider request. ZIP/timezone/date changes, permission revocation, and expiry clear or replace those slots. Saved plans intentionally have no live weather and never store it. The pure presentation test runs with `node tests/weather_view_test.cjs`; the Python suite covers the provider code contract and unknown-code handling.

## Optional Plan B in local review

User-set Indoor/Outdoor/Mixed/Unknown labels and explicit indoor swaps use only an existing valid forecast. No wind field or extra lookup is added. See [Plan B behavior and limits](guide/Settings-and-everyday-use.md#optional-weather-aware-plan-b). Unlike the original weather-only release, this feature adds a version 6 idea column with a pre-migration safety backup; historical saved items are not retroactively labeled.
