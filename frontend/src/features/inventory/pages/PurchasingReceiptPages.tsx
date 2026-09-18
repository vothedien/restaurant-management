import { useState } from 'react';
import type { FormEvent } from 'react';
import { flushSync } from 'react-dom';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { cancelGoodsReceipt, confirmGoodsReceipt, createGoodsReceipt, getGoodsReceipt, getPurchaseOrder, getPurchasingContext, listGoodsReceipts, listPurchaseOrders } from '../api/purchasing';
import { Badge, ConfirmDialog, CurrentActor, DecimalInput, EmptyState, ErrorPanel, Field, LoadingState, PageHeader, Pagination, Panel } from '../components/ui';
import { useInventoryAuth } from '../auth/useInventoryAuth';
import { useMutation } from '../hooks/useMutation';
import { useQuery } from '../hooks/useQuery';
import { useUnsavedChanges } from '../hooks/useUnsavedChanges';
import type { PurchaseOrder, ReceiptItemInput } from '../types/purchasing';
import { addDecimal, compareDecimal, date, dateTime, money, multiplyDecimal, quantity } from '../utils/format';
import { canReceive, decimalError, inputDecimal, lineAmount, receiptLineErrors, todayISO } from '../utils/purchasing';
import './PurchasingPages.css';

const pageSize = 20;
function positiveId(value: string | null | undefined) { const id = Number(value); return Number.isSafeInteger(id) && id > 0 ? id : 0; }

export function GoodsReceiptsPage() {
  const { user, can } = useInventoryAuth();
  const [params, setParams] = useSearchParams();
  const page = positiveId(params.get('page')) || 1;
  const query = useQuery(`goods-receipts:${params}`, signal => listGoodsReceipts({ purchase_order_id: positiveId(params.get('purchase_order_id')) || undefined, status: params.get('status') || undefined, date_from: params.get('date_from') || undefined, date_to: params.get('date_to') || undefined, limit: pageSize, offset: (page - 1) * pageSize }, signal));
  const [dateError, setDateError] = useState('');
  function apply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const from = String(data.get('date_from') ?? ''); const to = String(data.get('date_to') ?? '');
    if (from && to && from > to) { setDateError('Ngày bắt đầu không được sau ngày kết thúc.'); return; }
    setDateError('');
    const next = new URLSearchParams();
    ['purchase_order_id', 'status', 'date_from', 'date_to'].forEach(key => { const value = String(data.get(key) ?? ''); if (value) next.set(key, value); });
    setParams(next);
  }
  return <>
    <PageHeader title="Phiếu nhập hàng" description="Đối chiếu từng lần giao, mã lô và hạn dùng trước khi chốt tăng tồn." actions={can('createReceipts') && <Link className="inv-button" to="/inventory/goods-receipts/new">Lập phiếu nhập</Link>} />
    <Panel>
      <form key={params.toString()} className="pur-filters" onSubmit={apply}>
        <Field label="ID đơn mua"><input name="purchase_order_id" type="number" min="1" step="1" defaultValue={params.get('purchase_order_id') ?? ''} placeholder="Tất cả đơn mua" /></Field>
        <Field label="Trạng thái"><select name="status" defaultValue={params.get('status') ?? ''}><option value="">Tất cả trạng thái</option><option value="DRAFT">Nháp</option><option value="CONFIRMED">Đã chốt</option><option value="CANCELLED">Đã hủy</option></select></Field>
        <Field label="Nhập từ ngày"><input type="date" name="date_from" defaultValue={params.get('date_from') ?? ''} /></Field>
        <Field label="Đến ngày" error={dateError}><input type="date" name="date_to" defaultValue={params.get('date_to') ?? ''} /></Field>
        <div className="inv-actions"><button type="submit" className="inv-button">Áp dụng</button><button type="button" className="inv-button secondary" onClick={() => { setParams({}); setDateError(''); }}>Xóa bộ lọc</button></div>
      </form>
      {query.error ? <ErrorPanel error={query.error} onRetry={query.refresh} /> : query.loading ? <LoadingState /> : !query.data?.items.length ? <EmptyState title={params.size ? 'Không tìm thấy phiếu nhập phù hợp' : 'Chưa có phiếu nhập'} description="Chọn một đơn đã đặt hoặc đã nhập một phần để nhận hàng." action={can('createReceipts') && <Link className="inv-button" to="/inventory/goods-receipts/new">Chọn đơn mua</Link>} /> : <>
        <div className="inv-table-wrap"><table className="inv-table pur-table"><caption>Phiếu nhập hàng · {query.data.total} kết quả</caption><thead><tr><th>Mã phiếu</th><th>Đơn mua</th><th>Ngày nhập</th><th>Số lô</th><th>Giá trị</th><th>Người nhận</th><th>Trạng thái</th></tr></thead><tbody>{query.data.items.map(receipt => <tr key={receipt.goods_receipt_id}>
          <td data-label="Mã phiếu"><Link className="inv-link inv-code" to={`/inventory/goods-receipts/${receipt.goods_receipt_id}`}>{receipt.receipt_number}</Link>{receipt.supplier_document_no && <small>Chứng từ: {receipt.supplier_document_no}</small>}</td>
          <td data-label="Đơn mua">{can('viewPurchaseOrders') ? <Link to={`/inventory/purchase-orders/${receipt.purchase_order_id}`}>Đơn mua #{receipt.purchase_order_id}</Link> : `Đơn mua #${receipt.purchase_order_id}`}</td><td data-label="Ngày nhập">{date(receipt.receipt_date)}</td><td data-label="Số lô">{receipt.items.length}</td><td data-label="Giá trị">{money(receipt.items.reduce((sum, line) => addDecimal(sum, line.line_amount), '0'))}</td><td data-label="Người nhận">{user?.userId === receipt.received_by ? user.displayName || user.username : `Tài khoản #${receipt.received_by}`}</td><td data-label="Trạng thái"><Badge status={receipt.status} /></td>
        </tr>)}</tbody></table></div>
        <Pagination page={page} total={query.data.total} pageSize={pageSize} onChange={next => { const copy = new URLSearchParams(params); copy.set('page', String(next)); setParams(copy); }} />
      </>}
    </Panel>
  </>;
}

function ReceivableOrderPicker() {
  const [status, setStatus] = useState('ORDERED');
  const [page, setPage] = useState(1);
  const [id, setId] = useState('');
  const navigate = useNavigate();
  const query = useQuery(`receivable-orders:${status}:${page}`, signal => listPurchaseOrders({ status, limit: pageSize, offset: (page - 1) * pageSize }, signal));
  return <>
    <PageHeader title="Lập phiếu nhập hàng" description="Bước 1 · Chọn đơn đã đặt hoặc đã nhập một phần." />
    <Panel title="Chọn đơn mua">
      <form className="pur-filters" onSubmit={event => { event.preventDefault(); if (positiveId(id)) navigate(`/inventory/goods-receipts/new?purchase_order_id=${id}`); }}>
        <Field label="Trạng thái đơn"><select value={status} onChange={event => { setStatus(event.target.value); setPage(1); }}><option value="ORDERED">Đã đặt hàng</option><option value="PARTIALLY_RECEIVED">Đã nhập một phần</option></select></Field>
        <Field label="Mở nhanh bằng ID đơn"><input type="number" min="1" step="1" value={id} onChange={event => setId(event.target.value)} placeholder="ID đơn mua" /></Field><button className="inv-button secondary" type="submit" disabled={!positiveId(id)}>Mở đơn</button>
      </form>
      {query.error ? <ErrorPanel error={query.error} onRetry={query.refresh} /> : query.loading ? <LoadingState /> : !query.data?.items.length ? <EmptyState title="Chưa có đơn ở trạng thái này" action={<Link to="/inventory/purchase-orders">Mở danh sách đơn mua</Link>} /> : <><div className="inv-table-wrap"><table className="inv-table pur-table"><thead><tr><th>Đơn mua</th><th>Nhà cung cấp</th><th>Dự kiến nhận</th><th>Dòng còn chờ</th><th>Thao tác</th></tr></thead><tbody>{query.data.items.map(order => <tr key={order.purchase_order_id}><td data-label="Đơn mua"><Link to={`/inventory/purchase-orders/${order.purchase_order_id}`}>{order.purchase_order_number}</Link></td><td data-label="Nhà cung cấp"><Link to={`/inventory/suppliers/${order.supplier_id}`}>Nhà cung cấp #{order.supplier_id}</Link></td><td data-label="Dự kiến nhận">{date(order.expected_delivery_date)}</td><td data-label="Dòng còn chờ">{order.items.filter(item => compareDecimal(item.remaining_quantity, '0') > 0).length}</td><td data-label="Thao tác"><Link className="inv-button" to={`/inventory/goods-receipts/new?purchase_order_id=${order.purchase_order_id}`}>Nhận hàng</Link></td></tr>)}</tbody></table></div><Pagination page={page} total={query.data.total} pageSize={pageSize} onChange={setPage} /></>}
    </Panel>
  </>;
}

export function GoodsReceiptEditorPage() {
  const [params] = useSearchParams();
  const id = positiveId(params.get('purchase_order_id'));
  const query = useQuery(`receipt-order:${id}`, signal => id ? getPurchaseOrder(id, signal) : Promise.resolve(undefined));
  if (!params.get('purchase_order_id')) return <ReceivableOrderPicker />;
  if (!id) return <ErrorPanel error={new Error('ID đơn mua không hợp lệ.')} />;
  if (query.error && !query.data) return <ErrorPanel error={query.error} onRetry={query.refresh} />;
  if (!query.data) return <LoadingState />;
  return <>{query.error && <ErrorPanel error={query.error} onRetry={query.refresh} />}<ReceiptForm key={id} order={query.data} refreshOrder={query.refresh} refreshing={query.loading} /></>;
}

interface ReceiptDraftLine extends ReceiptItemInput { key: number }
function ReceiptForm({ order, refreshOrder, refreshing }: { order: PurchaseOrder; refreshOrder: () => void; refreshing: boolean }) {
  const { user, can } = useInventoryAuth();
  const navigate = useNavigate();
  const mutation = useMutation();
  const context = useQuery(`receipt-editor-context:${order.supplier_id}:${can('viewSuppliers')}:${can('viewUnits')}`, signal => can('viewSuppliers') ? getPurchasingContext(order.supplier_id, signal, can('viewUnits')) : Promise.resolve(undefined));
  const [lines, setLines] = useState<ReceiptDraftLine[]>(() => order.items.filter(item => compareDecimal(item.remaining_quantity, '0') > 0).map((item, index) => ({ key: index, purchase_order_item_id: item.purchase_order_item_id, received_quantity: '', actual_unit_price: '', lot_code: '', manufacture_date: '', expiry_date: '' })));
  const [nextKey, setNextKey] = useState(order.items.length);
  const [receiptDate, setReceiptDate] = useState(todayISO());
  const [number, setNumber] = useState('');
  const [supplierDocument, setSupplierDocument] = useState('');
  const [notes, setNotes] = useState('');
  const [dirty, setDirty] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  useUnsavedChanges(dirty);
  const items: ReceiptItemInput[] = lines.filter(line => line.received_quantity.trim() !== '' && (!!decimalError(line.received_quantity, 3) || compareDecimal(inputDecimal(line.received_quantity), '0') !== 0)).map(line => ({ purchase_order_item_id: line.purchase_order_item_id, received_quantity: inputDecimal(line.received_quantity), actual_unit_price: inputDecimal(line.actual_unit_price), lot_code: line.lot_code?.trim() || null, manufacture_date: line.manufacture_date || null, expiry_date: line.expiry_date || null }));
  const errors = receiptLineErrors(order, items, receiptDate);
  const total = items.reduce((sum, item) => addDecimal(sum, lineAmount(item.received_quantity, item.actual_unit_price)), '0');
  const totalsByOrderLine = new Map<number, string>();
  items.forEach(item => { if (!decimalError(item.received_quantity, 3)) totalsByOrderLine.set(item.purchase_order_item_id, addDecimal(totalsByOrderLine.get(item.purchase_order_item_id) ?? '0', item.received_quantity)); });
  function changeLine(key: number, field: keyof ReceiptItemInput, value: string) { setLines(lines.map(line => line.key === key ? { ...line, [field]: value } : line)); setDirty(true); }
  function splitLine(line: ReceiptDraftLine) {
    if (lines.length >= 200) return;
    const position = lines.findIndex(item => item.key === line.key);
    const copy: ReceiptDraftLine = { ...line, key: nextKey, received_quantity: '', actual_unit_price: '', lot_code: '', manufacture_date: '', expiry_date: '' };
    setLines([...lines.slice(0, position + 1), copy, ...lines.slice(position + 1)]); setNextKey(nextKey + 1); setDirty(true);
  }
  async function submit(event: FormEvent) {
    event.preventDefault(); setSubmitted(true);
    if (!user || !can('createReceipts') || mutation.pending || refreshing || !canReceive(order.status) || errors.length) return;
    await mutation.run(() => createGoodsReceipt({ purchase_order_id: order.purchase_order_id, receipt_date: receiptDate, received_by: user.userId, receipt_number: number.trim() || null, supplier_document_no: supplierDocument.trim() || null, notes: notes.trim() || null, items }), receipt => {
      flushSync(() => setDirty(false)); navigate(`/inventory/goods-receipts/${receipt.goods_receipt_id}`);
    });
  }
  return <>
    <PageHeader title="Nhận hàng từ đơn mua" description={`Bước 2 · ${order.purchase_order_number} · Nhập đúng số lượng giao lần này.`} actions={<Link className="inv-button secondary" to={`/inventory/purchase-orders/${order.purchase_order_id}`}>Xem đơn mua</Link>} />
    {!canReceive(order.status) && <div className="pur-error" role="alert">Đơn mua hiện không cho phép nhận hàng. Chỉ đơn đã đặt hoặc đã nhập một phần được lập phiếu nhập. Dữ liệu đang nhập được giữ lại để đối chiếu.</div>}
    {refreshing && <p role="status" className="inv-muted">Đang cập nhật số còn phải nhập; các dòng đã nhập được giữ nguyên.</p>}
    <form className="pur-editor" onSubmit={submit} noValidate>
      <div className="pur-editor-main">
        <Panel title={context.data?.supplier.supplier_name ?? `Nhà cung cấp #${order.supplier_id}`}><div className="inv-form-grid">
          <Field label="Ngày nhập"><input type="date" value={receiptDate} min={order.order_date} max={todayISO()} required onChange={event => { setReceiptDate(event.target.value); setDirty(true); }} /></Field>
          <Field label="Mã phiếu (tự tạo nếu để trống)"><input value={number} maxLength={40} onChange={event => { setNumber(event.target.value); setDirty(true); }} /></Field>
          <Field label="Số chứng từ nhà cung cấp"><input value={supplierDocument} maxLength={80} onChange={event => { setSupplierDocument(event.target.value); setDirty(true); }} /></Field>
          <CurrentActor label="Người nhận hàng" />
        </div>{context.error && <ErrorPanel error={context.error} onRetry={context.refresh} />}</Panel>
        <Panel title="Đối chiếu và nhận hàng">
          <p className="pur-notice">Số lượng nhập lần này mặc định để trống. Dòng để trống hoặc bằng 0 sẽ không được đưa vào phiếu. Tách lô khi cùng nguyên liệu có mã lô hoặc hạn dùng khác nhau.</p>
          <div className="pur-receiving-lines">{lines.map((line, index) => {
            const po = order.items.find(item => item.purchase_order_item_id === line.purchase_order_item_id)!;
            const mapping = context.data?.mappings.find(item => item.supplier_ingredient_id === po.supplier_ingredient_id);
            const unit = context.data?.units.find(item => item.unit_id === po.purchase_unit_id)?.unit_code ?? `đơn vị #${po.purchase_unit_id}`;
            const baseUnit = context.data?.units.find(item => item.unit_id === mapping?.ingredient.base_unit_id)?.unit_code ?? 'đơn vị cơ sở';
            const validQty = !!line.received_quantity && !decimalError(line.received_quantity, 3);
            const aggregate = totalsByOrderLine.get(po.purchase_order_item_id) ?? '0';
            const over = compareDecimal(aggregate, po.remaining_quantity) > 0;
            const participates = line.received_quantity.trim() !== '' && (!validQty || compareDecimal(inputDecimal(line.received_quantity), '0') > 0);
            return <section key={line.key} className={`pur-receiving-line${over ? ' has-error' : ''}`} aria-label={`Dòng nhận hàng ${index + 1}`}>
              <div className="pur-receiving-title"><h3>{index + 1}. {mapping?.ingredient.ingredient_name ?? `Dòng đơn #${po.purchase_order_item_id}`}</h3><div className="inv-actions"><button type="button" className="inv-button secondary" disabled={lines.length >= 200} onClick={() => splitLine(line)}>Tách thêm lô</button>{lines.filter(item => item.purchase_order_item_id === po.purchase_order_item_id).length > 1 && <button type="button" className="inv-button secondary" aria-label={`Bỏ lô dòng ${index + 1}`} onClick={() => { setLines(lines.filter(item => item.key !== line.key)); setDirty(true); }}>Bỏ lô</button>}</div></div>
              <dl className="pur-receiving-comparison"><div><dt>Số đặt</dt><dd>{quantity(po.ordered_quantity)} {unit}</dd></div><div><dt>Đã nhập</dt><dd>{quantity(po.received_quantity)} {unit}</dd></div><div><dt>Còn phải nhập</dt><dd className="pur-remaining">{quantity(po.remaining_quantity)} {unit}</dd></div><div><dt>Tổng nhận lần này</dt><dd>{quantity(aggregate)} {unit}</dd></div></dl>
              <div className="inv-form-grid">
                <Field label={`Số lượng nhập lần này · dòng ${index + 1} (${unit})`} error={over ? 'Tổng các lô vượt số còn phải nhập.' : submitted && participates ? decimalError(line.received_quantity, 3, true) : undefined}><DecimalInput value={line.received_quantity} onChange={value => changeLine(line.key, 'received_quantity', value)} placeholder="0" /></Field>
                <Field label={`Đơn giá thực nhận · dòng ${index + 1} (VND)`} error={submitted && participates ? decimalError(line.actual_unit_price, 2) : undefined}><DecimalInput value={line.actual_unit_price} onChange={value => changeLine(line.key, 'actual_unit_price', value)} placeholder="Nhập giá thực nhận" /></Field>
                <Field label={`Mã lô · dòng ${index + 1}`}><input value={line.lot_code ?? ''} maxLength={80} onChange={event => changeLine(line.key, 'lot_code', event.target.value)} placeholder="Tự tạo nếu để trống" /></Field>
                <Field label={`Ngày sản xuất · dòng ${index + 1}`}><input type="date" max={receiptDate} value={line.manufacture_date ?? ''} onChange={event => changeLine(line.key, 'manufacture_date', event.target.value)} /></Field>
                <Field label={`Hạn sử dụng · dòng ${index + 1}`} error={line.expiry_date && line.expiry_date < receiptDate ? 'Hàng đã hết hạn tại ngày nhập.' : undefined}><input type="date" min={receiptDate} value={line.expiry_date ?? ''} onChange={event => changeLine(line.key, 'expiry_date', event.target.value)} /></Field>
              </div>
              <div className="pur-line-footer"><span>Quy đổi lần này: <strong>{validQty ? quantity(multiplyDecimal(inputDecimal(line.received_quantity), po.base_qty_per_purchase_unit)) : '—'} {baseUnit}</strong></span><span>Giá theo đơn: {money(po.expected_unit_price)} / {unit}</span><span>Thành tiền: <strong>{money(lineAmount(line.received_quantity, line.actual_unit_price))}</strong></span></div>
              {line.expiry_date && line.expiry_date < todayISO() && line.expiry_date >= receiptDate && <p className="pur-warning">Lô đã hết hạn ở thời điểm hiện tại. Nếu chốt phiếu hồi tố, lô sẽ mang trạng thái hết hạn và không được xuất.</p>}
            </section>;
          })}</div>
        </Panel>
        <Panel title="Ghi chú nhận hàng"><Field label="Ghi chú"><textarea rows={3} value={notes} onChange={event => { setNotes(event.target.value); setDirty(true); }} /></Field></Panel>
      </div>
      <aside className="pur-summary"><Panel title="Tóm tắt lần nhập"><dl className="pur-facts"><dt>Đơn mua</dt><dd>{order.purchase_order_number}</dd><dt>Dòng lô sẽ nhận</dt><dd>{items.length}</dd><dt>Nguyên liệu nhận</dt><dd>{new Set(items.map(item => item.purchase_order_item_id)).size}</dd><dt>Giá trị lần nhập</dt><dd className="pur-total">{money(total)}</dd><dt>Sau khi lưu</dt><dd><Badge status="DRAFT" /></dd></dl>
        <p className="inv-muted">Phiếu nháp chưa tăng tồn và không giữ chỗ số lượng còn lại. Sau khi lưu, kiểm tra và chốt phiếu tại trang chi tiết.</p>
        {submitted && !!errors.length && <div className="pur-error" role="alert"><strong>Kiểm tra trước khi lưu</strong><ul>{errors.map((error, index) => <li key={index}>{error}</li>)}</ul></div>}
        {mutation.error && <><ErrorPanel error={mutation.error} /><p className="inv-muted">Các dòng đã nhập được giữ nguyên. Tải lại số còn phải nhập để đối chiếu nếu đơn có phiếu vừa được chốt.</p><button type="button" className="inv-button secondary" onClick={refreshOrder}>Cập nhật số còn phải nhập</button></>}
        <div className="pur-submit">{can('createReceipts') && <button className="inv-button" type="submit" disabled={!user || mutation.pending || refreshing || !canReceive(order.status)}>{mutation.pending ? 'Đang lưu…' : 'Lưu phiếu nháp'}</button>}<Link className="inv-button secondary" to={`/inventory/purchase-orders/${order.purchase_order_id}`}>Hủy thao tác</Link></div>
      </Panel></aside>
    </form>
  </>;
}

export function GoodsReceiptDetailPage() {
  const { user, can } = useInventoryAuth();
  const { id } = useParams();
  const receiptId = positiveId(id);
  const query = useQuery(`goods-receipt:${id}`, signal => receiptId ? getGoodsReceipt(receiptId, signal) : Promise.reject(new Error('ID phiếu nhập không hợp lệ.')));
  const order = useQuery(`receipt-detail-order:${query.data?.purchase_order_id ?? ''}:${can('viewPurchaseOrders')}`, signal => query.data && can('viewPurchaseOrders') ? getPurchaseOrder(query.data.purchase_order_id, signal) : Promise.resolve(undefined));
  const context = useQuery(`receipt-detail-context:${order.data?.supplier_id ?? ''}:${can('viewSuppliers')}:${can('viewUnits')}`, signal => order.data && can('viewSuppliers') ? getPurchasingContext(order.data.supplier_id, signal, can('viewUnits')) : Promise.resolve(undefined));
  const mutation = useMutation();
  const [action, setAction] = useState<'confirm' | 'cancel' | undefined>();
  async function performAction() {
    if (!user || !action || !can(action === 'confirm' ? 'finalizeReceipts' : 'cancelReceipts') || query.data?.status !== 'DRAFT' || (action === 'confirm' && (!receivable || excessive))) return;
    await mutation.run(() => action === 'confirm' ? confirmGoodsReceipt(receiptId) : cancelGoodsReceipt(receiptId), () => { setAction(undefined); query.refresh(); order.refresh(); });
  }
  if (query.error) return <ErrorPanel error={query.error} onRetry={query.refresh} />;
  if (query.loading || !query.data) return <LoadingState />;
  const receipt = query.data;
  const total = receipt.items.reduce((sum, item) => addDecimal(sum, item.line_amount), '0');
  const receivable = order.data && canReceive(order.data.status);
  const totalByItem = new Map<number, string>();
  receipt.items.forEach(item => totalByItem.set(item.purchase_order_item_id, addDecimal(totalByItem.get(item.purchase_order_item_id) ?? '0', item.received_quantity)));
  const excessive = !!order.data && [...totalByItem].some(([itemId, qty]) => { const po = order.data!.items.find(item => item.purchase_order_item_id === itemId); return !po || compareDecimal(qty, po.remaining_quantity) > 0; });
  return <>
    <PageHeader title={receipt.receipt_number} description={`Tạo lúc ${dateTime(receipt.created_at)} · Người nhận: ${user?.userId === receipt.received_by ? user.displayName || user.username : `Tài khoản #${receipt.received_by}`}`} actions={<>
      {receipt.status === 'DRAFT' && <>{can('finalizeReceipts') && <button className="inv-button" disabled={mutation.pending || !receivable || excessive} onClick={() => { if (!can('finalizeReceipts')) return; mutation.clearError(); setAction('confirm'); }}>Chốt phiếu nhập</button>}{can('cancelReceipts') && <button className="inv-button danger" disabled={mutation.pending} onClick={() => { if (!can('cancelReceipts')) return; mutation.clearError(); setAction('cancel'); }}>Hủy phiếu nháp</button>}</>}
      <button className="inv-button secondary" onClick={() => window.print()}>In phiếu</button>
    </>} />
    <Panel><div className="pur-detail-overview"><div><Badge status={receipt.status} /><h2>{context.data?.supplier.supplier_name ?? (order.data ? `Nhà cung cấp #${order.data.supplier_id}` : 'Thông tin nhận hàng')}</h2>{can('viewPurchaseOrders') ? <Link to={`/inventory/purchase-orders/${receipt.purchase_order_id}`}>{order.data?.purchase_order_number ?? `Đơn mua #${receipt.purchase_order_id}`}</Link> : `Đơn mua #${receipt.purchase_order_id}`}</div><dl className="pur-facts"><dt>Ngày nhập</dt><dd>{date(receipt.receipt_date)}</dd><dt>Số chứng từ</dt><dd>{receipt.supplier_document_no || '—'}</dd><dt>Số lô</dt><dd>{receipt.items.length}</dd><dt>Giá trị</dt><dd className="pur-total">{money(total)}</dd></dl></div>
      {receipt.notes && <p>Ghi chú: {receipt.notes}</p>}
      {receipt.status === 'DRAFT' && <p className="pur-notice">Phiếu đang ở trạng thái nháp. Chốt phiếu mới tạo lô và tăng tồn kho. Nếu nội dung sai, hủy phiếu và lập lại vì API chưa hỗ trợ sửa phiếu nhập.</p>}
      {receipt.status === 'DRAFT' && order.data && (!receivable || excessive) && <div className="pur-error" role="alert"><p>{!receivable ? 'Đơn mua hiện không cho phép nhận hàng.' : 'Lượng trên phiếu vượt số còn lại hiện tại của đơn mua.'} Hãy đối chiếu đơn, hủy phiếu nháp và lập lại khi phù hợp.</p><button type="button" className="inv-button secondary" onClick={order.refresh}>Tải lại đơn mua</button></div>}
      {receipt.status === 'CONFIRMED' && <div className="pur-success" role="status"><strong>Đã chốt {receipt.receipt_number}.</strong> Tồn kho và trạng thái đơn mua đã được backend cập nhật. Mỗi dòng dưới đây tương ứng một lô nhập.</div>}
      {receipt.status === 'CANCELLED' && can('createReceipts') && <Link className="inv-button" to={`/inventory/goods-receipts/new?purchase_order_id=${receipt.purchase_order_id}`}>Lập phiếu mới từ đơn mua</Link>}
      {mutation.error && <><ErrorPanel error={mutation.error} /><p className="inv-muted">Phiếu được giữ để đối chiếu. Nếu mã lô trùng hoặc đơn đã nhận thêm hàng, tải lại dữ liệu; hủy nháp rồi lập phiếu mới với mã lô hoặc số lượng đúng.</p><button type="button" className="inv-button secondary" onClick={() => { query.refresh(); order.refresh(); }}>Tải lại phiếu và đơn mua</button></>}
      {order.error && <ErrorPanel error={order.error} onRetry={order.refresh} />}
    </Panel>
    <Panel title="Chi tiết lô nhận">
      {context.error && <ErrorPanel error={context.error} onRetry={context.refresh} />}
      <div className="inv-table-wrap"><table className="inv-table pur-table"><caption>Số nhận theo đơn vị mua · Số nhập kho theo đơn vị cơ sở</caption><thead><tr><th>Nguyên liệu / Mã lô</th><th>Số nhận</th><th>Nhập kho</th><th>Ngày sản xuất</th><th>Hạn sử dụng</th><th>Đơn giá</th><th>Thành tiền</th>{receipt.status === 'CONFIRMED' && can('viewStock') && <th>Tra cứu kho</th>}</tr></thead><tbody>{receipt.items.map(item => {
        const po = order.data?.items.find(line => line.purchase_order_item_id === item.purchase_order_item_id);
        const mapping = context.data?.mappings.find(line => line.supplier_ingredient_id === po?.supplier_ingredient_id);
        const unit = context.data?.units.find(value => value.unit_id === item.purchase_unit_id)?.unit_code ?? `đơn vị #${item.purchase_unit_id}`;
        const baseUnit = context.data?.units.find(value => value.unit_id === mapping?.ingredient.base_unit_id)?.unit_code ?? 'đơn vị cơ sở';
        return <tr key={item.goods_receipt_item_id}><td data-label="Nguyên liệu / Mã lô"><strong>{mapping?.ingredient.ingredient_name ?? `Dòng đơn #${item.purchase_order_item_id}`}</strong><small className="inv-code">{item.lot_code ?? '—'}</small></td><td data-label="Số nhận">{quantity(item.received_quantity)} {unit}</td><td data-label="Nhập kho">{quantity(item.base_quantity)} {baseUnit}</td><td data-label="Ngày sản xuất">{date(item.manufacture_date ?? null)}</td><td data-label="Hạn sử dụng">{date(item.expiry_date ?? null)}{item.expiry_date && item.expiry_date < todayISO() && <small className="pur-warning">Đã hết hạn</small>}</td><td data-label="Đơn giá">{money(item.actual_unit_price)}</td><td data-label="Thành tiền">{money(item.line_amount)}</td>{receipt.status === 'CONFIRMED' && can('viewStock') && <td data-label="Tra cứu kho">{mapping ? <div className="inv-actions"><Link to={`/inventory/lots?ingredient_id=${mapping.ingredient_id}`}>Lô của nguyên liệu</Link><Link to={`/inventory/movements?ingredient_id=${mapping.ingredient_id}&movement_type=RECEIPT`}>Biến động nhập</Link></div> : <Link to="/inventory/lots">Danh sách lô</Link>}</td>}</tr>;
      })}</tbody></table></div>
      {receipt.status === 'CONFIRMED' && <p className="inv-muted">Dùng mã lô để đối chiếu trong danh sách lô của nguyên liệu. API phiếu nhập chưa trả về ID lô để mở trực tiếp.</p>}
    </Panel>
    <ConfirmDialog open={!!action && can(action === 'confirm' ? 'finalizeReceipts' : 'cancelReceipts')} title={action === 'confirm' ? 'Chốt phiếu và tăng tồn kho?' : 'Hủy phiếu nhập nháp?'} pending={mutation.pending} onClose={() => { if (!mutation.pending) setAction(undefined); }} onConfirm={performAction}>
      <CurrentActor />
      {action === 'confirm' ? <><p>Phiếu {receipt.receipt_number} · {receipt.items.length} lô · {money(total)}.</p><ul className="pur-confirm-lines">{receipt.items.map(item => <li key={item.goods_receipt_item_id}>{item.lot_code}: <strong>+{quantity(item.base_quantity)}</strong> {context.data?.units.find(unit => unit.unit_id === context.data?.mappings.find(mapping => mapping.supplier_ingredient_id === order.data?.items.find(line => line.purchase_order_item_id === item.purchase_order_item_id)?.supplier_ingredient_id)?.ingredient.base_unit_id)?.unit_code ?? 'đơn vị cơ sở'}</li>)}</ul><p>Thao tác tạo {receipt.items.length} lô, ghi biến động nhập và cập nhật số đã nhận của đơn mua. Sau khi chốt, phiếu không thể sửa hoặc hủy.</p><p>Backend kiểm tra lại số còn lại khi chốt; phiếu nháp không giữ chỗ lượng hàng.</p></> : <p>Phiếu {receipt.receipt_number} sẽ bị hủy. Phiếu nháp chưa tạo lô nên thao tác này không làm thay đổi tồn kho.</p>}
      {mutation.error && <ErrorPanel error={mutation.error} />}
    </ConfirmDialog>
  </>;
}
