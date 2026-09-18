import axios, { type InternalAxiosRequestConfig } from 'axios';
import { apiClient } from '../../../api/client';

// Reuse the app API configuration; keep session effects scoped to Inventory.
export const inventoryApiClient = axios.create({ baseURL: apiClient.defaults.baseURL, timeout: apiClient.defaults.timeout, headers: { Accept: 'application/json' } });
type InventoryRequest = InternalAxiosRequestConfig & { inventorySessionRevision?: number; inventoryOriginPath?: string | null };
let accessToken: string | null = null;
let sessionRevision = 0;
let originPath: string | null = null;
const listeners = new Set<(status: 401 | 403, requestPath: string | null) => void>();
export function setInventoryCredential(token: string | null) { accessToken = token; sessionRevision += 1; }
// Router state supplies this value so browser and memory routers behave alike.
export function setInventoryRequestLocation(path: string | null) { originPath = path; }
export function onInventoryAuthorizationFailure(listener: (status: 401 | 403, requestPath: string | null) => void) { listeners.add(listener); return () => { listeners.delete(listener); }; }
inventoryApiClient.interceptors.request.use(config => {
  (config as InventoryRequest).inventorySessionRevision = sessionRevision;
  (config as InventoryRequest).inventoryOriginPath = originPath;
  const inventoryPath = /^\/api\/v1\/(?:inventory|purchasing|recipes)(?:\/|$)/.test(config.url ?? '');
  if (accessToken && inventoryPath) config.headers.set('Authorization', `Bearer ${accessToken}`);
  return config;
});
inventoryApiClient.interceptors.response.use(response => response, (error: unknown) => {
  if (axios.isAxiosError(error)) {
    const status = error.response?.status;
    const config = error.config as InventoryRequest | undefined;
    if ((status === 401 || status === 403) && config?.inventorySessionRevision === sessionRevision) {
      listeners.forEach(listener => listener(status, config.inventoryOriginPath ?? null));
    }
  }
  return Promise.reject(error);
});
