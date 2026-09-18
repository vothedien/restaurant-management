import type { ApiResponse } from "../../../api/client";
import { inventoryApiClient as apiClient } from '../auth/transport';

export type Params = Record<string, string | number | boolean | null | undefined>;
const pathOf = (path: string) => path.startsWith("/api/") ? path : `/api/v1${path}`;
export async function get<T>(path: string, params?: Params, signal?: AbortSignal): Promise<T> {
  const response = await apiClient.get<ApiResponse<T>>(pathOf(path), { params, signal });
  return response.data.data;
}
export async function post<T>(path: string, body?: unknown): Promise<T> {
  return (await apiClient.post<ApiResponse<T>>(pathOf(path), body)).data.data;
}
export async function patch<T>(path: string, body: unknown): Promise<T> {
  return (await apiClient.patch<ApiResponse<T>>(pathOf(path), body)).data.data;
}
export async function put<T>(path: string, body: unknown): Promise<T> {
  return (await apiClient.put<ApiResponse<T>>(pathOf(path), body)).data.data;
}
export async function del<T = void>(path: string): Promise<T> {
  return (await apiClient.delete<ApiResponse<T>>(pathOf(path))).data.data;
}
