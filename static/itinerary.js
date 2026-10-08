/* Portable snapshots contain no scripts, remote assets, or live app dependencies. */
const GroveItinerary = (() => {
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const amount = (n, currency) => `${Number(n).toFixed(2)} ${esc(currency || 'USD')}`;
  const date = (start, day) => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(start || '')) return 'Date not recorded';
    const d = new Date(start+'T12:00:00Z');
    if (!Number.isFinite(d.getTime())) return 'Date not recorded';
    if (day === 'Sunday') d.setUTCDate(d.getUTCDate()+1);
    return d.toISOString().slice(0,10);
  };
  function body(p, notes='') {
    const defaults=p.defaults || {}, currency=p.currency || 'USD';
    const item = i => `<article><h3>${esc(i.title)}</h3><p>${esc(i.category)} · ${esc(i.duration ?? defaults.duration)} min${i.duration==null?' (estimate)':''} · ${amount(i.cost ?? defaults.cost,currency)}${i.cost==null?' (estimate)':''}</p><p>${i.location?esc(i.location):'Location not recorded'}</p>${i.location?`<p><a href="https://www.google.com/maps/dir/?api=1&amp;destination=${esc(encodeURIComponent(i.location))}" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer">Open directions for ${esc(i.title)}</a></p>`:''}${i.metadata?.time_label?`<p>${esc(i.metadata.time_label)}</p>`:''}</article>`;
    const schedule=p.schedule || [];
    const sections=schedule.length?['Saturday','Sunday'].map(day=>{
      const entries=schedule.filter(e=>e.day===day);
      return `<section><h2>${day} · ${esc(date(p.limits?.weekend_date,day))}</h2>${entries.length?entries.map(e=>e.kind==='lazy'?`<article><h3>Lazy Day time</h3><p>${esc(e.duration)} min · ${amount(0,currency)} · Room to relax</p></article>`:item(p.items.find(i=>i.id===e.id))).join(''):'<p>No activities planned.</p>'}</section>`;
    }).join(''):`<section><h2>Day unspecified</h2><p>Dates and day assignments were not recorded for this older snapshot.</p>${p.items.map(item).join('')}</section>`;
    return `<header><p>WEEKEND GROVE · PORTABLE SNAPSHOT</p><h1>${esc(p.name || 'Your weekend')}</h1><p>${esc(p.minutes)} minutes planned · ${amount(p.cost,currency)} planned${p.limits?.budget!=null?` · budget ${amount(p.limits.budget,currency)}`:''}</p>${p.currency_assumed?'<p>Currency was assumed in this older plan; amounts were not converted.</p>':''}</header>${sections}${notes.trim()?`<section><h2>Your trip notes</h2><p class="trip-notes">${esc(notes)}</p></section>`:''}<footer><p>Standalone copy. Changes in the app will not update this file. Forecasts are not included.</p><p>Locations are recorded text, not verified addresses. Check hours, costs and travel time before going. Directions links send the selected location to Google Maps only when you open them; maps need internet access.</p><p>This file contains your itinerary. Share it only with people you choose. Provider facts, including Ticketmaster facts, may have retention or reuse restrictions.</p></footer>`;
  }
  function html(p, notes='') {
    return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="referrer" content="no-referrer"><meta http-equiv="x-dns-prefetch-control" content="off"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"><title>${esc(p.name || 'Weekend itinerary')}</title><style>html{color-scheme:light dark}body{font:16px/1.6 system-ui,sans-serif;margin:auto;padding:24px;max-width:780px;background:#f6f8f0;color:#26372a;overflow-wrap:anywhere}h1{font-size:30px;line-height:1.2}h2{font-size:22px}h3{font-size:19px}section{margin:28px 0}article{border:1px solid #899982;border-radius:14px;padding:16px;margin:12px 0;break-inside:avoid}a{color:#315e30;display:inline-block;padding:10px 0;min-height:24px}footer{font-size:13px;border-top:1px solid #899982;margin-top:24px}.trip-notes{white-space:pre-wrap}@media(prefers-color-scheme:dark){body{background:#15221b;color:#e0e7d9}a{color:#b9d9a6}}@media(max-width:400px){body{padding:16px}}@media print{html{color-scheme:light}body{background:white;color:black;padding:0;max-width:none;font-size:11pt}a{color:black}article{border-color:#777}footer{font-size:9pt}}</style></head><body>${body(p,notes)}</body></html>`;
  }
  return {body,html};
})();
if (typeof module !== 'undefined') module.exports=GroveItinerary;
if (typeof document !== 'undefined') {
  let captured=null, opener=null;
  const dialog=document.querySelector('#itinerary-dialog'), notes=document.querySelector('#itinerary-notes');
  const paint=()=>{document.querySelector('#itinerary-preview').innerHTML=GroveItinerary.body(captured,notes.value);};
  document.addEventListener('click',event=>{
    const button=event.target.closest('[data-itinerary]');
    if(!button)return;
    if(busy || window.GrovePlanB?.isPending()){notify('Wait for the current plan change before making an itinerary.',true);return;}
    const value=button.dataset.itinerary==='current'?plan:state.plans.find(p=>String(p.id)===button.dataset.itinerary);
    if(!value)return;
    captured=structuredClone(value);
    if(button.dataset.itinerary==='current')captured.name=planName || 'Your weekend';
    opener=button;notes.value='';paint();dialog.showModal();document.querySelector('#itinerary-title').focus();
  });
  notes.addEventListener('input',paint);
  document.querySelector('#close-itinerary').addEventListener('click',()=>dialog.close());
  dialog.addEventListener('close',()=>{captured=null;notes.value='';document.querySelector('#itinerary-preview').replaceChildren();opener?.focus();});
  document.querySelector('#download-itinerary').addEventListener('click',()=>{
    if(!captured)return;
    const url=URL.createObjectURL(new Blob([GroveItinerary.html(captured,notes.value)],{type:'text/html;charset=utf-8'}));
    const a=document.createElement('a');a.href=url;a.download='weekend-grove-itinerary.html';a.click();
    setTimeout(()=>URL.revokeObjectURL(url),30000);
  });
  document.querySelector('#print-itinerary').addEventListener('click',()=>{if(captured)window.print();});
}
