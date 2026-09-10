// Uses the pinned upstream parser and rigger without rewriting their algorithms.
const fs = require('node:fs');
const path = require('node:path');
const [root, input, output] = process.argv.slice(2);
const Rigger = require(path.join(root, 'lib/rigger.js'));
const ag = require(path.join(root, 'lib/ag-psd.min.js'));
ag.initializeCanvas(undefined, (width,height)=>({width,height,data:new Uint8ClampedArray(width*height*4)}));
const GP = require(path.join(root, 'lib/genericparts.js'));
const generic = {eyeL:GP.get('eyeL'),eyeR:GP.get('eyeR'),mouth:GP.get('mouth')};
function flatten(file){return Rigger.flattenPsdToImg(ag.readPsd(fs.readFileSync(path.join(root,file)),{useImageData:true,skipThumbnail:true,skipCompositeImageData:true}));}
const eyes = Rigger.splitImgLR(flatten('eye_close.psd'));
if(eyes){generic.eyeL=eyes.l;generic.eyeR=eyes.r;}
const mouth = flatten('mouth_close.psd');
if(mouth)generic.mouth=mouth;
const psd = ag.readPsd(fs.readFileSync(input), {useImageData:true, skipThumbnail:true, skipCompositeImageData:true});
const cleanup = Rigger.cleanPsdLayers(psd);
const rig = Rigger.buildRig(psd,{generic});
fs.mkdirSync(output, {recursive:false});
fs.copyFileSync(input, path.join(output, 'source.psd'));
fs.copyFileSync(path.join(root, 'LICENSE'), path.join(output, 'ANIME25D-LICENSE.txt'));
fs.mkdirSync(path.join(output,'layers'));
const painted=rig.layers.map((part,i)=>{
  const file=`layers/${i}.rgba`;
  fs.writeFileSync(path.join(output,file),Buffer.from(part.img.data));
  return {name:part.name,x:part.x,y:part.y,width:part.w,height:part.h,synthetic:!!part.synthetic,file};
});
fs.writeFileSync(path.join(output,'layers.json'),JSON.stringify({canvas:rig.canvas,layers:painted},null,2));
const summary = {canvas:rig.canvas, anchors:rig.anchors, warnings:rig.warnings, cleanup, synth:rig.synth,
  layers:rig.layers.map(({img,...layer})=>({...layer, image:img ? {width:img.width,height:img.height}:null}))};
fs.writeFileSync(path.join(output, 'rig.json'), JSON.stringify(summary, (k,v)=>ArrayBuffer.isView(v)?Array.from(v):v, 2));
// Common interchange is painted layers on the original canvas, not foreign rig coordinates.
const children=rig.layers.map(p=>{
  let name=p.name;
  if(p.side)name=name.replace(/_(l|r)$/,'')+' '+(p.x+p.w/2<rig.canvas.w/2?'right':'left');
  if(name==='mouth_close')name='mouth closed';
  if(name==='mouth_open')name='mouth open';
  return {name,left:p.x,top:p.y,right:p.x+p.w,bottom:p.y+p.h,imageData:p.img,opacity:p.opacity??1};
});
fs.writeFileSync(path.join(output,'prepared.psd'),Buffer.from(ag.writePsd({width:psd.width,height:psd.height,children},{generateThumbnail:false})));
// PuppetLoom imports every mouth as closed; its native enhance API registers open variants.
fs.writeFileSync(path.join(output,'puppetloom-base.psd'),Buffer.from(ag.writePsd({width:psd.width,height:psd.height,
  children:children.filter((c,i)=>rig.layers[i].name!=='mouth_open')},{generateThumbnail:false})));
console.log(JSON.stringify({canvas:rig.canvas,layers:rig.layers.length,warnings:rig.warnings,synth:rig.synth,format:'anime25d-psd-settings',moc3:false,interchange:'prepared.psd'}));
