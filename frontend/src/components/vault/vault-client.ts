import axios from "axios";
import { api } from "@/lib/api";

export interface VaultListItem {
  id: number;
  filename: string;
  content_type: string | null;
  width: number | null;
  height: number | null;
  created_at: string | null;
  hidden_at: string | null;
}

function vaultHeaders(sessionToken: string) {
  return { Authorization: `Bearer ${sessionToken}` };
}

export async function unlockVault(passphrase: string): Promise<string> {
  const response = await api.post<{ session_token: string }>(
    "/api/vault/unlock",
    { passphrase },
  );
  return response.data.session_token;
}

export async function getVaultStatus(): Promise<{
  initialized: boolean;
  recovery_available: boolean;
}> {
  const response = await api.get<{
    initialized: boolean;
    recovery_available: boolean;
  }>("/api/vault/status");
  return response.data;
}

export async function setupVault(
  passphrase: string,
): Promise<{ session_token: string; recovery_code: string }> {
  const response = await api.post<{
    session_token: string;
    recovery_code: string;
  }>("/api/vault/setup", { passphrase });
  return response.data;
}

export async function recoverVault(
  recoveryCode: string,
  newPassphrase: string,
): Promise<{ session_token: string; recovery_code: string }> {
  const response = await api.post<{
    session_token: string;
    recovery_code: string;
  }>("/api/vault/recover", {
    recovery_code: recoveryCode,
    new_passphrase: newPassphrase,
  });
  return response.data;
}

export async function changeVaultPassword(
  currentPassphrase: string,
  newPassphrase: string,
): Promise<{ session_token: string; recovery_code: string }> {
  const response = await api.post<{
    session_token: string;
    recovery_code: string;
  }>("/api/vault/password", {
    current_passphrase: currentPassphrase,
    new_passphrase: newPassphrase,
  });
  return response.data;
}

export async function listVaultItems(
  sessionToken: string,
): Promise<VaultListItem[]> {
  const response = await api.get<VaultListItem[]>("/api/vault/list", {
    headers: vaultHeaders(sessionToken),
  });
  return response.data;
}

export async function lockVaultSession(sessionToken: string): Promise<void> {
  await api.post(
    "/api/vault/lock",
    {},
    { headers: vaultHeaders(sessionToken) },
  );
}

export async function fetchVaultThumbnail(
  mediaId: number,
  sessionToken: string,
): Promise<Blob> {
  const response = await api.get<Blob>(`/api/vault/thumbnail/${mediaId}`, {
    headers: vaultHeaders(sessionToken),
    responseType: "blob",
  });
  return response.data;
}

export async function fetchVaultOriginal(
  mediaId: number,
  sessionToken: string,
): Promise<Blob> {
  const response = await api.get<Blob>(`/api/vault/stream/${mediaId}`, {
    headers: vaultHeaders(sessionToken),
    responseType: "blob",
  });
  return response.data;
}

export async function restoreVaultItem(
  mediaId: number,
  sessionToken: string,
): Promise<void> {
  await api.post(
    "/api/vault/restore",
    { media_id: mediaId },
    { headers: vaultHeaders(sessionToken) },
  );
}

export function isExpiredVaultSession(error: unknown): boolean {
  return axios.isAxiosError(error) && error.response?.status === 401;
}
