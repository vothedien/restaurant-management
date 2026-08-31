import axios from "axios";

const apiUrl = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export const apiClient = axios.create({
  baseURL: apiUrl.replace(/\/$/, ""),
  timeout: 10_000,
  headers: { Accept: "application/json" },
});

export interface ApiResponse<T> {
  success: boolean;
  message: string;
  data: T;
}
