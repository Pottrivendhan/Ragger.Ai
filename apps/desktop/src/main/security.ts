/**
 * Security utilities for Electron host.
 */

import crypto from 'crypto';

let sessionApiToken: string | null = null;

/**
 * Generates or retrieves the 256-bit cryptographically secure session token.
 * This token is held ONLY in Electron Main process memory and passed to
 * Python via environment variable RAGGER_API_TOKEN.
 * It is NEVER exposed to the React renderer window.
 */
export function getOrCreateSessionToken(): string {
  if (!sessionApiToken) {
    sessionApiToken = crypto.randomBytes(32).toString('hex');
  }
  return sessionApiToken;
}

/**
 * Returns true if a session token has been initialized.
 */
export function hasSessionToken(): boolean {
  return sessionApiToken !== null;
}
