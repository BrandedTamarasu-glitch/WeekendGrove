// Guard semantic palette contrast when either theme changes.
const assert=require('node:assert/strict'),fs=require('node:fs');
const css=fs.readFileSync('static/style.css','utf8');
function palette(theme){const out={};for(const [_,selector,body] of css.matchAll(/(:root(?:\[data-theme=dark\])?)\{([^}]+)\}/g)){if(selector===':root'||theme==='dark')for(const [__,key,value] of body.matchAll(/--([\w-]+):(#[0-9a-f]{6})(?:;|$)/g))out[key]=value;}return out;}
function luminance(hex){return [1,3,5].map(i=>parseInt(hex.slice(i,i+2),16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((n,v,i)=>n+v*[.2126,.7152,.0722][i],0);}
function contrast(a,b){const x=luminance(a),y=luminance(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);}
const textPairs=[['ink','paper'],['ink','surface'],['muted','paper'],['muted','surface'],['muted','soft'],['muted','softest'],['muted','input'],['green','surface'],['green','soft'],['on-green','green'],['disabled-ink','disabled-bg'],['badge-ink','badge-bg'],['project-ink','project-bg'],['food-ink','food-bg'],['place-ink','place-bg'],['activity-ink','activity-bg'],['error-ink','error-bg']];
for(const theme of ['light','dark']){
 const colors=palette(theme);const text=textPairs.map(([fg,bg])=>{const value=contrast(colors[fg],colors[bg]);assert.ok(value>=4.5,`${theme}: ${fg}/${bg} ${value.toFixed(2)} < 4.5`);return value;});
 const controls=['control','focus'].flatMap(fg=>['input','surface','soft','paper'].map(bg=>{const value=contrast(colors[fg],colors[bg]);assert.ok(value>=3,`${theme}: ${fg}/${bg} ${value.toFixed(2)} < 3`);return value;}));
 console.log(`${theme}: semantic text minimum ${Math.min(...text).toFixed(2)}:1; control/focus minimum ${Math.min(...controls).toFixed(2)}:1.`);
}
