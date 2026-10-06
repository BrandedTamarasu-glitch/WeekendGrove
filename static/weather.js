/* Explicit manual lookups only; no weather is added to plan objects or storage. */
(() => {
  const form=document.querySelector('#weather-form'), result=document.querySelector('#weather-result');
  const button=document.querySelector('#check-weather'), weekend=document.querySelector('#planner-form').elements.weekend_date;
  let sequence=0,loading=false,expires,data=null,error='';
  const context=()=>({zip:form.elements.zip.value,zone:form.elements.timezone.value,consent:form.elements.consent.checked,loading,data,error});
  const paint=()=>document.querySelectorAll('#plan-output [data-plan-weather]').forEach(slot=>{slot.innerHTML=WeatherDisplay.card(slot.dataset.planWeather,context());});
  window.GroveWeather={card:date=>WeatherDisplay.card(date,context())};
  function clear(message='') {
    sequence++;loading=false;data=null;error=message;clearTimeout(expires);
    button.disabled=!form.elements.consent.checked;button.textContent='Check weather';
    result.textContent=message||'Check weather for the selected weekend and ZIP. Previous forecasts have been cleared.';paint();
  }
  function weekendContext(){document.querySelector('#weather-weekend-context').textContent='Forecast dates follow the weekend selected in Plan: '+weekend.value+'. Change the weekend in Plan before checking weather.';}
  weekendContext();
  form.addEventListener('input',()=>clear());weekend.addEventListener('change',()=>{clear();weekendContext();});
  api('/api/discovery').then(value=>{
    if(!form.elements.zip.value){form.elements.zip.value=value.settings.zip||'';form.elements.timezone.value=value.settings.timezone||'America/Los_Angeles';paint();}
  }).catch(()=>{});
  form.addEventListener('submit',async event=>{
    event.preventDefault();if(loading||!form.elements.consent.checked)return;
    const request={zip:form.elements.zip.value,timezone:form.elements.timezone.value,weekend_date:weekend.value,consent:true};
    const current=++sequence;clearTimeout(expires);loading=true;data=null;error='';button.disabled=true;button.textContent='Checking…';
    result.textContent='Checking the forecast window…';paint();
    try {
      const response=await api('/api/weather',request);if(current!==sequence)return;
      data=response;loading=false;paint();
      result.innerHTML=`<p class="helper">${data.status==='unavailable'?'Forecast unavailable. Try again later.':data.status==='outside_window'?'These dates are outside the forecast window.':'Weather updated for ZIP '+escape(data.zip)+'. Forecasts appear in the matching Saturday and Sunday plan cards.'}</p>${document.querySelector('#plan-output [data-plan-weather]')?'':'<p class="helper">Generate your weekend to see the daily weather beside your ideas.</p>'}`;
      if(data.fetched_at)expires=setTimeout(()=>clear('Forecast expired · check weather again.'),Math.max(0,3600000-(Date.now()-Date.parse(data.fetched_at))));
    } catch(e){if(current===sequence){loading=false;error=e.message;result.textContent=error;paint();}}
    finally{if(current===sequence){loading=false;button.disabled=!form.elements.consent.checked;button.textContent='Check weather';}}
  });
})();
