/* Pure, conservative weather gate. It never fetches or changes a plan. */
const PlanBDecision = (() => {
  const wet = new Set([51,53,55,56,57,61,63,65,66,67,71,73,75,77,80,81,82,85,86,95,96,97,99]);
  function assess(date, context, prefs, now=Date.now()) {
    const no = message => ({eligible:false,message});
    if(!prefs.enabled)return no('Plan B is off.');
    if(![40,60,80].includes(prefs.threshold))return no('Choose a supported precipitation threshold.');
    if(!context?.consent)return no('Allow and check weather first. No automatic lookup is made.');
    if(context.loading||context.error)return no('Wait for a successful weather check.');
    const data=context.data;
    if(!data||data.zip!==context.zip||data.timezone!==context.zone||!date)return no('Check weather for this ZIP and weekend first.');
    const age=now-Date.parse(data.fetched_at);
    if(!Number.isFinite(age)||age<0||age>=3600000)return no('Forecast expired. Check weather again.');
    let today;
    try {const parts=new Intl.DateTimeFormat('en-US',{timeZone:context.zone,year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date(now));today=['year','month','day'].map(k=>parts.find(p=>p.type===k).value).join('-');}catch(_){return no('Choose a valid forecast timezone.');}
    const horizon=new Date(today+'T12:00:00Z');horizon.setUTCDate(horizon.getUTCDate()+15);
    if(date<today||date>horizon.toISOString().slice(0,10))return no('No current forecast for this date.');
    const day=data.days?.find(d=>d.date===date);
    if(!day||!['available','partial'].includes(day.status))return no('No usable forecast for this date.');
    const reasons=[];
    if(typeof day.rain==='number'&&Number.isFinite(day.rain)&&day.rain>=prefs.threshold&&day.rain<=100)reasons.push(`${Math.round(day.rain)}% maximum precipitation chance meets your ${prefs.threshold}% threshold`);
    if(prefs.conditions&&Number.isInteger(day.code)&&wet.has(day.code))reasons.push('rain, snow or storm conditions are forecast');
    if(!reasons.length)return no('This forecast does not meet your Plan B triggers. Unknown weather is not treated as clear.');
    return {eligible:true,message:reasons.join('; ')+'.',fingerprint:JSON.stringify([date,context.zip,context.zone,data.fetched_at,day.rain,day.code,prefs.threshold,prefs.conditions])};
  }
  function sameLimits(a,b) {
    if(!a||!b)return false;
    if(['minutes','budget','energy','count','include_lazy','weekend_date'].some(k=>a[k]!==b[k]))return false;
    return ['Saturday','Sunday'].every(d=>['Projects','Restaurants','Places','Activities'].every(c=>a.day_caps?.[d]?.[c]===b.day_caps?.[d]?.[c]));
  }
  return {assess,sameLimits};
})();
if(typeof module!=='undefined')module.exports=PlanBDecision;
