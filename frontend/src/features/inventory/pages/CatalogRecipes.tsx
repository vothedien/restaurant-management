import { useEffect, useState } from 'react';
import { flushSync } from 'react-dom';
import type { FormEvent } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { catalogApi, catalogOptions } from '../api/catalog';
import { useInventoryAuth } from '../auth/useInventoryAuth';
import type { Ingredient, Recipe, RecipeDetail, RecipeItemWrite, RecipeMetadata } from '../types/catalog';
import { Badge, ConfirmDialog, EmptyState, ErrorPanel, Field, LoadingState, Modal, PageHeader, Panel } from '../components/ui';
import { useQuery } from '../hooks/useQuery';
import { useMutation } from '../hooks/useMutation';
import { useUnsavedChanges } from '../hooks/useUnsavedChanges';
import { compareDecimal, date, dateTime, multiplyDecimal, normalizeDecimal, quantity, roundDecimal } from '../utils/format';
import { CatalogResult, DecimalField, FormActions, IngredientPicker, UnitSelect } from './CatalogShared';
import { decimalError, useCatalogFilters, useUnitOptions } from './CatalogHelpers';

export function RecipesPage() {
  const { can } = useInventoryAuth();
  const filter = useCatalogFilters(); const navigate = useNavigate(); const [create, setCreate] = useState(false);
  const dishId = filter.params.get('dish_id') ?? '';
  const query = useQuery(`recipes:${dishId}:${filter.status}:${filter.page}`, signal => catalogApi.recipes({ page: filter.page, status: filter.status || undefined, dish_id: dishId || undefined }, signal));
  const add = can('manageRecipes') ? <button className="inv-button" onClick={() => setCreate(true)}>Tạo phiên bản công thức</button> : undefined;
  return <><PageHeader title="Công thức món" description="Quản lý phiên bản và định lượng nguyên liệu cho từng món." actions={add} /><Panel><div className="inv-form-grid"><Field label="ID món"><input type="number" min={1} step={1} value={dishId} onChange={event => filter.setFilter('dish_id', event.target.value)} placeholder="Lọc theo ID món đã có" /></Field><Field label="Trạng thái công thức"><select value={filter.status} onChange={event => filter.setFilter('status', event.target.value)}><option value="">Tất cả trạng thái</option><option value="DRAFT">Nháp</option><option value="ACTIVE">Đang áp dụng</option><option value="INACTIVE">Ngừng áp dụng</option><option value="EXPIRED">Hết hiệu lực</option></select></Field><button className="inv-button secondary" onClick={filter.clear}>Xóa bộ lọc</button></div></Panel>
    <CatalogResult query={query} page={filter.page} onPage={page => filter.setFilter('page', String(page))} empty={<EmptyState title={dishId || filter.status ? 'Không có công thức phù hợp' : 'Chưa có phiên bản công thức'} description="Mỗi món có thể có nhiều phiên bản; chỉ bản nháp được sửa và kích hoạt." action={add} />}>{data => <div className="inv-table-wrap"><table className="inv-table"><caption>Các phiên bản công thức theo món</caption><thead><tr><th>Món ăn</th><th>Phiên bản</th><th>Trạng thái</th><th>Hiệu lực</th><th>Ngày tạo</th><th>Chi tiết</th></tr></thead><tbody>{data.items.map(recipe => <tr key={recipe.recipe_version_id}><td><Link className="inv-link" to={`/inventory/recipes/${recipe.dish_id}?version=${recipe.recipe_version_id}`}>{recipe.dish.dish_name}</Link><div className="inv-code inv-muted">{recipe.dish.dish_code} · ID {recipe.dish_id}</div></td><td>v{recipe.version_no}</td><td><Badge status={recipe.status} /></td><td>{recipe.effective_from ? date(recipe.effective_from) : 'Chưa đặt'} → {recipe.effective_to ? date(recipe.effective_to) : 'Không giới hạn'}</td><td>{dateTime(recipe.created_at)}</td><td><Link className="inv-link" to={`/inventory/recipes/${recipe.dish_id}?version=${recipe.recipe_version_id}`}>Xem định lượng</Link></td></tr>)}</tbody></table></div>}</CatalogResult>
    {can('manageRecipes') && create && <RecipeMetadataForm dishId={dishId ? Number(dishId) : undefined} onClose={() => setCreate(false)} onSaved={recipe => { flushSync(() => setCreate(false)); navigate(`/inventory/recipes/${recipe.dish_id}?version=${recipe.recipe_version_id}`); }} />}
  </>;
}

function RecipeMetadataForm({ dishId, recipe, onClose, onSaved }: { dishId?: number; recipe?: Recipe; onClose: () => void; onSaved: (recipe: RecipeDetail) => void }) {
  const { can } = useInventoryAuth();
  const initial: RecipeMetadata = { effective_from: recipe?.effective_from ?? null, effective_to: recipe?.effective_to ?? null, notes: recipe?.notes ?? null };
  const [form, setForm] = useState(initial); const [targetDishId, setTargetDishId] = useState(dishId ? String(dishId) : ''); const [attempted, setAttempted] = useState(false);
  const mutation = useMutation(); const dirty = JSON.stringify(form) !== JSON.stringify(initial) || targetDishId !== (dishId ? String(dishId) : ''); useUnsavedChanges(dirty);
  const close = () => { if (!mutation.pending && (!dirty || window.confirm('Bỏ các thay đổi công thức chưa lưu?'))) onClose(); };
  const invalidDates = !!form.effective_from && !!form.effective_to && form.effective_to < form.effective_from;
  function submit(event: FormEvent) { event.preventDefault(); if (!can('manageRecipes')) return; setAttempted(true); if (invalidDates) return; void mutation.run(() => recipe ? catalogApi.updateRecipe(recipe.recipe_version_id, form) : catalogApi.createRecipe(Number(targetDishId), form), onSaved); }
  return <Modal title={recipe ? `Sửa thông tin phiên bản ${recipe.version_no}` : 'Tạo phiên bản công thức nháp'} open onClose={close}><form onSubmit={submit}><div className="inv-form-grid">{!recipe && <Field label="ID món đã có trong hệ thống"><input autoFocus type="number" min={1} max={Number.MAX_SAFE_INTEGER} step={1} required readOnly={!!dishId} value={targetDishId} onChange={event => setTargetDishId(event.target.value)} /></Field>}<Field label="Ngày bắt đầu hiệu lực"><input type="date" value={form.effective_from ?? ''} onChange={event => setForm(current => ({ ...current, effective_from: event.target.value || null }))} /></Field><Field label="Ngày kết thúc hiệu lực" error={attempted && invalidDates ? 'Ngày kết thúc không được trước ngày bắt đầu.' : undefined}><input type="date" value={form.effective_to ?? ''} onChange={event => setForm(current => ({ ...current, effective_to: event.target.value || null }))} /></Field><Field label="Ghi chú"><textarea value={form.notes ?? ''} onChange={event => setForm(current => ({ ...current, notes: event.target.value || null }))} /></Field></div>{!recipe && <p className="inv-muted">Dùng ID món đang hoạt động. Sau khi tạo nháp, thêm định lượng rồi kích hoạt riêng. Danh sách chọn món hiện chưa được hệ thống cung cấp.</p>}{mutation.error && <ErrorPanel error={mutation.error} />}<FormActions pending={mutation.pending} onClose={close} label={recipe ? 'Lưu thông tin' : 'Tạo bản nháp'} /></form></Modal>;
}

export function RecipeDetailPage() {
  const { can } = useInventoryAuth();
  const { dishId: dishParam, id } = useParams(); const dishId = Number(dishParam ?? id);
  const [params, setParams] = useSearchParams(); const page = Math.max(1, Number(params.get('page')) || 1);
  const query = useQuery(`dish-recipes:${dishId}:${page}`, signal => catalogApi.recipes({ dish_id: dishId, page }, signal));
  const selectedId = Number(params.get('version')) || query.data?.items.find(recipe => recipe.status === 'ACTIVE')?.recipe_version_id || query.data?.items[0]?.recipe_version_id;
  const [create, setCreate] = useState(false);
  const [editingVersion, setEditingVersion] = useState(false);
  function selectVersion(recipe: RecipeDetail) { setParams(current => { const next = new URLSearchParams(current); next.set('version', String(recipe.recipe_version_id)); return next; }); query.refresh(); }
  return <><PageHeader title={query.data?.items[0]?.dish.dish_name ?? `Công thức món #${dishId}`} description="Lịch sử phiên bản và định lượng theo đơn vị cơ sở." actions={can('manageRecipes') && <button className="inv-button" disabled={editingVersion} onClick={() => setCreate(true)}>Tạo phiên bản mới</button>} /><Panel title="Các phiên bản"><CatalogResult query={query} page={page} onPage={value => setParams(current => { const next = new URLSearchParams(current); next.set('page', String(value)); return next; })} empty={<EmptyState title="Chưa có phiên bản công thức cho món này" action={can('manageRecipes') && <button className="inv-button" disabled={editingVersion} onClick={() => setCreate(true)}>Tạo bản nháp</button>} />}>{data => <div className="inv-actions">{data.items.map(recipe => <button key={recipe.recipe_version_id} className={`inv-button ${recipe.recipe_version_id === selectedId ? '' : 'secondary'}`} onClick={() => setParams(current => { const next = new URLSearchParams(current); next.set('version', String(recipe.recipe_version_id)); return next; })}>Phiên bản {recipe.version_no} · {recipe.status === 'DRAFT' ? 'Nháp' : recipe.status === 'ACTIVE' ? 'Đang áp dụng' : recipe.status === 'EXPIRED' ? 'Hết hiệu lực' : 'Lịch sử'}</button>)}</div>}</CatalogResult></Panel>
    {selectedId && <RecipeVersion key={selectedId} recipeId={selectedId} dishId={dishId} onChanged={query.refresh} onEditingChange={setEditingVersion} />}
    {can('manageRecipes') && create && <RecipeMetadataForm dishId={dishId} onClose={() => setCreate(false)} onSaved={recipe => { flushSync(() => setCreate(false)); selectVersion(recipe); }} />}
  </>;
}

function RecipeVersion({ recipeId, dishId, onChanged, onEditingChange }: { recipeId: number; dishId: number; onChanged: () => void; onEditingChange: (editing: boolean) => void }) {
  const { can } = useInventoryAuth();
  const query = useQuery(`recipe:${recipeId}`, signal => catalogApi.recipe(recipeId, signal));
  const [metadata, setMetadata] = useState(false); const [items, setItems] = useState(false); const [activate, setActivate] = useState(false);
  const mutation = useMutation();
  useEffect(() => () => onEditingChange(false), [onEditingChange]);
  if (query.loading && !query.data) return <LoadingState />;
  if (query.error) return <ErrorPanel error={query.error} onRetry={query.refresh} />;
  const recipe = query.data; if (!recipe) return null;
  if (recipe.dish_id !== dishId) return <EmptyState title="Phiên bản không thuộc món đang xem" description="Chọn lại phiên bản trong danh sách phía trên." />;
  const reload = () => { query.refresh(); onChanged(); };
  return <><Panel title={`Phiên bản ${recipe.version_no}`} actions={recipe.status === 'DRAFT' && !items ? <>
    {can('manageRecipes') && <><button className="inv-button secondary" onClick={() => { setMetadata(true); onEditingChange(true); }}>Sửa thông tin</button><button className="inv-button secondary" onClick={() => { setItems(true); onEditingChange(true); }}>Sửa định lượng</button></>}
    {can('activateRecipes') && <button className="inv-button" disabled={!recipe.items.length} onClick={() => { mutation.clearError(); setActivate(true); }}>Kích hoạt phiên bản</button>}
  </> : undefined}><dl className="inv-summary"><div><dt>Trạng thái</dt><dd><Badge status={recipe.status} /></dd></div><div><dt>Nguyên liệu</dt><dd>{recipe.items.length}</dd></div><div><dt>Bắt đầu hiệu lực</dt><dd>{date(recipe.effective_from)}</dd></div><div><dt>Kết thúc hiệu lực</dt><dd>{recipe.effective_to ? date(recipe.effective_to) : 'Không giới hạn'}</dd></div></dl>{recipe.notes && <p>{recipe.notes}</p>}{recipe.status !== 'DRAFT' && <p className="inv-muted">Phiên bản đã chốt chỉ được xem. Tạo bản nháp mới để thay đổi công thức.</p>}</Panel>
    {can('manageRecipes') && items && recipe.status === 'DRAFT' ? <RecipeItemsEditor recipe={recipe} onClose={() => { setItems(false); onEditingChange(false); }} onSaved={() => { setItems(false); onEditingChange(false); reload(); }} /> : <Panel title="Định lượng cho một món">{recipe.items.length ? <div className="inv-table-wrap"><table className="inv-table"><thead><tr><th>Nguyên liệu</th><th>Định lượng</th><th>Lượng cơ sở đã lưu</th></tr></thead><tbody>{recipe.items.map(item => <tr key={item.recipe_item_id}><td>{can('viewIngredients') ? <Link className="inv-link" to={`/inventory/ingredients/${item.ingredient_id}`}>{item.ingredient.ingredient_name}</Link> : item.ingredient.ingredient_name}<div className="inv-muted inv-code">{item.ingredient.ingredient_code}</div></td><td>{quantity(item.quantity)} {item.unit.unit_code}</td><td>{quantity(item.base_quantity)} {item.ingredient.base_unit.unit_code}</td></tr>)}</tbody></table></div> : <EmptyState title="Chưa có nguyên liệu trong công thức" description="Thêm ít nhất một nguyên liệu trước khi kích hoạt." action={can('manageRecipes') && recipe.status === 'DRAFT' && <button className="inv-button" onClick={() => { setItems(true); onEditingChange(true); }}>Thêm định lượng</button>} />}</Panel>}
    {can('manageRecipes') && metadata && <RecipeMetadataForm dishId={dishId} recipe={recipe} onClose={() => { setMetadata(false); onEditingChange(false); }} onSaved={() => { setMetadata(false); onEditingChange(false); reload(); }} />}
    <ConfirmDialog open={can('activateRecipes') && activate} title={`Kích hoạt phiên bản ${recipe.version_no}?`} pending={mutation.pending} onClose={() => setActivate(false)} onConfirm={() => { if (!can('activateRecipes')) return; void mutation.run(() => catalogApi.activateRecipe(recipeId), () => { setActivate(false); reload(); }); }}><p>Phiên bản đang áp dụng của món {recipe.dish.dish_name} sẽ ngừng hoạt động ngay khi xác nhận. Phiên bản mới sẽ chỉ được dùng trong khoảng hiệu lực đã chọn.</p>{recipe.effective_from && <p>Ngày bắt đầu: {date(recipe.effective_from)}. Nếu ngày này ở tương lai, món sẽ tạm thời không có công thức đủ hiệu lực.</p>}<p>Định lượng đã lưu sẽ không còn chỉnh sửa được.</p>{mutation.error && <ErrorPanel error={mutation.error} />}</ConfirmDialog>
  </>;
}

interface EditableItem extends RecipeItemWrite {
  ingredient: Pick<Ingredient, 'ingredient_id' | 'ingredient_code' | 'ingredient_name' | 'base_unit_id' | 'base_unit' | 'status'>;
}
function RecipeItemsEditor({ recipe, onClose, onSaved }: { recipe: RecipeDetail; onClose: () => void; onSaved: () => void }) {
  const { can } = useInventoryAuth();
  const initial: EditableItem[] = recipe.items.map(item => ({ ingredient_id: item.ingredient_id, unit_id: item.unit_id, quantity: item.quantity, ingredient: item.ingredient }));
  const [rows, setRows] = useState(initial); const [attempted, setAttempted] = useState(false);
  const units = useUnitOptions(); const conversions = useQuery('catalog:recipe-conversions', signal => catalogOptions(page => catalogApi.conversions({ page, page_size: 100 }, signal)));
  const mutation = useMutation(); const dirty = JSON.stringify(rows) !== JSON.stringify(initial); useUnsavedChanges(dirty);
  const close = () => { if (!mutation.pending && (!dirty || window.confirm('Bỏ các định lượng chưa lưu?'))) onClose(); };
  function preview(row: EditableItem): { value?: string; error?: string } {
    if (decimalError(row.quantity, 3, true)) return {};
    if (row.ingredient.status !== 'ACTIVE' || !row.ingredient.base_unit.is_active) return { error: 'Nguyên liệu hoặc đơn vị cơ sở đã ngừng hoạt động.' };
    const unit = units.data?.find(item => item.unit_id === row.unit_id);
    if (!unit) return { error: 'Chọn đơn vị hợp lệ.' };
    if (!unit.is_active) return { error: 'Đơn vị đã ngừng hoạt động.' };
    const factor = row.unit_id === row.ingredient.base_unit_id ? '1' : conversions.data?.find(item => item.from_unit_id === row.unit_id && item.to_unit_id === row.ingredient.base_unit_id)?.factor;
    if (!factor) return { error: 'Chưa có quy đổi trực tiếp sang đơn vị cơ sở.' };
    if (unit.dimension !== row.ingredient.base_unit.dimension) return { error: 'Đơn vị phải cùng nhóm với đơn vị cơ sở.' };
    const value = roundDecimal(multiplyDecimal(normalizeDecimal(row.quantity), factor), 3);
    if (compareDecimal(value, '0') <= 0 || compareDecimal(value, '99999999999.999') > 0) return { error: 'Lượng sau quy đổi nằm ngoài giới hạn cho phép.' };
    return { value };
  }
  function submit(event: FormEvent) { event.preventDefault(); if (!can('manageRecipes')) return; setAttempted(true); if (!rows.length || rows.some(row => decimalError(row.quantity, 3, true) || preview(row).error)) return; void mutation.run(() => catalogApi.replaceRecipeItems(recipe.recipe_version_id, rows.map(row => ({ ingredient_id: row.ingredient_id, unit_id: row.unit_id, quantity: normalizeDecimal(row.quantity) }))), onSaved); }
  return <Panel title="Chỉnh sửa định lượng"><form onSubmit={submit}><IngredientPicker excluded={rows.map(row => row.ingredient_id)} onPick={ingredient => { setRows(current => current.some(row => row.ingredient_id === ingredient.ingredient_id) ? current : [...current, { ingredient_id: ingredient.ingredient_id, ingredient, unit_id: ingredient.base_unit_id, quantity: '' }]); }} /><p className="inv-muted">Chọn nguyên liệu để thêm dòng. Tab chuyển giữa định lượng và đơn vị. Lượng cơ sở được làm tròn tới 0,001 theo quy tắc công thức.</p>
    <div className="inv-table-wrap"><table className="inv-table"><thead><tr><th>Nguyên liệu</th><th>Số lượng</th><th>Đơn vị</th><th>Lượng cơ sở dự kiến</th><th>Thao tác</th></tr></thead><tbody>{rows.map((row, index) => { const computed = preview(row); return <tr key={row.ingredient_id}><td>{row.ingredient.ingredient_name}<div className="inv-muted inv-code">{row.ingredient.ingredient_code}</div></td><td><DecimalField label={`Định lượng ${row.ingredient.ingredient_name}`} value={row.quantity} onChange={value => setRows(current => current.map((item, i) => i === index ? { ...item, quantity: value } : item))} attempted={attempted} positive /></td><td><UnitSelect label={`Đơn vị ${row.ingredient.ingredient_name}`} units={units.data ?? []} value={row.unit_id} onChange={value => setRows(current => current.map((item, i) => i === index ? { ...item, unit_id: value } : item))} /></td><td>{computed.value ? `${quantity(computed.value)} ${row.ingredient.base_unit.unit_code}` : '—'}{computed.error && <p className="inv-field-error" role={attempted ? 'alert' : undefined}>{computed.error}</p>}</td><td><button type="button" className="inv-button danger" aria-label={`Bỏ ${row.ingredient.ingredient_name}`} onClick={() => setRows(current => current.filter(item => item.ingredient_id !== row.ingredient_id))}>Bỏ dòng</button></td></tr>; })}</tbody></table></div>
    {attempted && !rows.length && <p role="alert">Công thức cần ít nhất một nguyên liệu.</p>}{units.error && <ErrorPanel error={units.error} onRetry={units.refresh} />}{conversions.error && <ErrorPanel error={conversions.error} onRetry={conversions.refresh} />}{mutation.error && <ErrorPanel error={mutation.error} />}<FormActions pending={mutation.pending || units.loading || conversions.loading} onClose={close} label="Lưu toàn bộ định lượng" />
  </form></Panel>;
}
