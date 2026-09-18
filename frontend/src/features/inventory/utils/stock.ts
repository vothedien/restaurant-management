import type { Balance, Lot, Movement } from '../api/stock';
import type { Ingredient } from '../types/catalog';
import { addDecimal,compareDecimal,multiplyDecimal } from './format';
export function stockHealth(balance:Balance,ingredient?:Ingredient) { return compareDecimal(balance.available_quantity,'0')===0?'OUT_OF_STOCK':ingredient&&compareDecimal(balance.available_quantity,ingredient.minimum_stock_qty)<0?'LOW':'HEALTHY'; }
export function movementLabel(row:Movement) { return row.stocktake_item_id?'Kiểm kê':row.movement_type==='ADJUSTMENT'?row.direction==='IN'?'Điều chỉnh tăng':'Điều chỉnh giảm / xuất':row.movement_type==='RECEIPT'?'Nhập hàng':row.movement_type==='CONSUMPTION'?'Tiêu hao món':'Hoàn trả'; }
export const inventoryValue=(lots:Lot[])=>lots.reduce((sum,lot)=>addDecimal(sum,multiplyDecimal(lot.current_quantity,lot.unit_cost)),'0');
