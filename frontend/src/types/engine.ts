/**
 * Engine and diagnostic types for the frontend.
 */

export interface AuthenticatedHealthResponse {
  status: string;
  service: string;
  version: string;
  authenticated: boolean;
  process_id: number;
}

export interface RuntimeDiagnosticsResponse {
  python_version: string;
  platform: string;
  engine_version: string;
  process_id: number;
  environment: string;
  host: string;
  port: number;
}

export interface SupervisorStatus {
  is_running: boolean;
  pid: number | null;
  port: number | null;
  host: string;
  authenticated: boolean;
  error: string | null;
  last_health_check: string | null;
}

export interface IPCResult<T> {
  success: boolean;
  data?: T;
  error?: string;
}

declare global {
  interface Window {
    ragger?: {
      engine: {
        getStatus: () => Promise<IPCResult<SupervisorStatus>>;
        getHealth: () => Promise<IPCResult<AuthenticatedHealthResponse>>;
        getRuntime: () => Promise<IPCResult<RuntimeDiagnosticsResponse>>;
        getApiConfig?: () => Promise<IPCResult<{ baseUrl: string | null; token: string | null; host: string; port: number | null }>>;
        restart: () => Promise<IPCResult<SupervisorStatus>>;
        onStatusChange: (callback: (status: SupervisorStatus) => void) => () => void;
      };
      ingestion?: {
        openFileDialog: () => Promise<IPCResult<string[] | string | null>>;
        detectFile: (filePath: string) => Promise<IPCResult<any>>;
        ingestFile: (filePath: string, customId?: string) => Promise<IPCResult<any>>;
        listSources: () => Promise<IPCResult<any[]>>;
      };
      analysis?: {
        analyzeFile: (sourceId: string, provider?: string) => Promise<IPCResult<any>>;
        synthesizeWorkspace: (workspaceId?: string) => Promise<IPCResult<any>>;
        getProfiles: () => Promise<IPCResult<any[]>>;
        getWorkspaceProfile: () => Promise<IPCResult<any | null>>;
        listProviders: () => Promise<IPCResult<any[]>>;
      };
      recommendation?: {
        evaluate: (workspaceId?: string) => Promise<IPCResult<any>>;
        getCurrent: () => Promise<IPCResult<any | null>>;
        listArchitectures: () => Promise<IPCResult<any[]>>;
        approve: (payload: any) => Promise<IPCResult<any>>;
        getApproved: () => Promise<IPCResult<any | null>>;
        validateBuild: () => Promise<IPCResult<any>>;
      };
      builder?: {
        start: () => Promise<IPCResult<{ status: string; build_id: string }>>;
        getProgress: () => Promise<IPCResult<any>>;
        getManifest: () => Promise<IPCResult<any | null>>;
        cancel: (buildId: string) => Promise<IPCResult<{ status: string; build_id: string }>>;
      };
      retrieval?: {
        query: (payload: any) => Promise<IPCResult<any>>;
        getStatus: () => Promise<IPCResult<any>>;
        reload: () => Promise<IPCResult<any>>;
      };
      chat?: {
        generate: (payload: any) => Promise<IPCResult<any>>;
        cancel: (sessionId: string) => Promise<IPCResult<any>>;
        getSessions: () => Promise<IPCResult<any>>;
        getSession: (sessionId: string) => Promise<IPCResult<any>>;
        deleteSession: (sessionId: string) => Promise<IPCResult<any>>;
        getConfig: () => Promise<IPCResult<any>>;
        updateConfig: (config: any) => Promise<IPCResult<any>>;
      };
    };
  }
}

