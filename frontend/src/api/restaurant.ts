import { apiClient, type ApiResponse } from "./client";

export interface DatabaseHealth {
  status: "ok";
  schema: string;
  table_count: number;
}

export interface DiningTable {
  table_id: number;
  table_code: string;
  table_name: string | null;
  capacity: number;
  status: string;
  created_at: string;
}

export interface Ingredient {
  ingredient_id: number;
  ingredient_code: string;
  ingredient_name: string;
  base_unit_id: number;
  manages_lot: boolean;
  minimum_stock_qty: string;
  safety_stock_qty: string;
  status: string;
}

export async function getDatabaseStatus(): Promise<DatabaseHealth> {
  const response = await apiClient.get<ApiResponse<DatabaseHealth>>("/health/database");
  return response.data.data;
}

export async function getDiningTables(): Promise<DiningTable[]> {
  const response = await apiClient.get<ApiResponse<{ items: DiningTable[] }>>("/api/v1/sales/tables");
  return response.data.data.items;
}

export async function getIngredients(): Promise<Ingredient[]> {
  const response = await apiClient.get<ApiResponse<{ items: Ingredient[] }>>(
    "/api/v1/inventory/ingredients",
  );
  return response.data.data.items;
}
