const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync('static/theme.js','utf8');
function boot(saved,systemDark=false,blocked=false){
 const events={},storage=new Map(saved?[['weekend-grove-theme',saved]]:[]),nodes={};
 for(const id of ['theme-toggle','theme-label','theme-choice'])nodes[id]={events:{},attrs:{},addEventListener(n,f){this.events[n]=f},setAttribute(n,v){this.attrs[n]=v}};
 const media={matches:systemDark,addEventListener(n,f){this.change=f}};
 const document={documentElement:{dataset:{}},getElementById:id=>nodes[id],addEventListener:(n,f)=>events[n]=f};
 vm.runInNewContext(source,{window:{matchMedia:()=>media},document,localStorage:{getItem(k){if(blocked)throw Error();return storage.get(k)},setItem(k,v){if(blocked)throw Error();storage.set(k,v)},removeItem(k){if(blocked)throw Error();storage.delete(k)}}});
 return {document,nodes,media,storage,ready:()=>events.DOMContentLoaded()};
}
let app=boot(null,true);assert.equal(app.document.documentElement.dataset.theme,'dark');app.ready();assert.equal(app.nodes['theme-choice'].value,'system');
app.nodes['theme-toggle'].events.click();assert.equal(app.document.documentElement.dataset.theme,'light');assert.equal(app.storage.get('weekend-grove-theme'),'light');
app.media.matches=true;app.media.change();assert.equal(app.document.documentElement.dataset.theme,'light');
app=boot('dark');app.ready();assert.equal(app.document.documentElement.dataset.theme,'dark');assert.equal(app.nodes['theme-toggle'].attrs['aria-pressed'],'true');
app.nodes['theme-choice'].events.change({target:{value:'system'}});assert.equal(app.storage.size,0);assert.equal(app.document.documentElement.dataset.theme,'light');app.media.matches=true;app.media.change();assert.equal(app.document.documentElement.dataset.theme,'dark');
app=boot('garbage',false);app.ready();assert.equal(app.document.documentElement.dataset.theme,'light');
app=boot(null,true,true);app.ready();app.nodes['theme-toggle'].events.click();assert.equal(app.document.documentElement.dataset.theme,'light');
console.log('Theme checks passed: early application, system changes, explicit persistence, reset, invalid and blocked storage.');
