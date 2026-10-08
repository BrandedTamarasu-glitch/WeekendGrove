(() => {
  const form=document.querySelector('#backup-form'), status=document.querySelector('#backup-status');
  let current=null, pending=false;
  function paint(value, replace=true){
    current=value;
    if(replace) for(const key of ['enabled','prune'])form.elements[key].checked=value.settings[key];
    if(replace) for(const key of ['time','timezone','keep'])form.elements[key].value=value.settings[key];
    document.querySelector('#backup-destination').textContent=value.configured?value.destination:value.unavailable;
    form.elements.enabled.disabled=!value.configured && !value.settings.enabled;form.elements.prune.disabled=!value.configured && !value.settings.prune;
    document.querySelector('#backup-now').disabled=!value.configured || pending;
    status.textContent=`Backup status: ${value.status}. ${value.settings.enabled?'Daily schedule enabled':'Scheduling disabled'}. Last success: ${value.last_success?new Date(value.last_success).toLocaleString():'never'}. Last attempt: ${value.last_attempt?new Date(value.last_attempt).toLocaleString():'never'}. Last failure: ${value.last_failure?new Date(value.last_failure).toLocaleString():'never'}. ${value.count} recorded automatic copies. ${value.error || ''} ${value.warning || ''}`;
    if(replace){form.elements.approve_schedule.checked=false;form.elements.approve_deletion.checked=false;}
  }
  async function refresh(keepDraft=false){try{paint(await api('/api/backups'),!keepDraft);}catch(e){status.textContent=e.message;}}
  async function action(path,data){
    if(pending)return;pending=true;form.inert=true;
    form.querySelector('button').disabled=true;document.querySelector('#backup-now').disabled=true;
    document.querySelector('#backup-error').textContent='';
    try{paint(await api(path,data));}
    catch(e){document.querySelector('#backup-error').textContent=e.message;await refresh(true);}
    finally{pending=false;form.inert=false;form.querySelector('button').disabled=false;document.querySelector('#backup-now').disabled=!current?.configured;}
  }
  form.addEventListener('submit',event=>{
    event.preventDefault();const f=form.elements;
    action('/api/backups/settings',{settings:{enabled:f.enabled.checked,prune:f.prune.checked,time:f.time.value,timezone:f.timezone.value,keep:Number(f.keep.value)},approve_schedule:f.approve_schedule.checked,approve_deletion:f.approve_deletion.checked});
  });
  document.querySelector('#backup-now').addEventListener('click',()=>{
    if(pending || !current?.configured)return;
    if(!confirm(`Write a consistent database copy to ${current.destination}? ${current.settings.prune?'Approved retention cleanup will run after success.':'Existing copies will be kept.'}`))return;
    action('/api/backups/run',{approve_backup:true});
  });
  document.querySelector('#refresh-backup-status').addEventListener('click',()=>{if(!pending)refresh();});
  form.addEventListener('input',event=>{if(!event.target.name.startsWith('approve_')){form.elements.approve_schedule.checked=false;form.elements.approve_deletion.checked=false;}});
  refresh();
})();
