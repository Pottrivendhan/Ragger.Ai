/**
 * Electron Main Process Entry Point.
 */

import { app, BrowserWindow, Menu } from 'electron';
import path from 'path';
import fs from 'fs';
import { PythonProcessSupervisor } from './supervisor';
import { registerEngineIpcHandlers } from './ipc/engineHandler';
import { registerIngestionIpcHandlers } from './ipc/ingestionHandler';
import { registerAnalysisIpcHandlers } from './ipc/analysisHandler';
import { registerRecommendationIpcHandlers } from './ipc/recommendationHandler';
import { registerBuilderIpcHandlers } from './ipc/builderHandler';
import { registerRetrievalIpcHandlers } from './ipc/retrievalHandler';
import { registerChatIpcHandlers } from './ipc/chatHandler';
import { registerEvaluationIpcHandlers } from './ipc/evaluationHandler';
import { registerModelsIpcHandlers } from './ipc/modelsHandler';

let mainWindow: BrowserWindow | null = null;
const supervisor = new PythonProcessSupervisor();

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1080,
    height: 720,
    minWidth: 800,
    minHeight: 600,
    title: 'Ragger.ai — Runtime Diagnostics',
    backgroundColor: '#F8FAFC',
    show: false,
    autoHideMenuBar: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      preload: path.join(__dirname, '../preload/index.js'),
    },
  });

  // Remove native window menu on Windows / Linux
  mainWindow.setMenu(null);

  // Relay supervisor state changes to renderer window
  supervisor.onStateChange((status) => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('engine:status-change', status);
    }
  });

  mainWindow.once('ready-to-show', () => {
    mainWindow?.show();
  });

  // Open external links in default browser
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    require('electron').shell.openExternal(url);
    return { action: 'deny' };
  });

  // Load URL based on environment
  const isDev = !app.isPackaged && process.env.NODE_ENV !== 'production';

  if (isDev) {
    const devServerUrl = process.env.VITE_DEV_SERVER_URL || 'http://127.0.0.1:5173';
    console.log(`[Electron] Loading Vite dev server at ${devServerUrl}`);
    
    // Retry loading in case Vite is still booting
    let attempts = 0;
    const maxAttempts = 20;
    while (attempts < maxAttempts) {
      try {
        await mainWindow.loadURL(devServerUrl);
        break;
      } catch (err) {
        attempts++;
        if (attempts >= maxAttempts) {
          console.error(`[Electron] Failed to connect to Vite dev server after ${maxAttempts} attempts:`, err);
        } else {
          await new Promise((res) => setTimeout(res, 500));
        }
      }
    }
  } else {
    // Production Mode: load compiled static assets
    let prodHtml = path.join(__dirname, '../../../frontend/dist/index.html');
    if (app.isPackaged) {
      const packagedHtml = path.join(process.resourcesPath, 'frontend/dist/index.html');
      if (fs.existsSync(packagedHtml)) {
        prodHtml = packagedHtml;
      }
    }
    await mainWindow.loadFile(prodHtml);
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// Ensure single-instance lock
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(async () => {
    // Remove the default application menu bar (File, Edit, View, Window)
    Menu.setApplicationMenu(null);

    console.log('[Electron] App ready. Initializing Python Engine Supervisor...');

    // Register IPC handlers before starting UI
    registerEngineIpcHandlers(supervisor);
    registerIngestionIpcHandlers(supervisor);
    registerAnalysisIpcHandlers(supervisor);
    registerRecommendationIpcHandlers(supervisor);
    registerBuilderIpcHandlers(supervisor);
    registerRetrievalIpcHandlers(supervisor);
    registerChatIpcHandlers(supervisor);
    registerEvaluationIpcHandlers(supervisor);
    registerModelsIpcHandlers(supervisor);

    if (process.argv.includes('--check-packaged-smoke')) {
      console.log('[SmokeTest] Running packaged smoke test...');
      try {
        const status = await supervisor.start();
        console.log(`[SmokeTest] Supervisor started: port=${status.port}, pid=${status.pid}, auth=${status.authenticated}`);
        const health = await supervisor.getHealth();
        console.log(`[SmokeTest] Health check result: status=${health.status}, pid=${health.process_id}`);
        console.log('[SmokeTest] Stopping supervisor...');
        await supervisor.stop();
        console.log('[SmokeTest] Clean shutdown completed successfully.');
        app.exit(0);
        return;
      } catch (err: any) {
        console.error('[SmokeTest] Smoke test failed:', err);
        try { await supervisor.stop(); } catch {}
        app.exit(1);
        return;
      }
    }

    try {
      // Start Python engine
      await supervisor.start();
    } catch (err) {
      console.error('[Electron] Failed to start Python engine on launch:', err);
      // Window will still open to show the diagnostic error state to developer
    }

    await createWindow();

    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) {
        createWindow();
      }
    });
  });
}

// Clean up child processes on shutdown
let isQuitting = false;

app.on('before-quit', async (event) => {
  if (!isQuitting) {
    event.preventDefault();
    isQuitting = true;
    console.log('[Electron] Initiating graceful shutdown of Python Engine...');
    try {
      await supervisor.stop();
    } catch (err) {
      console.error('[Electron] Error during supervisor shutdown:', err);
    }
    app.quit();
  }
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
