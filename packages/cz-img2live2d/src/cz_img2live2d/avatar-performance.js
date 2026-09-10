'use strict';
// Shared by the real avatar and its review page; no yaw animation.
(() => {
  const expressions = {
    neutral: {eye:1, smile:0, form:0, browL:0, browR:0, angleL:0, angleR:0, tilt:0,surprise:0},
    happy: {eye:.82, smile:.8, form:.9, browL:.35, browR:.35, tilt:-5},
    curious: {eye:1.06, form:-.25, browL:.7, browR:-.1, tilt:10},
    surprised: {eye:1.12, form:-.8, browL:.9, browR:.9, tilt:0,surprise:1},
    serious: {eye:.72, form:-.6, browL:-.25, browR:-.25, angleL:.55, angleR:-.55, tilt:-3},
  };
  const states = {
    idle: {},
    listening: {eye:1.05, browL:.3, browR:.15, tilt:4},
    thinking: {eye:.78, form:-.25, browL:.5, browR:-.1, tilt:-5},
    speaking: {eye:1, form:.4, browL:.16, browR:.16, tilt:0},
  };
  class AvatarPerformance {
    constructor(core, {reference=false}={}) {
      this.core=core; this.reference=reference; this.state='idle'; this.expression='auto';
      this.current={...expressions.neutral};this.last=performance.now();this.nextBlink=this.last+3800;
      this.expressionTilt=0;
      this.hairFollow=new HairFollow();
      this.blinkAt=-Infinity;this.action=null;this.parameters=new Set(core._model.parameters.ids);
      this.pose={head:0,body:0,pitch:0,hair:0,lift:0,lean:0,shoulderL:0,shoulderR:0,headV:0,bodyV:0,pitchV:0,hairV:0,liftV:0,leanV:0,shoulderLV:0,shoulderRV:0};
      this.poseTarget={head:-.18,body:.08,pitch:0};this.nextPose=this.last+3300;
      this.offset={x:0,y:0};this.accent=null;this.nextAccent=0;this.voiceLevel=0;
      this.nextHop=this.last+1100+Math.random()*800;
      this.gaze={x:0,y:0,targetX:0,targetY:0,changed:this.last,next:this.last+900};
      this.noticeAt=-Infinity;
      this.idleBeat=null;this.idleBeatIndex=0;
      this.stateAt=this.last;this.expressionAt=this.last;this.lastVoice=this.last;this.wasVoiced=false;
      this.attention=null;this.phraseAt=-Infinity;this.phraseIndex=0;this.phraseSide=1;this.speechStarted=false;
      if(this.parameters.has('ParamRuntimeGaze'))this.bindGaze();
    }
    bindGaze(){
      // A local iris warp avoids multiplying every eye keyform by two gaze axes.
      // Restore native vertices before Cubism updates, so held poses never drift.
      const draw=this.core._model.drawables,rects={EyeLeftOpen:[529,302,584,340],EyeRightOpen:[678,302,719,341],EyeLeftSurprised:[529,302,584,340],EyeRightSurprised:[678,302,719,341]};
      const smooth=(a,b,x)=>{const t=Math.max(0,Math.min(1,(x-a)/(b-a)));return t*t*(3-2*t);};
      const eyes=[], meshes=draw.vertexPositions.map((vertices,index)=>({index,native:new Float32Array(vertices)}));
      draw.ids.forEach((name,index)=>{
        const rect=rects[name];if(!rect)return;
        const uv=draw.vertexUvs[index],weights=[];
        const minU=Math.min(...Array.from(uv).filter((_,i)=>i%2===0));
        const minV=Math.min(...Array.from(uv).filter((_,i)=>i%2===1));
        for(let i=0;i<uv.length;i+=2){
          const x=rect[0]+(uv[i]-minU)*2048,y=rect[3]-(uv[i+1]-minV)*2048;
          weights.push((1-smooth(.38,1,Math.abs(x-rect[2])/40))*(1-smooth(.38,1,Math.abs(y-rect[3])/27)));
        }
        eyes.push({index,left:name.includes('Left'),weights,native:new Float32Array(draw.vertexPositions[index])});
      });
      const nativeUpdate=this.core.update.bind(this.core);
      this.core.update=()=>{
        for(const mesh of meshes)draw.vertexPositions[mesh.index].set(mesh.native);
        nativeUpdate();
        for(const mesh of meshes)mesh.native.set(draw.vertexPositions[mesh.index]);
        const angle=((this.values?.ParamAngleZ||0)*20/30+(this.values?.ParamBodyAngleZ||0)*8/30)*Math.PI/180;
        const cos=Math.cos(angle),sin=Math.sin(angle);
        for(const eye of eyes){
          const vertices=draw.vertexPositions[eye.index];
          const open=Math.max(.06,this.values?.[eye.left?'ParamEyeLOpen':'ParamEyeROpen']??1);
          const dx=7*this.gaze.x,dy=-4*this.gaze.y*open;
          for(let i=0;i<eye.weights.length;i++){
            const weight=eye.weights[i]*2/1254;
            vertices[i*2]+=(dx*cos-dy*sin)*weight;
            // Cubism runtime is Y-up; atlas/source pixels are Y-down.
            vertices[i*2+1]-=(dx*sin+dy*cos)*weight;
          }
          draw.dynamicFlags[eye.index]|=32;
        }
        // Local sleeve motion only. Do not scale the head or upper body to
        // imitate leaning toward the camera: it reads as an unwanted zoom.
        const left=this.pose.shoulderL,right=this.pose.shoulderR;
        for(const mesh of meshes){
          const vertices=draw.vertexPositions[mesh.index],uv=draw.vertexUvs[mesh.index];
          for(let i=0;i<vertices.length;i+=2){
            let dx=0,dy=0;
            if(draw.ids[mesh.index]==='BodyHeadSkin'){
              // Use immutable source-image coordinates, as a layered rig does.
              // Runtime vertex Y is inverted and may already contain a pose;
              // using it as image Y applies sleeve weights to the cheeks.
              const rx=uv[i]*2048,ry=(1-uv[i+1])*2048;
              const side=rx<646?-1:1,shoulder=side<0?left:right;
              const lateral=smooth(55,135,Math.abs(rx-646));
              const sleeve=lateral*smooth(440,600,ry)*(1-smooth(1030,1240,ry));
              dx+=side*shoulder*42*sleeve*smooth(500,850,ry);
              dy-=shoulder*36*sleeve*(1-smooth(790,1190,ry));
              // The source has no hidden hair backing. Weight only the outer
              // silhouette, outside the sleeves; keep face, collar and scalp fixed.
              const hairSide=this.hairFollow.sides[side<0?0:1];
              const boundary=170+smooth(400,1000,ry)*195;
              const hairWeight=smooth(boundary,boundary+65,Math.abs(rx-646))*smooth(330,690,ry);
              const tip=smooth(530,1020,ry);
              const hairDx=(hairSide.x*(1-tip)+hairSide.tipX*tip)*hairWeight;
              dx+=hairDx;
              dy+=Math.abs(hairDx)*.08;
            }
            vertices[i]+=dx*2/1254;vertices[i+1]-=dy*2/1254;
          }
          draw.dynamicFlags[mesh.index]|=32;
        }
      };
    }
    setState(state, reset=false) {
      if (!(state in states)) return;
      if(reset)this.idleBeat=null;
      if (reset) {this.expression='auto';this.action=null;this.accent=null;this.attention=null;this.voiceLevel=0;this.noticeAt=-Infinity;this.nextHop=performance.now()+2800+Math.random()*1100;this.look(0,0,1800);}
      if (state!=='speaking') this.accent=null;
      if(state!==this.state){
        this.idleBeat=null;
        this.stateAt=performance.now();this.nextPose=this.stateAt+1800;
        this.poseTarget={head:0,body:0,pitch:0};
        this.action=null;this.attention=null;
        if(state==='thinking')this.look(-.5,.32,8000);
        else if(state==='listening')this.beginAttention();
        else if(state==='speaking'){
          this.look(0,0,8000);this.speechStarted=false;this.phraseIndex=0;
          this.phraseAt=-Infinity;this.nextAccent=this.stateAt+450;
        }else{
          this.look(0,0,2200);this.nextHop=this.stateAt+3000+Math.random()*1300;
        }
      }
      this.state=state;
    }
    look(x,y,hold=1000){
      const now=performance.now();
      Object.assign(this.gaze,{targetX:x,targetY:y,changed:now,next:now+hold});
    }
    notice(){
      if(this.state==='speaking'){this.look(.45,.02,400);return;}
      if(this.attention && performance.now()-this.attention.start<700)return;
      this.beginAttention();
    }
    beginAttention(){
      this.idleBeat=null;
      this.noticeAt=performance.now();this.attention={start:this.noticeAt,returned:false};
      this.action=null;this.poseTarget={head:0,body:0,pitch:0};
      this.look(.85,.04,3000);
    }
    setExpression(name) {if (name==='auto'||name in expressions) {if(name!==this.expression)this.expressionAt=performance.now();this.expression=name;}}
    gesture(name) {
      if (!['nod','wink','tilt','bounce','peek','shrug'].includes(name)) return;
      const now=performance.now();
      // Repeated expression events must not pin a hop at its first frame.
      if (this.action?.name===name && now-this.action.start<650) return;
      this.action={name,start:now,side:Math.random()<.5?-1:1,amount:.65+Math.random()*.5,double:name==='bounce'&&Math.random()<.3};
      this.idleBeat=null;
      this.nextHop=now+5100+Math.random()*2900;
    }
    set(id,value) {if (this.parameters.has(id)) this.core.setParameterValueById(id,value);}
    update(now, mouth=0) {
      const dt=Math.max(0,Math.min(100,now-this.last));this.last=now;
      if(this.attention && now-this.attention.start>1450 && !this.attention.returned){
        this.attention.returned=true;this.look(0,0,2300);
      }
      if(now>=this.gaze.next && !this.attention){
        const camera=Math.abs(this.gaze.targetX)>.2||Math.random()<(this.state==='speaking'?.92:.55);
        const x=camera?(Math.random()-.5)*.10:(Math.random()<.7?1:-1)*(.45+Math.random()*.4);
        const y=camera?0:(Math.random()-.35)*.45;
        if(this.state==='thinking')this.look(-.5,.3,4000);
        else if(this.state==='listening')this.look(0,0,3000);
        else this.look(x,y,camera?1800+Math.random()*2300:650+Math.random()*700);
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
      if(!this.action && !this.attention && !this.idleBeat && now>=this.nextHop && this.expression!=='serious' && this.state==='idle'){
        const choice=Math.random();
        this.gesture(choice<.28?'bounce':choice<.58?'shrug':choice<.82?'peek':'tilt');
        const side=this.action.side;
        this.poseTarget={head:side*(.12+Math.random()*.18),body:-side*(.09+Math.random()*.12),pitch:(Math.random()-.5)*.12};
      }
      if(now>=this.nextPose && !this.attention && !this.action && !this.idleBeat && this.state==='idle'){
        const side=this.idleBeatIndex++%2===0?1:-1;
        this.idleBeat={start:now,side,amount:.24+Math.random()*.12,hold:.65+Math.random()*.7,returned:false};
        this.poseTarget={head:0,body:0,pitch:0};
        this.look(side*.65,.08,3200);
        this.nextPose=now+4200+Math.random()*1900;
      }
      // A loud rising syllable can initiate one accent, with a refractory period.
      // Mouth itself stays the supplied real RMS; this only drives head/body.
      const rising=mouth-this.voiceLevel;
      this.voiceLevel+=(mouth-this.voiceLevel)*(1-Math.exp(-dt/160));
      const gap=now-this.lastVoice,calm=this.expression==='neutral'||this.expression==='serious';
      if(this.state==='speaking' && mouth>.08){
        if(!this.speechStarted || gap>300){
          this.phraseAt=now;this.phraseSide=this.phraseIndex++%2===0?1:-1;
          this.speechStarted=true;this.look(0,0,4000);
        }
        this.lastVoice=now;
      }
      const actionAllowsAccent=!this.action||!['bounce','nod'].includes(this.action.name);
      if(this.state==='speaking' && mouth>.19 && rising>.10 && now>=this.nextAccent && now-this.phraseAt>220 && actionAllowsAccent){
        this.accent={start:now,amount:Math.min(1,.45+mouth),side:this.phraseSide};
        this.nextAccent=now+1150+Math.random()*850;
      }
      const pulse=(age,center,width)=>Math.exp(-Math.pow((age-center)/width,2));
      const ramp=(age,start,end)=>{const x=Math.max(0,Math.min(1,(age-start)/(end-start)));return x*x*(3-2*x);};
      let reactHead=0,reactPitch=0,reactBody=0,lift=0,left=blink,right=blink,shoulderL=0,shoulderR=0,lean=0;
      if(this.idleBeat){
        const beat=this.idleBeat,age=(now-beat.start)/1000,end=.8+beat.hold;
        // Gaze initiates the beat, then head, then torso; soften the hold before
        // returning. This uses PuppetLoom's observed timing design, not its code.
        const head=ramp(age,.16,.7)*(1-.05*ramp(age,.7,end))*(1-ramp(age,end,end+.95));
        const body=ramp(age,.36,.95)*(1-ramp(age,end+.16,end+1.18));
        reactHead+=beat.side*beat.amount*head;
        reactBody-=beat.side*beat.amount*.52*body;
        reactPitch-=.08*head;
        if(age>end-.1&&!beat.returned){beat.returned=true;this.look(0,0,2200);}
        if(age>end+1.2)this.idleBeat=null;
      }
      const ageState=(now-this.stateAt)/1000;
      if(this.state==='listening'){
        shoulderR=.08;reactPitch=-.07;
      }else if(this.state==='thinking'){
        const consider=ramp(ageState,.3,.8)*(1-.55*ramp(ageState,1.25,2.2));
        shoulderL=.35*consider;reactBody=.25*consider;reactHead=-.3*consider;reactPitch=-.1;
      }else if(this.state==='speaking'){
        // A sentence opens toward the viewer. A sustained audio gap releases
        // the shoulders; the next phrase takes a different, held stance.
        const phraseAge=(now-this.phraseAt)/1000;
        const quiet=ramp((now-this.lastVoice)/1000,.16,.55),energy=calm?.4:1;
        const open=pulse(phraseAge,.28,.24),hold=ramp(phraseAge,.12,.45)*(1-quiet);
        reactHead=this.phraseSide*.16*hold*energy;
        reactBody=-this.phraseSide*.16*hold*energy;
        reactPitch=(-.24*open+.08*quiet)*energy;
        const shoulder=(.34*open+.15*hold)*energy;
        if(this.phraseSide<0)shoulderL=shoulder;else shoulderR=shoulder;
        // Before audio begins: eye contact, then a small breath, not a nod loop.
        if(!this.speechStarted)reactPitch=-.1*pulse(ageState,.3,.25);
      }
      if(this.attention){
        const age=(now-this.attention.start)/1000;
        const head=ramp(age,.18,.52)*(1-ramp(age,1.63,2.1));
        const body=ramp(age,.38,.83)*(1-ramp(age,1.88,2.5));
        reactHead+=.35*head;reactPitch-=.12*head;
        reactBody-=.23*body;shoulderR+=.22*body;
        if(age>2.55)this.attention=null;
      }
      if(this.accent){
        const age=(now-this.accent.start)/1000,a=this.accent.amount*(calm?.35:1);
        reactPitch+=a*(-.6*pulse(age,.14,.095)+.26*pulse(age,.37,.16));
        reactHead+=this.accent.side*a*.29*pulse(age,.22,.2);
        reactBody-=this.accent.side*a*.18*pulse(age,.36,.28);
        lean+=a*.2*pulse(age,.24,.25);
        const shoulder=a*.58*pulse(age,.32,.25);
        if(this.accent.side<0)shoulderL+=shoulder;else shoulderR+=shoulder;
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
          lean+=.5*pulse(age,.55,.4);
          reactPitch=-.25*pulse(age,.24,.22);
          reactHead=side*.23*pulse(age,.3,.28);
          reactBody=-side*.11*pulse(age,.44,.3);
        }
        if(this.action.name==='nod')reactPitch=-.85*pulse(age,.2,.13)+.38*pulse(age,.49,.19);
        if(this.action.name==='wink')left=Math.min(left,blinkCurve(age/.5));
        if(this.action.name==='tilt'){
          reactHead+=side*.30*pulse(age,.65,.5);
          reactBody-=side*.14*pulse(age,.85,.5);
        }
        if(this.action.name==='shrug'){
          const hold=pulse(age,.58,.39),a=this.action.amount;
          shoulderL+=a*hold;shoulderR+=a*.68*pulse(age,.75,.43);
          reactHead-=side*.4*hold;reactBody+=side*.2*hold;lean-=.24*hold;
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
      const follow=this.attention?0:ramp((now-this.gaze.changed)/1000,.16,.4);
      for(let i=0;i<steps;i++){
        spring('head',this.poseTarget.head*energy+reactHead+this.gaze.x*.18*follow,12,.76,step);
        spring('pitch',this.poseTarget.pitch*energy+reactPitch-this.gaze.y*.18*follow,15,.7,step);
        spring('body',this.poseTarget.body*energy+reactBody+this.pose.head*.12-this.gaze.x*.08*follow,6,.82,step);
        spring('lift',lift,29,.66,step);
        spring('hair',-this.pose.body*.65-this.pose.head*.25-this.pose.pitchV*.035-this.pose.liftV*.035,5.8,.58,step);
        spring('lean',lean,7,.9,step);
        spring('shoulderL',shoulderL,10,.78,step);spring('shoulderR',shoulderR,9,.8,step);
      }
      const sway=this.pose.body*23,headTilt=this.pose.head*22;
      const headBob=this.pose.pitch*22+Math.sin(t*1.35)*.65;
      this.offset.x=this.pose.body*.006;
      this.offset.y=this.pose.lift*.018;
      const p=this.current, emphasis=this.state==='speaking'?mouth*.3:.25*pulse((now-this.noticeAt)/1000,.25,.3);
      const idleSmile=this.state==='idle'&&this.action?.name==='bounce'?.28*pulse((now-this.action.start)/1000,.48,.3):0;
      // Smile with eye contact through the line; brief eye closures carry the
      // laugh itself instead of holding both eyes shut for the whole utterance.
      const laugh=this.expression==='happy'?pulse((now-this.expressionAt)/1000,.5,.25):0;
      // Curiosity introduces the line; it should not pin the head to one side
      // after the sentence's own gestures have taken over.
      const curiousIntro=this.expression==='curious'?.2+.8*Math.exp(-Math.max(0,now-this.expressionAt)/850):1;
      this.expressionTilt+=(target.tilt*curiousIntro-this.expressionTilt)*ease;
      this.hairFollow.update(dt/1000,this.expressionTilt+headTilt,sway,this.pose.pitch);
      const values={
        ParamAngleX:0,ParamAngleY:Math.max(-30,Math.min(30,headBob)),ParamAngleZ:Math.max(-30,Math.min(30,this.expressionTilt+headTilt)),
        ParamBodyAngleX:0,ParamBodyAngleY:0,ParamBodyAngleZ:sway,
        ParamBreath:Math.max(0,Math.min(1,.3+(Math.sin(t*1.24)+1)*.12-this.pose.lift*.48)),ParamHairSway:0,
        ParamEyeBallX:this.gaze.x,ParamEyeBallY:this.gaze.y,
        ParamEyeLOpen:p.eye*left*(1-idleSmile*.35)*(1-laugh),ParamEyeROpen:p.eye*right*(1-idleSmile*.35)*(1-laugh),
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
