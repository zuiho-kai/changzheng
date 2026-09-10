const fs=require('node:fs'),path=require('node:path');
const [root,build,settings]=process.argv.slice(2);
const RT=require(path.join(root,'lib/runtime.js'));
const app=fs.readFileSync(path.join(root,'lib/app.js'),'utf8');
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
const block=app.match(/const sliders\s*=\s*\{([\s\S]*?)\};/);
if(!block)throw new Error('Pinned slider mapping changed');
const inputs=new Map([...html.matchAll(/<input\b[^>]*>/g)].map(match=>{
  const attrs=Object.fromEntries([...match[0].matchAll(/([\w-]+)="([^"]*)"/g)].map(m=>[m[1],m[2]]));return [attrs.id,attrs];
}));
const ranges={};
for(const match of block[1].matchAll(/(\w+)\s*:\s*'([^']+)'/g)){
  const input=inputs.get(match[1]);if(!input)throw new Error('Missing upstream slider '+match[1]);
  ranges[match[2]]=[Number(input.min),Number(input.max)];
}
const buffer=fs.readFileSync(path.join(build,'source.psd'));
const modelId=RT.fingerprint(buffer.buffer.slice(buffer.byteOffset,buffer.byteOffset+buffer.byteLength));
const layers=JSON.parse(fs.readFileSync(path.join(build,'rig.json'),'utf8')).layers;
const value=JSON.parse(fs.readFileSync(settings,'utf8').replace(/^\uFEFF/,''));
const normalized=RT.settings(value,modelId,ranges,layers.map(p=>String(p.z)+':'+p.name));
console.log(JSON.stringify({format:'anime25d-settings',version:1,modelId,modelName:'source.psd',...normalized}));
