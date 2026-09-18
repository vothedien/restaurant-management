import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import type { FormEvent } from 'react';
import { catalogApi } from '../api/catalog';
import { useInventoryAuth } from '../auth/useInventoryAuth';
import type { Ingredient, IngredientWrite } from '../types/catalog';
import { useQuery } from '../hooks/useQuery';
import { useMutation } from '../hooks/useMutation';
import { useUnsavedChanges } from '../hooks/useUnsavedChanges';
import { Badge, ConfirmDialog, EmptyState, ErrorPanel, Field, LoadingState, Modal, PageHeader, Panel } from '../components/ui';
import { dateTime, money, normalizeDecimal, quantity } from '../utils/format';
import { ActiveFilter, CatalogResult, CatalogSearch, DecimalField, FormActions, UnitSelect } from './CatalogShared';
import { decimalError, useCatalogFilters, useUnitOptions } from './CatalogHelpers';

export function IngredientsPage() {
  const { can } = useInventoryAuth();
  const filter = useCatalogFilters();
  const query = useQuery(`ingredients:${JSON.stringify(filter.query)}`, signal => catalogApi.ingredients(filter.query, signal));
  const [editor, setEditor] = useState<Ingredient | 'new' | null>(null);
  const [deactivate, setDeactivate] = useState<Ingredient | null>(null);
  const mutation = useMutation();
  const add = can('manageIngredients') ? <button className="inv-button" onClick={() => setEditor('new')}>Thêm nguyên liệu</button> : undefined;
  return <>
    <PageHeader title="Nguyên liệu" description="Quản lý đơn vị cơ sở, ngưỡng tồn và trạng thái sử dụng." actions={add} />
    <Panel><div className="inv-form-grid"><CatalogSearch value={filter.search} onChange={value => filter.setFilter('search', value)} /><ActiveFilter value={filter.status} onChange={value => filter.setFilter('status', value)} /><div className="inv-actions"><button className="inv-button secondary" onClick={filter.clear}>Xóa bộ lọc</button>{can('viewStock') && <Link className="inv-link" to="/inventory/stock">Tra cứu tồn và tình trạng kho</Link>}</div></div></Panel>
    <CatalogResult query={query} page={filter.page} onPage={page => filter.setFilter('page', String(page))} empty={<EmptyState title={filter.search || filter.status ? 'Không tìm thấy nguyên liệu phù hợp' : 'Chưa có nguyên liệu'} description="Thiết lập nguyên liệu trước khi tạo công thức và mua hàng." action={filter.search || filter.status ? <button className="inv-button secondary" onClick={filter.clear}>Xóa bộ lọc</button> : add} />}>
      {data => <div className="inv-table-wrap"><table className="inv-table"><caption>Danh mục nguyên liệu</caption><thead><tr><th>Mã / nguyên liệu</th><th>Đơn vị cơ sở</th><th>Tồn tối thiểu</th><th>Tồn an toàn</th><th>Trạng thái</th><th>Thao tác</th></tr></thead><tbody>{data.items.map(item => <tr key={item.ingredient_id}><td><Link className="inv-link" to={`/inventory/ingredients/${item.ingredient_id}`}>{item.ingredient_name}</Link><div className="inv-code inv-muted">{item.ingredient_code}</div></td><td>{item.base_unit.unit_code}</td><td>{quantity(item.minimum_stock_qty)} {item.base_unit.unit_code}</td><td>{quantity(item.safety_stock_qty)} {item.base_unit.unit_code}</td><td><Badge status={item.status} /></td><td>{can('manageIngredients') && <div className="inv-actions"><button className="inv-button secondary" onClick={() => setEditor(item)}>Sửa</button>{item.status === 'ACTIVE' && <button className="inv-button secondary" onClick={() => { mutation.clearError(); setDeactivate(item); }}>Ngừng dùng</button>}</div>}</td></tr>)}</tbody></table></div>}
    </CatalogResult>
    {can('manageIngredients') && editor && <IngredientForm ingredient={editor === 'new' ? undefined : editor} onClose={() => setEditor(null)} onSaved={() => { setEditor(null); query.refresh(); }} />}
    <ConfirmDialog open={can('manageIngredients') && !!deactivate} title="Ngừng sử dụng nguyên liệu?" onClose={() => setDeactivate(null)} pending={mutation.pending} onConfirm={() => { if (can('manageIngredients') && deactivate) void mutation.run(() => catalogApi.deactivateIngredient(deactivate.ingredient_id), () => { setDeactivate(null); query.refresh(); }); }}><p>{deactivate?.ingredient_name} sẽ không dùng được cho công thức, mua hàng hoặc xuất kho mới. Lịch sử và số tồn vẫn được giữ.</p>{mutation.error && <ErrorPanel error={mutation.error} />}</ConfirmDialog>
  </>;
}

export function IngredientForm(props: { ingredient?: Ingredient; onClose: () => void; onSaved: (ingredient: Ingredient) => void }) {
  const { can } = useInventoryAuth();
  return can('manageIngredients') ? <IngredientEditor {...props} /> : <EmptyState title="Không có quyền sửa nguyên liệu" />;
}

function IngredientEditor({ ingredient, onClose, onSaved }: { ingredient?: Ingredient; onClose: () => void; onSaved: (ingredient: Ingredient) => void }) {
  const { can } = useInventoryAuth();
  const initial: IngredientWrite = ingredient ? { ingredient_code: ingredient.ingredient_code, ingredient_name: ingredient.ingredient_name, base_unit_id: ingredient.base_unit_id, manages_lot: ingredient.manages_lot, default_shelf_life_days: ingredient.default_shelf_life_days, minimum_stock_qty: ingredient.minimum_stock_qty, safety_stock_qty: ingredient.safety_stock_qty, status: ingredient.status } : { ingredient_code: '', ingredient_name: '', base_unit_id: 0, manages_lot: true, default_shelf_life_days: null, minimum_stock_qty: '0', safety_stock_qty: '0', status: 'ACTIVE' };
  const [form, setForm] = useState(initial);
  const [attempted, setAttempted] = useState(false);
  const units = useUnitOptions();
  const mutation = useMutation();
  const dirty = JSON.stringify(form) !== JSON.stringify(initial);
  useUnsavedChanges(dirty);
  const close = () => { if (!mutation.pending && (!dirty || window.confirm('Bỏ các thay đổi nguyên liệu chưa lưu?'))) onClose(); };
  const change = <K extends keyof IngredientWrite>(key: K, value: IngredientWrite[K]) => setForm(current => ({ ...current, [key]: value }));
  function submit(event: FormEvent) {
    event.preventDefault(); if (!can('manageIngredients')) return; setAttempted(true);
    if (decimalError(form.minimum_stock_qty) || decimalError(form.safety_stock_qty)) return;
    void mutation.run(() => catalogApi.saveIngredient({ ...form, ingredient_code: form.ingredient_code.trim(), ingredient_name: form.ingredient_name.trim(), minimum_stock_qty: normalizeDecimal(form.minimum_stock_qty), safety_stock_qty: normalizeDecimal(form.safety_stock_qty) }, ingredient?.ingredient_id), onSaved);
  }
  return <Modal title={ingredient ? `Sửa ${ingredient.ingredient_code}` : 'Thêm nguyên liệu'} open onClose={close}><form onSubmit={submit}><div className="inv-form-grid">
    <Field label="Mã nguyên liệu"><input autoFocus required pattern=".*\S.*" maxLength={40} value={form.ingredient_code} onChange={event => change('ingredient_code', event.target.value)} /></Field>
    <Field label="Tên nguyên liệu"><input required pattern=".*\S.*" maxLength={150} value={form.ingredient_name} onChange={event => change('ingredient_name', event.target.value)} /></Field>
    <UnitSelect label="Đơn vị cơ sở" units={units.data ?? []} value={form.base_unit_id} onChange={value => change('base_unit_id', value)} />
    <Field label="Trạng thái"><select value={form.status} onChange={event => change('status', event.target.value as IngredientWrite['status'])}><option value="ACTIVE">Đang hoạt động</option><option value="INACTIVE">Ngừng hoạt động</option></select></Field>
    <DecimalField label="Mức tồn tối thiểu" value={form.minimum_stock_qty} onChange={value => change('minimum_stock_qty', value)} attempted={attempted} />
    <DecimalField label="Mức tồn an toàn" value={form.safety_stock_qty} onChange={value => change('safety_stock_qty', value)} attempted={attempted} />
    <Field label="Hạn sử dụng mặc định (ngày)"><input type="number" min={0} max={2147483647} step={1} value={form.default_shelf_life_days ?? ''} onChange={event => change('default_shelf_life_days', event.target.value === '' ? null : Number(event.target.value))} /></Field>
    <Field label="Theo dõi lô"><input type="checkbox" checked={form.manages_lot} onChange={event => change('manages_lot', event.target.checked)} /></Field>
  </div><p className="inv-muted">Số lượng dùng đơn vị cơ sở. Khi đã có công thức, liên kết nhà cung cấp hoặc lịch sử kho, hệ thống sẽ từ chối đổi đơn vị cơ sở.</p>
    {units.loading && <p role="status">Đang tải đơn vị…</p>}{units.error && <ErrorPanel error={units.error} onRetry={units.refresh} />}{mutation.error && <ErrorPanel error={mutation.error} />}<FormActions pending={mutation.pending || units.loading} onClose={close} label={ingredient ? 'Lưu nguyên liệu' : 'Tạo nguyên liệu'} />
  </form></Modal>;
}

export function IngredientDetailPage() {
  const { can } = useInventoryAuth();
  const { id } = useParams(); const ingredientId = Number(id);
  const query = useQuery(`ingredient:${id}`, signal => catalogApi.ingredient(ingredientId, signal));
  const [editing, setEditing] = useState(false);
  const [tab, setTab] = useState('overview');
  if (query.loading && !query.data) return <LoadingState />;
  if (query.error) return <ErrorPanel error={query.error} onRetry={query.refresh} />;
  const item = query.data; if (!item) return null;
  return <><PageHeader title={item.ingredient_name} description={item.ingredient_code} actions={<div className="inv-actions">
    {can('manageIngredients') && <button className="inv-button secondary" onClick={() => setEditing(true)}>Sửa nguyên liệu</button>}
    {(can('issueStock') || can('adjustStock')) && <Link className="inv-button" to={`/inventory/adjustments/new?ingredient_id=${item.ingredient_id}`}>Xuất / điều chỉnh</Link>}
  </div>} />
    <div className="inv-tabs" role="group" aria-label="Thông tin nguyên liệu">
      <button className={`inv-button ${tab === 'overview' ? '' : 'secondary'}`} onClick={() => setTab('overview')}>Tổng quan</button>
      {can('viewSuppliers') && <button className={`inv-button ${tab === 'suppliers' ? '' : 'secondary'}`} onClick={() => setTab('suppliers')}>Nhà cung cấp</button>}
      {can('viewStock') && <><Link className="inv-button secondary" to={`/inventory/lots?ingredient_id=${item.ingredient_id}`}>Tồn theo lô</Link><Link className="inv-button secondary" to={`/inventory/movements?ingredient_id=${item.ingredient_id}`}>Biến động kho</Link></>}
    </div>
    {tab === 'suppliers' && can('viewSuppliers') ? <IngredientSuppliers ingredientId={item.ingredient_id} /> : <>
      {can('viewStock') && <IngredientBalance ingredient={item} />}
      <Panel title="Thiết lập nguyên liệu"><dl className="inv-summary"><div><dt>Trạng thái</dt><dd><Badge status={item.status} /></dd></div><div><dt>Đơn vị cơ sở</dt><dd>{item.base_unit.unit_name} ({item.base_unit.unit_code})</dd></div><div><dt>Mức tồn tối thiểu</dt><dd>{quantity(item.minimum_stock_qty)} {item.base_unit.unit_code}</dd></div><div><dt>Mức tồn an toàn</dt><dd>{quantity(item.safety_stock_qty)} {item.base_unit.unit_code}</dd></div><div><dt>Hạn sử dụng mặc định</dt><dd>{item.default_shelf_life_days === null ? 'Chưa thiết lập' : `${item.default_shelf_life_days} ngày`}</dd></div><div><dt>Theo dõi lô</dt><dd>{item.manages_lot ? 'Có' : 'Không'}</dd></div><div><dt>Cập nhật</dt><dd>{dateTime(item.updated_at)}</dd></div></dl></Panel>
    </>}
    {can('manageIngredients') && editing && <IngredientForm ingredient={item} onClose={() => setEditing(false)} onSaved={() => { setEditing(false); query.refresh(); }} />}
  </>;
}

function IngredientBalance({ ingredient }: { ingredient: Ingredient }) {
  const balance = useQuery(`ingredient-balance:${ingredient.ingredient_id}`, signal => catalogApi.balances(ingredient.ingredient_id, signal));
  const stock = balance.data?.items[0];
  return <Panel title="Tồn kho hiện tại">{balance.error ? <ErrorPanel error={balance.error} onRetry={balance.refresh} /> : balance.loading ? <LoadingState /> : stock ? <dl className="inv-summary"><div><dt>Tổng tồn</dt><dd>{quantity(stock.current_quantity)} {ingredient.base_unit.unit_code}</dd></div><div><dt>Có thể cấp xuất</dt><dd>{quantity(stock.available_quantity)} {ingredient.base_unit.unit_code}</dd></div><div><dt>Chưa thể cấp xuất</dt><dd>{quantity(stock.unavailable_quantity)} {ingredient.base_unit.unit_code}</dd></div></dl> : <p>Chưa có số dư cho nguyên liệu này.</p>}</Panel>;
}

function IngredientSuppliers({ ingredientId }: { ingredientId: number }) {
  const [page, setPage] = useState(1);
  const query = useQuery(`ingredient-suppliers:${ingredientId}:${page}`, signal => catalogApi.mappings({ ingredient_id: ingredientId, page }, signal));
  return <Panel title="Nhà cung cấp liên kết"><CatalogResult query={query} page={page} onPage={setPage} empty={<EmptyState title="Chưa có nhà cung cấp liên kết" action={<Link className="inv-button" to="/inventory/suppliers">Chọn nhà cung cấp</Link>} />}>{data => <div className="inv-table-wrap"><table className="inv-table"><thead><tr><th>Nhà cung cấp</th><th>Đơn vị mua</th><th>Giá gần nhất</th><th>Ưu tiên</th><th>Trạng thái</th></tr></thead><tbody>{data.items.map(row => <tr key={row.supplier_ingredient_id}><td><Link className="inv-link" to={`/inventory/suppliers/${row.supplier_id}`}>{row.supplier.supplier_name}</Link></td><td>{row.purchase_unit.unit_code}</td><td>{row.latest_unit_price === null ? 'Chưa có giá' : money(row.latest_unit_price)}</td><td>{row.is_preferred ? 'Ưu tiên' : '—'}</td><td><Badge status={row.is_active ? 'ACTIVE' : 'INACTIVE'} /></td></tr>)}</tbody></table></div>}</CatalogResult></Panel>;
}
