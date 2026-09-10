// Inserted inside the pinned upstream app closure. Its rigging/render loop is intact.
let czSettingsReady=false,czBridgeError=null;
window.cz = {
  get ready(){return !!currentRig && !contextLost && czSettingsReady;},
  get error(){return czBridgeError || (dropStatus.textContent.startsWith('エラー:') ? dropStatus.textContent : null);},
  setState(state){
    setAuto('talk',false);
    if(state==='listening'){setSlider('eyeX',.35);setSlider('angleZ',.1);}
    if(state==='thinking')setSlider('eyeY',-.3);
    if(state==='idle'){setSlider('eyeX',0);setSlider('eyeY',0);setSlider('angleZ',0);}
  },
  mouth(value){setAuto('talk',false);setSlider('mouthOpen',value);if(value===0)cur.mouthOpen=0;},
  settings:settingsSnapshot,
  applySettings,
  stats(){return {mouth:cur.mouthOpen,layers:layers.length,modelId,contextLost,head:cur.angleZ};}
};
fetch('settings.json').then(r=>r.ok?r.json():null).then(async value=>{
  if(value){
    while(!currentRig)await new Promise(r=>setTimeout(r,50));
    applySettings(value);
  }
  czSettingsReady=true;
}).catch(error=>{czBridgeError=String(error);status(error.message,true);});
