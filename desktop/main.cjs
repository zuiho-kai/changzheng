const {app, BrowserWindow, ipcMain, session} = require('electron');
const path = require('node:path');

const APP_URL = process.env.CHANGZHENG_URL || 'http://127.0.0.1:17861';
let window, compact = false, normalBounds;
const singleInstance = app.requestSingleInstanceLock();
if (!singleInstance) app.quit();
else {
  app.on('second-instance', () => {if (window) {if (window.isMinimized()) window.restore(); window.show(); window.focus();}});
  app.whenReady().then(() => {
    session.defaultSession.setPermissionRequestHandler((contents, permission, callback) => {
      const local = contents.getURL().startsWith(APP_URL + '/');
      callback(local && ['media','audioCapture'].includes(permission));
    });
    session.defaultSession.setPermissionCheckHandler((contents, permission, requestingOrigin) => requestingOrigin === APP_URL && ['media','audioCapture'].includes(permission));
    window = new BrowserWindow({width:1180,height:850,minWidth:650,minHeight:620,title:'小征 · 在你身边',backgroundColor:'#f5f3ed',autoHideMenuBar:true,show:false,
      webPreferences:{preload:path.join(__dirname,'preload.cjs'),contextIsolation:true,nodeIntegration:false,sandbox:true}});
    window.webContents.setWindowOpenHandler(() => ({action:'deny'}));
    window.webContents.on('will-navigate',(event,url)=>{if (!url.startsWith(APP_URL+'/') && url !== APP_URL) event.preventDefault();});
    window.once('ready-to-show',()=>window.show());
    window.loadURL(APP_URL);
    ipcMain.handle('companion:compact',(event)=>{
      if (event.sender !== window.webContents) return compact;
      compact = !compact;
      if (compact) {normalBounds = window.getBounds(); window.setMinimumSize(260,300); window.setAlwaysOnTop(true); window.setSize(310,390);}
      else {window.setResizable(true); window.setAlwaysOnTop(false); window.setMinimumSize(650,620); if (normalBounds) window.setBounds(normalBounds);}
      window.webContents.send('companion:compact-changed',compact);
      return compact;
    });
  });
  app.on('window-all-closed',()=>app.quit());
}
