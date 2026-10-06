/* Runs before styles paint. Only a theme preference is stored in this browser. */
(() => {
  const key='weekend-grove-theme', media=window.matchMedia('(prefers-color-scheme: dark)');
  let choice='system';
  try { const saved=localStorage.getItem(key); if(['light','dark'].includes(saved))choice=saved; } catch {}
  function apply() {
    const dark=choice==='dark'||(choice==='system'&&media.matches);
    document.documentElement.dataset.theme=dark?'dark':'light';
    const button=document.getElementById('theme-toggle'), label=document.getElementById('theme-label'), select=document.getElementById('theme-choice');
    if(button){button.setAttribute('aria-pressed',String(dark));button.setAttribute('aria-label',dark?'Use light mode':'Use dark mode');}
    if(label)label.textContent=dark?'Switch to light':'Switch to dark';
    if(select)select.value=choice;
  }
  function choose(value){choice=value;try{if(value==='system')localStorage.removeItem(key);else localStorage.setItem(key,value);}catch{}apply();}
  apply();
  media.addEventListener('change',()=>{if(choice==='system')apply();});
  document.addEventListener('DOMContentLoaded',()=>{
    apply();
    document.getElementById('theme-toggle').addEventListener('click',()=>choose(document.documentElement.dataset.theme==='dark'?'light':'dark'));
    document.getElementById('theme-choice').addEventListener('change',event=>choose(event.target.value));
  });
})();
