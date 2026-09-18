import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { flushSync } from 'react-dom';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { createPurchaseOrder, getPurchaseOrder, getPurchasingContext, listGoodsReceipts, listPurchaseOrders, listPurchasingSuppliers, transitionPurchaseOrder, updatePurchaseOrder } from '../api/purchasing';
import { Badge, ConfirmDialog, CurrentActor, DecimalInput, EmptyState, ErrorPanel, Field, LoadingState, PageHeader, Pagination, Panel } from '../components/ui';
import { useInventoryAuth } from '../auth/useInventoryAuth';
import { useMutation } from '../hooks/useMutation';
import { useQuery } from '../hooks/useQuery';
import { useUnsavedChanges } from '../hooks/useUnsavedChanges';
import type { OrderTransition, PurchaseOrder, PurchaseOrderItemInput, PurchasingContext, PurchasingSupplier } from '../types/purchasing';
import { addDecimal, compareDecimal, date, dateTime, money, multiplyDecimal, quantity } from '../utils/format';
import { canReceive, decimalError, inputDecimal, lineAmount, orderActions, orderLineError, orderStatusLabels, todayISO } from '../utils/purchasing';
import './PurchasingPages.css';

export { GoodsReceiptDetailPage, GoodsReceiptEditorPage, GoodsReceiptsPage } from './PurchasingReceiptPages';

const pageSize = 20;
const actionLabels: Record<OrderTransition, string> = { PENDING_APPROVAL: 'Gửi duyệt', APPROVED: 'Duyệt đơn', ORDERED: 'Xác nhận đã đặt hàng', CANCELLED: 'Hủy đơn' };
function positiveId(value: string | null | undefined) { const n = Number(value); return Number.isSafeInteger(n) && n > 0 ? n : 0; }
function pageNumber(value: string | null) { return Math.max(1, positiveId(value) || 1); }

function SupplierPicker({ value, onChange, selected }: { value: string; onChange: (value: string) => void; selected?: PurchasingSupplier }) {
  const { can } = useInventoryAuth();
  const [search, setSearch] = useState('');
  const [debounced, setDebounced] = useState('');
  const [page, setPage] = useState(1);
  useEffect(() => { const timer = setTimeout(() => { setDebounced(search); setPage(1); }, 350); return () => clearTimeout(timer); }, [search]);
  const query = useQuery(`purchasing-supplier-picker:${debounced}:${page}:${can('viewSuppliers')}`, signal => can('viewSuppliers') ? listPurchasingSuppliers({ status: 'ACTIVE', search: debounced || undefined, limit: 20, offset: (page - 1) * 20 }, signal) : Promise.resolve(undefined));
  const options = query.data?.items ?? [];
  return <div className="pur-picker">
    <Field label="Tìm nhà cung cấp"><input value={search} onChange={event => setSearch(event.target.value)} placeholder="Mã hoặc tên nhà cung cấp" /></Field>
    <Field label="Nhà cung cấp"><select required value={value} onChange={event => onChange(event.target.value)}>
      <option value="">Chọn nhà cung cấp đang hoạt động</option>
      {selected && !options.some(supplier => supplier.supplier_id === selected.supplier_id) && <option value={selected.supplier_id}>{selected.supplier_name}</option>}
      {options.map(supplier => <option key={supplier.supplier_id} value={supplier.supplier_id}>{supplier.supplier_code} · {supplier.supplier_name}</option>)}
    </select></Field>
    {query.loading && <span className="inv-muted">Đang tải nhà cung cấp…</span>}
    {query.error && <ErrorPanel error={query.error} onRetry={query.refresh} />}
    {query.data && query.data.total > 20 && <Pagination page={page} total={query.data.total} pageSize={20} onChange={setPage} />}
  </div>;
}

function DocumentFilter({ children, onApply, onClear }: { children: React.ReactNode; onApply: (data: FormData) => void; onClear: () => void }) {
  return <form className="pur-filters" onSubmit={event => { event.preventDefault(); onApply(new FormData(event.currentTarget)); }}>
    {children}<div className="inv-actions"><button className="inv-button" type="submit">Áp dụng</button><button type="button" className="inv-button secondary" onClick={onClear}>Xóa bộ lọc</button></div>
  </form>;
}

export function PurchaseOrdersPage() {
  const { can } = useInventoryAuth();
  const [params, setParams] = useSearchParams();
  const page = pageNumber(params.get('page'));
  const filters = { status: params.get('status') || undefined, supplier_id: positiveId(params.get('supplier_id')) || undefined, limit: pageSize, offset: (page - 1) * pageSize };
  const query = useQuery(`purchase-orders:${params}`, signal => listPurchaseOrders(filters, signal));
  const suppliers = useQuery(`purchasing-supplier-labels:${can('viewSuppliers')}`, signal => can('viewSuppliers') ? listPurchasingSuppliers({ limit: 100, offset: 0 }, signal) : Promise.resolve(undefined));
  function apply(data: FormData) {
    const next = new URLSearchParams();
    ['status', 'supplier_id'].forEach(key => { const value = String(data.get(key) ?? ''); if (value) next.set(key, value); });
    setParams(next);
  }
  return <>
    <PageHeader title="Đơn mua hàng" description="Theo dõi từ nháp đến khi nhà cung cấp giao đủ hàng." actions={can('createPurchaseOrders') && <Link className="inv-button" to="/inventory/purchase-orders/new">Tạo đơn mua</Link>} />
    <Panel>
      <DocumentFilter key={params.toString()} onApply={apply} onClear={() => setParams({})}>
        <Field label="Trạng thái"><select name="status" defaultValue={params.get('status') ?? ''}><option value="">Tất cả trạng thái</option>{Object.entries(orderStatusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field>
        <Field label="ID nhà cung cấp"><input name="supplier_id" type="number" min="1" step="1" defaultValue={params.get('supplier_id') ?? ''} placeholder="Tất cả nhà cung cấp" /></Field>
      </DocumentFilter>
      {query.error ? <ErrorPanel error={query.error} onRetry={query.refresh} /> : query.loading ? <LoadingState /> : !query.data?.items.length ? <EmptyState title={params.size ? 'Không tìm thấy đơn mua phù hợp' : 'Chưa có đơn mua'} action={can('createPurchaseOrders') && <Link className="inv-button" to="/inventory/purchase-orders/new">Tạo đơn mua</Link>} /> : <>
        <div className="inv-table-wrap"><table className="inv-table pur-table"><caption>Đơn mua hàng · {query.data.total} kết quả</caption><thead><tr><th>Mã đơn / Nhà cung cấp</th><th>Ngày đặt</th><th>Dự kiến nhận</th><th>Dòng hàng</th><th>Giá trị</th><th>Tiến độ nhận</th><th>Trạng thái</th><th>Thao tác</th></tr></thead><tbody>{query.data.items.map(order => <tr key={order.purchase_order_id}>
          <td data-label="Đơn mua"><Link className="inv-link inv-code" to={`/inventory/purchase-orders/${order.purchase_order_id}`}>{order.purchase_order_number}</Link><small>{can('viewSuppliers') ? <Link to={`/inventory/suppliers/${order.supplier_id}`}>{suppliers.data?.items.find(supplier => supplier.supplier_id === order.supplier_id)?.supplier_name ?? `Nhà cung cấp #${order.supplier_id}`}</Link> : `Nhà cung cấp #${order.supplier_id}`}</small></td>
          <td data-label="Ngày đặt">{date(order.order_date)}</td><td data-label="Dự kiến nhận">{date(order.expected_delivery_date)}</td><td data-label="Dòng hàng">{order.items.length}</td><td data-label="Giá trị">{money(order.subtotal_amount)}</td>
          <td data-label="Tiến độ nhận">{order.items.filter(item => compareDecimal(item.remaining_quantity, '0') === 0).length}/{order.items.length} dòng đủ</td><td data-label="Trạng thái"><Badge status={order.status} /></td>
          <td data-label="Thao tác"><div className="inv-actions"><Link className="inv-link" to={`/inventory/purchase-orders/${order.purchase_order_id}`}>Chi tiết</Link>{can('createReceipts') && canReceive(order.status) && <Link className="inv-link" to={`/inventory/goods-receipts/new?purchase_order_id=${order.purchase_order_id}`}>Nhập hàng</Link>}</div></td>
        </tr>)}</tbody></table></div>
        <Pagination page={page} total={query.data.total} pageSize={pageSize} onChange={next => { const copy = new URLSearchParams(params); copy.set('page', String(next)); setParams(copy); }} />
      </>}
    </Panel>
  </>;
}

export function PurchaseOrderEditorPage() {
  const { id } = useParams();
  const orderId = positiveId(id);
  const query = useQuery(`purchase-order-edit:${id ?? 'new'}`, signal => orderId ? getPurchaseOrder(orderId, signal) : Promise.resolve(undefined));
  if (id && !orderId) return <ErrorPanel error={new Error('ID đơn mua không hợp lệ.')} />;
  if (query.error) return <ErrorPanel error={query.error} onRetry={query.refresh} />;
  if (query.loading) return <LoadingState />;
  if (query.data && query.data.status !== 'DRAFT') return <EmptyState title="Đơn mua đã khóa chỉnh sửa" description="Chỉ đơn nháp chưa có phiếu nhập được sửa." action={<Link to={`/inventory/purchase-orders/${orderId}`}>Trở về chi tiết</Link>} />;
  return <PurchaseOrderForm key={id ?? 'new'} order={query.data} />;
}

function PurchaseOrderForm({ order }: { order?: PurchaseOrder }) {
  const { user, can } = useInventoryAuth();
  const navigate = useNavigate();
  const mutation = useMutation();
  const [supplierId, setSupplierId] = useState(order ? String(order.supplier_id) : '');
  const [switchSupplier, setSwitchSupplier] = useState<string | undefined>();
  const [lines, setLines] = useState<PurchaseOrderItemInput[]>(order?.items.map(item => ({ supplier_ingredient_id: item.supplier_ingredient_id, ordered_quantity: item.ordered_quantity, expected_unit_price: item.expected_unit_price })) ?? []);
  const [number, setNumber] = useState('');
  const [orderDate, setOrderDate] = useState(order?.order_date ?? todayISO());
  const [delivery, setDelivery] = useState(order?.expected_delivery_date ?? '');
  const [notes, setNotes] = useState(order?.notes ?? '');
  const [dirty, setDirty] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [search, setSearch] = useState('');
  const [mappingId, setMappingId] = useState('');
  useUnsavedChanges(dirty);
  const context = useQuery(`purchasing-context:${supplierId}:${can('viewSuppliers')}:${can('viewUnits')}`, signal => supplierId && can('viewSuppliers') ? getPurchasingContext(Number(supplierId), signal, can('viewUnits')) : Promise.resolve(undefined));
  const data = context.data;
  const active = (data?.mappings ?? []).filter(mapping => mapping.is_active && mapping.supplier.status === 'ACTIVE' && mapping.ingredient.status === 'ACTIVE' && data?.units.find(unit => unit.unit_id === mapping.purchase_unit_id)?.is_active && data?.units.find(unit => unit.unit_id === mapping.ingredient.base_unit_id)?.is_active);
  const available = active.filter(mapping => !lines.some(line => line.supplier_ingredient_id === mapping.supplier_ingredient_id) && `${mapping.ingredient.ingredient_name} ${mapping.ingredient.ingredient_code}`.toLocaleLowerCase('vi').includes(search.toLocaleLowerCase('vi')));
  const total = lines.reduce((sum, line) => addDecimal(sum, lineAmount(line.ordered_quantity, line.expected_unit_price)), '0');
  const lineErrors = lines.map(line => orderLineError(data?.mappings.find(mapping => mapping.supplier_ingredient_id === line.supplier_ingredient_id), line.ordered_quantity, line.expected_unit_price));
  const dateError = delivery && delivery < orderDate ? 'Ngày dự kiến nhận không được trước ngày đặt.' : undefined;
  function changeSupplier(value: string) {
    if (lines.length && value !== supplierId) { setSwitchSupplier(value); return; }
    setSupplierId(value); setLines([]); setMappingId(''); setDirty(true);
  }
  function addLine() {
    const id = Number(mappingId);
    if (!id || lines.length >= 200 || lines.some(line => line.supplier_ingredient_id === id)) return;
    setLines([...lines, { supplier_ingredient_id: id, ordered_quantity: '', expected_unit_price: '' }]); setMappingId(''); setDirty(true);
  }
  function updateLine(index: number, field: 'ordered_quantity' | 'expected_unit_price', value: string) { setLines(lines.map((line, row) => row === index ? { ...line, [field]: value } : line)); setDirty(true); }
  async function submit(event: FormEvent) {
    event.preventDefault(); setSubmitted(true);
    if (!user || !can(order ? 'updatePurchaseOrders' : 'createPurchaseOrders') || mutation.pending || !supplierId || !orderDate || !lines.length || lineErrors.some(Boolean) || dateError || decimalError(total, 2) || context.loading || !data || data.supplier.status !== 'ACTIVE') return;
    const body = { order_date: orderDate, expected_delivery_date: delivery || null, notes: notes.trim() || null, items: lines.map(line => ({ ...line, ordered_quantity: inputDecimal(line.ordered_quantity), expected_unit_price: inputDecimal(line.expected_unit_price) })) };
    await mutation.run(() => order ? updatePurchaseOrder(order.purchase_order_id, body) : createPurchaseOrder({ ...body, supplier_id: Number(supplierId), created_by: user.userId, purchase_order_number: number.trim() || null }), saved => {
      flushSync(() => setDirty(false)); navigate(`/inventory/purchase-orders/${saved.purchase_order_id}`);
    });
  }
  return <>
    <PageHeader title={order ? `Sửa ${order.purchase_order_number}` : 'Tạo đơn mua hàng'} description="Lưu nháp, kiểm tra lại rồi gửi duyệt tại trang chi tiết." />
    <form className="pur-editor" onSubmit={submit} noValidate>
      <div className="pur-editor-main">
        <Panel title="1. Nhà cung cấp">
          {order ? <p>Nhà cung cấp: <Link to={`/inventory/suppliers/${order.supplier_id}`}>{data?.supplier.supplier_name ?? `#${order.supplier_id}`}</Link></p> : <SupplierPicker value={supplierId} onChange={changeSupplier} selected={data?.supplier} />}
          {submitted && !supplierId && <p className="pur-error" role="alert">Chọn nhà cung cấp.</p>}
          {data && <p className="inv-muted">{data.supplier.contact_name} {data.supplier.phone} {data.supplier.email}</p>}
          {context.error && <ErrorPanel error={context.error} onRetry={context.refresh} />}
          {context.loading && supplierId && <LoadingState />}
          {data && data.supplier.status !== 'ACTIVE' && <p className="pur-error" role="alert">Nhà cung cấp đã ngừng hoạt động. Không thể lưu hoặc gửi duyệt đơn.</p>}
          {data && !data.complete && <p role="status">Đã tải tối đa 1.000 liên kết và đơn vị. Danh mục lớn hơn giới hạn này cần tra cứu qua trang nhà cung cấp.</p>}
        </Panel>
        <Panel title="2. Nguyên liệu cần mua">
          <div className="pur-add-row">
            <Field label="Tìm nguyên liệu liên kết"><input value={search} onChange={event => setSearch(event.target.value)} placeholder="Tên hoặc mã nguyên liệu" disabled={!supplierId} /></Field>
            <Field label="Nguyên liệu"><select value={mappingId} disabled={!data || context.loading} onChange={event => setMappingId(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); addLine(); } }}><option value="">Chọn nguyên liệu</option>{available.map(mapping => <option key={mapping.supplier_ingredient_id} value={mapping.supplier_ingredient_id}>{mapping.ingredient.ingredient_name} · {mapping.purchase_unit.unit_code}{mapping.is_preferred ? ' · Ưu tiên' : ''}</option>)}</select></Field>
            <button type="button" className="inv-button secondary" disabled={!mappingId || lines.length >= 200} onClick={addLine}>Thêm nguyên liệu</button>
          </div>
          {data && !active.length && <EmptyState title="Chưa có nguyên liệu hợp lệ để mua" description="Cần liên kết nguyên liệu và đơn vị đang hoạt động với nhà cung cấp này." action={<Link to={`/inventory/suppliers/${supplierId}`}>Mở danh mục nhà cung cấp</Link>} />}
          {submitted && !lines.length && <p role="alert" className="pur-error">Thêm ít nhất một nguyên liệu.</p>}
          {!!lines.length && <div className="inv-table-wrap"><table className="inv-table pur-table"><caption>Số lượng theo đơn vị mua · Giá thỏa thuận nhập bằng VND</caption><thead><tr><th>Nguyên liệu</th><th>Số lượng đặt</th><th>Đơn giá</th><th>Thành tiền</th><th>Thao tác</th></tr></thead><tbody>{lines.map((line, index) => {
            const mapping = data?.mappings.find(item => item.supplier_ingredient_id === line.supplier_ingredient_id);
            const baseUnit = data?.units.find(unit => unit.unit_id === mapping?.ingredient.base_unit_id);
            return <tr key={line.supplier_ingredient_id}>
              <td data-label="Nguyên liệu"><strong>{mapping?.ingredient.ingredient_name ?? `Liên kết #${line.supplier_ingredient_id}`}</strong><small>Đơn vị mua: {mapping?.purchase_unit.unit_code ?? '—'}</small>{mapping && <small>1 {mapping.purchase_unit.unit_code} = {quantity(mapping.base_qty_per_purchase_unit)} {baseUnit?.unit_code ?? `đơn vị #${mapping.ingredient.base_unit_id}`}</small>}</td>
              <td data-label="Số lượng đặt"><Field label={`Số lượng dòng ${index + 1}`} error={submitted ? lineErrors[index] : undefined}><DecimalInput value={line.ordered_quantity} onChange={value => updateLine(index, 'ordered_quantity', value)} aria-required="true" /></Field>{mapping && <small>Tối thiểu {quantity(mapping.minimum_order_qty)} {mapping.purchase_unit.unit_code}</small>}{mapping && !decimalError(line.ordered_quantity, 3, true) && <small>Quy đổi: {quantity(multiplyDecimal(inputDecimal(line.ordered_quantity), mapping.base_qty_per_purchase_unit))} {baseUnit?.unit_code}</small>}</td>
              <td data-label="Đơn giá"><Field label={`Đơn giá dòng ${index + 1} (VND)`} error={submitted ? decimalError(line.expected_unit_price, 2) : undefined}><DecimalInput value={line.expected_unit_price} onChange={value => updateLine(index, 'expected_unit_price', value)} aria-required="true" /></Field>{mapping?.latest_unit_price != null && <small>Giá tham khảo: {money(mapping.latest_unit_price)}. Nhập giá thỏa thuận.</small>}</td>
              <td data-label="Thành tiền">{money(lineAmount(line.ordered_quantity, line.expected_unit_price))}</td>
              <td data-label="Thao tác"><button type="button" className="inv-button secondary" aria-label={`Xóa dòng ${index + 1}`} onClick={() => { setLines(lines.filter((_, row) => row !== index)); setDirty(true); }}>Xóa</button></td>
            </tr>;
          })}</tbody></table></div>}
        </Panel>
        <Panel title="3. Thông tin đơn"><div className="inv-form-grid">
          {!order && <Field label="Mã đơn (bỏ trống để tạo tự động)"><input value={number} maxLength={40} onChange={event => { setNumber(event.target.value); setDirty(true); }} /></Field>}
          <Field label="Ngày đặt" error={submitted && !orderDate ? 'Chọn ngày đặt.' : undefined}><input type="date" required value={orderDate} onChange={event => { setOrderDate(event.target.value); setDirty(true); }} /></Field>
          <Field label="Ngày dự kiến nhận" error={dateError}><input type="date" min={orderDate} value={delivery} onChange={event => { setDelivery(event.target.value); setDirty(true); }} /></Field>
          <CurrentActor label={order ? 'Người sửa' : 'Người tạo'} />
          <Field label="Ghi chú"><textarea rows={3} value={notes} onChange={event => { setNotes(event.target.value); setDirty(true); }} /></Field>
        </div></Panel>
      </div>
      <aside className="pur-summary"><Panel title="Tóm tắt đơn mua"><dl className="pur-facts"><dt>Nhà cung cấp</dt><dd>{data?.supplier.supplier_name ?? 'Chưa chọn'}</dd><dt>Dòng nguyên liệu</dt><dd>{lines.length}</dd><dt>Giá trị dự kiến</dt><dd className="pur-total">{money(total)}</dd><dt>Dự kiến nhận</dt><dd>{date(delivery || null)}</dd><dt>Sau khi lưu</dt><dd><Badge status="DRAFT" /></dd></dl><p className="inv-muted">Tiền làm tròn từng dòng đến 2 chữ số. Lưu nháp chưa làm tăng tồn kho.</p>
        {submitted && decimalError(total, 2) && <p role="alert" className="pur-error">Tổng tiền vượt giới hạn lưu trữ.</p>}
        {mutation.error && <><ErrorPanel error={mutation.error} /><p className="inv-muted">Dữ liệu nhập vẫn được giữ. Nếu trạng thái đã thay đổi, mở chi tiết để đối chiếu trước khi thử lại.</p></>}
        <div className="pur-submit">{can(order ? 'updatePurchaseOrders' : 'createPurchaseOrders') && <button type="submit" className="inv-button" disabled={!user || mutation.pending || context.loading}>{mutation.pending ? 'Đang lưu…' : order ? 'Lưu thay đổi' : 'Lưu nháp'}</button>}<Link className="inv-button secondary" to={order ? `/inventory/purchase-orders/${order.purchase_order_id}` : '/inventory/purchase-orders'}>Hủy thao tác</Link></div>
      </Panel></aside>
    </form>
    <ConfirmDialog open={switchSupplier !== undefined} title="Đổi nhà cung cấp?" onClose={() => setSwitchSupplier(undefined)} onConfirm={() => { setSupplierId(switchSupplier ?? ''); setLines([]); setMappingId(''); setSwitchSupplier(undefined); setDirty(true); }}><p>{lines.length} dòng hiện tại sẽ được xóa để chọn đúng nguyên liệu của nhà cung cấp mới.</p></ConfirmDialog>
  </>;
}

function OrderLines({ order, context }: { order: PurchaseOrder; context?: PurchasingContext }) {
  const { can } = useInventoryAuth();
  return <div className="inv-table-wrap"><table className="inv-table pur-table"><caption>Đối chiếu theo phiếu nhập đã chốt · Đơn vị và hệ số tại thời điểm đặt hàng</caption><thead><tr><th>Nguyên liệu</th><th>Đơn vị mua</th><th>Số đặt</th><th>Đã nhập</th><th>Còn lại</th><th>Đơn giá</th><th>Thành tiền</th></tr></thead><tbody>{order.items.map(item => {
    const mapping = context?.mappings.find(value => value.supplier_ingredient_id === item.supplier_ingredient_id);
    const unit = context?.units.find(value => value.unit_id === item.purchase_unit_id);
    return <tr key={item.purchase_order_item_id}><td data-label="Nguyên liệu">{mapping ? can('viewIngredients') ? <Link to={`/inventory/ingredients/${mapping.ingredient_id}`}>{mapping.ingredient.ingredient_name}</Link> : mapping.ingredient.ingredient_name : `Liên kết #${item.supplier_ingredient_id}`}<small>{quantity(item.ordered_base_qty)} {context?.units.find(value => value.unit_id === mapping?.ingredient.base_unit_id)?.unit_code ?? 'đơn vị cơ sở'}</small></td><td data-label="Đơn vị mua">{unit?.unit_code ?? `#${item.purchase_unit_id}`}</td><td data-label="Số đặt">{quantity(item.ordered_quantity)}</td><td data-label="Đã nhập">{quantity(item.received_quantity)}</td><td data-label="Còn lại"><strong className={compareDecimal(item.remaining_quantity, '0') > 0 ? 'pur-remaining' : undefined}>{quantity(item.remaining_quantity)}</strong></td><td data-label="Đơn giá">{money(item.expected_unit_price)}</td><td data-label="Thành tiền">{money(item.line_amount)}</td></tr>;
  })}</tbody></table></div>;
}

export function PurchaseOrderDetailPage() {
  const { user, can } = useInventoryAuth();
  const { id } = useParams();
  const orderId = positiveId(id);
  const query = useQuery(`purchase-order:${id}`, signal => orderId ? getPurchaseOrder(orderId, signal) : Promise.reject(new Error('ID đơn mua không hợp lệ.')));
  const [receiptPage, setReceiptPage] = useState(1);
  const receipts = useQuery(`order-receipts:${id}:${receiptPage}:${can('viewReceipts')}`, signal => orderId && can('viewReceipts') ? listGoodsReceipts({ purchase_order_id: orderId, limit: 10, offset: (receiptPage - 1) * 10 }, signal) : Promise.resolve(undefined));
  const context = useQuery(`order-context:${query.data?.supplier_id ?? ''}:${can('viewSuppliers')}:${can('viewUnits')}`, signal => query.data && can('viewSuppliers') ? getPurchasingContext(query.data.supplier_id, signal, can('viewUnits')) : Promise.resolve(undefined));
  const mutation = useMutation();
  const [action, setAction] = useState<OrderTransition | undefined>();
  const [reason, setReason] = useState('');
  const [attempted, setAttempted] = useState(false);
  function canTransition(status: OrderTransition) {
    return can(status === 'APPROVED' ? 'approvePurchaseOrders' : status === 'PENDING_APPROVAL' ? 'submitPurchaseOrders' : status === 'ORDERED' ? 'orderPurchaseOrders' : 'cancelPurchaseOrders');
  }
  function actorName(actorId: number) { return user?.userId === actorId ? user.displayName || user.username : `Tài khoản #${actorId}`; }
  async function transition() {
    setAttempted(true);
    if (!user || !action || !canTransition(action) || !query.data || !orderActions(query.data.status).includes(action) || (action === 'CANCELLED' && !reason.trim())) return;
    await mutation.run(() => transitionPurchaseOrder(orderId, action, user.userId, reason.trim()), () => { setAction(undefined); query.refresh(); receipts.refresh(); });
  }
  if (query.error) return <ErrorPanel error={query.error} onRetry={query.refresh} />;
  if (query.loading || !query.data) return <LoadingState />;
  const order = query.data;
  return <>
    <PageHeader title={order.purchase_order_number} description={`Ngày tạo ${dateTime(order.created_at)} · Người tạo: ${actorName(order.created_by)}`} actions={<>
      {can('updatePurchaseOrders') && order.status === 'DRAFT' && (!can('viewReceipts') || receipts.data?.total === 0) && <Link className="inv-button secondary" to={`/inventory/purchase-orders/${orderId}/edit`}>Sửa đơn</Link>}
      {can('createReceipts') && canReceive(order.status) && <Link className="inv-button" to={`/inventory/goods-receipts/new?purchase_order_id=${orderId}`}>{order.status === 'PARTIALLY_RECEIVED' ? 'Nhập hàng còn lại' : 'Lập phiếu nhập'}</Link>}
      <button className="inv-button secondary" onClick={() => window.print()}>In đơn</button>
    </>} />
    <Panel><div className="pur-detail-overview"><div><Badge status={order.status} /><h2>{can('viewSuppliers') ? <Link to={`/inventory/suppliers/${order.supplier_id}`}>{context.data?.supplier.supplier_name ?? `Nhà cung cấp #${order.supplier_id}`}</Link> : `Nhà cung cấp #${order.supplier_id}`}</h2><p className="inv-muted">{context.data?.supplier.phone}</p></div><dl className="pur-facts"><dt>Ngày đặt</dt><dd>{date(order.order_date)}</dd><dt>Dự kiến nhận</dt><dd>{date(order.expected_delivery_date)}</dd><dt>Tổng giá trị</dt><dd className="pur-total">{money(order.subtotal_amount)}</dd><dt>Nhận đủ</dt><dd>{order.items.filter(item => compareDecimal(item.remaining_quantity, '0') === 0).length}/{order.items.length} dòng</dd></dl></div>
      {order.notes && <p>Ghi chú: {order.notes}</p>}{order.cancellation_reason && <p>Lý do hủy: {order.cancellation_reason}</p>}
      {mutation.error && <><ErrorPanel error={mutation.error} onRetry={query.refresh} /><p className="inv-muted">Tải lại đơn để kiểm tra trạng thái mới nhất trước khi thao tác lại.</p></>}
      <div className="inv-actions">{orderActions(order.status).filter(canTransition).map(status => <button key={status} className={`inv-button ${status === 'CANCELLED' ? 'danger' : ''}`} disabled={mutation.pending} onClick={() => { if (!canTransition(status)) return; setAction(status); setAttempted(false); mutation.clearError(); }}>{actionLabels[status]}</button>)}</div>
    </Panel>
    <Panel title="Nguyên liệu đã đặt">{context.error && <ErrorPanel error={context.error} onRetry={context.refresh} />}<OrderLines order={order} context={context.data} /></Panel>
    {can('viewReceipts') && <Panel title="Phiếu nhập liên quan">{receipts.error ? <ErrorPanel error={receipts.error} onRetry={receipts.refresh} /> : receipts.loading ? <LoadingState /> : !receipts.data?.items.length ? <EmptyState title="Chưa có phiếu nhập" description="Phiếu nháp chưa được tính vào số đã nhập." /> : <><div className="inv-table-wrap"><table className="inv-table pur-table"><thead><tr><th>Mã phiếu</th><th>Ngày nhập</th><th>Số lô</th><th>Trạng thái</th></tr></thead><tbody>{receipts.data.items.map(receipt => <tr key={receipt.goods_receipt_id}><td data-label="Mã phiếu"><Link to={`/inventory/goods-receipts/${receipt.goods_receipt_id}`}>{receipt.receipt_number}</Link></td><td data-label="Ngày nhập">{date(receipt.receipt_date)}</td><td data-label="Số lô">{receipt.items.length}</td><td data-label="Trạng thái"><Badge status={receipt.status} /></td></tr>)}</tbody></table></div><Pagination page={receiptPage} total={receipts.data.total} pageSize={10} onChange={setReceiptPage} /></>}</Panel>}
    <Panel title="Thông tin xử lý"><ul className="pur-history"><li>Tạo đơn lúc {dateTime(order.created_at)} · Người tạo: {actorName(order.created_by)}</li>{order.approved_by && <li>Người duyệt: {actorName(order.approved_by)} · API chưa cung cấp thời điểm duyệt</li>}{order.cancelled_at && <li>Hủy đơn lúc {dateTime(order.cancelled_at)}</li>}<li>Trạng thái hiện tại: {orderStatusLabels[order.status]}</li></ul></Panel>
    <ConfirmDialog open={!!action && canTransition(action)} title={action ? `${actionLabels[action]}?` : ''} pending={mutation.pending} onClose={() => { if (!mutation.pending) setAction(undefined); }} onConfirm={transition}>
      <p>Đơn {order.purchase_order_number} · {money(order.subtotal_amount)} · {order.items.length} dòng nguyên liệu.</p>
      <p>{action === 'CANCELLED' ? 'Đơn bị hủy sẽ không thể tiếp tục nhận hàng.' : action === 'PENDING_APPROVAL' ? 'Sau khi gửi duyệt, nội dung đơn sẽ được khóa chỉnh sửa.' : action === 'APPROVED' ? 'Xác nhận nội dung và giá thỏa thuận trước khi duyệt.' : 'Đơn sẽ sẵn sàng cho lập phiếu nhập. Xác nhận bạn đã đặt hàng với nhà cung cấp.'}</p>
      <CurrentActor />
      {action === 'CANCELLED' && <Field label="Lý do hủy" error={attempted && !reason.trim() ? 'Nhập lý do hủy.' : undefined}><textarea value={reason} onChange={event => setReason(event.target.value)} /></Field>}
      {mutation.error && <ErrorPanel error={mutation.error} />}
    </ConfirmDialog>
  </>;
}
