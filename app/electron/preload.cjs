const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("nativeApp", {
  backendUrl: "http://127.0.0.1:18765",
  appearance: {
    setTheme: (theme) => ipcRenderer.invoke("appearance:setTheme", theme),
  },
  dialog: {
    selectFolder: (title) => ipcRenderer.invoke("dialog:selectFolder", title),
    selectFile: (title, filters) => ipcRenderer.invoke("dialog:selectFile", title, filters),
  },
});
