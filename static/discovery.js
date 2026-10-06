let discoveryState = null, discoveryDirty = false, discoveryPoll = null;
const discoveryForm = $('#discovery-form');
function renderDiscovery() {
  if (!discoveryState) return;
  const {settings:s,candidates,job} = discoveryState;
  $('#discovery-coverage').textContent=discoveryState.coverage;
  const providers=discoveryState.providers || {};
  $('#provider-status').textContent=['geoapify','ticketmaster'].map(name=>`${name==='geoapify'?'Geoapify':'Ticketmaster'}: ${providers[name]?.active?'ready for refresh':providers[name]?.configured?'key configured · permission off':'inactive · server key not configured'}`).join(' · ');
  for(const name of ['geoapify','ticketmaster']) discoveryForm.elements[name+'_consent'].disabled=!providers[name]?.configured;
  $('#discovery-settings-summary').textContent=s.zip ? `${s.zip} · ${s.local_miles} local miles${s.include_day_trips?' · '+s.day_trip_miles+' day-trip miles':''} · Weekly ${s.enabled?'on':'off'}` : 'ZIP not set · Weekly off';
  if (!discoveryDirty) for (const [key,value] of Object.entries(s)) { const input=discoveryForm.elements[key]; if(!input) continue; if(typeof value==='boolean') input.checked=value; else input.value=value; }
  $('#discovery-location').textContent=s.zip?`ZIP ${s.zip} · ${s.local_miles} local miles${s.include_day_trips?' · '+s.day_trip_miles+' day-trip miles':''}`:'Choose your ZIP and sources to begin.';
  $('#discovery-refresh-help').textContent=!s.zip||!s.consent?'Open Discovery settings to choose a ZIP and allow public lookups.':'Review each source before saving. Prices, hours and suitability are unconfirmed.';
  $('#refresh-discovery').disabled=job.running || !s.zip || !s.consent;
  $('#refresh-discovery').textContent=job.running?'Refreshing…':'Refresh now';
  const localTime=v=>v?new Date(v).toLocaleString(undefined,{timeZone:s.timezone})+' '+s.timezone:'Never';
  $('#discovery-run-summary').textContent=`${job.running?'Refreshing…':job.last_finished?'Last checked '+new Date(job.last_finished).toLocaleDateString(undefined,{timeZone:s.timezone}):'Not checked yet'} · Weekly ${s.enabled?'on':'off'}`;
  $('#discovery-status').textContent=`${job.outcome}. Last completed: ${localTime(job.last_finished)}. ${job.added} new; ${job.skipped} unsupported records skipped. ${s.enabled?'Next weekly refresh: '+localTime(job.next_run)+'.':'Weekly refresh is off.'}`;
  const pending=candidates.filter(r=>r.status==='pending'&&!r.expired);
  $('#discover-count').textContent=pending.length;
  const type=$('#discovery-type').value,range=$('#discovery-range').value;
  const rows=($('#discovery-history').checked?candidates:pending).filter(r=>(!type||r.payload.category===type)&&(!range||r.payload.metadata?.range===range));
  $('#discovery-grid').innerHTML=rows.length?rows.map(r=>`<article class="idea-card">${card(r.payload)}<p class="helper">${r.expired?'Ended or stale · ':''}${r.status==='pending'?'Ready to review':r.status==='saved'?'Saved to idea bank':'Dismissed'}</p>${r.status==='pending'?`<div class="card-actions">${!r.expired?`<button class="secondary" data-discovery-key="${escape(r.key)}" data-discovery-action="save" aria-label="Save ${escape(r.payload.title)} to idea bank">Save to idea bank</button>`:''}<button class="text-button" data-discovery-key="${escape(r.key)}" data-discovery-action="dismiss" aria-label="Dismiss ${escape(r.payload.title)}">Dismiss</button></div>`:''}</article>`).join(''):`<div class="empty"><span aria-hidden="true">⌁</span><h3>${(type||range)?'No suggestions match these filters':s.zip?'Nothing waiting to be reviewed':'Start with a ZIP code'}</h3><p>${(type||range)?'Try All types and All ranges to see the rest of your inbox.':s.zip?'Refresh supported sources when you’re ready. Sparse coverage or no matching dates may mean no new suggestions.':'Open Discovery settings to choose your range and review the public lookup permission.'}</p></div>`;
  clearTimeout(discoveryPoll);
  if(job.running) discoveryPoll=setTimeout(()=>loadDiscovery().catch(e=>notify(e.message,true)),2000);
}
async function loadDiscovery() { discoveryState=await api('/api/discovery'); renderDiscovery(); }
discoveryForm.addEventListener('input',()=>{discoveryDirty=true;});
discoveryForm.addEventListener('submit',async event=>{
  event.preventDefault();const f=discoveryForm.elements,button=discoveryForm.querySelector('button');button.disabled=true;$('#discovery-error').hidden=true;
  const data={zip:f.zip.value,local_miles:Number(f.local_miles.value),day_trip_miles:Number(f.day_trip_miles.value),include_day_trips:f.include_day_trips.checked,timezone:f.timezone.value,weekday:Number(f.weekday.value),time:f.time.value,consent:f.consent.checked,enabled:f.enabled.checked,geoapify_consent:f.geoapify_consent.checked,ticketmaster_consent:f.ticketmaster_consent.checked};
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
  try {const result=await api('/api/discovery/decision',{key:button.dataset.discoveryKey,action:button.dataset.discoveryAction});await Promise.all([loadDiscovery(),refresh()]);const heading=$('#discover-view h2');heading.tabIndex=-1;heading.focus({preventScroll:true});notify(result.status==='saved'?'Saved to your idea bank. Check the source for current details before planning.':'Suggestion dismissed. Refreshing will not bring it back.');}
  catch(error){notify(error.message,true);button.disabled=false;}
});
loadDiscovery().catch(error=>notify('Could not load Discover. '+error.message,true));

for(const id of ['discovery-type','discovery-range'])$('#'+id).addEventListener('change',renderDiscovery);
$('#open-discovery-settings').addEventListener('click',()=>{setView('settings');$('#discovery-settings').open=true;const summary=$('#discovery-settings summary');summary.focus();summary.scrollIntoView({block:'start'});});
