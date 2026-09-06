'use strict';
// Behavioral checks for reaction timing; visual judgement belongs to the video.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
let clock=0,seed=17;
const random=()=>{seed=(seed*16807)%2147483647;return (seed-1)/2147483646;};
const math=Object.create(Math);math.random=random;
const world={window:{},performance:{now:()=>clock},Math:math};
vm.runInNewContext(fs.readFileSync('web/avatar-performance.js','utf8'),world);
const core={_model:{parameters:{ids:[]}},setParameterValueById(){}};
const performer=new world.window.AvatarPerformance(core);
const step=(ms,mouth=0)=>{clock+=ms;return performer.update(clock,mouth);};
const checks={};
performer.setState('thinking'); // Observe one hop without the new idle scheduler.
performer.gesture('bounce');const start=performer.action.start;
step(100);performer.gesture('bounce');
checks.repeated_event_does_not_restart=performer.action.start===start;
let minY=0,maxY=0;
for(let i=0;i<110;i++){step(25);minY=Math.min(minY,performer.offset.y);maxY=Math.max(maxY,performer.offset.y);}
checks.hop_has_anticipation_and_lift=minY<-.01&&maxY>0;
checks.hop_finishes_and_settles=performer.action===null&&Math.abs(performer.offset.y)<.0001;
performer.setState('idle',true);
let idleHops=0,idleActions=0,lastHop=null;
for(let i=0;i<480;i++){
  const values=step(25);
  if(performer.action&&performer.action.start!==lastHop){idleActions++;if(performer.action.name==='bounce')idleHops++;lastHop=performer.action.start;}
  assert.equal(values.ParamMouthOpenY,0);
}
checks.idle_has_separate_hop_bursts_without_fake_speech=idleHops>=2&&idleActions>=3&&idleActions<=7;
performer.setState('speaking');
for(let i=0;i<80;i++)step(25);
let accents=0,previous=false;
for(let i=0;i<400;i++){
  const mouth=i%20<6?.7:0;
  const values=step(25,mouth);
  if(performer.accent&&!previous)accents++;
  previous=!!performer.accent;
  assert.equal(values.ParamMouthOpenY,mouth);
}
checks.accents_follow_audio_but_are_sparse=accents>=2&&accents<=14;
performer.gesture('bounce');step(250,.8);performer.setState('idle',true);
checks.stop_clears_action_and_audio_accent=performer.action===null&&performer.accent===null&&step(33,0).ParamMouthOpenY===0;
let bounded=true;
for(let i=0;i<300;i++){
  const values=step(i%9===0?2000:33);
  bounded&&=Object.values(values).every(Number.isFinite)&&values.ParamAngleX===0&&Math.abs(values.ParamAngleY)<=30&&Math.abs(values.ParamAngleZ)<=30;
}
checks.frame_stalls_stay_finite_and_no_yaw=bounded;
console.log(JSON.stringify({checks,idleHops,accents,minY,maxY},null,2));
assert.ok(Object.values(checks).every(Boolean));
