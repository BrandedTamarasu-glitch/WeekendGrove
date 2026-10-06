/* Pure forecast presentation: never initiates a lookup or changes a plan. */
const WeatherDisplay = (() => {
  const conditions = {
    0:['☀','Sunny'],1:['🌤','Mostly sunny'],2:['⛅','Partly cloudy'],3:['☁','Cloudy'],
    45:['≋','Foggy'],48:['≋','Freezing fog'],51:['🌦','Light drizzle'],53:['🌦','Drizzle'],55:['🌧','Heavy drizzle'],
    56:['🌧','Freezing drizzle'],57:['🌧','Heavy freezing drizzle'],61:['🌦','Light rain'],63:['🌧','Rain'],65:['🌧','Heavy rain'],
    66:['🌧','Freezing rain'],67:['🌧','Heavy freezing rain'],71:['❄','Light snow'],73:['❄','Snow'],75:['❄','Heavy snow'],77:['❄','Snow grains'],
    80:['🌦','Rain showers'],81:['🌧','Rain showers'],82:['🌧','Heavy rain showers'],85:['❄','Snow showers'],86:['❄','Heavy snow showers'],
    95:['⛈','Thunderstorms'],96:['⛈','Thunderstorms with hail'],97:['⛈','Strong thunderstorms'],99:['⛈','Thunderstorms with heavy hail']
  };
  const esc = v => String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function todayIn(zone,now) {
    const parts = new Intl.DateTimeFormat('en-US',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date(now));
    return ['year','month','day'].map(k=>parts.find(p=>p.type===k).value).join('-');
  }
  function card(date,c,now=Date.now()) {
    const action='<button class="text-button" type="button" data-weather-jump>Weather settings</button>';
    const note = text => `<p class="weather-inline-note">${esc(text)}</p>${action}`;
    if (!date) return note('Choose a dated weekend to check weather.');
    let today;
    try {today=todayIn(c.zone,now);} catch (_) {return note('Choose a valid forecast timezone.');}
    const horizon=new Date(today+'T12:00:00Z');horizon.setUTCDate(horizon.getUTCDate()+15);
    if(date<today)return note('Past date · no forecast shown.');
    if(date>horizon.toISOString().slice(0,10))return note('Too early · forecasts reach up to 16 days ahead.');
    if(!c.consent)return note('Weather is optional · allow weather lookups to see this day.');
    if(c.loading)return note('Checking weather…');
    if(c.error)return note(c.error);
    const data=c.data;
    if(!data||data.zip!==c.zip||data.timezone!==c.zone)return note('Weather not checked for this ZIP and weekend.');
    const day=data.days.find(d=>d.date===date);
    if(!day)return note('Weather not checked for this date.');
    if(day.status==='too_early')return note('Too early · check closer to this weekend.');
    if(day.status==='past')return note('Past date · no forecast shown.');
    if(day.status==='unavailable')return note('Forecast unavailable · try again later.');
    const age=now-Date.parse(data.fetched_at);
    if(!Number.isFinite(age)||age<0||age>=3600000)return note('Forecast expired · check weather again.');
    const [icon,label]=Number.isInteger(day.code)&&conditions[day.code]||['?','Condition unknown'];
    const temp=v=>typeof v==='number'&&Number.isFinite(v)?`${Math.round(v)}°F`:'unknown';
    const stamp=new Date(data.fetched_at).toLocaleString(undefined,{timeZone:c.zone,month:'short',day:'numeric',hour:'numeric',minute:'2-digit',timeZoneName:'short'});
    return `<div class="weather-inline-main"><span class="weather-symbol" aria-hidden="true">${icon}</span><div><strong>${label}</strong><p>High ${temp(day.high)} <span aria-hidden="true">·</span> Low ${temp(day.low)}</p></div></div><p class="weather-inline-context">ZIP ${esc(c.zip)} area · checked ${esc(stamp)}${data.cached?' · cached':''}<br>ZIP forecast; outing destinations may differ.</p><p class="weather-inline-source"><a href="https://open-meteo.com/" target="_blank" rel="noopener noreferrer">Open-Meteo</a> · <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener noreferrer">CC BY 4.0</a> · ${action}</p>`;
  }
  return {card,conditions};
})();
if(typeof module!=='undefined')module.exports=WeatherDisplay;
