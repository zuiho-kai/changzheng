'use strict';
(async () => {
  let mouth = 0, updated = 0;
  addEventListener('message', event => {
    if (event.source !== parent || event.origin !== location.origin || event.data?.type !== 'mouth') return;
    if (!Number.isFinite(event.data.value)) return;
    mouth = Math.max(0, Math.min(1, event.data.value)); updated = performance.now();
  });
  try {
    const app = new PIXI.Application({resizeTo: window, backgroundAlpha: 0, antialias: true, resolution: Math.min(devicePixelRatio, 1.5)});
    app.ticker.maxFPS = 30;
    document.body.append(app.view);
    const model = await PIXI.live2d.Live2DModel.from('/static/models/hiyori/runtime/hiyori_free_t08.model3.json', {autoInteract:false});
    app.stage.addChild(model);
    const original = {width:model.width, height:model.height};
    model.anchor.set(.5, 1);
    const resize = () => {model.scale.set(Math.min(innerWidth / original.width, innerHeight / original.height) * .98); model.position.set(innerWidth / 2, innerHeight);};
    addEventListener('resize', resize); resize();
    model.internalModel.on('beforeModelUpdate', () => {
      const value = performance.now() - updated < 250 ? mouth : 0;
      model.internalModel.coreModel.setParameterValueById('ParamMouthOpenY', value);
      document.body.dataset.mouth = String(value);
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
