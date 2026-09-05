const {contextBridge,ipcRenderer} = require('electron');
contextBridge.exposeInMainWorld('companionDesktop',{
  toggleCompact:()=>ipcRenderer.invoke('companion:compact'),
  onCompact:(callback)=>{ipcRenderer.on('companion:compact-changed',(_event,enabled)=>callback(Boolean(enabled)));}
});
