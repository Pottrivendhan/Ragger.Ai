/**
 * Local-First Offline Authentication & Recovery System for Ragger.ai v1.1.
 * 100% offline — zero cloud authentication server, zero external telemetry.
 * Stores salted SHA-256 hashes locally in browser storage / local file.
 */

export interface LocalAccount {
  accountId: string; // e.g. "acc_a1b2c3d4e5f6"
  fullName: string;
  username: string;
  passwordHash: string;
  salt: string;
  recoveryCodeHash: string;
  createdAt: string;
  updatedAt: string;
  hasCompletedFirstLaunch: boolean;
}

export interface AuthSession {
  isAuthenticated: boolean;
  accountId: string;
  username: string;
  fullName: string;
  loginTime: string;
}

const STORAGE_KEY_ACCOUNTS_MAP = 'ragger_local_accounts_v1';
const STORAGE_KEY_SESSION = 'ragger_local_session_v1';
// Backward compatibility key
const STORAGE_KEY_LEGACY_ACCOUNT = 'ragger_local_account_v1';

async function sha256(data: string): Promise<string> {
  const encoder = new TextEncoder();
  const buffer = await crypto.subtle.digest('SHA-256', encoder.encode(data));
  const hashArray = Array.from(new Uint8Array(buffer));
  return hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');
}

function generateRandomSalt(length = 16): string {
  const array = new Uint8Array(length);
  crypto.getRandomValues(array);
  return Array.from(array, (byte) => byte.toString(16).padStart(2, '0')).join('');
}

function generateAccountId(): string {
  const rand = Array.from(crypto.getRandomValues(new Uint8Array(6)), (b) => b.toString(16).padStart(2, '0')).join('');
  return `acc_${rand}`;
}

/**
 * Generates an offline 16-character recovery code in 4-character blocks:
 * e.g. "A7B9-C3D4-E5F6-G7H8"
 */
export function generateRecoveryCode(): string {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'; // Avoid ambiguous chars like 0/O, 1/I
  const parts: string[] = [];
  for (let p = 0; p < 4; p++) {
    let block = '';
    for (let c = 0; c < 4; c++) {
      const idx = Math.floor(Math.random() * chars.length);
      block += chars[idx];
    }
    parts.push(block);
  }
  return parts.join('-');
}

function loadAccountsMap(): Record<string, LocalAccount> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY_ACCOUNTS_MAP);
    if (raw) {
      return JSON.parse(raw);
    }
    // Check legacy single account migration
    const legacyRaw = localStorage.getItem(STORAGE_KEY_LEGACY_ACCOUNT);
    if (legacyRaw) {
      const legacy = JSON.parse(legacyRaw);
      const accId = legacy.accountId || 'acc_default';
      const migrated: LocalAccount = {
        ...legacy,
        accountId: accId,
      };
      const map: Record<string, LocalAccount> = { [migrated.username.toLowerCase()]: migrated };
      localStorage.setItem(STORAGE_KEY_ACCOUNTS_MAP, JSON.stringify(map));
      return map;
    }
    return {};
  } catch {
    return {};
  }
}

function saveAccountsMap(map: Record<string, LocalAccount>): void {
  try {
    localStorage.setItem(STORAGE_KEY_ACCOUNTS_MAP, JSON.stringify(map));
  } catch (err) {
    console.warn('[localAuth] Failed to persist accounts map:', err);
  }
}

export const localAuth = {
  getAccount(username?: string): LocalAccount | null {
    const map = loadAccountsMap();
    if (username) {
      return map[username.toLowerCase().trim()] || null;
    }
    const session = this.getSession();
    if (session?.username) {
      return map[session.username.toLowerCase().trim()] || null;
    }
    // Fallback: return first account if exists
    const accounts = Object.values(map);
    return accounts.length > 0 ? accounts[0] : null;
  },

  getAccountById(accountId: string): LocalAccount | null {
    const map = loadAccountsMap();
    return Object.values(map).find((a) => a.accountId === accountId) || null;
  },

  hasAccount(): boolean {
    const map = loadAccountsMap();
    return Object.keys(map).length > 0;
  },

  getSession(): AuthSession | null {
    try {
      const raw = localStorage.getItem(STORAGE_KEY_SESSION);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  },

  async createAccount(fullName: string, username: string, password: string): Promise<{ account: LocalAccount; recoveryCode: string }> {
    const cleanUsername = username.toLowerCase().trim();
    const map = loadAccountsMap();
    if (map[cleanUsername]) {
      throw new Error(`An account with username/email "${username}" already exists.`);
    }

    const salt = generateRandomSalt();
    const passwordHash = await sha256(password + ':' + salt);
    const recoveryCode = generateRecoveryCode();
    const recoveryCodeHash = await sha256(recoveryCode.replace(/[^A-Za-z0-9]/g, '').toUpperCase());
    const accountId = generateAccountId();

    const account: LocalAccount = {
      accountId,
      fullName: fullName.trim(),
      username: username.trim(),
      passwordHash,
      salt,
      recoveryCodeHash,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      hasCompletedFirstLaunch: false,
    };

    map[cleanUsername] = account;
    saveAccountsMap(map);
    this.createSession(account.accountId, account.username, account.fullName);
    return { account, recoveryCode };
  },

  async login(username: string, password: string): Promise<boolean> {
    const cleanUsername = username.toLowerCase().trim();
    const map = loadAccountsMap();
    const account = map[cleanUsername];
    if (!account) return false;

    const computedHash = await sha256(password + ':' + account.salt);
    if (computedHash === account.passwordHash) {
      this.createSession(account.accountId, account.username, account.fullName);
      return true;
    }
    return false;
  },

  createSession(accountId: string, username: string, fullName: string): void {
    const session: AuthSession = {
      isAuthenticated: true,
      accountId,
      username,
      fullName,
      loginTime: new Date().toISOString(),
    };
    localStorage.setItem(STORAGE_KEY_SESSION, JSON.stringify(session));
  },

  logout(): void {
    localStorage.removeItem(STORAGE_KEY_SESSION);
  },

  async verifyRecoveryCode(inputCode: string, username?: string): Promise<boolean> {
    const account = this.getAccount(username);
    if (!account) return false;
    const cleanCode = inputCode.replace(/[^A-Za-z0-9]/g, '').toUpperCase();
    const inputHash = await sha256(cleanCode);
    return inputHash === account.recoveryCodeHash;
  },

  async resetPasswordWithRecovery(recoveryCode: string, newPassword: string, username?: string): Promise<boolean> {
    const account = this.getAccount(username);
    if (!account) return false;

    const isValid = await this.verifyRecoveryCode(recoveryCode, username);
    if (!isValid) return false;

    const newSalt = generateRandomSalt();
    const newPasswordHash = await sha256(newPassword + ':' + newSalt);

    account.salt = newSalt;
    account.passwordHash = newPasswordHash;
    account.updatedAt = new Date().toISOString();

    const map = loadAccountsMap();
    map[account.username.toLowerCase().trim()] = account;
    saveAccountsMap(map);
    return true;
  },

  /**
   * Reset local account credentials without deleting knowledge base data.
   */
  resetAccountWithoutDeletingData(): void {
    const session = this.getSession();
    if (session?.username) {
      const map = loadAccountsMap();
      delete map[session.username.toLowerCase().trim()];
      saveAccountsMap(map);
    }
    localStorage.removeItem(STORAGE_KEY_SESSION);
  },

  completeFirstLaunch(): void {
    const account = this.getAccount();
    if (account) {
      account.hasCompletedFirstLaunch = true;
      const map = loadAccountsMap();
      map[account.username.toLowerCase().trim()] = account;
      saveAccountsMap(map);
    }
  },
};
