import React, { useState } from 'react';
import { Sidebar, ActiveNavTab } from './components/Sidebar';
import { LandingView } from './views/LandingView';
import { AuthView } from './views/AuthView';
import { DashboardView } from './views/DashboardView';
import { StudioView } from './views/StudioView';
import { KnowledgeBasesView } from './views/KnowledgeBasesView';
import { AgentView } from './views/AgentView';
import { ModelHubView } from './views/ModelHubView';
import { SettingsView } from './views/SettingsView';
import { SourceDrawer } from './components/SourceDrawer';
import { ExportImportModal } from './components/ExportImportModal';

import { localAuth, AuthSession } from '../services/localAuth';
import { IngestionClient } from '../services/ingestionClient';
import { AnalysisClient } from '../services/analysisClient';
import { RecommendationClient } from '../services/recommendationClient';
import { BuilderClient } from '../services/builderClient';
import { ChatClient } from '../services/chatClient';
import { ModelsClient } from '../services/modelsClient';
import { MessageCitation } from '../types/chat';

import { LogoutConfirmationModal } from './components/LogoutConfirmationModal';

// Singleton client instances
const ingestionClient = new IngestionClient();
const analysisClient = new AnalysisClient();
const recommendationClient = new RecommendationClient();
const builderClient = new BuilderClient();
const chatClient = new ChatClient();
const modelsClient = new ModelsClient();

export type AppViewMode = 'landing' | 'auth' | 'app';

export const App: React.FC = () => {
  const [session, setSession] = useState<AuthSession | null>(() => {
    // If a session exists in local storage, keep it
    return localAuth.getSession();
  });

  const [viewMode, setViewMode] = useState<AppViewMode>(() => {
    const existing = localAuth.getSession();
    return existing ? 'app' : 'landing';
  });

  const [authInitialMode, setAuthInitialMode] = useState<'login' | 'signup'>('signup');
  const [activeTab, setActiveTab] = useState<ActiveNavTab>('home');
  const [selectedRagId, setSelectedRagId] = useState<string | null>(null);
  const [selectedCitation, setSelectedCitation] = useState<MessageCitation | null>(null);
  const [studioTargetRagId, setStudioTargetRagId] = useState<string | undefined>(undefined);

  const [isExportModalOpen, setIsExportModalOpen] = useState(false);
  const [exportKbTitle, setExportKbTitle] = useState('Product Docs');
  const [isLogoutModalOpen, setIsLogoutModalOpen] = useState(false);
  const [settingsSection, setSettingsSection] = useState<'account' | 'security' | 'storage' | 'about'>('account');

  const handleGetStarted = () => {
    setAuthInitialMode('signup');
    setViewMode('auth');
  };

  const handleSignIn = () => {
    setAuthInitialMode('login');
    setViewMode('auth');
  };

  const handleAuthenticated = () => {
    const s = localAuth.getSession();
    setSession(s);
    setViewMode('app');
    setActiveTab('home');
  };

  const handleConfirmLogout = () => {
    setIsLogoutModalOpen(false);
    localAuth.logout();
    setSession(null);
    setSelectedRagId(null);
    setSelectedCitation(null);
    setStudioTargetRagId(undefined);
    setActiveTab('home');
    setViewMode('landing');
  };

  return (
    <>
      {/* Sarvam AI Subtle Animated Ambient Background */}
      <div className="ambient-background">
        <div className="ambient-orb ambient-orb-1" />
        <div className="ambient-orb ambient-orb-2" />
        <div className="ambient-orb ambient-orb-3" />
      </div>

      {/* 01: LANDING VIEW */}
      {viewMode === 'landing' && (
        <LandingView
          onGetStarted={handleGetStarted}
          onSignIn={handleSignIn}
        />
      )}

      {/* 02: AUTH VIEW (Sign Up / Log In / First Launch) */}
      {viewMode === 'auth' && (
        <AuthView
          initialMode={authInitialMode}
          onAuthenticated={handleAuthenticated}
          modelsClient={modelsClient}
        />
      )}

      {/* 03+: AUTHENTICATED APP WORKSPACE */}
      {viewMode === 'app' && (
        <div className="app-shell">
          <Sidebar
            activeTab={activeTab}
            onSelectTab={(tab, section) => {
              if (tab === 'agent') {
                setSelectedRagId(null);
              }
              if (section) {
                setSettingsSection(section);
              }
              setActiveTab(tab);
            }}
            session={session}
            onRequestLogout={() => setIsLogoutModalOpen(true)}
          />

          <main className="app-main">
            {/* Dashboard / Home */}
            {activeTab === 'home' && (
              <DashboardView
                session={session}
                onCreateRag={() => setActiveTab('studio')}
                onOpenKnowledgeBase={(id) => {
                  setSelectedRagId(id);
                  setActiveTab('agent');
                }}
                onOpenAgent={(id) => {
                  setSelectedRagId(id || null);
                  setActiveTab('agent');
                }}
                onNavigateToSettings={(section) => {
                  setSettingsSection(section || 'account');
                  setActiveTab('settings');
                }}
                onNavigateToLibrary={() => setActiveTab('kb')}
                onRequestLogout={() => setIsLogoutModalOpen(true)}
              />
            )}

            {/* Knowledge Studio (Upload -> Analyze -> Recommend -> Build -> Ready) */}
            {activeTab === 'studio' && (
              <StudioView
                initialStep="upload"
                targetRagId={studioTargetRagId}
                ingestionClient={ingestionClient}
                analysisClient={analysisClient}
                recommendationClient={recommendationClient}
                builderClient={builderClient}
                onGoToChat={(id) => {
                  setSelectedRagId(id || null);
                  setActiveTab('agent');
                }}
                onExportRagger={(title) => {
                  setExportKbTitle(title);
                  setIsExportModalOpen(true);
                }}
                onBackToHome={() => setActiveTab('home')}
              />
            )}

            {/* RAG Library (Discovered builds, index inspection) */}
            {activeTab === 'kb' && (
              <KnowledgeBasesView
                onOpenChat={(ragId) => {
                  setSelectedRagId(ragId);
                  setActiveTab('agent');
                }}
                onExportRagger={(title) => {
                  setExportKbTitle(title);
                  setIsExportModalOpen(true);
                }}
                onCreateNew={() => {
                  setStudioTargetRagId(undefined);
                  setActiveTab('studio');
                }}
                onBuildNewVersion={(ragId) => {
                  setStudioTargetRagId(ragId);
                  setActiveTab('studio');
                }}
              />
            )}

            {/* AI Agent / Chat */}
            {activeTab === 'agent' && (
              <AgentView
                chatClient={chatClient}
                selectedRagId={selectedRagId}
                onOpenCitation={setSelectedCitation}
                onNavigateToModels={() => setActiveTab('models')}
                onNavigateToStudio={() => {
                  setStudioTargetRagId(undefined);
                  setActiveTab('studio');
                }}
                onNavigateToLibrary={() => setActiveTab('kb')}
              />
            )}

            {/* Model Hub */}
            {activeTab === 'models' && (
              <ModelHubView
                modelsClient={modelsClient}
                onBackToHome={() => setActiveTab('home')}
              />
            )}

            {/* Settings */}
            {activeTab === 'settings' && (
              <SettingsView
                key={settingsSection}
                session={session}
                initialSection={settingsSection}
              />
            )}
          </main>

          {/* Interactive Slide-Out Source Drawer */}
          <SourceDrawer
            citation={selectedCitation}
            onClose={() => setSelectedCitation(null)}
          />

          {/* Portable .ragger Package Export/Import Modal */}
          <ExportImportModal
            isOpen={isExportModalOpen}
            onClose={() => setIsExportModalOpen(false)}
            kbTitle={exportKbTitle}
          />

          {/* Explicit Sign Out Confirmation Modal */}
          <LogoutConfirmationModal
            isOpen={isLogoutModalOpen}
            onClose={() => setIsLogoutModalOpen(false)}
            onConfirmLogout={handleConfirmLogout}
            username={session?.username || session?.fullName || 'User'}
          />
        </div>
      )}
    </>
  );
};
