/* Explicit local suggestions/swaps only. No external provider requests. */
(() => {
  const prefs=()=>({enabled:$('#plan-b-enabled').checked,threshold:Number($('#plan-b-threshold').value),conditions:$('#plan-b-conditions').checked});
  let offers=null,undo=null,pending=false,sequence=0;
  const snapshot=()=>JSON.stringify([plan,limits(),[...locks].sort(),$('#include-samples').checked]);
  function risk(id) {
    const entry=plan?.schedule?.find(e=>e.id===id&&e.kind==='idea');
    if(!PlanBDecision.sameLimits(plan?.limits,limits()))return {eligible:false,message:'Planning limits changed. Generate or reroll before choosing Plan B.'};
    if(!entry||!plan.limits.weekend_date)return {eligible:false,message:'Choose a dated plan first.'};
    if(plan.limits.weekend_date!==$('#planner-form').elements.weekend_date.value)return {eligible:false,message:'Generate the selected weekend first.'};
    return PlanBDecision.assess(weekendDay(plan.limits.weekend_date,entry.day),window.GroveWeather?.context(),prefs());
  }
  function paint() {
    const p=prefs();$('#plan-b-threshold').disabled=!p.enabled;$('#plan-b-conditions').disabled=!p.enabled;
    document.querySelectorAll('[data-plan-b-slot]').forEach(slot=>{
      const id=Number(slot.dataset.planBSlot),idea=plan?.items.find(i=>i.id===id);
      if(!p.enabled||!idea){slot.innerHTML='';return;}
      if(!['outdoor','mixed'].includes(idea.environment)){slot.innerHTML=idea.environment==='unknown'?'<p class="helper">Plan B needs your indoor/outdoor label. Edit this idea to set it.</p>':'';return;}
      const decision=risk(id);
      if(!decision.eligible){slot.innerHTML=`<p class="helper">Plan B: ${escape(decision.message)}</p>`;return;}
      slot.innerHTML=`<p class="helper"><strong>Consider an indoor Plan B</strong><br>${escape(decision.message)} ZIP-area forecast; a day-trip destination may differ.</p>${locks.has(id)?'<p class="helper">This suggestion is locked. Unlock it before choosing a swap.</p>':`<button type="button" class="secondary" data-find-plan-b="${id}" ${pending?'disabled':''}>Find indoor alternative</button>`}`;
      if(offers?.target===id&&!locks.has(id))slot.innerHTML+=offers.items.length?`<div class="plan-b-offers" role="region" aria-label="Indoor alternatives for ${escape(idea.title)}"><p class="helper">Nothing changes until you choose Swap. Alternatives use your own indoor labels.</p>${offers.items.map(i=>`<div class="plan-b-option"><strong>${escape(i.title)}</strong>${metrics(i,true,plan.defaults,plan.currency)}<button type="button" class="secondary" data-swap-plan-b="${i.id}" data-target="${id}" ${pending?'disabled':''}>Swap to ${escape(i.title)}</button></div>`).join('')}<button type="button" class="text-button" data-cancel-plan-b>Keep current idea</button></div>`:'<p class="helper" role="status">No indoor alternative fits this day and your current limits. Keep this idea, loosen limits, or add an indoor idea.</p><button type="button" class="text-button" data-cancel-plan-b>Keep current idea</button>';
    });
    const area=$('#plan-b-undo');
    if(area)area.innerHTML=undo?`<p class="helper">Swapped ${escape(undo.oldTitle)} for ${escape(undo.newTitle)}. The plan is not saved yet.</p><button type="button" class="secondary" data-undo-plan-b ${pending||locks.has(undo.newId)?'disabled':''}>Undo last swap</button>${locks.has(undo.newId)?'<p class="helper">Unlock the replacement to undo this swap.</p>':''}`:'';
  }
  function invalidate(){sequence++;offers=null;paint();}
  async function request(target,replacement,reverse=false) {
    if(pending||busy||!plan)return;
    if(!PlanBDecision.sameLimits(plan.limits,limits())){notify('Planning limits changed. Generate or reroll first.',true);return;}
    const decision=risk(target);
    if(!reverse&&!decision.eligible){invalidate();notify(decision.message,true);return;}
    if(locks.has(target)){notify('Unlock this suggestion before swapping.',true);return;}
    const before=snapshot(),token=++sequence,old=plan.items.find(i=>i.id===target);
    let focusOffers=false;
    pending=true;paint();
    try {
      const body={plan,locked:[...locks],target_id:target,include_samples:$('#include-samples').checked};
      if(replacement!==undefined)body.replacement_id=replacement;
      if(reverse)body.undo=true;
      const response=await api('/api/plan-b',body);
      if(token!==sequence||before!==snapshot())return;
      if(!reverse){const current=risk(target);if(!current.eligible||current.fingerprint!==decision.fingerprint){invalidate();notify('Weather changed. Review the current forecast before a swap.',true);return;}}
      if(replacement===undefined){offers={target,items:response.alternatives};focusOffers=offers.items.length>0;if(!focusOffers)notify('No indoor alternative fits your current limits.');}
      else {
        plan=response.plan;offers=null;
        undo=reverse?null:{oldId:target,newId:replacement,oldTitle:old.title,newTitle:plan.items.find(i=>i.id===replacement).title};
        renderPlan();notify(reverse?'Last swap undone. Your plan has not been saved.':'Indoor alternative swapped into this day. Review it before saving.');
        const card=document.querySelector(`[data-lock="${replacement}"]`);if(card)card.focus();
      }
    }catch(e){if(token===sequence)notify(e.message,true);}
    finally{pending=false;paint();if(focusOffers&&token===sequence){const region=document.querySelector(`[data-plan-b-slot="${target}"] .plan-b-offers`);if(region){region.tabIndex=-1;region.focus();}}}
  }
  document.addEventListener('click',event=>{
    const button=event.target.closest('button');if(!button)return;
    if(button.dataset.findPlanB)request(Number(button.dataset.findPlanB));
    if(button.dataset.swapPlanB)request(Number(button.dataset.target),Number(button.dataset.swapPlanB));
    if(button.hasAttribute('data-cancel-plan-b')){invalidate();notify('Current idea kept. No plan changes.');}
    if(button.hasAttribute('data-undo-plan-b')&&undo)request(undo.newId,undo.oldId,true);
  });
  for(const id of ['plan-b-enabled','plan-b-threshold','plan-b-conditions','include-samples'])$('#'+id).addEventListener('change',invalidate);
  window.addEventListener('grove-weather-change',invalidate);
  document.addEventListener('input',event=>{if(event.target.form?.id==='planner-form')invalidate();});
  window.GrovePlanB={isPending:()=>pending,paint:()=>{sequence++;offers=null;paint();},reset:()=>{sequence++;offers=null;undo=null;},invalidate};
  paint();
})();
