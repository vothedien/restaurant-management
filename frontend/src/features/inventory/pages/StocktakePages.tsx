import { useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { cancelStocktake, completeStocktake, countStocktake, createStocktake, getLotContexts, getStocktake, listStocktakes, startStocktake } from '../api/operations';
import { OperationLotPicker } from '../components/OperationsFields';
import { Badge, ConfirmDialog, CurrentActor, EmptyState, ErrorPanel, Field, LoadingState, Modal, PageHeader, Pagination, Panel } from '../components/ui';
import { useInventoryAuth } from '../auth/useInventoryAuth';
import { useMutation } from '../hooks/useMutation';
import { useQuery } from '../hooks/useQuery';
import { useUnsavedChanges } from '../hooks/useUnsavedChanges';
import type { CountDraft, CountFilter, OperationLot, StocktakeDetail, StocktakeItem, StocktakeStatus } from '../types/operations';
import { date, dateTime, quantity, subtractDecimal, compareDecimal } from '../utils/format';
import { errorInfo } from '../utils/errors';
import { countState, draftFor, matchesCountFilter, quantityError, validActor } from '../utils/operations';
import './operations.css';

const statuses: { value: StocktakeStatus; label: string }[] = [{ value: 'DRAFT', label: 'Nháp' }, { value: 'IN_PROGRESS', label: 'Đang kiểm kê' }, { value: 'COMPLETED', label: 'Đã chốt' }, { value: 'CANCELLED', label: 'Đã hủy' }];

export function StocktakesPage() {
  const { user, can } = useInventoryAuth();
  const [params, setParams] = useSearchParams();
  const page = Math.max(1, Number(params.get('page')) || 1);
  const status = statuses.find(item => item.value === params.get('status'))?.value;
  const query = useQuery(`stocktakes:${page}:${status ?? ''}`, signal => listStocktakes(page, status, signal));
  function change(value: string, nextPage = 1) { const next = new URLSearchParams(); if (value) next.set('status', value); if (nextPage > 1) next.set('page', String(nextPage)); setParams(next); }
  return <>
    <PageHeader title="Kiểm kê" description="Ghi nhận số đếm thực tế, đối chiếu chênh lệch và chốt điều chỉnh kho." actions={can('createStocktakes') && <Link className="inv-button" to="/inventory/stocktakes/new">Tạo kiểm kê</Link>} />
    <Panel><Field label="Trạng thái"><select value={status ?? ''} onChange={event => change(event.target.value)}><option value="">Tất cả trạng thái</option>{statuses.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}</select></Field></Panel>
    {query.loading && <LoadingState />}
    {Boolean(query.error) && <ErrorPanel error={query.error} onRetry={query.refresh} />}
    {query.data && !query.loading && (query.data.items.length ? <Panel>
      <div className="inv-table-wrap"><table className="inv-table"><caption>Phiếu kiểm kê · tiến độ và chênh lệch hiển thị trong chi tiết phiếu</caption><thead><tr><th>Mã phiếu</th><th>Ngày tạo</th><th>Bắt đầu</th><th>Trạng thái</th><th>Người tạo</th><th>Ghi chú</th><th>Thao tác</th></tr></thead><tbody>{query.data.items.map(item => <tr key={item.stocktake_id}>
        <td><Link className="inv-code" to={`/inventory/stocktakes/${item.stocktake_id}`}>{item.stocktake_number}</Link></td><td>{dateTime(item.created_at)}</td><td>{dateTime(item.started_at)}</td><td><Badge status={item.status} /></td><td>{item.created_by === user?.userId ? user.displayName : `Nhân viên #${item.created_by}`}</td><td>{item.notes || '—'}</td><td><Link to={`/inventory/stocktakes/${item.stocktake_id}`}>{can('countStocktakes') && (item.status === 'DRAFT' || item.status === 'IN_PROGRESS') ? 'Tiếp tục' : 'Xem chi tiết'}</Link></td>
      </tr>)}</tbody></table></div><Pagination page={page} total={query.data.total} pageSize={20} onChange={next => change(status ?? '', next)} />
    </Panel> : <EmptyState title={status ? 'Không có phiếu ở trạng thái này' : 'Chưa có phiếu kiểm kê'} description="Tạo phiếu và chọn các lô cần kiểm đếm." action={status ? <button className="inv-button secondary" onClick={() => change('')}>Xóa bộ lọc</button> : can('createStocktakes') && <Link className="inv-button" to="/inventory/stocktakes/new">Tạo kiểm kê</Link>} />)}
  </>;
}

export function StocktakeCreatePage() {
  const { user, can } = useInventoryAuth();
  const [number, setNumber] = useState(''); const [notes, setNotes] = useState('');
  const [selected, setSelected] = useState<OperationLot[]>([]); const [saved, setSaved] = useState(false);
  const mutation = useMutation(); const navigate = useNavigate();
  useUnsavedChanges(!saved && Boolean(number || notes || selected.length));
  async function submit(event: React.FormEvent) {
    event.preventDefault(); if (!user || !can('createStocktakes')) return;
    await mutation.run(() => createStocktake({ created_by: user.userId, stocktake_number: number.trim() || undefined, notes: notes.trim() || undefined }), result => { flushSync(() => setSaved(true)); navigate(`/inventory/stocktakes/${result.stocktake_id}`, { state: { selectedLots: selected } }); });
  }
  if (!user || !can('createStocktakes')) return <EmptyState title="Không đủ quyền truy cập" action={<Link to="/inventory">Về tổng quan kho</Link>} />;
  return <>
    <PageHeader title="Tạo phiếu kiểm kê" description="Chọn phạm vi trước; số tồn hệ thống được ghi nhận khi bạn bắt đầu kiểm kê." actions={<Link className="inv-button secondary" to="/inventory/stocktakes">Danh sách kiểm kê</Link>} />
    <form onSubmit={submit}><Panel title="1. Thông tin phiếu"><div className="inv-form-grid">
      <Field label="Mã phiếu (không bắt buộc)"><input value={number} maxLength={40} onChange={event => setNumber(event.target.value)} placeholder="Để trống để tạo mã tự động" disabled={mutation.pending} /></Field>
      <CurrentActor label="Người tạo" />
      <Field label="Ghi chú"><textarea value={notes} maxLength={2000} onChange={event => setNotes(event.target.value)} rows={3} disabled={mutation.pending} /></Field>
    </div></Panel>
    {can('viewStock') && <Panel title="2. Chọn lô cần kiểm"><OperationLotPicker selected={selected} onChange={setSelected} disabled={mutation.pending} /></Panel>}
    {Boolean(mutation.error) && <ErrorPanel error={mutation.error} />}
    <div className="inv-count-sticky"><span className="inv-muted">{selected.length} lô được chọn · phiếu mới ở trạng thái Nháp</span><button className="inv-button" disabled={mutation.pending} type="submit">{mutation.pending ? 'Đang tạo…' : 'Tạo phiếu nháp'}</button></div></form>
  </>;
}

export function StocktakeDetailPage() {
  const { id } = useParams(); const validId = validActor(id ?? '');
  const query = useQuery(`stocktake:${id}`, signal => validId ? getStocktake(Number(id), signal) : Promise.reject(new Error('Mã phiếu kiểm kê không hợp lệ.')));
  if (!query.data) return query.error ? <ErrorPanel error={query.error} onRetry={query.refresh} /> : <LoadingState />;
  return <StocktakeEditor key={id} initial={query.data} />;
}

function StocktakeEditor({ initial }: { initial: StocktakeDetail }) {
  const { user, can } = useInventoryAuth();
  const [document, setDocument] = useState(initial);
  const location = useLocation();
  const [selected, setSelected] = useState<OperationLot[]>(() => (location.state as { selectedLots?: OperationLot[] } | null)?.selectedLots ?? []);
  const [drafts, setDrafts] = useState<Record<number, CountDraft>>({});
  const [filter, setFilter] = useState<CountFilter>('all'); const [page, setPage] = useState(1); const [mobileIndex, setMobileIndex] = useState(0);
  const [action, setAction] = useState<'start' | 'complete' | 'cancel' | null>(null);
  const [message, setMessage] = useState(''); const [validation, setValidation] = useState(''); const [conflict, setConflict] = useState<unknown>();
  const mutation = useMutation(); const refreshMutation = useMutation(); const locked = useRef(false);
  const inputs = useRef<Record<string, HTMLInputElement | null>>({});
  const inProgress = document.status === 'IN_PROGRESS';
  const editable = inProgress && can('countStocktakes') && can('viewStock'); const dirty = Object.keys(drafts).length > 0;
  useUnsavedChanges(dirty || (document.status === 'DRAFT' && selected.length > 0));
  const draft = (item: StocktakeItem) => drafts[item.stocktake_item_id] ?? draftFor(item);
  const filtered = document.items.filter(item => matchesCountFilter(item, draft(item), filter));
  const effectivePage = Math.min(page, Math.max(1, Math.ceil(filtered.length / 20)));
  const visible = filtered.slice((effectivePage - 1) * 20, effectivePage * 20);
  const ids = visible.map(item => item.stock_lot_id).join(',');
  const viewStock = can('viewStock');
  const contexts = useQuery(`count-contexts:${document.stocktake_id}:${ids}:${viewStock}`, signal => getLotContexts(viewStock && ids ? ids.split(',').map(Number) : [], signal));
  const states = document.items.map(item => countState(item, draft(item)));
  const counted = states.filter(state => state !== 'uncounted').length;
  const matched = states.filter(state => state === 'matched').length;
  const increases = document.items.filter(item => countState(item, draft(item)) === 'difference' && compareDecimal(draft(item).actual.replace(',', '.'), item.system_quantity) > 0).length;
  const decreases = counted - matched - increases;
  const current = visible[Math.min(mobileIndex, Math.max(0, visible.length - 1))];
  const conflictTitle = conflict && errorInfo(conflict).message.includes('Tồn kho đã thay đổi') ? 'Dữ liệu tồn kho đã thay đổi' : 'Có xung đột khi ghi phiếu kiểm kê';

  async function reloadDocument() {
    await refreshMutation.run(async () => {
      const fresh = await getStocktake(document.stocktake_id);
      setDocument(fresh); contexts.refresh();
      setMessage('Đã tải trạng thái phiếu và tồn hiện tại; số đếm chưa lưu được giữ để đối chiếu.');
    });
  }

  function update(item: StocktakeItem, changes: Partial<CountDraft>) { if (!user || !editable) return; setMessage(''); setDrafts(previous => ({ ...previous, [item.stocktake_item_id]: { ...(previous[item.stocktake_item_id] ?? draftFor(item)), ...changes } })); }
  function verify(item: StocktakeItem) {
    if (!user || !editable) return false;
    const value = draft(item); const error = quantityError(value.actual);
    if (error) { setValidation(`Lô #${item.stock_lot_id}: ${error}`); return false; }
    const reason = value.reason.trim() || (compareDecimal(value.actual.replace(',', '.'), item.system_quantity) === 0 ? 'Đã kiểm đếm, khớp tồn hệ thống' : '');
    if (!reason) { setValidation(`Lô #${item.stock_lot_id}: ghi lý do cho số đếm chênh lệch.`); return false; }
    setValidation(''); update(item, { verified: true, reason }); return true;
  }
  function lineError(item: StocktakeItem) {
    const value = draft(item); if (!value.actual) return undefined;
    const error = quantityError(value.actual); if (error) return error;
    const lot = contexts.data?.[item.stock_lot_id]?.lot;
    if (lot && compareDecimal(value.actual.replace(',', '.'), lot.received_quantity) > 0) return `Tối đa ${quantity(lot.received_quantity)} theo lượng nhận gốc của lô.`;
  }
  async function save() {
    if (!user || locked.current || !editable) return;
    const entries = document.items.filter(item => drafts[item.stocktake_item_id]);
    const invalid = entries.find(item => countState(item, draft(item)) === 'uncounted' || lineError(item));
    if (invalid) { setValidation(`Lô #${invalid.stock_lot_id}: ${lineError(invalid) || 'nhập số thực tế, lý do và xác nhận số đếm trước khi lưu.'}`); return; }
    locked.current = true; setValidation(''); setMessage('');
    try {
      await mutation.run(async () => {
        for (const item of entries) {
          try {
            const next = await countStocktake(document.stocktake_id, item.stocktake_item_id, draft(item));
            setDocument(next); setDrafts(previous => { const nextDrafts = { ...previous }; delete nextDrafts[item.stocktake_item_id]; return nextDrafts; });
          } catch (error) { if (errorInfo(error).status === 409) setConflict(error); throw error; }
        }
        setMessage(`Đã lưu ${entries.length} số đếm. Tồn kho chỉ thay đổi khi chốt phiếu.`);
      });
    } finally { locked.current = false; }
  }
  async function performAction() {
    if (!user || !action || !can(action === 'start' ? 'countStocktakes' : 'finalizeStocktakes') || (action === 'start' && !can('viewStock'))) return;
    await mutation.run(async () => {
      try {
        const result = action === 'start' ? await startStocktake(document.stocktake_id, selected.map(lot => lot.stock_lot_id)) : action === 'complete' ? await completeStocktake(document.stocktake_id, user.userId) : await cancelStocktake(document.stocktake_id);
        setDocument(result); setDrafts({}); setSelected([]); setAction(null); setMessage(action === 'start' ? 'Đã ghi nhận tồn hệ thống. Bạn có thể bắt đầu đếm.' : action === 'complete' ? `Đã chốt phiếu ${result.stocktake_number}. Tồn và biến động kho đã được cập nhật.` : 'Đã hủy phiếu kiểm kê.');
      } catch (error) { setAction(null); if (errorInfo(error).status === 409) setConflict(error); throw error; }
    });
  }
  function changeMobile(next: number) {
    if (next < 0 && effectivePage > 1) { setPage(effectivePage - 1); setMobileIndex(19); }
    else if (next >= visible.length && effectivePage * 20 < filtered.length) { setPage(effectivePage + 1); setMobileIndex(0); }
    else setMobileIndex(Math.max(0, Math.min(next, visible.length - 1)));
  }
  function amountInput(item: StocktakeItem, mobile: boolean) {
    const value = draft(item); const key = `${mobile ? 'mobile' : 'desktop'}-${item.stocktake_item_id}`;
    return <input ref={node => { inputs.current[key] = node; }} className="inv-count-input" type="text" inputMode="decimal" aria-label={`Số thực tế lô ${contexts.data?.[item.stock_lot_id]?.lot.lot_code ?? item.stock_lot_id}`} value={value.actual} disabled={!editable || mutation.pending || !contexts.data?.[item.stock_lot_id]} placeholder="Chưa kiểm" onChange={event => update(item, { actual: event.target.value, verified: false })} onKeyDown={event => {
      if (event.key !== 'Enter') return; event.preventDefault(); if (!verify(item)) return;
      const next = visible[visible.indexOf(item) + 1]; if (mobile) changeMobile(mobileIndex + 1); else if (next) inputs.current[`desktop-${next.stocktake_item_id}`]?.focus();
    }} />;
  }
  function reasonInput(item: StocktakeItem) { return <input className="inv-count-reason" aria-label={`Lý do lô ${contexts.data?.[item.stock_lot_id]?.lot.lot_code ?? item.stock_lot_id}`} value={draft(item).reason} maxLength={2000} disabled={!editable || mutation.pending} placeholder="Lý do chênh lệch / xác nhận" onChange={event => update(item, { reason: event.target.value, verified: false })} />; }
  function marker(item: StocktakeItem) { const state = countState(item, draft(item)); return <><span className={`inv-count-state ${state}`}>{state === 'uncounted' ? '○ Chưa kiểm' : state === 'matched' ? '✓ Khớp' : '≠ Chênh lệch'}</span>{editable && <button type="button" className="inv-button secondary" disabled={mutation.pending || state !== 'uncounted' || !draft(item).actual} onClick={() => verify(item)}>Xác nhận số đếm</button>}</>; }
  function variance(item: StocktakeItem) { const value = draft(item).actual; return !value || quantityError(value) ? '—' : quantity(subtractDecimal(value.replace(',', '.'), item.system_quantity)); }

  return <div className="inv-operations-page">
    <PageHeader title={document.stocktake_number} description={`Tạo ${dateTime(document.created_at)} · Người tạo ${document.created_by === user?.userId ? user.displayName : `#${document.created_by}`}`} actions={<><Badge status={document.status} /><button className="inv-button secondary" disabled={mutation.pending || refreshMutation.pending} onClick={reloadDocument}>Tải lại phiếu</button><Link className="inv-button secondary" to="/inventory/stocktakes">Danh sách</Link></>} />
    {document.notes && <p className="inv-operation-notice">{document.notes}</p>}
    <p className="inv-muted">Bắt đầu: {dateTime(document.started_at)} · Chốt: {dateTime(document.completed_at)}{document.completed_by ? ` · Người chốt ${document.completed_by === user?.userId ? user.displayName : `#${document.completed_by}`}` : ''}</p>
    {message && <div className="inv-operation-notice" role="status">{message}</div>}
    {Boolean(mutation.error) && <ErrorPanel error={mutation.error} />}
    {Boolean(refreshMutation.error) && <ErrorPanel error={refreshMutation.error} onRetry={reloadDocument} />}
    {validation && <div role="alert" className="inv-operation-notice inv-operation-warning">{validation}</div>}
    {document.status === 'DRAFT' ? <Panel title="Phạm vi kiểm kê">{can('countStocktakes') && viewStock ? <><OperationLotPicker selected={selected} onChange={setSelected} disabled={mutation.pending} /><p className="inv-muted">Bắt đầu sẽ chụp số tồn của {selected.length} lô đã chọn; sau đó phạm vi không thể sửa.</p><button className="inv-button" disabled={!selected.length || mutation.pending} onClick={() => setAction('start')}>Bắt đầu kiểm kê</button></> : <p>Phiếu nháp đang chờ người có quyền kiểm đếm chọn lô và bắt đầu.</p>}</Panel> : <>
      <Panel title="Tiến độ kiểm đếm">
        <div className="inv-count-summary" aria-live="polite"><span><strong>{counted} / {document.items.length}</strong> đã kiểm</span><span><strong>{matched}</strong> khớp</span><span><strong>{increases}</strong> lệch tăng</span><span><strong>{decreases}</strong> lệch giảm</span><span><strong>{document.items.length - counted}</strong> chưa kiểm</span></div>
        <progress className="inv-count-progress" aria-label="Tiến độ kiểm kê" max={document.items.length || 1} value={counted} />
        {dirty && <p className="inv-muted">Có số đếm chưa lưu. Chốt phiếu chỉ khả dụng khi tất cả số đếm đã lưu.</p>}
        <div className="inv-tabs" role="group" aria-label="Lọc trạng thái kiểm đếm">{([{ value: 'all', label: 'Tất cả' }, { value: 'uncounted', label: 'Chưa kiểm' }, { value: 'counted', label: 'Đã kiểm' }, { value: 'matched', label: 'Khớp' }, { value: 'difference', label: 'Chênh lệch' }] as const).map(tab => <button className={`inv-button ${filter === tab.value ? '' : 'secondary'}`} key={tab.value} aria-pressed={filter === tab.value} onClick={() => { setFilter(tab.value); setPage(1); setMobileIndex(0); }}>{tab.label}</button>)}</div>
      </Panel>
      {contexts.loading && <LoadingState />}{Boolean(contexts.error) && <ErrorPanel error={contexts.error} onRetry={contexts.refresh} />}
      {!filtered.length ? <EmptyState title="Không có mục trong bộ lọc này" action={<button className="inv-button secondary" onClick={() => setFilter('all')}>Xem tất cả</button>} /> : <Panel>
        <div className="inv-table-wrap inv-count-desktop"><table className="inv-table"><caption>Số lượng theo đơn vị cơ sở. Nhập số thực tế, lý do và xác nhận số đếm; Enter chuyển ô tiếp theo.</caption><thead><tr><th>Nguyên liệu / lô / hạn</th><th>Tồn khi bắt đầu</th><th>Số thực tế</th><th>Chênh lệch</th><th>Lý do</th><th>Xác nhận</th></tr></thead><tbody>{visible.map(item => {
          const context = contexts.data?.[item.stock_lot_id]; const unit = context?.ingredient.base_unit.unit_code ?? '';
          return <tr key={item.stocktake_item_id}><td>{context?.ingredient.ingredient_name ?? `Lô #${item.stock_lot_id}`}<br />{viewStock ? <Link className="inv-code" to={`/inventory/lots/${item.stock_lot_id}`}>{context?.lot.lot_code ?? `#${item.stock_lot_id}`}</Link> : <span className="inv-code">#{item.stock_lot_id}</span>}<br /><span className="inv-muted">{date(context?.lot.expiry_date)} · {unit}</span></td><td>{quantity(item.system_quantity)} {unit}</td><td>{amountInput(item, false)}{lineError(item) && <p className="inv-operation-error">{lineError(item)}</p>}</td><td>{variance(item)} {unit}</td><td>{reasonInput(item)}</td><td><div className="inv-actions">{marker(item)}</div></td></tr>;
        })}</tbody></table></div>
        {current && <div className="inv-count-mobile"><div className="inv-count-card">
          <p className="inv-muted">Mục {(effectivePage - 1) * 20 + Math.min(mobileIndex, visible.length - 1) + 1} / {filtered.length}</p><h2>{contexts.data?.[current.stock_lot_id]?.ingredient.ingredient_name ?? `Lô #${current.stock_lot_id}`}</h2>{viewStock ? <Link className="inv-code" to={`/inventory/lots/${current.stock_lot_id}`}>{contexts.data?.[current.stock_lot_id]?.lot.lot_code ?? `#${current.stock_lot_id}`}</Link> : <span className="inv-code">#{current.stock_lot_id}</span>}
          <dl><dt>Hạn dùng</dt><dd>{date(contexts.data?.[current.stock_lot_id]?.lot.expiry_date)}</dd><dt>Tồn khi bắt đầu</dt><dd>{quantity(current.system_quantity)} {contexts.data?.[current.stock_lot_id]?.ingredient.base_unit.unit_code}</dd><dt>Chênh lệch</dt><dd>{variance(current)} {contexts.data?.[current.stock_lot_id]?.ingredient.base_unit.unit_code}</dd></dl>
          <Field label={`Số thực tế (${contexts.data?.[current.stock_lot_id]?.ingredient.base_unit.unit_code ?? 'đơn vị cơ sở'})`} error={lineError(current)}>{amountInput(current, true)}</Field><Field label="Lý do / ghi chú xác nhận">{reasonInput(current)}</Field><div className="inv-actions">{marker(current)}</div>
        </div><div className="inv-actions"><button className="inv-button secondary" disabled={effectivePage === 1 && mobileIndex === 0} onClick={() => changeMobile(mobileIndex - 1)}>Mục trước</button><button className="inv-button secondary" disabled={(effectivePage - 1) * 20 + mobileIndex >= filtered.length - 1} onClick={() => changeMobile(mobileIndex + 1)}>Mục sau</button></div></div>}
        <Pagination page={effectivePage} total={filtered.length} pageSize={20} onChange={next => { setPage(next); setMobileIndex(0); }} />
      </Panel>}
    </>}
    {inProgress && can('finalizeStocktakes') && <Panel title="Rà soát và chốt"><CurrentActor label="Người chốt" /><p className="inv-muted">{increases + decreases} lô có chênh lệch sẽ được điều chỉnh khi chốt. Tất cả mục phải được xác nhận và lưu.</p></Panel>}
    <div className="inv-count-sticky">
      {editable && <button className="inv-button secondary" disabled={!dirty || mutation.pending} onClick={save}>{mutation.pending ? 'Đang lưu…' : 'Lưu số đếm'}</button>}
      {inProgress && can('finalizeStocktakes') && <button className="inv-button" disabled={mutation.pending || dirty || !user || !document.items.length || document.items.some(item => !item.counted)} onClick={() => setAction('complete')}>Rà soát và chốt</button>}
      {can('finalizeStocktakes') && (inProgress || document.status === 'DRAFT') && <button className="inv-button danger" disabled={mutation.pending} onClick={() => setAction('cancel')}>Hủy phiếu</button>}
      {viewStock && <Link className="inv-button secondary" to="/inventory/movements">Xem biến động kho</Link>}
    </div>
    <ConfirmDialog open={action !== null} title={action === 'start' ? 'Bắt đầu kiểm kê?' : action === 'complete' ? 'Chốt phiếu kiểm kê?' : 'Hủy phiếu kiểm kê?'} pending={mutation.pending} onClose={() => setAction(null)} onConfirm={performAction}>
      {action === 'start' ? <p>Ghi nhận tồn hệ thống của {selected.length} lô đã chọn. Các biến động kho sau thời điểm này có thể yêu cầu lập lại phiếu.</p> : action === 'complete' ? <><p>{document.items.length} mục đã kiểm: {matched} khớp, {increases} lệch tăng, {decreases} lệch giảm.</p><p>Hệ thống sẽ điều chỉnh {increases + decreases} lô và tạo biến động kiểm kê. Phiếu đã chốt không thể sửa, hủy hoặc chốt thêm lần nữa.</p></> : <p>Phiếu sẽ ngừng kiểm kê. Số đếm chưa lưu sẽ bị bỏ; tồn kho không thay đổi.</p>}
    </ConfirmDialog>
    <Modal open={Boolean(conflict)} title={conflictTitle} onClose={() => setConflict(undefined)}>
      <p>Dữ liệu tồn kho hoặc trạng thái phiếu có thể đã thay đổi. Số đếm bạn vừa nhập được giữ nguyên để đối chiếu; hệ thống không tự gửi lại.</p>
      {Boolean(conflict) && <ErrorPanel error={conflict} />}
      <p>Nếu có biến động sau lúc bắt đầu, hãy hủy phiếu cũ và lập phiếu mới để lấy số tồn hiện tại.</p>
      <div className="inv-actions"><button className="inv-button secondary" disabled={refreshMutation.pending} onClick={reloadDocument}>Tải lại tồn và trạng thái</button>{viewStock && <Link className="inv-button secondary" to="/inventory/movements">Xem biến động mới</Link>}{can('createStocktakes') && <Link className="inv-button" to="/inventory/stocktakes/new">Lập phiếu mới</Link>}</div>
      {Boolean(refreshMutation.error) && <ErrorPanel error={refreshMutation.error} />}
      {contexts.data && <div className="inv-table-wrap"><table className="inv-table"><caption>Tồn hiện tại của các lô đang xem</caption><thead><tr><th>Lô</th><th>Tồn hiện tại</th></tr></thead><tbody>{Object.values(contexts.data).map(context => <tr key={context.lot.stock_lot_id}><td>{context.lot.lot_code}</td><td>{quantity(context.lot.current_quantity)} {context.ingredient.base_unit.unit_code}</td></tr>)}</tbody></table></div>}
    </Modal>
  </div>;
}
