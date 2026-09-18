export interface Page<T> { items: T[]; total: number; limit: number; offset: number }
export type ActiveStatus = "ACTIVE" | "INACTIVE";
