'use strict';
(() => {
  // spring() reused from Anime2.5DRig lib/runtime.js, MIT, hakoniwa (2026).
  // Upstream 7450341934a8ff77bf05b90d9f708786e3eb3996. See vendor/ANIME25D-LICENSE.txt.
  function spring(s,target,k,damping,dt) {
    const count=Math.max(1,Math.ceil(dt/(1/120))), h=dt/count;
    for(let i=0;i<count;i++){ s.v+=(-k*(s.x-target)-damping*s.v)*h; s.x+=s.v*h; }
  }
  // Two sides have different lengths and settling times. Displacement is relative
  // to the moving attachment: when the head stops, the tips catch up and settle.
  class HairFollow {
    constructor() {
      this.sides=[.93,1.08].map(rate=>({rate,root:{x:0,v:0},tip:{x:0,v:0},x:0,tipX:0}));
      this.ready=false;
    }
    update(dt,headDegrees,bodyDegrees,pitch) {
      const roll=headDegrees*Math.PI/180,body=bodyDegrees*Math.PI/180;
      const target=Math.sin(roll)*185+Math.sin(body)*740+pitch*3;
      const limit=x=>Math.max(-38,Math.min(38,x));
      if(!this.ready){for(const s of this.sides)s.root.x=s.tip.x=target;this.ready=true;}
      const steps=Math.max(1,Math.ceil(dt/(1/120))),step=dt/steps;
      for(let i=0;i<steps;i++)for(const s of this.sides){
        spring(s.root,target,88*s.rate,13,step);
        spring(s.tip,s.root.x,24*s.rate,5.8,step);
      }
      for(const s of this.sides){s.x=limit((s.root.x-target)*1.25);s.tipX=limit((s.tip.x-target)*1.65);}
    }
  }
  window.HairFollow=HairFollow;
})();
