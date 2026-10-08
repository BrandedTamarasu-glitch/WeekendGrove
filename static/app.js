const $ = (selector) => document.querySelector(selector);
const categories = ['Projects', 'Restaurants', 'Places', 'Activities'];
const symbols = {Projects: '⌂', Restaurants: '◡', Places: '⌁', Activities: '✳'};
const initialDefaults = {duration:60, cost:20, energy:'medium'};
const currencySymbols = {USD:'$',CAD:'$',EUR:'€',GBP:'£',AUD:'$',NZD:'$'};
let state = {ideas: [], plans: [], defaults:initialDefaults, currency:'USD',currency_assumed:false}, filter = 'All', plan = null, locks = new Set(), busy = false;
let planName = '', defaultsDirty = false, currencyDirty = false, restoreCandidate = null, restoreSequence = 0, restoreBusy = false;
const escape = (value) => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = (n, currency = state.currency) => `${new Intl.NumberFormat(undefined,{style:'currency',currency,currencyDisplay:'narrowSymbol',minimumFractionDigits:0,maximumFractionDigits:2}).format(n)} ${currency}`;
const denomination = (currency) => `${currencySymbols[currency]} ${currency}`;
function notify(message, error = false) { $('#notice').setAttribute('role', error ? 'alert' : 'status'); $('#notice-message').textContent = message; $('#notice').hidden = false; $('#notice').classList.toggle('error', error); }
async function api(path, data) {
  const response = await fetch(path, data === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Something went wrong. Try again.');
  return result;
}
async function refresh() {
  state = await api('/api/state');
  // Keep an already-open browser usable while the local server is upgraded.
  state.currency ??= 'USD'; state.currency_assumed ??= true;
  state.plans.forEach(p => {p.currency ??= 'USD'; p.currency_assumed ??= true;});
  renderIdeas(); renderSaved(); renderDefaults(); renderCurrency(); window.GrovePlanB?.invalidate();
}
function defaultText(d, currency = state.currency) { return `${d.duration} min · ${money(d.cost,currency)} · ${d.energy} energy`; }
function renderCurrency() {
  $('#currency-summary').textContent = denomination(state.currency) + (state.currency_assumed ? ' · assumed' : '');
  if (!currencyDirty) $('#currency-form').elements.currency.value = state.currency;
  $('#currency-assumption').hidden = !state.currency_assumed;
  $('#currency-assumption').textContent = `Older amounts had no currency label. ${state.currency} is assumed until you confirm your currency. Older saved plans retain their visible assumption.`;
  document.querySelectorAll('.currency-label').forEach(e => e.textContent = denomination(state.currency));
}
function renderDefaults() {
  $('#defaults-summary').textContent = defaultText(state.defaults);
  if (!defaultsDirty) for (const key of ['duration','cost','energy']) $('#defaults-form').elements[key].value = state.defaults[key];
}
function setView(view, fromHistory = false) {
  if(!['ideas','discover','planner','saved','settings'].includes(view))view='ideas';
  if(!fromHistory && location.hash !== '#'+view)history.pushState(null,'','#'+view);
  for (const name of ['ideas','discover','planner','saved','settings']) $(`#${name}-view`).hidden = name !== view;
  document.querySelectorAll('[data-view]').forEach(button => {const active = button.dataset.view === view; button.classList.toggle('active', active); if (active) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current');});
  const heading = $(`#${view}-view h2`); heading.tabIndex = -1; heading.focus();
}
function metrics(idea, planning = false, defaults = initialDefaults, currency = state.currency) {
  const duration = idea.duration ?? (planning ? defaults.duration : null), cost = idea.cost ?? (planning ? defaults.cost : null), energy = idea.energy || (planning ? defaults.energy : '');
  return `<div class="metrics"><span>${duration === null ? 'Time unknown' : duration + ' min' + (idea.duration === null ? ' · estimate' : '')}</span><span>${cost === null ? 'Cost unknown ('+currency+')' : money(cost,currency) + (idea.cost === null ? ' · estimate' : '')}</span><span>${energy ? escape(energy) + ' energy' + (!idea.energy ? ' · estimate' : '') : 'Energy unknown'}</span></div>`;
}
function card(idea, planning = false, defaults = initialDefaults, currency = state.currency) {
  return `<div class="card-top"><span class="category-icon ${idea.category.toLowerCase()}" aria-hidden="true">${symbols[idea.category] || '✳'}</span><span class="category">${escape(idea.category)}</span>${idea.sample ? '<span class="sample">Generic demo</span>' : ''}</div>${planning?'<h4>':'<h3>'}${escape(idea.title)}${planning?'</h4>':'</h3>'}${idea.location ? `<p class="location">${escape(idea.location)}</p>` : ''}${metrics(idea, planning, defaults, currency)}${idea.environment?`<p class="environment-label">${escape({indoor:'Indoor · user label',outdoor:'Outdoor · user label',mixed:'Mixed indoor/outdoor · user label',unknown:'Indoor/outdoor unknown'}[idea.environment]||'Indoor/outdoor unknown')}</p>`:''}${provenance(idea.metadata)}`;
}
function provenance(m) {
  if (!m?.source_url) return '';
  // Source URLs are validated at import; keep a second guard at rendering.
  let url; try {url = new URL(m.source_url); if (url.protocol !== 'https:') return '';} catch {return '';}
  return `<details class="provenance"><summary>${escape(m.source_name)} · ${escape(m.range)} · ${escape(m.distance_miles)} mi · checked ${escape(m.fetched_at.slice(0,10))}</summary><p>${escape(m.range)} · about ${escape(m.distance_miles)} straight-line miles</p><p>${m.start_date?escape(m.start_date)+(m.end_date!==m.start_date?' – '+escape(m.end_date):'')+' · ':''}${escape(m.time_label)}</p><a href="${escape(url.href)}" target="_blank" rel="noopener noreferrer">${escape(m.source_name)}</a>${m.source_id==='geoapify'?'<p>Places data: <a href="https://www.geoapify.com/" target="_blank" rel="noopener noreferrer">Geoapify</a> · <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">© OpenStreetMap contributors</a></p>':''}<p>Checked ${escape(m.fetched_at.slice(0,10))}. ZIP-center estimate; confirm current details and suitability.</p></details>`;
}
function renderIdeas() {
  $('#idea-count').textContent = state.ideas.filter(i => !i.archived).length;
  $('#plan-count').textContent = state.plans.length;
  const demos = state.ideas.filter(i => i.sample && !i.archived).length;
  $('#archive-samples').hidden = !demos;
  $('#demo-description').textContent = demos ? `${demos} generic demo ideas are available. Archive them to start with your own; your ideas and saved plans stay.` : 'Demo ideas are optional. Add your own ideas anytime; archived demos can be restored.';
  $('#category-filters').innerHTML = ['All', ...categories].map(c => `<button class="chip ${filter === c ? 'selected' : ''}" data-category="${c}" aria-pressed="${filter === c}">${c === 'All' ? 'All ideas' : c}</button>`).join('');
  const archived = $('#show-archived').checked;
  const query=$('#idea-search').value.trim().toLocaleLowerCase();
  const ideas = state.ideas.filter(i => Boolean(i.archived) === archived && (filter === 'All' || i.category === filter) && (!query || (i.title+' '+i.location).toLocaleLowerCase().includes(query)));
  $('#idea-grid').innerHTML = ideas.length ? ideas.map(i => `<article class="idea-card ${i.archived ? 'archived' : ''}">${card(i)}<div class="card-actions"><button class="text-button" data-edit="${i.id}" aria-label="Edit ${escape(i.title)}">Edit</button><button class="text-button" data-archive="${i.id}" aria-label="${i.archived ? 'Restore' : 'Archive'} ${escape(i.title)}">${i.archived ? 'Restore' : 'Archive'}</button></div></article>`).join('') : `<div class="empty"><span aria-hidden="true">✳</span><h3>${archived ? 'No archived ideas here' : state.ideas.length ? 'A little room for more' : 'Every good weekend starts with an idea'}</h3><p>${archived ? 'Archived ideas can be restored whenever you want.' : 'Add an idea, or load generic sample ideas in Settings.'}</p></div>`;
}
function openIdea(id) {
  const form = $('#idea-form'); form.reset(); form.querySelector('details').open = false;
  const idea = state.ideas.find(i => i.id === id);
  if (idea) { for (const key of ['id','title','category','duration','cost','location','energy','environment']) form.elements[key].value = idea[key] ?? (key==='environment'?'unknown':''); form.querySelector('details').open = true; }
  $('#dialog-title').textContent = idea ? 'Edit your idea' : 'Add an idea'; $('#form-error').hidden = true;
  $('#idea-estimates').textContent = `Blank details stay unknown. During planning, estimates are ${defaultText(state.defaults)}.${idea?.sample ? ' Editing a demo saves it as your own idea.' : ''}`;
  $('#idea-dialog').showModal(); form.elements.title.focus();
}
const days = ['Saturday','Sunday'];
function limits() {
  const f = $('#planner-form').elements;
  return {weekend_date:f.weekend_date.value, minutes:Number(f.minutes.value), budget:Number(f.budget.value), energy:f.energy.value, count:Number(f.count.value),
    day_caps:Object.fromEntries(days.map(d=>[d,Object.fromEntries(categories.map(c=>[c,Number(f[`cap-${d}-${c}`].value)]))])),include_lazy:$('#include-lazy').checked};
}
function weekendDay(start,day) { const d=new Date(start+'T12:00:00Z'); if(day==='Sunday')d.setUTCDate(d.getUTCDate()+1); return d.toISOString().slice(0,10); }
function scheduledIds(p) {return (p.schedule || []).map(e=>e.id);}
function scheduleHTML(p, interactive = false) {
  if (!p.schedule?.length) return `<p class="helper">Older plan: day assignments were not saved. These suggestions remain unassigned.</p><section class="day-section"><h4>Day unspecified</h4>${p.items.map(i=>`<article class="idea-card">${card(i,true,p.defaults,p.currency)}</article>`).join('')}</section>`;
  return `<div class="weekend-days">${days.map(day=>{
    const entries = p.schedule.filter(e=>e.day===day);
    const total = entries.reduce((n,e)=>n+(e.kind==='lazy'?e.duration:(p.items.find(i=>i.id===e.id).duration ?? p.defaults.duration)),0);
    return `<section class="day-section" aria-label="${day} plan"><div class="day-heading"><h3>${day}${p.limits.weekend_date?` <small>${escape(weekendDay(p.limits.weekend_date,day))}</small>`:''}</h3><span>${total} min planned</span></div>${interactive?`<div class="plan-weather" data-plan-weather="${escape(p.limits.weekend_date?weekendDay(p.limits.weekend_date,day):'')}" aria-label="${day} weather" aria-live="polite">${window.GroveWeather?.card(p.limits.weekend_date?weekendDay(p.limits.weekend_date,day):'')||'Weather not checked.'}</div>`:''}<div class="day-activities">${entries.length?entries.map(e=>{
      const i=p.items.find(i=>i.id===e.id), label=e.kind==='lazy'?`Lazy Day time on ${day}`:i.title;
      return `<article class="idea-card plan-card ${locks.has(e.id)&&interactive?'locked':''} ${e.kind==='lazy'?'lazy-card':''}">${e.kind==='lazy'?`<p class="eyebrow">ROOM TO RELAX</p><h4>Lazy Day time</h4><p class="helper">Rest, wander, or leave this time open.</p><div class="metrics"><span>${e.duration} min</span><span>${money(0,p.currency)}</span><span>No category quota</span></div>`:card(i,true,p.defaults,p.currency)}${interactive?`<button class="lock-button" data-lock="${e.id}" aria-label="${locks.has(e.id)?'Unlock':'Lock'} ${escape(label)}" aria-pressed="${locks.has(e.id)}">${locks.has(e.id)?'● Locked · keep this':'○ Lock this suggestion'}</button>${e.kind==='idea'?`<div class="plan-b-slot" data-plan-b-slot="${e.id}"></div>`:''}`:''}</article>`;
    }).join(''):'<p class="day-empty">No suggestions on this day. Keep the space open.</p>'}</div></section>`;
  }).join('')}</div>`;
}
function renderPlan() {
  const out = $('#plan-output');
  if (!plan.schedule?.length) {out.innerHTML='<div class="empty"><h3>No suggestions fit just yet</h3><p>Try more time or budget, raise a daily category maximum, or add another idea. Lazy Day blocks need at least 30 minutes.</p><button class="secondary" id="back-to-bank">Go to idea bank</button></div>';return;}
  const allLocked = scheduledIds(plan).every(id=>locks.has(id));
  out.innerHTML = `<div class="plan-heading"><div><p class="eyebrow">A FEW GOOD POSSIBILITIES</p><h2>Your weekend, lightly planned</h2><p>${plan.minutes} of ${plan.limits.minutes} minutes · ${money(plan.cost,plan.currency)} of ${money(plan.limits.budget,plan.currency)}</p></div><button class="secondary" id="reroll" ${allLocked?'disabled':''}>${allLocked?'All suggestions locked':'↻ Reroll unlocked'}</button></div><p class="helper plan-estimates">Estimates used for unknown details: ${escape(defaultText(plan.defaults,plan.currency))}. Each estimated value is labeled.</p>${plan.currency_assumed?`<p class="helper">${plan.currency} assumed: original cost units were unspecified. Amounts were not converted.</p>`:''}${plan.currency!==state.currency?`<p class="helper">This preview keeps ${plan.currency}. Reroll to use the current ${state.currency} label; numeric costs are not converted.</p>`:''}${scheduleHTML(plan,true)}<p class="helper">${plan.items.length<plan.limits.count?'Fewer ideas fit these maximums; empty space is welcome. ':''}Time and budget are shared across both days. Locks preserve the suggestion and its day. Relaxation blocks use time, with no cost or category quota.</p><button class="secondary" type="button" data-itinerary="current">Download / print itinerary</button><div id="plan-b-undo" class="plan-b-undo" aria-live="polite"></div><form id="save-plan" class="save-bar"><label for="plan-name">Keep this weekend</label><input id="plan-name" name="name" maxlength="120" placeholder="e.g. A slow October weekend" value="${escape(planName)}" required><button class="primary" type="submit">Save plan</button></form>`;
  window.GrovePlanB?.paint();
}
async function generate() {
  if(window.GrovePlanB?.isPending()){notify('Wait for the Plan B check to finish first.');return;}
  if (busy) return;
  busy = true; $('#generate').disabled = true; const reroll = $('#reroll'); if (reroll) reroll.disabled = true;
  try {
    const previous = plan ? scheduledIds(plan) : [];
    const next = await api('/api/generate', {...limits(), locked:[...locks], previous, previous_schedule:plan?.schedule || [], include_samples:$('#include-samples').checked});
    next.currency ??= state.currency; next.currency_assumed ??= state.currency_assumed;
    window.GrovePlanB?.reset(); plan = next; renderPlan();
    const same = previous.length && previous.length === scheduledIds(plan).length && previous.every(id => scheduledIds(plan).includes(id));
    notify(same ? 'These ideas still fit best. Add more ideas for more variety, or unlock a suggestion.' : plan.schedule.length ? 'A little weekend possibility is ready. Lock anything you want to keep.' : 'No match within those limits. Your idea bank is safe.');
    const heading = outHeading(); heading.tabIndex = -1; heading.focus(); heading.scrollIntoView({block:'start'});
  } catch (error) { notify(error.message, true); }
  finally { busy = false; $('#generate').disabled = false; if ($('#reroll') && plan) $('#reroll').disabled = scheduledIds(plan).every(id => locks.has(id)); }
}
function outHeading() { return $('#plan-output h2') || $('#plan-output h3'); }
function renderSaved() {
  const opened=new Set([...document.querySelectorAll('.saved-plan[open]')].map(el=>el.dataset.saved));
  const ordered=[...state.plans].sort((a,b)=>(b.limits.weekend_date||'').localeCompare(a.limits.weekend_date||'')||b.created.localeCompare(a.created));
  $('#saved-plans').innerHTML=ordered.length?ordered.map(p=>`<details class="saved-plan" data-saved="${p.id}" ${opened.has(String(p.id))?'open':''}><summary class="saved-head"><span><span class="eyebrow">${p.limits.weekend_date?escape(p.limits.weekend_date)+' — '+escape(weekendDay(p.limits.weekend_date,'Sunday')):'Weekend dates not recorded'}</span><span class="saved-name">${escape(p.name)}</span><span class="saved-total">${p.minutes} min · ${money(p.cost,p.currency)}</span></span><span class="view-snapshot">View snapshot</span></summary><div class="snapshot-content"><p class="helper">Saved ${escape(new Date(p.created).toLocaleDateString(undefined,{month:'short',day:'numeric',year:'numeric'}))}. Snapshot estimates: ${escape(defaultText(p.defaults,p.currency))}. Forecasts are not stored.</p>${p.currency_assumed?`<p class="helper">${p.currency} assumed for this older plan. Amounts were not converted.</p>`:''}${scheduleHTML(p)}<button class="secondary" type="button" data-itinerary="${p.id}">Download / print itinerary</button></div></details>`).join(''):'<div class="empty"><span aria-hidden="true">☀</span><h3>A good weekend is worth keeping</h3><p>Generate a plan, then give it a name to save it here.</p><button class="secondary" id="start-planning">Find a weekend</button></div>';
}
document.addEventListener('click', async event => {
  const button = event.target.closest('button'); if (!button) return;
  if (button.dataset.view) setView(button.dataset.view);
  if (button.hasAttribute('data-weather-jump')) { setView('settings'); $('#weather-settings').open=true; const heading=$('#weather-heading'); heading.tabIndex=-1; heading.focus({preventScroll:true}); heading.scrollIntoView({block:'start'}); }
  if (button.id === 'dismiss-notice') {$('#notice').hidden = true; const heading = document.querySelector('main section:not([hidden]) h2'); if (heading) {heading.tabIndex = -1; heading.focus({preventScroll:true});}}
  if (button.hasAttribute('data-plan-jump')) { setView('planner'); const heading=outHeading(); if(heading){heading.tabIndex=-1;heading.focus();heading.scrollIntoView({block:'start'});} }
  if (button.dataset.category) { filter = button.dataset.category; renderIdeas(); document.querySelector(`[data-category="${filter}"]`).focus(); }
  if (button.id === 'add-idea') openIdea();
  if (button.dataset.edit) openIdea(Number(button.dataset.edit));
  if (['close-dialog','cancel-dialog'].includes(button.id)) $('#idea-dialog').close();
  if (button.id === 'open-restore') {
    restoreCandidate = null; restoreSequence++; $('#restore-file').value = ''; $('#restore-preview').textContent = ''; $('#restore-error').hidden = true; $('#restore-defaults').checked = false; $('#restore-discovery').checked = false; $('#acknowledge-relabel').checked = false; $('#restore-currency-consent').hidden = true; $('#apply-restore').disabled = true;
    $('#restore-dialog').showModal(); $('#restore-file').focus();
  }
  if (['close-restore','cancel-restore'].includes(button.id)) {restoreSequence++; $('#restore-dialog').close();}
  if (button.id === 'back-to-bank') setView('ideas');
  if (button.id === 'start-planning') setView('planner');
  if (button.dataset.lock) { const id = Number(button.dataset.lock); locks.has(id) ? locks.delete(id) : locks.add(id); renderPlan(); $(`[data-lock="${id}"]`).focus(); }
  if (button.id === 'reroll') await generate();
  if (button.id === 'archive-samples') {
    button.disabled = true;
    try {const result = await api('/api/archive-samples',{}); await refresh(); notify(`${result.count} demo ideas archived. Your own ideas and saved plans are unchanged. Restore demos using Show archived.`);}
    catch (error) {notify(error.message,true);} finally {button.disabled = false;}
  }
  if (button.id === 'apply-restore' && restoreCandidate && !restoreBusy) {
    restoreBusy = true; button.disabled = true; $('#restore-error').hidden = true;
    try {
      const result = await api('/api/restore',{backup_text:restoreCandidate.text, digest:restoreCandidate.summary.digest, apply_defaults:$('#restore-defaults').checked, apply_discovery:$('#restore-discovery').checked, acknowledge_relabel:$('#acknowledge-relabel').checked});
      restoreCandidate = null; $('#restore-dialog').close(); defaultsDirty = false; currencyDirty = false; await refresh();
      notify(`Restored ${result.ideas_to_add} ideas and ${result.plans_to_add} plans. Kept ${result.ideas_skipped} existing ideas and ${result.plans_skipped} existing plans unchanged.${result.defaults_applied ? ' Backup estimates and currency applied.' : ''} Numeric amounts were not converted.${result.discovery_preferences_applied ? ' Discovery preferences restored; public lookups and weekly refresh are off.' : ''}`); loadDiscovery();
    } catch (error) {$('#restore-error').textContent = error.message; $('#restore-error').hidden = false;}
    finally {restoreBusy = false; updateRestoreConsent();}
  }
  if (button.dataset.archive || button.id === 'load-samples') {
    button.disabled = true;
    try {
      if (button.dataset.archive) {const idea = state.ideas.find(i => i.id === Number(button.dataset.archive)); await api('/api/archive',{id:idea.id, archived:!idea.archived}); notify(idea.archived ? 'Idea restored.' : 'Idea archived. You can restore it using Show archived.');}
      else {await api('/api/samples',{}); notify('Generic sample ideas loaded. Each is labeled Sample.');}
      await refresh();
    } catch (error) {notify(error.message,true);} finally {button.disabled = false;}
  }
});
document.addEventListener('input', event => {
  if (event.target.id === 'plan-name') planName = event.target.value;
  if (event.target.closest('#defaults-form')) defaultsDirty = true;
  if (event.target.closest('#currency-form')) currencyDirty = true;
});
$('#currency-form').addEventListener('submit', async event => {
  event.preventDefault(); const button = event.target.querySelector('button'); button.disabled = true; $('#currency-error').hidden = true;
  try {
    await api('/api/currency',{currency:event.target.elements.currency.value}); currencyDirty = false; await refresh(); if (plan) renderPlan();
    notify(`Currency saved as ${denomination(state.currency)}. Existing idea costs, estimates, and the current budget keep their numeric values. Previews and saved plans keep their captured currency; no conversion occurs.`);
  } catch (error) {$('#currency-error').textContent = error.message; $('#currency-error').hidden = false;}
  finally {button.disabled = false;}
});
$('#defaults-form').addEventListener('submit', async event => {
  event.preventDefault(); const f = event.target.elements, button = event.target.querySelector('button'); button.disabled = true; $('#defaults-error').hidden = true;
  try {await api('/api/defaults',{duration:Number(f.duration.value), cost:Number(f.cost.value), energy:f.energy.value}); defaultsDirty = false; await refresh(); notify('Estimates saved. Generate or reroll to use them; existing previews and saved plans keep their original estimates.');}
  catch (error) {$('#defaults-error').textContent = error.message; $('#defaults-error').hidden = false;}
  finally {button.disabled = false;}
});
$('#restore-file').addEventListener('change', async event => {
  const file = event.target.files[0], sequence = ++restoreSequence;
  restoreCandidate = null; $('#apply-restore').disabled = true; $('#restore-error').hidden = true; $('#restore-preview').textContent = '';
  if (!file) return;
  try {
    if (file.size > 2 * 1024 * 1024) throw new Error('Choose a JSON export smaller than 2 MiB.');
    $('#restore-preview').textContent = 'Checking every record…';
    const text = await file.text(), summary = await api('/api/restore/preview',{backup_text:text});
    if (sequence !== restoreSequence) return;
    restoreCandidate = {text,summary};
    $('#restore-preview').innerHTML = `<div class="restore-summary"><strong>${escape(file.name)}</strong><p>Add ${summary.ideas_to_add} ideas and ${summary.plans_to_add} saved plans.</p><p>Add ${summary.discovery_to_add || 0} discovery records; keep ${summary.discovery_skipped || 0} existing decisions.</p><p>Keep ${summary.ideas_skipped} existing ideas and ${summary.plans_skipped} existing plans unchanged.</p><p>Backup estimates: ${escape(defaultText(summary.defaults,summary.currency))}.</p>${summary.currency_assumed ? `<p>${summary.currency} is an assumption for older unlabeled amounts. No amounts have been converted.</p>` : ''}${summary.version === 1 ? '<p>Older backup: repeat restores of this exact file skip duplicates. Different older files may add separate copies.</p>' : ''}</div>`;
    $('#acknowledge-relabel').checked = false; $('#restore-currency-consent').hidden = !summary.currency_mismatch;
    updateRestoreConsent();
  } catch (error) {if (sequence === restoreSequence) {$('#restore-preview').textContent = ''; $('#restore-error').textContent = error.message; $('#restore-error').hidden = false;}}
});
function updateRestoreConsent() {
  $('#apply-restore').disabled = restoreBusy || !restoreCandidate || (restoreCandidate.summary.currency_mismatch && !$('#acknowledge-relabel').checked);
  if (!restoreCandidate) return;
  let warning = $('#restore-currency-warning');
  if (!warning) {warning = document.createElement('p'); warning.id = 'restore-currency-warning'; warning.className = 'helper'; $('#restore-preview').append(warning);}
  const s = restoreCandidate.summary, target = $('#restore-defaults').checked ? s.currency : s.current_currency;
  warning.textContent = s.currency_mismatch ? `Backup currency is ${s.currency}; this bank uses ${s.current_currency}. With the current choice, all idea costs will be labeled ${target}, with their numeric values unchanged. Saved plans retain their snapshot currencies. Confirm that relabeling before merging.` : `Idea costs will use ${target}. Saved plans keep their snapshot currencies. Nothing is converted.`;
}
$('#acknowledge-relabel').addEventListener('change',updateRestoreConsent);
$('#restore-defaults').addEventListener('change',updateRestoreConsent);
$('#restore-dialog').addEventListener('cancel', () => {restoreSequence++;});
$('#show-archived').addEventListener('change', renderIdeas);
$('#planner-form').addEventListener('submit', event => {event.preventDefault(); generate();});
$('#planner-form').elements.weekend_date.addEventListener('change', () => { if (plan) {plan=null; locks.clear(); $('#plan-output').innerHTML='<p class="helper">Weekend changed. Generate a fresh plan for these dates.</p>'; } });
$('#idea-form').addEventListener('submit', async event => {
  event.preventDefault(); const form = event.target, f = form.elements, submit = form.querySelector('[type="submit"]'); submit.disabled = true;
  const data = {title:f.title.value, category:f.category.value, duration:f.duration.value === '' ? null : Number(f.duration.value), cost:f.cost.value === '' ? null : Number(f.cost.value), location:f.location.value, energy:f.energy.value || null, environment:f.environment.value};
  if (f.id.value) data.id = Number(f.id.value);
  try {await api('/api/ideas',data); $('#idea-dialog').close(); await refresh(); notify('Idea saved. A little possibility for later.');}
  catch (error) {$('#form-error').textContent = error.message; $('#form-error').hidden = false;} finally {submit.disabled = false;}
});
document.addEventListener('submit', async event => {
  if (event.target.id !== 'save-plan') return;
  event.preventDefault();
  if(busy||window.GrovePlanB?.isPending()){notify('Wait for the current plan change to finish before saving.');return;}
  busy=true; const submit = event.target.querySelector('button'); submit.disabled = true;
  try {await api('/api/plans',{name:$('#plan-name').value, ids:plan.items.map(i => i.id), expected_items:plan.items, limits:plan.limits, schedule:plan.schedule, defaults:plan.defaults, currency:plan.currency, currency_assumed:plan.currency_assumed}); planName = ''; await refresh(); setView('saved'); notify('Weekend saved. You can come back to it anytime.');}
  catch (error) {notify(error.message,true);} finally {busy=false;submit.disabled = false;}
});
const initialWeekend = new Date(); initialWeekend.setDate(initialWeekend.getDate()+(6-initialWeekend.getDay())%7);
$('#planner-form').elements.weekend_date.value = `${initialWeekend.getFullYear()}-${String(initialWeekend.getMonth()+1).padStart(2,'0')}-${String(initialWeekend.getDate()).padStart(2,'0')}`;
refresh().catch(error => notify('Could not load your idea bank. '+error.message,true));

// Navigation is browser-history aware and never regenerates or saves a plan.
window.addEventListener('popstate',()=>{if(location.hash!=='#workspace')setView(location.hash.slice(1),true);});
window.addEventListener('hashchange',()=>{if(location.hash!=='#workspace')setView(location.hash.slice(1),true);});
$('#idea-search').addEventListener('input',renderIdeas);
function planningSummary(){
  const f=$('#planner-form').elements;
  const changed=days.some(d=>categories.some(c=>Number(f[`cap-${d}-${c}`].value)!==1));
  $('#planning-options-summary').textContent=`${f.energy.options[f.energy.selectedIndex].text.split(' · ')[0]} energy · ${f.count.value} ideas${changed?' · custom caps':''}${$('#include-lazy').checked?' · Lazy Day':''}${!$('#include-samples').checked?' · no demos':''}`;
}
$('#planning-options').addEventListener('input',planningSummary);
planningSummary();
setView(location.hash.slice(1)||'ideas',true);

document.addEventListener('toggle',event=>{if(event.target.matches('.saved-plan'))event.target.querySelector('.view-snapshot').textContent=event.target.open?'Close snapshot':'View snapshot';},true);
