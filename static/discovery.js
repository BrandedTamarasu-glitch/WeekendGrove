let discoveryState = null, discoveryDirty = false, discoveryPoll = null;
const discoveryForm = $('#discovery-form');
function renderDiscovery() {
  if (!discoveryState) return;
  const {settings:s,candidates,job} = discoveryState;
  $('#discovery-coverage').textContent=discoveryState.coverage;
  $('#discovery-settings-summary').textContent=s.zip ? `${s.zip} · ${s.local_miles} local miles${s.include_day_trips?' · '+s.day_trip_miles+' day-trip miles':''} · Weekly ${s.enabled?'on':'off'}` : 'ZIP not set · Weekly off';
  if (!discoveryDirty) for (const [key,value] of Object.entries(s)) { const input=discoveryForm.elements[key]; if(typeof value==='boolean') input.checked=value; else input.value=value; }
  $('#refresh-discovery').disabled=job.running || !s.zip || !s.consent;
  $('#refresh-discovery').textContent=job.running?'Refreshing…':'Refresh now';
  const localTime=v=>v?new Date(v).toLocaleString(undefined,{timeZone:s.timezone})+' '+s.timezone:'Never';
  $('#discovery-status').textContent=`${job.outcome}. Last completed: ${localTime(job.last_finished)}. ${job.added} new; ${job.skipped} unsupported records skipped. ${s.enabled?'Next weekly refresh: '+localTime(job.next_run)+'.':'Weekly refresh is off.'}`;
  const pending=candidates.filter(r=>r.status==='pending'&&!r.expired);
  $('#discover-count').textContent=pending.length;
  const rows=$('#discovery-history').checked?candidates:pending;
  $('#discovery-grid').innerHTML=rows.length?rows.map(r=>`<article class="idea-card">${card(r.payload)}<p class="helper">${r.expired?'Event ended · ':''}${r.status==='pending'?'Ready to review':r.status==='saved'?'Saved to idea bank':'Dismissed'}</p>${r.status==='pending'?`<div class="card-actions">${!r.expired?`<button class="secondary" data-discovery-key="${escape(r.key)}" data-discovery-action="save" aria-label="Save ${escape(r.payload.title)} to idea bank">Save to idea bank</button>`:''}<button class="text-button" data-discovery-key="${escape(r.key)}" data-discovery-action="dismiss" aria-label="Dismiss ${escape(r.payload.title)}">Dismiss</button></div>`:''}</article>`).join(''):`<div class="empty"><span aria-hidden="true">⌁</span><h3>${s.zip?'Nothing waiting to be reviewed':'Start with a ZIP code'}</h3><p>${s.zip?'Refresh supported sources when you’re ready. Sparse coverage or no matching dates may mean no new suggestions.':'Open Location & weekly refresh to choose your range and review the public lookup permission.'}</p></div>`;
  clearTimeout(discoveryPoll);
  if(job.running) discoveryPoll=setTimeout(()=>loadDiscovery().catch(e=>notify(e.message,true)),2000);
}
async function loadDiscovery() { discoveryState=await api('/api/discovery'); renderDiscovery(); }
discoveryForm.addEventListener('input',()=>{discoveryDirty=true;});
discoveryForm.addEventListener('submit',async event=>{
  event.preventDefault();const f=discoveryForm.elements,button=discoveryForm.querySelector('button');button.disabled=true;$('#discovery-error').hidden=true;
  const data={zip:f.zip.value,local_miles:Number(f.local_miles.value),day_trip_miles:Number(f.day_trip_miles.value),include_day_trips:f.include_day_trips.checked,timezone:f.timezone.value,weekday:Number(f.weekday.value),time:f.time.value,consent:f.consent.checked,enabled:f.enabled.checked};
  try {await api('/api/discovery/settings',data);discoveryDirty=false;await loadDiscovery();notify(data.consent?'Discovery settings saved. Refresh now whenever you’re ready.':'Discovery settings saved. Public lookups and weekly refresh are off.');}
  catch(error){$('#discovery-error').textContent=error.message;$('#discovery-error').hidden=false;}
  finally{button.disabled=false;}
});
$('#discovery-history').addEventListener('change',renderDiscovery);
$('#refresh-discovery').addEventListener('click',async event=>{
  event.target.disabled=true;
  try {await api('/api/discovery/refresh',{});await loadDiscovery();}
  catch(error){notify(error.message,true);await loadDiscovery();}
});
document.addEventListener('click',async event=>{
  const button=event.target.closest('[data-discovery-action]');if(!button)return;button.disabled=true;
  try {const result=await api('/api/discovery/decision',{key:button.dataset.discoveryKey,action:button.dataset.discoveryAction});await Promise.all([loadDiscovery(),refresh()]);const heading=$('#discover-view h2');heading.tabIndex=-1;heading.focus({preventScroll:true});notify(result.status==='saved'?'Saved to your idea bank. The planner will respect its event dates.':'Suggestion dismissed. Refreshing will not bring it back.');}
  catch(error){notify(error.message,true);button.disabled=false;}
});
loadDiscovery().catch(error=>notify('Could not load Discover. '+error.message,true));
