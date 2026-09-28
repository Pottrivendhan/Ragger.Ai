import React, { useState } from 'react';
import {
  Key,
  Copy,
  Check,
  ArrowRight,
  User,
  Mail,
  Lock,
  Eye,
} from 'lucide-react';
import { localAuth } from '../../services/localAuth';
import { ModelsClient } from '../../services/modelsClient';
import { SetupWorkspaceView } from './SetupWorkspaceView';
import raggerBoxLogo from '../../assets/ragger.ai_box_logo.png';
import raggerFullLogo from '../../assets/ragger.ai_full_logo.png';

type AuthMode = 'login' | 'signup' | 'recovery_display' | 'forgot_password' | 'first_launch';

interface AuthViewProps {
  initialMode?: 'login' | 'signup';
  onAuthenticated: () => void;
  modelsClient?: ModelsClient;
}

export const AuthView: React.FC<AuthViewProps> = ({
  initialMode = 'signup',
  onAuthenticated,
  modelsClient,
}) => {
  const [mode, setMode] = useState<AuthMode>(initialMode);

  // Form states - initially empty, zero demo credentials
  const [fullName, setFullName] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [agreeTerms, setAgreeTerms] = useState(true);
  const [recoveryCode, setRecoveryCode] = useState('');
  const [inputRecoveryCode, setInputRecoveryCode] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [errorMsg, setErrorMsg] = useState('');
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSignUp = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg('');
    if (!fullName.trim() || !username.trim() || !password) {
      setErrorMsg('Please fill in all required fields.');
      return;
    }

    setLoading(true);
    try {
      const { recoveryCode: code } = await localAuth.createAccount(
        fullName.trim(),
        username.trim(),
        password
      );
      setRecoveryCode(code);
      setMode('recovery_display');
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to create account.');
    } finally {
      setLoading(false);
    }
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg('');
    if (!username.trim() || !password) {
      setErrorMsg('Please enter your username and password.');
      return;
    }

    setLoading(true);
    try {
      const ok = await localAuth.login(username.trim(), password);
      if (ok) {
        const acc = localAuth.getAccount();
        if (acc && !acc.hasCompletedFirstLaunch) {
          setMode('first_launch');
        } else {
          onAuthenticated();
        }
      } else {
        setErrorMsg('Invalid username or password.');
      }
    } catch {
      setErrorMsg('Login failed.');
    } finally {
      setLoading(false);
    }
  };

  const handleResetPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg('');
    if (!inputRecoveryCode.trim() || !newPassword) {
      setErrorMsg('Please enter your recovery code and new password.');
      return;
    }

    setLoading(true);
    try {
      const ok = await localAuth.resetPasswordWithRecovery(inputRecoveryCode.trim(), newPassword);
      if (ok) {
        alert('Password updated successfully. You may now log in.');
        setMode('login');
      } else {
        setErrorMsg('Invalid recovery code.');
      }
    } catch {
      setErrorMsg('Error updating password.');
    } finally {
      setLoading(false);
    }
  };

  const handleFinishFirstLaunch = () => {
    localAuth.completeFirstLaunch();
    onAuthenticated();
  };

  return (
    <div
      style={{
        height: '100%',
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 24,
        overflowY: 'auto',
        overflowX: 'hidden',
      }}
    >
      {/* SIGN UP: Exact Split Card (Panel 2 Reference) */}
      {mode === 'signup' && (
        <div
          className="glass-card"
          style={{
            display: 'flex',
            width: '100%',
            maxWidth: 880,
            padding: 0,
            overflow: 'hidden',
            borderRadius: 24,
            border: '1px solid rgba(15, 23, 42, 0.08)',
            boxShadow: '0 20px 60px -12px rgba(15, 23, 42, 0.12)',
          }}
        >
          {/* Left Column: Organic Waves + Stepper */}
          <div
            style={{
              flex: '1 1 45%',
              background: 'linear-gradient(145deg, #EFF6FF 0%, #EDE9FE 50%, #F1F5F9 100%)',
              padding: '48px 36px',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              borderRight: '1px solid rgba(15, 23, 42, 0.06)',
            }}
          >
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 36 }}>
                <img
                  src={raggerBoxLogo}
                  alt="Ragger Logo"
                  style={{ width: 32, height: 32, borderRadius: 8, objectFit: 'contain' }}
                />
                <img
                  src={raggerFullLogo}
                  alt="Ragger.ai"
                  style={{ height: 26, objectFit: 'contain' }}
                />
              </div>

              <h2 style={{ fontSize: 24, fontWeight: 800, color: '#0F172A', letterSpacing: '-0.02em', marginBottom: 10 }}>
                Create your account
              </h2>
              <p style={{ fontSize: 13, color: '#64748B', lineHeight: 1.5, marginBottom: 40 }}>
                Start building intelligent knowledge systems in minutes.
              </p>

              {/* Numbered Stepper */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                  <div
                    style={{
                      width: 28,
                      height: 28,
                      borderRadius: '50%',
                      background: '#0F172A',
                      color: '#FFFFFF',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: 12,
                      fontWeight: 700,
                    }}
                  >
                    1
                  </div>
                  <span style={{ fontSize: 13, fontWeight: 700, color: '#0F172A' }}>
                    Create Account
                  </span>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                  <div
                    style={{
                      width: 28,
                      height: 28,
                      borderRadius: '50%',
                      background: '#E2E8F0',
                      color: '#64748B',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: 12,
                      fontWeight: 600,
                    }}
                  >
                    2
                  </div>
                  <span style={{ fontSize: 13, fontWeight: 500, color: '#64748B' }}>
                    Setup Workspace
                  </span>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                  <div
                    style={{
                      width: 28,
                      height: 28,
                      borderRadius: '50%',
                      background: '#E2E8F0',
                      color: '#64748B',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: 12,
                      fontWeight: 600,
                    }}
                  >
                    3
                  </div>
                  <span style={{ fontSize: 13, fontWeight: 500, color: '#64748B' }}>
                    Build Your First RAG
                  </span>
                </div>
              </div>
            </div>

            <div style={{ fontSize: 11, color: '#94A3B8' }}>
              Local-first · Zero cloud transmission
            </div>
          </div>

          {/* Right Column: Form Fields */}
          <div
            style={{
              flex: '1 1 55%',
              background: '#FFFFFF',
              padding: '48px 40px',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'center',
            }}
          >
            <h3 style={{ fontSize: 22, fontWeight: 800, color: '#0F172A', marginBottom: 6 }}>
              Welcome to Ragger.ai
            </h3>
            <p style={{ fontSize: 13, color: '#64748B', marginBottom: 28 }}>
              A smarter way to work with your data.
            </p>

            {errorMsg && (
              <div style={{ padding: '8px 12px', borderRadius: 8, background: '#FEF2F2', color: '#DC2626', fontSize: 12, marginBottom: 16 }}>
                {errorMsg}
              </div>
            )}

            <form onSubmit={handleSignUp} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div>
                <label style={{ fontSize: 12, fontWeight: 600, color: '#475569', display: 'block', marginBottom: 6 }}>
                  Full name
                </label>
                <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                  <User size={15} color="#94A3B8" style={{ position: 'absolute', left: 14 }} />
                  <input
                    type="text"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    placeholder="Enter your name"
                    style={{
                      width: '100%',
                      padding: '10px 14px 10px 38px',
                      borderRadius: 10,
                      border: '1px solid #E2E8F0',
                      fontSize: 13,
                      outline: 'none',
                    }}
                    required
                  />
                </div>
              </div>

              <div>
                <label style={{ fontSize: 12, fontWeight: 600, color: '#475569', display: 'block', marginBottom: 6 }}>
                  Business email
                </label>
                <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                  <Mail size={15} color="#94A3B8" style={{ position: 'absolute', left: 14 }} />
                  <input
                    type="text"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    placeholder="Enter your email"
                    style={{
                      width: '100%',
                      padding: '10px 14px 10px 38px',
                      borderRadius: 10,
                      border: '1px solid #E2E8F0',
                      fontSize: 13,
                      outline: 'none',
                    }}
                    required
                  />
                </div>
              </div>

              <div>
                <label style={{ fontSize: 12, fontWeight: 600, color: '#475569', display: 'block', marginBottom: 6 }}>
                  Password
                </label>
                <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                  <Lock size={15} color="#94A3B8" style={{ position: 'absolute', left: 14 }} />
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Enter your password"
                    style={{
                      width: '100%',
                      padding: '10px 38px 10px 38px',
                      borderRadius: 10,
                      border: '1px solid #E2E8F0',
                      fontSize: 13,
                      outline: 'none',
                    }}
                    required
                  />
                  <Eye size={15} color="#94A3B8" style={{ position: 'absolute', right: 14, cursor: 'pointer' }} />
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
                <input
                  type="checkbox"
                  id="agreeTerms"
                  checked={agreeTerms}
                  onChange={(e) => setAgreeTerms(e.target.checked)}
                  style={{ accentColor: '#0F172A', cursor: 'pointer' }}
                />
                <label htmlFor="agreeTerms" style={{ fontSize: 12, color: '#64748B', cursor: 'pointer' }}>
                  I agree to the <span style={{ color: '#0F172A', fontWeight: 600 }}>Terms</span> and <span style={{ color: '#0F172A', fontWeight: 600 }}>Privacy Policy</span>
                </label>
              </div>

              <button
                type="submit"
                disabled={loading || !agreeTerms}
                className="btn-primary"
                style={{ width: '100%', padding: '12px', marginTop: 10, borderRadius: 9999 }}
              >
                <span>{loading ? 'Creating...' : 'Create Account'}</span>
                <ArrowRight size={15} />
              </button>
            </form>

            <div style={{ textAlign: 'center', marginTop: 20, fontSize: 12, color: '#64748B' }}>
              Already have an account?{' '}
              <button
                onClick={() => { setErrorMsg(''); setMode('login'); }}
                style={{ color: '#0F172A', fontWeight: 700 }}
              >
                Sign in
              </button>
            </div>
          </div>
        </div>
      )}

      {/* LOGIN CARD */}
      {mode === 'login' && (
        <div
          className="glass-card"
          style={{
            width: '100%',
            maxWidth: 440,
            padding: '40px 36px',
            borderRadius: 20,
            background: '#FFFFFF',
            boxShadow: '0 20px 50px -10px rgba(15, 23, 42, 0.1)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 24 }}>
            <img
              src={raggerBoxLogo}
              alt="Ragger Logo"
              style={{ width: 32, height: 32, borderRadius: 8, objectFit: 'contain' }}
            />
            <img
              src={raggerFullLogo}
              alt="Ragger.ai"
              style={{ height: 26, objectFit: 'contain' }}
            />
          </div>

          <h2 style={{ fontSize: 22, fontWeight: 800, color: '#0F172A', marginBottom: 6 }}>
            Welcome back.
          </h2>
          <p style={{ fontSize: 13, color: '#64748B', marginBottom: 24 }}>
            Continue working with your knowledge.
          </p>

          {errorMsg && (
            <div style={{ padding: '8px 12px', borderRadius: 8, background: '#FEF2F2', color: '#DC2626', fontSize: 12, marginBottom: 16 }}>
              {errorMsg}
            </div>
          )}

          <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div>
              <label style={{ fontSize: 12, fontWeight: 600, color: '#475569', display: 'block', marginBottom: 6 }}>
                Username / Email
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Enter your email or username"
                style={{ width: '100%', padding: '10px 14px', borderRadius: 10, border: '1px solid #E2E8F0', fontSize: 13 }}
                required
              />
            </div>

            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                <label style={{ fontSize: 12, fontWeight: 600, color: '#475569' }}>Password</label>
                <button
                  type="button"
                  onClick={() => setMode('forgot_password')}
                  style={{ fontSize: 11, color: '#4F46E5', fontWeight: 600 }}
                >
                  Forgot password?
                </button>
              </div>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter your password"
                style={{ width: '100%', padding: '10px 14px', borderRadius: 10, border: '1px solid #E2E8F0', fontSize: 13 }}
                required
              />
            </div>

            <button type="submit" disabled={loading} className="btn-primary" style={{ width: '100%', padding: '12px', marginTop: 8 }}>
              <span>{loading ? 'Signing in...' : 'Sign in'}</span>
              <ArrowRight size={15} />
            </button>
          </form>

          <div style={{ textAlign: 'center', marginTop: 20, fontSize: 12, color: '#64748B' }}>
            Don't have an account?{' '}
            <button
              onClick={() => { setErrorMsg(''); setMode('signup'); }}
              style={{ color: '#0F172A', fontWeight: 700 }}
            >
              Create account
            </button>
          </div>
        </div>
      )}

      {/* FORGOT PASSWORD SCREEN */}
      {mode === 'forgot_password' && (
        <div
          className="glass-card"
          style={{
            width: '100%',
            maxWidth: 440,
            padding: '40px 36px',
            borderRadius: 20,
            background: '#FFFFFF',
          }}
        >
          <h2 style={{ fontSize: 22, fontWeight: 800, color: '#0F172A', marginBottom: 6 }}>
            Recover account
          </h2>
          <p style={{ fontSize: 13, color: '#64748B', marginBottom: 20 }}>
            Enter your 16-character offline recovery code and a new password.
          </p>

          {errorMsg && (
            <div style={{ padding: '8px 12px', borderRadius: 8, background: '#FEF2F2', color: '#DC2626', fontSize: 12, marginBottom: 16 }}>
              {errorMsg}
            </div>
          )}

          <form onSubmit={handleResetPassword} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div>
              <label style={{ fontSize: 12, fontWeight: 600, color: '#475569', display: 'block', marginBottom: 6 }}>
                Recovery Code
              </label>
              <input
                type="text"
                value={inputRecoveryCode}
                onChange={(e) => setInputRecoveryCode(e.target.value)}
                placeholder="XXXX-XXXX-XXXX-XXXX"
                style={{ width: '100%', padding: '10px 14px', borderRadius: 10, border: '1px solid #E2E8F0', fontSize: 13, fontFamily: 'monospace' }}
                required
              />
            </div>

            <div>
              <label style={{ fontSize: 12, fontWeight: 600, color: '#475569', display: 'block', marginBottom: 6 }}>
                New Password
              </label>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                style={{ width: '100%', padding: '10px 14px', borderRadius: 10, border: '1px solid #E2E8F0', fontSize: 13 }}
                required
              />
            </div>

            <button type="submit" disabled={loading} className="btn-primary" style={{ width: '100%', padding: '12px', marginTop: 8 }}>
              <span>Update Password</span>
            </button>
          </form>

          <div style={{ textAlign: 'center', marginTop: 20 }}>
            <button
              onClick={() => setMode('login')}
              style={{ fontSize: 12, color: '#4F46E5', fontWeight: 600 }}
            >
              Back to Sign in
            </button>
          </div>
        </div>
      )}

      {/* RECOVERY CODE DISPLAY */}
      {mode === 'recovery_display' && (
        <div
          className="glass-card"
          style={{
            width: '100%',
            maxWidth: 480,
            padding: '40px 36px',
            borderRadius: 20,
            background: '#FFFFFF',
            textAlign: 'center',
          }}
        >
          <div style={{ width: 48, height: 48, borderRadius: 12, background: 'rgba(79, 70, 229, 0.08)', color: '#4F46E5', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px' }}>
            <Key size={24} />
          </div>

          <h2 style={{ fontSize: 22, fontWeight: 800, color: '#0F172A', marginBottom: 8 }}>
            Save your recovery code
          </h2>
          <p style={{ fontSize: 13, color: '#64748B', lineHeight: 1.5, marginBottom: 24 }}>
            This 16-character code works 100% offline and is required to recover your account if you forget your password.
          </p>

          <div
            style={{
              background: '#F8FAFC',
              border: '1.5px dashed #CBD5E1',
              borderRadius: 12,
              padding: '16px 20px',
              fontSize: 20,
              fontWeight: 800,
              letterSpacing: '0.12em',
              color: '#0F172A',
              fontFamily: 'monospace',
              marginBottom: 20,
              userSelect: 'all',
            }}
          >
            {recoveryCode || 'A4F9-892B-C012-78E4'}
          </div>

          <div style={{ display: 'flex', gap: 12, marginBottom: 24 }}>
            <button
              onClick={() => {
                navigator.clipboard.writeText(recoveryCode);
                setCopied(true);
                setTimeout(() => setCopied(false), 2000);
              }}
              className="btn-secondary"
              style={{ flex: 1, padding: 10 }}
            >
              {copied ? <Check size={14} color="#10B981" /> : <Copy size={14} />}
              <span>{copied ? 'Copied' : 'Copy Code'}</span>
            </button>

            <button
              onClick={() => {
                const element = document.createElement('a');
                const file = new Blob([`RAGGER.AI OFFLINE RECOVERY CODE\n\nCode: ${recoveryCode}\nDate: ${new Date().toISOString()}\n\nKeep this file safely stored offline.`], { type: 'text/plain' });
                element.href = URL.createObjectURL(file);
                element.download = 'ragger_recovery_code.txt';
                document.body.appendChild(element);
                element.click();
                document.body.removeChild(element);
              }}
              className="btn-secondary"
              style={{ flex: 1, padding: 10 }}
            >
              <span>Save as File</span>
            </button>
          </div>

          <button
            onClick={() => setMode('first_launch')}
            className="btn-primary"
            style={{ width: '100%', padding: '12px' }}
          >
            <span>I've saved my recovery code</span>
            <ArrowRight size={15} />
          </button>
        </div>
      )}

      {/* FIRST LAUNCH: SETUP WORKSPACE (LOCAL AI MODEL PREPARATION) */}
      {mode === 'first_launch' && (
        <SetupWorkspaceView
          onComplete={handleFinishFirstLaunch}
          modelsClient={modelsClient}
        />
      )}
    </div>
  );
};
