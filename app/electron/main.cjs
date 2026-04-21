const { app, BrowserWindow, ipcMain, nativeTheme, dialog, shell } = require("electron");
const path = require("path");
const fs = require("fs");
const { spawn } = require("child_process");
const http = require("http");

const BACKEND_PORT = 18765;
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`;
const APP_DISPLAY_NAME = "SteamTools ALLinOne";
const MAIN_LOG_FILE = "main-process.log";

let backendProcess = null;
let isQuitting = false;
let mainWindow = null;
const INTEGRATION_STATE_FILE = "integration-state.json";

function themeBackground() {
  return nativeTheme.shouldUseDarkColors ? "#0f1115" : "#f1f3f5";
}

function logPath() {
  return path.join(app.getPath("userData"), MAIN_LOG_FILE);
}

function appendLog(message) {
  try {
    fs.mkdirSync(app.getPath("userData"), { recursive: true });
    fs.appendFileSync(logPath(), `[${new Date().toISOString()}] ${message}\n`, "utf8");
  } catch (_error) {
    // ignore
  }
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1180,
    height: 760,
    minWidth: 900,
    minHeight: 600,
    backgroundColor: themeBackground(),
    autoHideMenuBar: true,
    frame: true,
    title: "SteamTools ALLinOne",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  mainWindow = win;
  appendLog("BrowserWindow created");

  nativeTheme.themeSource = "system";
  nativeTheme.on("updated", () => {
    win.setBackgroundColor(themeBackground());
  });

  win.webContents.on("did-fail-load", (_event, errorCode, errorDescription, validatedURL) => {
    appendLog(`did-fail-load: code=${errorCode} desc=${errorDescription} url=${validatedURL}`);
  });
  win.webContents.on("render-process-gone", (_event, details) => {
    appendLog(`render-process-gone: reason=${details.reason} exitCode=${details.exitCode}`);
  });
  win.webContents.on("console-message", (_event, level, message, line, sourceId) => {
    appendLog(`renderer-console[level=${level}] ${sourceId}:${line} ${message}`);
  });

  if (process.env.VITE_DEV_SERVER_URL) {
    appendLog(`Loading dev URL: ${process.env.VITE_DEV_SERVER_URL}`);
    win.loadURL(process.env.VITE_DEV_SERVER_URL);
  } else {
    const indexPath = path.join(__dirname, "..", "dist", "index.html");
    appendLog(`Loading file: ${indexPath}`);
    win.loadFile(indexPath);
  }
}

function integrationStatePath() {
  return path.join(app.getPath("userData"), INTEGRATION_STATE_FILE);
}

function readIntegrationState() {
  try {
    return JSON.parse(fs.readFileSync(integrationStatePath(), "utf8"));
  } catch (_error) {
    return {};
  }
}

function writeIntegrationState(nextState) {
  fs.mkdirSync(app.getPath("userData"), { recursive: true });
  fs.writeFileSync(integrationStatePath(), JSON.stringify(nextState, null, 2), "utf8");
}

function hasDesktopShortcut() {
  const shortcutPath = path.join(app.getPath("desktop"), `${APP_DISPLAY_NAME}.lnk`);
  return fs.existsSync(shortcutPath);
}

function createDesktopShortcut() {
  const shortcutPath = path.join(app.getPath("desktop"), `${APP_DISPLAY_NAME}.lnk`);
  return shell.writeShortcutLink(shortcutPath, "create", {
    target: process.execPath,
    cwd: path.dirname(process.execPath),
    description: APP_DISPLAY_NAME,
    icon: process.execPath,
    iconIndex: 0,
  });
}

async function ensureWindowsIntegrations() {
  if (!app.isPackaged || process.platform !== "win32") {
    return;
  }

  const state = readIntegrationState();
  const nextState = { ...state };
  const win = mainWindow || BrowserWindow.getFocusedWindow() || null;

  const loginSettings = app.getLoginItemSettings();
  if (!loginSettings.openAtLogin && !state.startupPromptShown) {
    const result = await dialog.showMessageBox(win, {
      type: "question",
      buttons: ["允许", "暂不"],
      defaultId: 0,
      cancelId: 1,
      title: "开机自启动",
      message: "是否允许 SteamTools ALLinOne 开机自启动？",
      detail: "允许后，软件会在 Windows 登录后自动启动，便于直接使用。",
      noLink: true,
    });
    if (result.response === 0) {
      app.setLoginItemSettings({
        openAtLogin: true,
        path: process.execPath,
      });
    }
    nextState.startupPromptShown = true;
  }

  if (!hasDesktopShortcut() && !state.desktopShortcutPromptShown) {
    const result = await dialog.showMessageBox(win, {
      type: "question",
      buttons: ["创建", "跳过"],
      defaultId: 0,
      cancelId: 1,
      title: "桌面快捷方式",
      message: "是否在桌面创建 SteamTools ALLinOne 快捷方式？",
      detail: "创建后，你可以从桌面直接启动本软件。",
      noLink: true,
    });
    if (result.response === 0) {
      createDesktopShortcut();
    }
    nextState.desktopShortcutPromptShown = true;
  }

  if (
    nextState.startupPromptShown !== state.startupPromptShown ||
    nextState.desktopShortcutPromptShown !== state.desktopShortcutPromptShown
  ) {
    writeIntegrationState(nextState);
  }
}

ipcMain.handle("appearance:setTheme", (_event, theme) => {
  const nextTheme = ["system", "dark", "light"].includes(theme) ? theme : "system";
  nativeTheme.themeSource = nextTheme;
  if (mainWindow) {
    mainWindow.setBackgroundColor(themeBackground());
  }
  return { theme: nextTheme, dark: nativeTheme.shouldUseDarkColors };
});

ipcMain.handle("dialog:selectFolder", async (_event, title) => {
  const win = mainWindow || BrowserWindow.getFocusedWindow();
  const result = await dialog.showOpenDialog(win, {
    title: title || "选择文件夹",
    properties: ["openDirectory"],
  });
  return result.canceled ? null : (result.filePaths[0] || null);
});

ipcMain.handle("dialog:selectFile", async (_event, title, filters) => {
  const win = mainWindow || BrowserWindow.getFocusedWindow();
  const result = await dialog.showOpenDialog(win, {
    title: title || "选择文件",
    properties: ["openFile"],
    filters: filters || [{ name: "所有文件", extensions: ["*"] }],
  });
  return result.canceled ? null : (result.filePaths[0] || null);
});

function startBackend() {
  const rootDir = path.join(__dirname, "..", "..");
  const isPackaged = app.isPackaged;
  const backendExe = path.join(process.resourcesPath, "backend", "backend-server.exe");
  const pythonCmd = process.env.PYTHON_PATH || "python";
  const command = isPackaged ? backendExe : pythonCmd;
  const args = isPackaged ? [] : ["-m", "backend.server"];
  const env = {
    ...process.env,
    STEAMTOOLS_MANAGER_BASE_DIR: isPackaged ? app.getPath("userData") : rootDir,
    STEAMTOOLS_MANAGER_ASSETS_DIR: isPackaged ? process.resourcesPath : rootDir,
  };
  appendLog(`Starting backend: command=${command} cwd=${isPackaged ? process.resourcesPath : rootDir}`);

  backendProcess = spawn(command, args, {
    cwd: isPackaged ? process.resourcesPath : rootDir,
    env,
    windowsHide: true,
    stdio: "pipe",
  });

  backendProcess.stderr.on("data", (chunk) => {
    appendLog(`backend-stderr: ${String(chunk).trim()}`);
    process.stderr.write(chunk);
  });
  backendProcess.stdout.on("data", (chunk) => {
    appendLog(`backend-stdout: ${String(chunk).trim()}`);
    process.stdout.write(chunk);
  });
  backendProcess.on("error", (error) => {
    appendLog(`backend-error: ${error?.stack || error}`);
    console.error("Failed to start backend:", error);
  });
}

function stopBackend() {
  if (backendProcess && !backendProcess.killed) {
    appendLog("Stopping backend");
    backendProcess.kill();
    backendProcess = null;
  }
}

function postToBackend(pathname, timeoutMs = 5000) {
  return new Promise((resolve) => {
    const req = http.request(
      {
        host: "127.0.0.1",
        port: BACKEND_PORT,
        path: pathname,
        method: "POST",
        timeout: timeoutMs,
      },
      (res) => {
        res.resume();
        resolve(res.statusCode && res.statusCode >= 200 && res.statusCode < 300);
      },
    );
    req.on("timeout", () => {
      req.destroy();
      resolve(false);
    });
    req.on("error", () => resolve(false));
    req.end();
  });
}

async function shutdownApp() {
  await postToBackend("/trainer/stop-all");
  stopBackend();
  isQuitting = true;
  app.quit();
}

function waitForBackendReady(timeoutMs = 120000) {
  const started = Date.now();
  return new Promise((resolve, reject) => {
    const tick = () => {
      const req = http.get(`${BACKEND_URL}/health`, (res) => {
        res.resume();
        if (res.statusCode === 200) {
          resolve();
        } else if (Date.now() - started > timeoutMs) {
          reject(new Error("Backend health check failed"));
        } else {
          setTimeout(tick, 250);
        }
      });
      req.on("error", () => {
        if (Date.now() - started > timeoutMs) {
          reject(new Error("Backend start timeout"));
        } else {
          setTimeout(tick, 250);
        }
      });
    };
    tick();
  });
}

app.whenReady().then(async () => {
  try {
    appendLog("App ready");
    if (process.platform === "win32") {
      app.setAppUserModelId("com.steamtools.allinone");
    }
    startBackend();
    await waitForBackendReady();
    createWindow();
    setTimeout(() => {
      ensureWindowsIntegrations().catch((error) => {
        appendLog(`integration-error: ${error?.stack || error}`);
        console.error("Failed to configure Windows integrations:", error);
      });
    }, 1200);
  } catch (error) {
    appendLog(`startup-error: ${error?.stack || error}`);
    console.error(error);
    stopBackend();
    app.quit();
    return;
  }

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  appendLog("window-all-closed");
  if (process.platform !== "darwin") {
    shutdownApp();
  }
});

app.on("before-quit", (event) => {
  if (isQuitting) {
    return;
  }
  event.preventDefault();
  shutdownApp();
});

process.on("uncaughtException", (error) => {
  appendLog(`uncaughtException: ${error?.stack || error}`);
});

process.on("unhandledRejection", (reason) => {
  appendLog(`unhandledRejection: ${reason?.stack || reason}`);
});
