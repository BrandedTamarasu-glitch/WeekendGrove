# Weather

[Guide home](Home.md) · [Everyday use](Settings-and-everyday-use.md)

Weather is optional and needs **no API key**. It adds condition text/icons and Fahrenheit high/low temperatures inside the generated Saturday/Sunday cards. It does not change the planner's suggestions.

1. Choose your weekend in **Plan** and generate a plan.
2. Open **Settings → Weather**, or **Weather settings** on either day card.
3. Enter a US ZIP and an IANA timezone. Read **Where weather data goes**.
4. Check **Allow these weather lookups when I press Check weather**, then press **Check weather**.
5. Use **Return to Plan** to see the same plan with matching forecast information.

Zippopotam.us receives the ZIP if a fresh local coordinate cache is unavailable. Open-Meteo receives approximate ZIP-center coordinates, the selected eligible dates, timezone and forecast fields. Both see your server's public IP. Your ideas and saved plans are not sent. No browser geolocation permission is needed.

Permission resets on page reload. Navigation, plan generation, rerolls and discovery's weekly job never request weather automatically. Turning permission off or changing ZIP/timezone/weekend clears the old display. Forecasts expire after one hour and are held only in server memory, not saved in plans, JSON exports or SQLite.

The forecast horizon is up to 16 days **including today**. Later weekends show “too early”; past days and missing data are shown as unavailable/unknown. One day may be available while the other is not. Daily condition codes represent the most severe predicted condition, not all-day constant weather. Maximum precipitation probability includes snow; it is not just a rain guarantee.

The app uses Open-Meteo's noncommercial free endpoint. Review [current terms](https://open-meteo.com/en/terms) before use outside a personal home installation; no paid/commercial endpoint is configured. Attribution remains visible: [Open-Meteo](https://open-meteo.com/) / [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) and [Zippopotam.us](https://docs.zippopotam.us/) / [GeoNames](https://www.geonames.org/) / [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/).
