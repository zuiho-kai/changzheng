'use strict';
// Shared by the real avatar and its review page; no yaw animation.
(() => {
  const expressions = {
    neutral: {eye:1, smile:0, form:0, browL:0, browR:0, angleL:0, angleR:0, tilt:0,surprise:0},
    happy: {eye:0, smile:1, form:.9, browL:.35, browR:.35, tilt:-7},
    curious: {eye:1.06, form:-.25, browL:.7, browR:-.1, tilt:10},
    surprised: {eye:1.12, form:-.8, browL:.9, browR:.9, tilt:0,surprise:1},
    serious: {eye:.72, form:-.6, browL:-.25, browR:-.25, angleL:.55, angleR:-.55, tilt:-3},
  };
  const states = {
    idle: {},
    listening: {eye:1.05, browL:.3, browR:.15, tilt:9},
    thinking: {eye:.78, form:-.25, browL:.5, browR:-.1, tilt:-9},
    speaking: {eye:1, form:.4, browL:.16, browR:.16, tilt:2},
  };
  class AvatarPerformance {
    constructor(core, {reference=false}={}) {
      this.core=core; this.reference=reference; this.state='idle'; this.expression='auto';
      this.current={...expressions.neutral};this.last=performance.now();this.nextBlink=this.last+3800;
      this.blinkAt=-Infinity;this.action=null;this.parameters=new Set(core._model.parameters.ids);
      this.pose={head:0,body:0,pitch:0,hair:0,lift:0,headV:0,bodyV:0,pitchV:0,hairV:0,liftV:0};
      this.poseTarget={head:-.18,body:.08,pitch:0};this.nextPose=this.last+3300;
      this.offset={x:0,y:0};this.accent=null;this.nextAccent=0;this.voiceLevel=0;
      this.nextHop=this.last+1100+Math.random()*800;
      this.gaze={x:0,y:0,targetX:0,targetY:0,changed:this.last,next:this.last+900};
      this.noticeAt=-Infinity;
      if(this.parameters.has('ParamRuntimeGaze'))this.bindGaze();
    }
    bindGaze(){
      // A local iris warp avoids multiplying every eye keyform by two gaze axes.
      // Restore native vertices before Cubism updates, so held poses never drift.
      const draw=this.core._model.drawables,rects={EyeLeftOpen:[529,302,584,340],EyeRightOpen:[678,302,719,341],EyeLeftSurprised:[529,302,584,340],EyeRightSurprised:[678,302,719,341]};
      const smooth=(a,b,x)=>{const t=Math.max(0,Math.min(1,(x-a)/(b-a)));return t*t*(3-2*t);};
      const eyes=[];
      draw.ids.forEach((name,index)=>{
        const rect=rects[name];if(!rect)return;
        const uv=draw.vertexUvs[index],weights=[];
        const minU=Math.min(...Array.from(uv).filter((_,i)=>i%2===0));
        const minV=Math.min(...Array.from(uv).filter((_,i)=>i%2===1));
        for(let i=0;i<uv.length;i+=2){
          const x=rect[0]+(uv[i]-minU)*2048,y=rect[1]+(uv[i+1]-minV)*2048;
          weights.push((1-smooth(.38,1,Math.abs(x-rect[2])/40))*(1-smooth(.38,1,Math.abs(y-rect[3])/27)));
        }
        eyes.push({index,left:name.includes('Left'),weights,native:new Float32Array(draw.vertexPositions[index])});
      });
      const nativeUpdate=this.core.update.bind(this.core);
      this.core.update=()=>{
        for(const eye of eyes)draw.vertexPositions[eye.index].set(eye.native);
        nativeUpdate();
        const angle=((this.values?.ParamAngleZ||0)*20/30+(this.values?.ParamBodyAngleZ||0)*8/30)*Math.PI/180;
        const cos=Math.cos(angle),sin=Math.sin(angle);
        for(const eye of eyes){
          const vertices=draw.vertexPositions[eye.index];eye.native.set(vertices);
          const open=Math.max(.06,this.values?.[eye.left?'ParamEyeLOpen':'ParamEyeROpen']??1);
          const dx=7*this.gaze.x,dy=-4*this.gaze.y*open;
          for(let i=0;i<eye.weights.length;i++){
            const weight=eye.weights[i]*2/1254;
            vertices[i*2]+=(dx*cos-dy*sin)*weight;
            vertices[i*2+1]+=(dx*sin+dy*cos)*weight;
          }
          draw.dynamicFlags[eye.index]|=32;
        }
      };
    }
    setState(state, reset=false) {
      if (!(state in states)) return;
      if (reset) {this.expression='auto';this.action=null;this.accent=null;this.voiceLevel=0;this.noticeAt=-Infinity;this.nextHop=performance.now()+1400+Math.random()*1100;this.look(0,0,1000);}
      if (!reset && state!==this.state && ['listening','speaking'].includes(state)) this.gesture(this.expression==='serious'?'peek':'bounce');
      if (state!=='speaking') this.accent=null;
      if(state!==this.state){
        if(state==='thinking')this.look(-.55,.45,1100);
        else if(state==='listening')this.look(.72,.08,900);
        else if(state==='speaking')this.look(0,0,1600);
      }
      this.state=state;
    }
    look(x,y,hold=1000){
      const now=performance.now();
      Object.assign(this.gaze,{targetX:x,targetY:y,changed:now,next:now+hold});
    }
    notice(){
      if(this.state==='speaking')return;
      this.look(.85,.05,1100);this.noticeAt=performance.now();
      if(!this.action)this.gesture('peek');
    }
    setExpression(name) {if (name==='auto'||name in expressions) this.expression=name;}
    gesture(name) {
      if (!['nod','wink','tilt','bounce','peek'].includes(name)) return;
      const now=performance.now();
      // Repeated expression events must not pin a hop at its first frame.
      if (this.action?.name===name && now-this.action.start<650) return;
      this.action={name,start:now,side:Math.random()<.5?-1:1,amount:.65+Math.random()*.5,double:name==='bounce'&&Math.random()<.3};
      this.nextHop=now+1500+Math.random()*2000;
    }
    set(id,value) {if (this.parameters.has(id)) this.core.setParameterValueById(id,value);}
    update(now, mouth=0) {
      const dt=Math.max(0,Math.min(100,now-this.last));this.last=now;
      if(now>=this.gaze.next){
        const camera=Math.abs(this.gaze.targetX)>.2||Math.random()<(this.state==='speaking'?.8:.48);
        const x=camera?(Math.random()-.5)*.10:(Math.random()<.7?1:-1)*(.45+Math.random()*.4);
        const y=camera?0:(Math.random()-.35)*.45;
        this.look(x,y,camera?1300+Math.random()*1900:650+Math.random()*950);
      }
      const eyeEase=1-Math.exp(-dt/42);
      this.gaze.x+=(this.gaze.targetX-this.gaze.x)*eyeEase;
      this.gaze.y+=(this.gaze.targetY-this.gaze.y)*eyeEase;
      const target={...expressions.neutral,...(this.expression==='auto'?states[this.state]:expressions[this.expression])};
      const ease=1-Math.exp(-dt/190);
      for (const key of Object.keys(this.current)) this.current[key]+=(target[key]-this.current[key])*ease;
      if (now>=this.nextBlink) {this.blinkAt=now;this.nextBlink=now+3600+Math.random()*2600;}
      const blinkCurve=u=>u<0||u>1?1:u<.3?1-u/.3:u<.5?0:(u-.5)/.5;
      const blink=blinkCurve((now-this.blinkAt)/310),t=now/1000;
      // Unscheduled-looking little hops also happen while nobody is talking.
      // Leave holds between bursts; serious delivery keeps the quieter movement.
      if(!this.action && now>=this.nextHop && this.expression!=='serious' && ['idle','listening'].includes(this.state)){
        const choice=Math.random();
        this.gesture(choice<.65?'bounce':choice<.84?'peek':'tilt');
        const side=this.action.side;
        this.poseTarget={head:side*(.18+Math.random()*.25),body:-side*(.12+Math.random()*.15),pitch:(Math.random()-.5)*.2};
      }
      if(now>=this.nextPose){
        if(Math.random()>.22){
          const head=(Math.random()-.5)*1.0;
          this.poseTarget={head,body:-head*.48+(Math.random()-.5)*.25,pitch:(Math.random()-.5)*.55};
        }
        this.nextPose=now+1700+Math.random()*2400;
      }
      // A loud rising syllable can initiate one accent, with a refractory period.
      // Mouth itself stays the supplied real RMS; this only drives head/body.
      const rising=mouth-this.voiceLevel;
      this.voiceLevel+=(mouth-this.voiceLevel)*(1-Math.exp(-dt/160));
      if(this.state==='speaking' && mouth>.19 && rising>.10 && now>=this.nextAccent && !this.action){
        this.accent={start:now,amount:Math.min(1,.45+mouth),side:Math.random()<.5?-1:1};
        this.nextAccent=now+650+Math.random()*750;
        if(this.expression!=='serious' && now>=this.nextHop){this.gesture('bounce');this.nextHop=now+1200+Math.random()*1500;}
      }
      const pulse=(age,center,width)=>Math.exp(-Math.pow((age-center)/width,2));
      let reactHead=0,reactPitch=0,reactBody=0,lift=0,left=blink,right=blink;
      if(this.accent){
        const age=(now-this.accent.start)/1000,a=this.accent.amount;
        reactPitch+=a*(-.6*pulse(age,.14,.095)+.26*pulse(age,.37,.16));
        reactHead+=this.accent.side*a*.16*pulse(age,.18,.16);
        reactBody+=this.accent.side*a*.08*pulse(age,.3,.2);
        if(age>.85)this.accent=null;
      }
      if(this.action){
        const age=(now-this.action.start)/1000,side=this.action.side;
        if(this.action.name==='bounce'){
          // Quick push-off, a light landing, sometimes a smaller second hop.
          // The root moves visibly; the head, torso and hair land at different times.
          const a=this.action.amount,second=this.action.double?.68:0;
          lift=a*(.23*pulse(age,.065,.04)-1.15*pulse(age,.22,.095)+.18*pulse(age,.39,.065)
            -second*pulse(age,.59,.095)+second*.16*pulse(age,.77,.07));
          // This rig's positive pitch lowers the face: keep it small so the neck
          // does not stretch against the root's take-off.
          reactPitch=a*(.10*pulse(age,.08,.06)-.18*pulse(age,.24,.12)+.12*pulse(age,.43,.10)-second*.12*pulse(age,.62,.13));
          reactHead=side*a*(.27*pulse(age,.3,.22)+second*.18*pulse(age,.69,.21));
          reactBody=-side*a*.38*pulse(age,.38,.3);
        }
        if(this.action.name==='peek'){
          reactPitch=-.25*pulse(age,.24,.22);
          reactHead=side*.23*pulse(age,.3,.28);
          reactBody=-side*.11*pulse(age,.44,.3);
        }
        if(this.action.name==='nod')reactPitch=-.85*pulse(age,.2,.13)+.38*pulse(age,.49,.19);
        if(this.action.name==='wink')left=Math.min(left,blinkCurve(age/.5));
        if(this.action.name==='tilt'){
          reactHead=side*.45*pulse(age,.65,.5);
          reactBody=-side*.20*pulse(age,.85,.5);
        }
        if(age>(this.action.name==='bounce'?1.08:1.7))this.action=null;
      }
      const energy=this.state==='thinking'?.7:1;
      const spring=(key,target,frequency,damping,step)=>{
        const velocity=key+'V',p=this.pose;
        p[velocity]+=(frequency*frequency*(target-p[key])-2*damping*frequency*p[velocity])*step;
        p[key]+=p[velocity]*step;
      };
      const steps=Math.max(1,Math.ceil(dt/12)),step=dt/1000/steps;
      const follow=now-this.gaze.changed>160?1:0;
      for(let i=0;i<steps;i++){
        spring('head',this.poseTarget.head*energy+reactHead+this.gaze.x*.18*follow,12,.76,step);
        spring('pitch',this.poseTarget.pitch*energy+reactPitch-this.gaze.y*.18*follow,15,.7,step);
        spring('body',this.poseTarget.body*energy+reactBody+this.pose.head*.12-this.gaze.x*.08*follow,6,.82,step);
        spring('lift',lift,29,.66,step);
        spring('hair',-this.pose.body*.65-this.pose.head*.25-this.pose.pitchV*.035-this.pose.liftV*.035,5.8,.58,step);
      }
      const sway=this.pose.body*23,headTilt=this.pose.head*22;
      const headBob=this.pose.pitch*22+Math.sin(t*1.35)*.65;
      this.offset.x=this.pose.body*.012+this.pose.head*.004;
      this.offset.y=this.pose.lift*.018;
      const p=this.current, emphasis=this.state==='speaking'?mouth*.3:.25*pulse((now-this.noticeAt)/1000,.25,.3);
      const idleSmile=this.state==='idle'&&this.action?.name==='bounce'?.28*pulse((now-this.action.start)/1000,.48,.3):0;
      const values={
        ParamAngleX:0,ParamAngleY:Math.max(-30,Math.min(30,headBob)),ParamAngleZ:Math.max(-30,Math.min(30,p.tilt+headTilt)),
        ParamBodyAngleX:0,ParamBodyAngleY:0,ParamBodyAngleZ:sway,
        ParamBreath:Math.max(0,Math.min(1,.3+(Math.sin(t*1.24)+1)*.12-this.pose.lift*.48)),ParamHairSway:Math.max(-1,Math.min(1,this.pose.hair+Math.sin(t*1.2)*.15)),
        ParamEyeBallX:this.gaze.x,ParamEyeBallY:this.gaze.y,
        ParamEyeLOpen:p.eye*left*(1-idleSmile*.35),ParamEyeROpen:p.eye*right*(1-idleSmile*.35),
        ParamEyeLSmile:Math.max(p.smile,idleSmile),ParamEyeRSmile:Math.max(p.smile,idleSmile),
        ParamMouthForm:Math.max(p.form,idleSmile),ParamMouthOpenY:mouth,
        ParamBrowLY:p.browL+emphasis,ParamBrowRY:p.browR+emphasis,
        ParamBrowLAngle:p.angleL,ParamBrowRAngle:p.angleR,
        ParamSurprised:p.surprise,
      };
      // The supplied 2000 expressions have their own author-defined switches.
      if (this.reference) {values.Param31=this.expression==='surprised'?10:0;values.Param32=this.expression==='serious'?1:0;}
      for (const [id,value] of Object.entries(values)) this.set(id,value);
      this.values=values;
      return values;
    }
  }
  window.AvatarPerformance=AvatarPerformance;
})();
