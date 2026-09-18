import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { DecimalInput, ErrorPanel, Field, LoadingState, Pagination } from '../components/ui';
import { useQuery } from '../hooks/useQuery';
import { catalogApi } from '../api/catalog';
import type { CatalogPage, Ingredient, Unit } from '../types/catalog';
import { decimalError } from './CatalogHelpers';

export function CatalogSearch({ value, onChange, placeholder = 'Tìm theo mã hoặc tên', maxLength = 150 }: { value: string; onChange: (value: string) => void; placeholder?: string; maxLength?: number }) {
  return <SearchInput initial={value} onChange={onChange} placeholder={placeholder} maxLength={maxLength} />;
}
function SearchInput({ initial, onChange, placeholder, maxLength }: { initial: string; onChange: (value: string) => void; placeholder: string; maxLength: number }) {
  const [value, setValue] = useState(initial);
  const [previous, setPrevious] = useState(initial);
  if (initial !== previous) { setPrevious(initial); setValue(initial); }
  useEffect(() => { if (value === initial) return; const timer = window.setTimeout(() => onChange(value), 350); return () => window.clearTimeout(timer); }, [value, initial, onChange]);
  return <Field label="Tìm kiếm"><input type="search" value={value} onChange={event => setValue(event.target.value)} placeholder={placeholder} maxLength={maxLength} /></Field>;
}

export function IngredientPicker({ onPick, excluded = [] }: { onPick: (ingredient: Ingredient) => void; excluded?: number[] }) {
  const [search, setSearch] = useState('');
  const query = useQuery(`catalog:ingredient-picker:${search}`, signal => catalogApi.ingredients({ search: search || undefined, status: 'ACTIVE', page_size: 100 }, signal));
  return <div><CatalogSearch value={search} onChange={setSearch} placeholder="Gõ tên hoặc mã nguyên liệu để thu hẹp kết quả" /><Field label="Chọn nguyên liệu"><select value="" disabled={query.loading} onChange={event => { const ingredient = query.data?.items.find(item => item.ingredient_id === Number(event.target.value)); if (ingredient) onPick(ingredient); }}><option value="">{query.loading ? 'Đang tải…' : 'Chọn nguyên liệu'}</option>{query.data?.items.filter(item => !excluded.includes(item.ingredient_id)).map(item => <option key={item.ingredient_id} value={item.ingredient_id}>{item.ingredient_name} — {item.ingredient_code} ({item.base_unit.unit_code})</option>)}</select></Field>{query.data && query.data.total > query.data.items.length && <p className="inv-muted">Đang hiển thị {query.data.items.length} / {query.data.total} nguyên liệu. Tìm theo mã hoặc tên để chọn chính xác.</p>}{query.error && <ErrorPanel error={query.error} onRetry={query.refresh} />}</div>;
}

export function CatalogResult<T>({ query, children, empty, page, onPage }: {
  query: { data: CatalogPage<T> | undefined; loading: boolean; error: unknown; refresh: () => void };
  children: (data: CatalogPage<T>) => ReactNode; empty: ReactNode; page: number; onPage: (page: number) => void;
}) {
  if (query.loading && !query.data) return <LoadingState />;
  if (query.error) return <ErrorPanel error={query.error} onRetry={query.refresh} />;
  if (!query.data) return null;
  return <>{query.loading && <p role="status" className="inv-muted">Đang cập nhật…</p>}{query.data.items.length ? children(query.data) : empty}<Pagination page={page} total={query.data.total} pageSize={20} onChange={onPage} /></>;
}

export function ActiveFilter({ value, onChange, suspended = false }: { value: string; onChange: (value: string) => void; suspended?: boolean }) {
  return <Field label="Trạng thái"><select value={value} onChange={event => onChange(event.target.value)}><option value="">Tất cả trạng thái</option><option value="ACTIVE">Đang hoạt động</option><option value="INACTIVE">Ngừng hoạt động</option>{suspended && <option value="SUSPENDED">Tạm ngưng</option>}</select></Field>;
}

export function UnitSelect({ value, onChange, units, disabled = false, label = 'Đơn vị', allowInactive = false }: { value: number; onChange: (value: number) => void; units: Unit[]; disabled?: boolean; label?: string; allowInactive?: boolean }) {
  return <Field label={label}><select required value={value || ''} onChange={event => onChange(Number(event.target.value))} disabled={disabled}><option value="">Chọn đơn vị</option>{units.filter(unit => allowInactive || unit.is_active || unit.unit_id === value).map(unit => <option key={unit.unit_id} value={unit.unit_id} disabled={!unit.is_active && unit.unit_id !== value}>{unit.unit_code} — {unit.unit_name}{!unit.is_active ? ' (ngừng hoạt động)' : ''}</option>)}</select></Field>;
}

export function DecimalField({ label, value, onChange, attempted, places = 3, positive = false, maxDigits = 14 }: { label: string; value: string; onChange: (value: string) => void; attempted: boolean; places?: number; positive?: boolean; maxDigits?: number }) {
  const error = attempted ? decimalError(value, places, positive, maxDigits) : undefined;
  return <Field label={label} error={error}><DecimalInput value={value} onChange={onChange} required aria-invalid={!!error} /></Field>;
}

export function FormActions({ pending, onClose, label = 'Lưu thay đổi' }: { pending: boolean; onClose: () => void; label?: string }) {
  return <div className="inv-actions"><button type="button" className="inv-button secondary" disabled={pending} onClick={onClose}>Đóng</button><button type="submit" className="inv-button" disabled={pending}>{pending ? 'Đang lưu…' : label}</button></div>;
}
