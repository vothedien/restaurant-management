import { get, post, patch, put, del } from './http';
import type {
  CatalogPage, Unit, UnitWrite, UnitConversion, ConversionWrite, Ingredient, IngredientWrite,
  Supplier, SupplierWrite, SupplierIngredient, MappingWrite, MappingUpdate, Recipe, RecipeDetail,
  RecipeMetadata, RecipeItemWrite, CatalogBalance,
} from '../types/catalog';

type Params = Record<string, string | number | boolean | undefined>;
type ApiPage<T> = { items: T[]; total: number; limit: number; offset: number };
async function page<T>(path: string, params: Params = {}, signal?: AbortSignal): Promise<CatalogPage<T>> {
  const { page: pageNumber = 1, page_size = 20, ...filters } = params;
  const response = await get<ApiPage<T>>(path, { ...filters, limit: page_size, offset: (Number(pageNumber) - 1) * Number(page_size) }, signal);
  return response;
}

export const catalogApi = {
  units: (params?: Params, signal?: AbortSignal) => page<Unit>('/inventory/units', params, signal),
  saveUnit: (data: UnitWrite, id?: number) => id ? patch<Unit>(`/inventory/units/${id}`, data) : post<Unit>('/inventory/units', data),
  deactivateUnit: (id: number) => del(`/inventory/units/${id}`),
  conversions: (params?: Params, signal?: AbortSignal) => page<UnitConversion>('/inventory/unit-conversions', params, signal),
  saveConversion: (data: ConversionWrite, id?: number) => id ? patch<UnitConversion>(`/inventory/unit-conversions/${id}`, data) : post<UnitConversion>('/inventory/unit-conversions', data),
  deleteConversion: (id: number) => del(`/inventory/unit-conversions/${id}`),
  ingredients: (params?: Params, signal?: AbortSignal) => page<Ingredient>('/inventory/ingredients', params, signal),
  ingredient: (id: number, signal?: AbortSignal) => get<Ingredient>(`/inventory/ingredients/${id}`, undefined, signal),
  saveIngredient: (data: IngredientWrite, id?: number) => id ? patch<Ingredient>(`/inventory/ingredients/${id}`, data) : post<Ingredient>('/inventory/ingredients', data),
  deactivateIngredient: (id: number) => del(`/inventory/ingredients/${id}`),
  suppliers: (params?: Params, signal?: AbortSignal) => page<Supplier>('/purchasing/suppliers', params, signal),
  supplier: (id: number, signal?: AbortSignal) => get<Supplier>(`/purchasing/suppliers/${id}`, undefined, signal),
  saveSupplier: (data: SupplierWrite, id?: number) => id ? patch<Supplier>(`/purchasing/suppliers/${id}`, data) : post<Supplier>('/purchasing/suppliers', data),
  deactivateSupplier: (id: number) => del(`/purchasing/suppliers/${id}`),
  mappings: (params?: Params, signal?: AbortSignal) => page<SupplierIngredient>('/purchasing/supplier-ingredients', params, signal),
  createMapping: (data: MappingWrite) => post<SupplierIngredient>('/purchasing/supplier-ingredients', data),
  updateMapping: (id: number, data: Partial<MappingUpdate>) => patch<SupplierIngredient>(`/purchasing/supplier-ingredients/${id}`, data),
  deactivateMapping: (id: number) => del(`/purchasing/supplier-ingredients/${id}`),
  recipes: (params?: Params, signal?: AbortSignal) => page<Recipe>('/recipes', params, signal),
  recipe: (id: number, signal?: AbortSignal) => get<RecipeDetail>(`/recipes/${id}`, undefined, signal),
  activeRecipe: (dishId: number, signal?: AbortSignal) => get<RecipeDetail>(`/recipes/dishes/${dishId}/active`, undefined, signal),
  createRecipe: (dishId: number, data: RecipeMetadata) => post<RecipeDetail>('/recipes', { dish_id: dishId, ...data }),
  updateRecipe: (id: number, data: RecipeMetadata) => patch<RecipeDetail>(`/recipes/${id}`, data),
  replaceRecipeItems: (id: number, items: RecipeItemWrite[]) => put<RecipeDetail>(`/recipes/${id}/items`, { items }),
  activateRecipe: (id: number) => post<RecipeDetail>(`/recipes/${id}/activate`),
  balances: (ingredientId: number, signal?: AbortSignal) => page<CatalogBalance>('/inventory/stock', { ingredient_id: ingredientId }, signal),
};

/** Only small reference catalogs are collected; transaction histories always stay paginated. */
export async function catalogOptions<T>(loader: (page: number) => Promise<CatalogPage<T>>): Promise<T[]> {
  const first = await loader(1);
  if (first.total > 1000) throw new Error('Danh mục vượt 1.000 mục. Cần bổ sung tìm kiếm phân trang cho bộ chọn trước khi tải danh mục này.');
  const items = [...first.items];
  for (let pageNo = 2; items.length < first.total; pageNo += 1) {
    const next = await loader(pageNo);
    if (next.items.length === 0) break;
    items.push(...next.items);
  }
  return items;
}
