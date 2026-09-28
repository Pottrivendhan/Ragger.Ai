/**
 * Electron Preload Script.
 * Exposes a narrow, secure, strongly-typed API to the renderer process via contextBridge.
 * Strictly adheres to contextIsolation and sandbox constraints.
 */

import { contextBridge, ipcRenderer } from 'electron';

export interface RaggerEngineAPI {
  getStatus: () => Promise<any>;
  getHealth: () => Promise<any>;
  getRuntime: () => Promise<any>;
  getApiConfig: () => Promise<any>;
  restart: () => Promise<any>;
  onStatusChange: (callback: (status: any) => void) => () => void;
}

export interface RaggerIngestionAPI {
  openFileDialog: () => Promise<any>;
  detectFile: (filePath: string) => Promise<any>;
  ingestFile: (filePath: string, customId?: string) => Promise<any>;
  listSources: () => Promise<any>;
}

export interface RaggerAnalysisAPI {
  analyzeFile: (sourceId: string, provider?: string) => Promise<any>;
  synthesizeWorkspace: (workspaceId?: string) => Promise<any>;
  getProfiles: () => Promise<any>;
  getWorkspaceProfile: () => Promise<any>;
  listProviders: () => Promise<any>;
}

export interface RaggerRecommendationAPI {
  evaluate: (workspaceId?: string) => Promise<any>;
  getCurrent: () => Promise<any>;
  listArchitectures: () => Promise<any>;
  approve: (payload: any) => Promise<any>;
  getApproved: () => Promise<any>;
  validateBuild: () => Promise<any>;
}

export interface RaggerBuilderAPI {
  start: () => Promise<any>;
  getProgress: () => Promise<any>;
  getManifest: () => Promise<any>;
  cancel: (buildId: string) => Promise<any>;
}

export interface RaggerRetrievalAPI {
  query: (payload: { query: string; top_k?: number; filters?: any }) => Promise<any>;
  getStatus: () => Promise<any>;
  reload: () => Promise<any>;
}

export interface RaggerChatAPI {
  generate: (payload: any) => Promise<any>;
  cancel: (sessionId: string) => Promise<any>;
  getSessions: () => Promise<any>;
  getSession: (sessionId: string) => Promise<any>;
  deleteSession: (sessionId: string) => Promise<any>;
  getConfig: () => Promise<any>;
  updateConfig: (config: any) => Promise<any>;
}

export interface RaggerEvaluationAPI {
  run: (payload?: any) => Promise<any>;
  getProgress: (evalId: string) => Promise<any>;
  cancel: (evalId: string) => Promise<any>;
  getReports: () => Promise<any>;
  getReport: (evalId: string) => Promise<any>;
  deleteReport: (evalId: string) => Promise<any>;
  getConfig: () => Promise<any>;
  updateConfig: (config: any) => Promise<any>;
}

export interface RaggerModelsAPI {
  getHardware: (refresh?: boolean) => Promise<any>;
  getCatalog: () => Promise<any>;
  getInventory: () => Promise<any>;
  getOllamaStatus: () => Promise<any>;
  download: (modelKey: string) => Promise<any>;
  getProgress: (modelKey: string) => Promise<any>;
  pauseDownload: (modelKey: string) => Promise<any>;
  resumeDownload: (modelKey: string) => Promise<any>;
  cancelDownload: (modelKey: string) => Promise<any>;
  deleteModel: (modelKey: string) => Promise<any>;
  activateModel: (payload: { model_key: string; target_role: string }) => Promise<any>;
}

export interface RaggerWindowAPI {
  engine: RaggerEngineAPI;
  ingestion: RaggerIngestionAPI;
  analysis: RaggerAnalysisAPI;
  recommendation: RaggerRecommendationAPI;
  builder: RaggerBuilderAPI;
  retrieval: RaggerRetrievalAPI;
  chat: RaggerChatAPI;
  evaluation: RaggerEvaluationAPI;
  models: RaggerModelsAPI;
}

const api: RaggerWindowAPI = {
  engine: {
    getStatus: () => ipcRenderer.invoke('engine:get-status'),
    getHealth: () => ipcRenderer.invoke('engine:get-health'),
    getRuntime: () => ipcRenderer.invoke('engine:get-runtime'),
    getApiConfig: () => ipcRenderer.invoke('engine:get-api-config'),
    restart: () => ipcRenderer.invoke('engine:restart'),
    onStatusChange: (callback: (status: any) => void) => {
      const listener = (_event: any, status: any) => callback(status);
      ipcRenderer.on('engine:status-change', listener);
      return () => {
        ipcRenderer.removeListener('engine:status-change', listener);
      };
    },
  },
  ingestion: {
    openFileDialog: () => ipcRenderer.invoke('dialog:open-file'),
    detectFile: (filePath: string) => ipcRenderer.invoke('ingestion:detect', filePath),
    ingestFile: (filePath: string, customId?: string) => ipcRenderer.invoke('ingestion:ingest', filePath, customId),
    listSources: () => ipcRenderer.invoke('ingestion:list-sources'),
  },
  analysis: {
    analyzeFile: (sourceId: string, provider?: string) => ipcRenderer.invoke('analysis:analyze-file', sourceId, provider),
    synthesizeWorkspace: (workspaceId: string = 'default') => ipcRenderer.invoke('analysis:synthesize-workspace', workspaceId),
    getProfiles: () => ipcRenderer.invoke('analysis:get-profiles'),
    getWorkspaceProfile: () => ipcRenderer.invoke('analysis:get-workspace-profile'),
    listProviders: () => ipcRenderer.invoke('analysis:list-providers'),
  },
  recommendation: {
    evaluate: (workspaceId: string = 'default') => ipcRenderer.invoke('recommendation:evaluate', workspaceId),
    getCurrent: () => ipcRenderer.invoke('recommendation:get-current'),
    listArchitectures: () => ipcRenderer.invoke('recommendation:list-architectures'),
    approve: (payload: any) => ipcRenderer.invoke('recommendation:approve', payload),
    getApproved: () => ipcRenderer.invoke('recommendation:get-approved'),
    validateBuild: () => ipcRenderer.invoke('recommendation:validate-build'),
  },
  builder: {
    start: () => ipcRenderer.invoke('builder:start'),
    getProgress: () => ipcRenderer.invoke('builder:get-progress'),
    getManifest: () => ipcRenderer.invoke('builder:get-manifest'),
    cancel: (buildId: string) => ipcRenderer.invoke('builder:cancel', buildId),
  },
  retrieval: {
    query: (payload: { query: string; top_k?: number; filters?: any }) => ipcRenderer.invoke('retrieval:query', payload),
    getStatus: () => ipcRenderer.invoke('retrieval:get-status'),
    reload: () => ipcRenderer.invoke('retrieval:reload'),
  },
  chat: {
    generate: (payload: any) => ipcRenderer.invoke('chat:generate', payload),
    cancel: (sessionId: string) => ipcRenderer.invoke('chat:cancel', sessionId),
    getSessions: () => ipcRenderer.invoke('chat:get-sessions'),
    getSession: (sessionId: string) => ipcRenderer.invoke('chat:get-session', sessionId),
    deleteSession: (sessionId: string) => ipcRenderer.invoke('chat:delete-session', sessionId),
    getConfig: () => ipcRenderer.invoke('chat:get-config'),
    updateConfig: (config: any) => ipcRenderer.invoke('chat:update-config', config),
  },
  evaluation: {
    run: (payload?: any) => ipcRenderer.invoke('evaluation:run', payload),
    getProgress: (evalId: string) => ipcRenderer.invoke('evaluation:progress', evalId),
    cancel: (evalId: string) => ipcRenderer.invoke('evaluation:cancel', evalId),
    getReports: () => ipcRenderer.invoke('evaluation:get-reports'),
    getReport: (evalId: string) => ipcRenderer.invoke('evaluation:get-report', evalId),
    deleteReport: (evalId: string) => ipcRenderer.invoke('evaluation:delete-report', evalId),
    getConfig: () => ipcRenderer.invoke('evaluation:get-config'),
    updateConfig: (config: any) => ipcRenderer.invoke('evaluation:update-config', config),
  },
  models: {
    getHardware: (refresh?: boolean) => ipcRenderer.invoke('models:get-hardware', refresh),
    getCatalog: () => ipcRenderer.invoke('models:get-catalog'),
    getInventory: () => ipcRenderer.invoke('models:get-inventory'),
    getOllamaStatus: () => ipcRenderer.invoke('models:get-ollama-status'),
    download: (modelKey: string) => ipcRenderer.invoke('models:download', modelKey),
    getProgress: (modelKey: string) => ipcRenderer.invoke('models:download-progress', modelKey),
    pauseDownload: (modelKey: string) => ipcRenderer.invoke('models:pause-download', modelKey),
    resumeDownload: (modelKey: string) => ipcRenderer.invoke('models:resume-download', modelKey),
    cancelDownload: (modelKey: string) => ipcRenderer.invoke('models:cancel-download', modelKey),
    deleteModel: (modelKey: string) => ipcRenderer.invoke('models:delete', modelKey),
    activateModel: (payload: { model_key: string; target_role: string }) => ipcRenderer.invoke('models:activate', payload),
  },
};

contextBridge.exposeInMainWorld('ragger', api);
