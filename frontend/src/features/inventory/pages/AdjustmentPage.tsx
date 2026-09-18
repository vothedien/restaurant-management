import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { adjustStock, getIssueConversions, getIssueLots, getOperationBalance, getOperationIngredient, getOperationLot, issueStock, listOperationLots } from '../api/operations';
import { OperationIngredientPicker } from '../components/OperationsFields';
import { Badge, ConfirmDialog, CurrentActor, DecimalInput, EmptyState, ErrorPanel, Field, LoadingState, PageHeader, Pagination, Panel } from '../components/ui';
import { useInventoryAuth } from '../auth/useInventoryAuth';
import { useMutation } from '../hooks/useMutation';
import { useQuery } from '../hooks/useQuery';
import { useUnsavedChanges } from '../hooks/useUnsavedChanges';
import type { OperationIngredient, OperationLot, StockChange } from '../types/operations';
import { compareDecimal, date, multiplyDecimal, normalizeDecimal, quantity, subtractDecimal } from '../utils/format';
import { planFefo, quantityError, validActor } from '../utils/operations';
import { errorInfo } from '../utils/errors';
import './operations.css';

export function AdjustmentPage() {
  const { user, can } = useInventoryAuth();
  const [params] = useSearchParams();
  if (!user || !can('viewStock') || (!can('issueStock') && !can('adjustStock')) || (params.has('lot_id') && !can('adjustStock'))) {
    return <EmptyState title="Không đủ quyền truy cập" description="Bạn chưa được cấp quyền cho thao tác kho này." action={<Link to="/inventory">Về tổng quan kho</Link>} />;
  }
  return <AdjustmentContent />;
}

function AdjustmentContent() {
  const [params] = useSearchParams(); const ingredientId = params.get('ingredient_id'); const lotId = params.get('lot_id');
  const initial = useQuery(`operation-initial:${ingredientId}:${lotId}`, async signal => {
    if (lotId) { if (!validActor(lotId)) throw new Error('Mã lô không hợp lệ.'); const lot = await getOperationLot(Number(lotId), signal); return { lot, ingredient: await getOperationIngredient(lot.ingredient_id, signal) }; }
    if (ingredientId) { if (!validActor(ingredientId)) throw new Error('Mã nguyên liệu không hợp lệ.'); return { ingredient: await getOperationIngredient(Number(ingredientId), signal), lot: undefined }; }
    return { ingredient: undefined, lot: undefined };
  });
  if (!initial.data) return initial.error ? <ErrorPanel error={initial.error} onRetry={initial.refresh} /> : <LoadingState />;
  return <AdjustmentForm key={`${ingredientId}:${lotId}`} initialIngredient={initial.data.ingredient} initialLot={initial.data.lot} />;
}

function AdjustmentForm({ initialIngredient, initialLot }: { initialIngredient?: OperationIngredient; initialLot?: OperationLot }) {
  const { user, can } = useInventoryAuth();
  const [mode, setMode] = useState<'issue' | 'adjust'>(initialLot || !can('issueStock') ? 'adjust' : 'issue');
  const [ingredient, setIngredient] = useState(initialIngredient); const [lotId, setLotId] = useState(initialLot?.stock_lot_id);
  const [unitId, setUnitId] = useState(initialIngredient?.base_unit_id); const [amount, setAmount] = useState(''); const [reason, setReason] = useState('');
  const [lotPage, setLotPage] = useState(1); const [submitted, setSubmitted] = useState(false); const [confirm, setConfirm] = useState(false); const [result, setResult] = useState<StockChange>();
  const mutation = useMutation(); useUnsavedChanges(Boolean(amount || reason));
  const context = useQuery(`operation-context:${ingredient?.ingredient_id ?? ''}:${mode}`, async signal => {
    if (!ingredient) return undefined;
    const [balance, lots, conversions] = await Promise.all([
      getOperationBalance(ingredient.ingredient_id, signal),
      mode === 'issue' ? getIssueLots(ingredient.ingredient_id, signal) : Promise.resolve(undefined),
      mode === 'issue' ? getIssueConversions(signal) : Promise.resolve(undefined),
    ]);
    return { balance, lots, conversions };
  });
  const lotQuery = useQuery(`operation-adjust-lot:${lotId ?? ''}`, signal => lotId ? getOperationLot(lotId, signal) : Promise.resolve(undefined));
  const lotsQuery = useQuery(`operation-adjust-lots:${ingredient?.ingredient_id ?? ''}:${lotPage}:${mode}`, signal => ingredient && mode === 'adjust' ? listOperationLots(lotPage, ingredient.ingredient_id, signal) : Promise.resolve(undefined));
  const selectedLot = lotQuery.data;
  const baseUnit = ingredient?.base_unit;
  const conversions = (context.data?.conversions?.items ?? []).filter(item => item.to_unit_id === baseUnit?.unit_id && item.to_unit.is_active && item.from_unit.is_active && item.from_unit.dimension === baseUnit.dimension);
  const units = baseUnit ? [baseUnit, ...conversions.map(item => item.from_unit).filter(item => item.unit_id !== baseUnit.unit_id)] : [];
  const conversion = conversions.find(item => item.from_unit_id === unitId);
  const factor = unitId === baseUnit?.unit_id ? '1' : conversion?.factor;
  const amountError = amount ? quantityError(amount, mode === 'issue') : submitted ? 'Nhập số lượng.' : undefined;
  const normalized = amount && !quantityError(amount, mode === 'issue') ? normalizeDecimal(amount) : undefined;
  const baseQuantity = mode === 'issue' && normalized && factor ? multiplyDecimal(normalized, factor) : undefined;
  const conversionError = baseQuantity && quantityError(baseQuantity, true) ? 'Lượng quy đổi phải biểu diễn chính xác tới 0,001 đơn vị cơ sở và nằm trong giới hạn số lượng.' : undefined;
  const overStock = baseQuantity && context.data?.balance && compareDecimal(baseQuantity, context.data.balance.available_quantity) > 0;
  const overReceived = mode === 'adjust' && normalized && selectedLot && compareDecimal(normalized, selectedLot.received_quantity) > 0;
  const plan = baseQuantity && !conversionError && context.data?.lots?.complete ? planFefo(context.data.lots.items, baseQuantity) : undefined;
  const metadataReady = ingredient && !context.loading && !context.error && context.data?.balance && (mode === 'issue' ? baseUnit?.is_active && ingredient.status === 'ACTIVE' && factor : selectedLot && !lotQuery.loading && !lotQuery.error);
  const canPerform = !!user && can(mode === 'issue' ? 'issueStock' : 'adjustStock');
  const canSubmit = Boolean(canPerform && metadataReady && normalized && !conversionError && !overStock && !overReceived && reason.trim());
  const delta = mode === 'adjust' && selectedLot && normalized ? subtractDecimal(normalized, selectedLot.current_quantity) : undefined;
  function discardQuantity() { return !amount || window.confirm('Đổi lựa chọn sẽ bỏ số lượng chưa gửi. Tiếp tục?'); }
  function changeIngredient(next: OperationIngredient | undefined) { if (!discardQuantity()) return; setIngredient(next); setLotId(undefined); setUnitId(next?.base_unit_id); setAmount(''); setLotPage(1); setResult(undefined); }
  function changeMode(next: 'issue' | 'adjust') { if (!can(next === 'issue' ? 'issueStock' : 'adjustStock') || mode === next || !discardQuantity()) return; setMode(next); setAmount(''); setResult(undefined); }
  function refresh() { context.refresh(); lotQuery.refresh(); lotsQuery.refresh(); }
  async function submit() {
    if (!user || !canSubmit || !ingredient || !normalized) return;
    await mutation.run(() => mode === 'issue' ? issueStock({ ingredient_id: ingredient.ingredient_id, quantity: normalized, unit_id: unitId!, performed_by: user.userId, reason: reason.trim() }) : adjustStock(lotId!, { actual_quantity: normalized, performed_by: user.userId, reason: reason.trim() }), value => { setResult(value); setAmount(''); setReason(''); setSubmitted(false); setConfirm(false); refresh(); });
  }
  return <>
    <PageHeader title="Xuất và điều chỉnh kho" description="Xem trước tác động, ghi lý do và xác nhận trước khi cập nhật tồn." actions={<Link className="inv-button secondary" to="/inventory/stock">Xem tồn kho</Link>} />
    <div className="inv-tabs" role="group" aria-label="Loại thao tác kho">{can('issueStock') && <button className={`inv-button ${mode === 'issue' ? '' : 'secondary'}`} disabled={mutation.pending} aria-pressed={mode === 'issue'} onClick={() => changeMode('issue')}>Xuất kho theo FEFO</button>}{can('adjustStock') && <button className={`inv-button ${mode === 'adjust' ? '' : 'secondary'}`} disabled={mutation.pending} aria-pressed={mode === 'adjust'} onClick={() => changeMode('adjust')}>Điều chỉnh một lô</button>}</div>
    <form onSubmit={event => { event.preventDefault(); setSubmitted(true); if (canSubmit) setConfirm(true); }}>
      <Panel title="1. Chọn nguyên liệu"><OperationIngredientPicker value={ingredient} onChange={changeIngredient} activeOnly={mode === 'issue'} disabled={mutation.pending} />
        {submitted && !ingredient && <p className="inv-operation-error" role="alert">Chọn nguyên liệu cần xử lý.</p>}
        {ingredient && <p className="inv-muted">{ingredient.ingredient_code} · Đơn vị cơ sở: {baseUnit?.unit_name} ({baseUnit?.unit_code}) · <Badge status={ingredient.status} /></p>}
        {context.loading && ingredient && <LoadingState />}{Boolean(context.error) && <ErrorPanel error={context.error} onRetry={refresh} />}
        {context.data?.balance && <div className="inv-count-summary"><span>Tồn hiện tại <strong>{quantity(context.data.balance.current_quantity)} {baseUnit?.unit_code}</strong></span><span>Khả dụng <strong>{quantity(context.data.balance.available_quantity)} {baseUnit?.unit_code}</strong></span><span>Chưa thể xuất <strong>{quantity(context.data.balance.unavailable_quantity)} {baseUnit?.unit_code}</strong></span></div>}
      </Panel>
      {mode === 'adjust' && ingredient && <Panel title="2. Chọn lô cần điều chỉnh">
        {lotsQuery.loading && <LoadingState />}{Boolean(lotsQuery.error) && <ErrorPanel error={lotsQuery.error} onRetry={lotsQuery.refresh} />}
        <Field label="Lô hàng"><select disabled={mutation.pending || lotsQuery.loading} value={lotId ?? ''} onChange={event => { if (!discardQuantity()) return; setLotId(Number(event.target.value) || undefined); setAmount(''); setResult(undefined); }}><option value="">Chọn lô</option>
          {selectedLot && !lotsQuery.data?.items.some(lot => lot.stock_lot_id === selectedLot.stock_lot_id) && <option value={selectedLot.stock_lot_id}>{selectedLot.lot_code}</option>}
          {lotsQuery.data?.items.map(lot => <option value={lot.stock_lot_id} key={lot.stock_lot_id}>{lot.lot_code} · {quantity(lot.current_quantity)} {baseUnit?.unit_code} · HSD {date(lot.expiry_date)}</option>)}
        </select></Field>
        {submitted && !lotId && <p className="inv-operation-error" role="alert">Chọn lô cần điều chỉnh.</p>}
        {lotsQuery.data && <Pagination page={lotPage} total={lotsQuery.data.total} pageSize={20} onChange={setLotPage} />}
        {lotsQuery.data?.total === 0 && <EmptyState title="Nguyên liệu chưa có lô" description="Chốt phiếu nhập để tạo lô trước khi điều chỉnh." />}
        {Boolean(lotQuery.error) && <ErrorPanel error={lotQuery.error} onRetry={lotQuery.refresh} />}
        {selectedLot && <div className="inv-operation-notice">Lô {selectedLot.lot_code} · <Badge status={selectedLot.status} /><p>Tồn hiện tại: {quantity(selectedLot.current_quantity)} {baseUnit?.unit_code}. Lượng nhập gốc: {quantity(selectedLot.received_quantity)} {baseUnit?.unit_code}.</p><p>Nhập số tồn thực tế sau điều chỉnh, từ 0 đến {quantity(selectedLot.received_quantity)} {baseUnit?.unit_code}. Điều chỉnh không gỡ trạng thái khóa hoặc hết hạn của lô.</p></div>}
      </Panel>}
      <Panel title={mode === 'issue' ? '2. Số lượng xuất' : '3. Số thực tế sau điều chỉnh'}><div className="inv-form-grid">
        <Field label={mode === 'issue' ? 'Số lượng xuất' : `Số tồn thực tế (${baseUnit?.unit_code ?? 'đơn vị cơ sở'})`} error={amountError || (overReceived ? `Số thực tế không được vượt lượng nhập gốc ${quantity(selectedLot?.received_quantity)} ${baseUnit?.unit_code}.` : undefined)}><DecimalInput value={amount} onChange={value => { setAmount(value); setResult(undefined); }} disabled={mutation.pending} placeholder={mode === 'issue' ? 'Lớn hơn 0' : 'Có thể bằng 0'} /></Field>
        {mode === 'issue' && <Field label="Đơn vị xuất"><select value={unitId ?? ''} disabled={mutation.pending || context.loading || !baseUnit?.is_active} onChange={event => setUnitId(Number(event.target.value))}><option value="">Chọn đơn vị</option>{units.filter(unit => unit.is_active).map(unit => <option value={unit.unit_id} key={unit.unit_id}>{unit.unit_name} ({unit.unit_code})</option>)}</select></Field>}
        <Field label="Lý do (bắt buộc)" error={submitted && !reason.trim() ? 'Nhập lý do cho thao tác kho.' : undefined}><textarea value={reason} maxLength={2000} rows={3} disabled={mutation.pending} onChange={event => setReason(event.target.value)} placeholder="Ví dụ: Xuất nguyên liệu cho ca chiều / Đối chiếu cân thực tế" /></Field>
        <CurrentActor />
      </div>
        {mode === 'issue' && <p className="inv-muted">Đơn vị xuất cần hoạt động và có quy đổi trực tiếp cùng loại về đơn vị cơ sở.</p>}
        {mode === 'issue' && ingredient && (!baseUnit?.is_active || ingredient.status !== 'ACTIVE') && <p role="alert" className="inv-operation-error">Nguyên liệu và đơn vị cơ sở cần hoạt động để xuất kho.</p>}
        {context.data?.conversions && !context.data.conversions.complete && <p className="inv-operation-notice inv-operation-warning">Danh sách quy đổi lớn hơn giới hạn tải 1.000 dòng. Chỉ các quy đổi đã tải và đơn vị cơ sở được chọn; kiểm tra cấu hình đơn vị nếu thiếu lựa chọn.</p>}
        {baseQuantity && !conversionError && <p className="inv-operation-notice">Quy đổi: {quantity(normalized)} {units.find(unit => unit.unit_id === unitId)?.unit_code} = <strong>{quantity(baseQuantity)} {baseUnit?.unit_code}</strong>.</p>}
        {conversionError && <p className="inv-operation-error" role="alert">{conversionError}</p>}
        {overStock && <p className="inv-operation-error" role="alert">Số lượng xuất vượt tồn khả dụng. Giảm lượng xuất hoặc tải lại tồn kho.</p>}
      </Panel>
      <Panel title="Xem trước tác động" actions={<button className="inv-button secondary" type="button" disabled={context.loading || mutation.pending} onClick={refresh}>Tải lại tồn kho</button>}>
        {mode === 'issue' ? <>
          <p>FEFO: lô có hạn dùng gần nhất được xuất trước; lô chưa có hạn dùng xếp cuối. Khi cùng hạn, ưu tiên thời điểm tạo rồi mã ID lô.</p>
          <p className="inv-muted">Lô hết hạn, bị khóa, chưa đến ngày sản xuất hoặc không còn tồn được loại khỏi tồn khả dụng bởi máy chủ.</p>
          {baseQuantity && !conversionError && !overStock && context.data?.balance && <p>Tồn khả dụng dự kiến sau xuất: <strong>{quantity(subtractDecimal(context.data.balance.available_quantity, baseQuantity))} {baseUnit?.unit_code}</strong>.</p>}
          {context.data?.lots && !context.data.lots.complete && <p className="inv-operation-notice inv-operation-warning">Chưa thể hiển thị toàn bộ phân bổ vì có hơn 1.000 lô hoặc dữ liệu thay đổi trong lúc tải. Tồn khả dụng vẫn lấy từ máy chủ; máy chủ sẽ chọn lô FEFO khi xác nhận.</p>}
          {plan && !overStock && <div className="inv-table-wrap"><table className="inv-table"><caption>Phân bổ dự kiến từ các lô khả dụng; máy chủ xác định lại khi thực hiện.</caption><thead><tr><th>Lô</th><th>Hạn dùng</th><th>Lượng xuất</th><th>Còn lại</th></tr></thead><tbody>{plan.allocations.map(row => <tr key={row.lot.stock_lot_id}><td>{row.lot.lot_code}</td><td>{date(row.lot.expiry_date)}</td><td>{quantity(row.quantity)} {baseUnit?.unit_code}</td><td>{quantity(row.after)} {baseUnit?.unit_code}</td></tr>)}</tbody></table></div>}
          {plan && compareDecimal(plan.remaining, '0') > 0 && <p className="inv-operation-notice inv-operation-warning">Danh sách lô và tồn tổng hợp có thể vừa thay đổi. Tải lại tồn để đối chiếu.</p>}
        </> : selectedLot && normalized && !overReceived ? <p>Lô {selectedLot.lot_code}: <strong>{quantity(selectedLot.current_quantity)} → {quantity(normalized)} {baseUnit?.unit_code}</strong>. {delta && compareDecimal(delta, '0') === 0 ? 'Số lượng không đổi, không tạo biến động mới.' : <>Chênh lệch: <strong>{quantity(delta)} {baseUnit?.unit_code}</strong>.</>}</p> : <p className="inv-muted">Chọn lô và nhập số thực tế để xem tác động.</p>}
      </Panel>
      {Boolean(mutation.error) && <><ErrorPanel error={mutation.error} />{errorInfo(mutation.error).status === 409 && <div className="inv-operation-notice inv-operation-warning"><p>Dữ liệu đã nhập được giữ nguyên. Tải lại tồn, đối chiếu giới hạn lượng nhập gốc và xác nhận lại sau khi sửa.</p><button className="inv-button secondary" type="button" onClick={() => { setConfirm(false); refresh(); }}>Tải lại để đối chiếu</button><Link to={`/inventory/movements?ingredient_id=${ingredient?.ingredient_id ?? ''}`}>Xem biến động mới</Link></div>}</>}
      {result && <Panel title="Đã cập nhật kho"><div className="inv-operation-result" role="status">{result.movements.length ? <><p>Đã tạo {result.movements.length} biến động kho:</p><ul>{result.movements.map(movement => <li key={movement.stock_movement_id}><span className="inv-code">{movement.movement_number}</span> · {movement.direction === 'OUT' ? 'Xuất' : 'Nhập'} {quantity(movement.quantity)} {baseUnit?.unit_code}</li>)}</ul></> : <p>Số thực tế khớp tồn hiện tại; không phát sinh biến động.</p>}<Link className="inv-button secondary" to={`/inventory/movements?ingredient_id=${ingredient?.ingredient_id ?? ''}`}>Xem lịch sử biến động</Link></div></Panel>}
      <div className="inv-count-sticky">{canPerform && <button className="inv-button" disabled={mutation.pending || Boolean(ingredient && context.loading)} type="submit">{mode === 'issue' ? 'Xem lại và xuất kho' : 'Xem lại và điều chỉnh'}</button>}</div>
    </form>
    <ConfirmDialog open={confirm} title={mode === 'issue' ? 'Xác nhận xuất kho?' : 'Xác nhận điều chỉnh lô?'} onClose={() => { if (!mutation.pending) setConfirm(false); }} onConfirm={submit} pending={mutation.pending}>
      <p>{ingredient?.ingredient_name} · {mode === 'issue' ? <>Xuất {quantity(baseQuantity)} {baseUnit?.unit_code} theo FEFO.</> : <>Đặt tồn lô {selectedLot?.lot_code} thành {quantity(normalized)} {baseUnit?.unit_code}.</>}</p><p>Lý do: {reason}</p><p>Thao tác cập nhật tồn và tạo biến động ngay. Hãy kiểm tra số lượng trước khi xác nhận.</p>
      {Boolean(mutation.error) && <ErrorPanel error={mutation.error} />}
    </ConfirmDialog>
  </>;
}
