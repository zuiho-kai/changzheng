'use strict';
(async () => {
  let mouth = 0, updated = 0, displayedMouth = 0, lastFrame = performance.now();
  let measuredFrames=0,measureStart=lastFrame;
  let performer, performanceState='idle', expression='auto';
  addEventListener('message', event => {
    if (event.source !== parent || event.origin !== location.origin) return;
    if (event.data?.type === 'performance') {
      if(event.data.attention==='chat')performer?.notice();
      if (['idle','listening','thinking','speaking'].includes(event.data.state)) {
        performanceState=event.data.state;performer?.setState(performanceState,!!event.data.reset);
      }
      if (event.data.reset) {mouth=0;displayedMouth=0;expression='auto';}
      if (['auto','neutral','happy','curious','surprised','serious'].includes(event.data.expression)) {
        expression=event.data.expression;performer?.setExpression(expression);
      }
      if (event.data.gesture) performer?.gesture(event.data.gesture);
      return;
    }
    if (event.data?.type !== 'mouth') return;
    if (!Number.isFinite(event.data.value)) return;
    mouth = Math.max(0, Math.min(1, event.data.value)); updated = performance.now();
  });
  try {
    const app = new PIXI.Application({width:innerWidth, height:innerHeight, backgroundAlpha: 0, antialias: true, resolution: Math.min(devicePixelRatio, 1.5)});
    app.ticker.maxFPS = 30;
    document.body.append(app.view);
    const params = new URLSearchParams(location.search);
    document.title = params.get('model') === 'changzheng' ? 'Live2D · 长征酱' : 'Live2D · 日和';
    const modelPath = params.get('model') === 'changzheng' ? '/static/models/changzheng/model.model3.json'
      : '/static/models/hiyori/runtime/hiyori_free_t08.model3.json';
    const model = await PIXI.live2d.Live2DModel.from(modelPath, {autoInteract:false});
    app.stage.addChild(model);
    if (params.get('model') === 'changzheng') {
      performer=new AvatarPerformance(model.internalModel.coreModel);
      performer.setState(performanceState);performer.setExpression(expression);
    }
    const original = {width:model.width, height:model.height};
    const restPosition={x:0,y:0};
    const portrait = new URLSearchParams(location.search).get('framing') === 'portrait';
    model.anchor.set(.5, portrait ? 0 : 1);
    const resize = () => {
      app.renderer.resize(innerWidth, innerHeight);
      if (params.get('model') === 'changzheng') {
        // The decomposer pads to a square; frame the painted figure, not that empty canvas.
        const box = {x:130 / 1254, y:28 / 1254, w:980 / 1254, h:1226 / 1254};
        const scale = Math.min(innerWidth / (original.width * box.w) * (portrait ? 1.25 : 1),
          innerHeight / (original.height * box.h * (portrait ? .72 : 1))) * .96;
        model.anchor.set(0, 0); model.scale.set(scale);
        model.position.set((innerWidth - original.width * box.w * scale) / 2 - original.width * box.x * scale,
          (portrait ? 0 : innerHeight - original.height * box.h * scale) - original.height * box.y * scale);
        restPosition.x=model.x;restPosition.y=model.y;
        app.render(); return;
      }
      const scale = portrait ? Math.min(innerWidth / original.width * 1.5, innerHeight / (original.height * .62))
        : Math.min(innerWidth / original.width, innerHeight / original.height) * .98;
      model.scale.set(scale); model.position.set(innerWidth / 2, portrait ? 0 : innerHeight);
      // Resize clears WebGL's buffer. Repaint with the new framing immediately,
      // rather than waiting for an independently scheduled ticker/resize pass.
      app.render();
    };
    addEventListener('resize', resize); resize();
    model.internalModel.on('beforeModelUpdate', () => {
      const now = performance.now();
      measuredFrames++;
      if(now-measureStart>=2000){document.body.dataset.fps=(measuredFrames*1000/(now-measureStart)).toFixed(1);measuredFrames=0;measureStart=now;}
      const target = now - updated < 250 ? mouth : 0;
      const dt = Math.min(100, Math.max(0, now - lastFrame)); lastFrame = now;
      // Ease positive RMS steps, but never ease a stop or stale audio event:
      // those must close the mouth on the very next rendered frame.
      displayedMouth = target === 0 ? 0 : displayedMouth + (target - displayedMouth) * (1 - Math.exp(-dt / 45));
      const values=performer?.update(now,displayedMouth);
      if(performer) model.position.set(restPosition.x+(performer.offset?.x||0)*innerHeight,restPosition.y+(performer.offset?.y||0)*innerHeight);
      document.body.dataset.performance=performanceState;
      document.body.dataset.expression=expression;
      if (values) document.body.dataset.yaw=String(values.ParamAngleX);
      model.internalModel.coreModel.setParameterValueById('ParamMouthOpenY', displayedMouth);
      document.body.dataset.mouth = String(displayedMouth);
      if(values){document.body.dataset.gazeX=String(values.ParamEyeBallX);document.body.dataset.gazeY=String(values.ParamEyeBallY);}
    });
    document.querySelector('#loading').remove();
    document.body.dataset.ready = 'true';
    parent.postMessage({type:'live2d-ready'}, location.origin);
    addEventListener('pagehide', () => app.destroy(true, {children:true, texture:true, baseTexture:true}), {once:true});
  } catch (error) {
    document.querySelector('#loading').textContent = 'Live2D 加载失败';
    parent.postMessage({type:'live2d-error', message:String(error.message)}, location.origin);
  }
})();
