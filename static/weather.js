/* No automatic provider requests. Weather permission is per browser session and separate from discovery. */
(() => {
  const form = document.querySelector('#weather-form');
  const result = document.querySelector('#weather-result');
  const button = document.querySelector('#check-weather');
  const weekend = document.querySelector('#planner-form').elements.weekend_date;
  let sequence = 0, loading = false, expires;
  function clear() {
    sequence++; loading = false; clearTimeout(expires);
    button.disabled = !form.elements.consent.checked;
    button.textContent = 'Check weather';
    result.innerHTML = '<p class="helper">Check weather for the selected weekend and ZIP. Previous results have been cleared.</p>';
  }
  form.addEventListener('input', clear);
  weekend.addEventListener('change', clear);
  // This reads only local app settings; it does not call a weather or ZIP provider.
  api('/api/discovery').then(data => {
    if (!form.elements.zip.value) {
      form.elements.zip.value = data.settings.zip || '';
      form.elements.timezone.value = data.settings.timezone || 'America/Los_Angeles';
    }
  }).catch(() => {});
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (loading || !form.elements.consent.checked) return;
    const request = {zip:form.elements.zip.value, timezone:form.elements.timezone.value,
      weekend_date:weekend.value, consent:true};
    const current = ++sequence;
    loading = true; button.disabled = true; button.textContent = 'Checking…';
    result.innerHTML = '<p class="helper">Checking the forecast window…</p>';
    try {
      const data = await api('/api/weather', request);
      if (current !== sequence) return;
      const messages = {past:'This date has passed. No forecast is shown.',too_early:'Too early for a forecast. Check again within 16 days.',unavailable:'Forecast unavailable. Try again later.',partial:'Some forecast details are unavailable.'};
      const shown = value => value == null ? 'Unknown' : Math.round(value);
      result.innerHTML = `<p class="weather-context">ZIP ${escape(data.zip)} · ${escape(data.timezone)}${data.fetched_at ? ` · Retrieved ${escape(new Date(data.fetched_at).toLocaleString(undefined,{timeZone:data.timezone}))}${data.cached?' · Cached':''}`:''}</p><div class="weather-days">${data.days.map(day=>`<section class="weather-day" aria-label="${escape(day.day)} weather"><h3>${escape(day.day)} <small>${escape(day.date)}</small></h3>${day.status==='available'||day.status==='partial'?`<div class="weather-metrics"><span>High<strong>${shown(day.high)}${day.high==null?'':'°F'}</strong></span><span>Low<strong>${shown(day.low)}${day.low==null?'':'°F'}</strong></span><span>Rain chance<strong>${shown(day.rain)}${day.rain==null?'':'%'}</strong></span></div>`:''}${messages[day.status]?`<p class="helper">${messages[day.status]}</p>`:''}</section>`).join('')}</div>`;
      // Never leave an old forecast looking current in a long-open tab.
      if (data.fetched_at) {
        const remaining = Math.max(0,3600000-(Date.now()-Date.parse(data.fetched_at)));
        expires = setTimeout(() => { clear(); result.innerHTML='<p class="helper">Forecast is over an hour old. Check weather again for current information.</p>'; },remaining);
      }
    } catch (error) {
      if (current === sequence) result.innerHTML = `<p class="error">${escape(error.message)}</p>`;
    } finally {
      if (current === sequence) {loading=false;button.disabled=!form.elements.consent.checked;button.textContent='Check weather';}
    }
  });
})();
