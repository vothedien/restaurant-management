import { useEffect, useState } from 'react';
import { getOperationIngredient, listOperationIngredients, listOperationLots } from '../api/operations';
import { useQuery } from '../hooks/useQuery';
import { Badge, EmptyState, ErrorPanel, Field, LoadingState, Pagination } from './ui';
import { date, quantity } from '../utils/format';
import type { OperationIngredient, OperationLot } from '../types/operations';

export function OperationIngredientPicker({ value, onChange, activeOnly = false, label = 'Nguyên liệu', disabled = false }: {
  value?: OperationIngredient; onChange: (value: OperationIngredient | undefined) => void; activeOnly?: boolean; label?: string; disabled?: boolean;
}) {
  const [search, setSearch] = useState('');
  const [debounced, setDebounced] = useState('');
  const [page, setPage] = useState(1);
  useEffect(() => { const timer = setTimeout(() => setDebounced(search), 350); return () => clearTimeout(timer); }, [search]);
  const query = useQuery(`operation-ingredients:${debounced}:${page}:${activeOnly}`, signal => listOperationIngredients(debounced, page, activeOnly, signal));
  const options = query.data?.items ?? [];
  return <div className="inv-operation-picker">
    <Field label={`Tìm ${label.toLowerCase()}`}><input value={search} onChange={event => { setSearch(event.target.value); setPage(1); }} placeholder="Tên hoặc mã nguyên liệu" disabled={disabled} /></Field>
    <Field label={label}><select value={value?.ingredient_id ?? ''} disabled={disabled || query.loading} onChange={event => onChange(options.find(item => item.ingredient_id === Number(event.target.value)))}>
      <option value="">Chọn nguyên liệu</option>
      {value && !options.some(item => item.ingredient_id === value.ingredient_id) && <option value={value.ingredient_id}>{value.ingredient_code} · {value.ingredient_name}</option>}
      {options.map(item => <option key={item.ingredient_id} value={item.ingredient_id}>{item.ingredient_code} · {item.ingredient_name}</option>)}
    </select></Field>
    {query.loading && <p className="inv-muted" role="status">Đang tìm nguyên liệu…</p>}
    {Boolean(query.error) && <ErrorPanel error={query.error} onRetry={query.refresh} />}
    {query.data && query.data.total === 0 && <p className="inv-muted">Không tìm thấy nguyên liệu phù hợp.</p>}
    {query.data && query.data.total > 20 && <Pagination page={page} total={query.data.total} pageSize={20} onChange={setPage} />}
  </div>;
}

export function OperationLotPicker({ selected, onChange, disabled = false }: { selected: OperationLot[]; onChange: (lots: OperationLot[]) => void; disabled?: boolean }) {
  const [ingredient, setIngredient] = useState<OperationIngredient>();
  const [page, setPage] = useState(1);
  const query = useQuery(`operation-select-lots:${ingredient?.ingredient_id ?? ''}:${page}`, async signal => {
    const lots = await listOperationLots(page, ingredient?.ingredient_id, signal);
    const ids = [...new Set(lots.items.map(lot => lot.ingredient_id))];
    const names: Record<number, OperationIngredient> = {};
    // At most one request per distinct ingredient on this 20-row page.
    for (let index = 0; index < ids.length; index += 4) {
      const group = await Promise.all(ids.slice(index, index + 4).map(id => getOperationIngredient(id, signal)));
      group.forEach(item => { names[item.ingredient_id] = item; });
    }
    return { ...lots, names };
  });
  const toggle = (lot: OperationLot) => onChange(selected.some(row => row.stock_lot_id === lot.stock_lot_id) ? selected.filter(row => row.stock_lot_id !== lot.stock_lot_id) : [...selected, lot]);
  return <div>
    <OperationIngredientPicker value={ingredient} onChange={next => { setIngredient(next); setPage(1); }} label="Lọc lô theo nguyên liệu" disabled={disabled} />
    <div className="inv-actions"><strong>Đã chọn {selected.length} / 1.000 lô</strong>
      <button className="inv-button secondary" type="button" disabled={disabled || !query.data?.items.length || selected.length >= 1000} onClick={() => {
        const result = new Map(selected.map(lot => [lot.stock_lot_id, lot]));
        query.data?.items.forEach(lot => { if (result.size < 1000) result.set(lot.stock_lot_id, lot); });
        onChange([...result.values()]);
      }}>Chọn trang này</button>
      <button className="inv-button secondary" type="button" disabled={disabled || !selected.length} onClick={() => onChange([])}>Bỏ chọn tất cả</button>
    </div>
    {query.loading && <LoadingState />}
    {Boolean(query.error) && <ErrorPanel error={query.error} onRetry={query.refresh} />}
    {query.data && !query.loading && (query.data.items.length ? <>
      <div className="inv-table-wrap"><table className="inv-table"><caption className="inv-muted">Chọn lô trên từng trang. Số tồn được chụp lại khi bắt đầu kiểm kê.</caption>
        <thead><tr><th>Chọn</th><th>Nguyên liệu / lô</th><th>Hạn dùng</th><th>Tồn hiện tại</th><th>Trạng thái</th></tr></thead>
        <tbody>{query.data.items.map(lot => {
          const item = query.data!.names[lot.ingredient_id]; const checked = selected.some(row => row.stock_lot_id === lot.stock_lot_id);
          return <tr key={lot.stock_lot_id}><td><input type="checkbox" aria-label={`Chọn lô ${lot.lot_code}`} checked={checked} disabled={disabled || (!checked && selected.length >= 1000)} onChange={() => toggle(lot)} /></td>
            <td>{item.ingredient_name}<br /><span className="inv-code">{lot.lot_code}</span></td><td>{date(lot.expiry_date)}</td><td>{quantity(lot.current_quantity)} {item.base_unit.unit_code}</td><td><Badge status={lot.status} /></td></tr>;
        })}</tbody></table></div>
      <Pagination page={page} total={query.data.total} pageSize={20} onChange={setPage} />
    </> : <EmptyState title="Chưa có lô phù hợp" description="Nhập và chốt phiếu nhập để tạo lô, hoặc xóa bộ lọc nguyên liệu." />)}
  </div>;
}
