import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { collect, stockSnapshot, type Movement } from '../api/stock';
import { get } from '../api/http';
import type { Page } from '../types/common';
import type { PurchaseOrder } from '../types/purchasing';
import { Badge, EmptyState, ErrorPanel, Field, LoadingState, PageHeader, Pagination, Panel } from '../components/ui';
import { useQuery } from '../hooks/useQuery';
import { addDecimal, compareDecimal, date, dateTime, expiryDays, money, quantity, todayISO } from '../utils/format';
import { downloadCsv } from '../utils/csv';
import { inventoryValue, movementLabel, stockHealth } from '../utils/stock';
import { useInventoryAuth } from '../auth/useInventoryAuth';

function useInsights() {
  const { can } = useInventoryAuth();
  const ordersAllowed = can('viewPurchaseOrders');
  const stocktakesAllowed = can('viewStocktakes');
  return useQuery(`insights:inventory:${ordersAllowed}:${stocktakesAllowed}`, async signal => {
    const [snapshot, recent, pending, partial, counting] = await Promise.all([
      stockSnapshot(signal), get<Page<Movement>>('/inventory/stock-movements',{limit:6,offset:0},signal),
      ordersAllowed ? get<Page<PurchaseOrder>>('/purchasing/purchase-orders',{status:'PENDING_APPROVAL',limit:1,offset:0},signal) : null,
      ordersAllowed ? get<Page<PurchaseOrder>>('/purchasing/purchase-orders',{status:'PARTIALLY_RECEIVED',limit:1,offset:0},signal) : null,
      stocktakesAllowed ? get<Page<unknown>>('/inventory/stocktakes',{status:'IN_PROGRESS',limit:1,offset:0},signal) : null,
    ]);
    const active = snapshot.ingredients.filter(item => item.status === 'ACTIVE');
    const health = snapshot.balances.map(row => ({...row, ingredient:snapshot.ingredients.find(item => item.ingredient_id === row.ingredient_id)})).filter(row => row.ingredient?.status === 'ACTIVE');
    const empty = health.filter(row => stockHealth(row,row.ingredient) === 'OUT_OF_STOCK');
    const low = health.filter(row => stockHealth(row,row.ingredient) === 'LOW');
    const remainingLots = snapshot.lots.filter(lot => compareDecimal(lot.current_quantity,'0') > 0);
    const expired = remainingLots.filter(lot => lot.status === 'EXPIRED' || (expiryDays(lot.expiry_date) ?? 0) < 0);
    const expiring = remainingLots.filter(lot => { const days=expiryDays(lot.expiry_date);return lot.status !== 'EXPIRED' && days !== null && days >= 0 && days <= 14; });
    return {...snapshot,active,empty,low,expired,expiring,recent:recent.items,pending:pending?.total ?? null,partial:partial?.total ?? null,counting:counting?.total ?? null};
  });
}
export function InventoryOverviewPage() {
  const { can } = useInventoryAuth();
  if (!can('viewStock')) return <><PageHeader title="Tổng quan kho" description="Truy cập các chức năng được cấp cho tài khoản của bạn." /><Panel><p>Chọn chức năng trong menu để bắt đầu.</p>{can('viewRecipes') && <Link className="inv-button" to="/inventory/recipes">Mở công thức món</Link>}</Panel></>;
  return <StockOverview />;
}
function StockOverview() {
  const { can } = useInventoryAuth();
  const query=useInsights(); const data=query.data;
  return <><PageHeader title="Tổng quan kho" description="Những việc cần xử lý và tình trạng nguyên liệu hôm nay." actions={<><button className="inv-button secondary" onClick={query.refresh}>Làm mới</button>{can('createReceipts') && <Link className="inv-button" to="/inventory/goods-receipts/new">+ Nhập hàng</Link>}</>} />
  {query.loading && <LoadingState />}{query.error && <ErrorPanel error={query.error} onRetry={query.refresh} />}{data && !query.loading && !query.error && <>
  <div className="inv-kpi-grid"><Link className="inv-kpi" to="/inventory/ingredients?status=ACTIVE"><span className="inv-kpi-label">Nguyên liệu hoạt động</span><strong>{data.active.length}</strong><small>Danh mục đang sử dụng</small></Link><Link className="inv-kpi danger" to="/inventory/stock?health=OUT_OF_STOCK&status=ACTIVE"><span className="inv-kpi-label">Hết tồn khả dụng</span><strong>{data.empty.length}</strong><small>Cần kiểm tra hoặc bổ sung</small></Link><Link className="inv-kpi warning" to="/inventory/stock?health=LOW&status=ACTIVE"><span className="inv-kpi-label">Dưới định mức tối thiểu</span><strong>{data.low.length}</strong><small>Chuẩn bị kế hoạch mua</small></Link><Link className="inv-kpi warning" to="/inventory/alerts?type=expiry"><span className="inv-kpi-label">Lô cận hạn</span><strong>{data.expiring.length}</strong><small>Còn tồn · Hạn trong 14 ngày</small></Link></div>
  <div className="inv-dashboard-grid"><Panel title="Việc cần xử lý" actions={<Link to="/inventory/alerts">Tất cả cảnh báo →</Link>}><ul className="inv-worklist"><li><Link to="/inventory/alerts?type=expired"><div><strong>Lô hết hạn còn tồn</strong><small>Đối chiếu và xử lý hàng hết hạn</small></div>{data.expired.length > 0 && <Badge status="EXPIRED" />}<strong>{data.expired.length}</strong></Link></li>{data.pending !== null && <li><Link to="/inventory/purchase-orders?status=PENDING_APPROVAL"><div><strong>Đơn mua chờ duyệt</strong><small>Kiểm tra số lượng và giá thỏa thuận</small></div><strong>{data.pending} đơn →</strong></Link></li>}{data.partial !== null && <li><Link to="/inventory/purchase-orders?status=PARTIALLY_RECEIVED"><div><strong>Đơn đã nhận một phần</strong><small>Tiếp tục nhập phần còn thiếu</small></div><strong>{data.partial} đơn →</strong></Link></li>}{data.counting !== null && <li><Link to="/inventory/stocktakes?status=IN_PROGRESS"><div><strong>Kiểm kê đang thực hiện</strong><small>Tiếp tục đếm và đối chiếu</small></div><strong>{data.counting} phiếu →</strong></Link></li>}</ul></Panel>
  <Panel title="Biến động gần đây" actions={<Link to="/inventory/movements">Xem sổ kho →</Link>}>{data.recent.length ? <ul className="inv-worklist">{data.recent.map(row => { const item=data.ingredients.find(item=>item.ingredient_id===row.ingredient_id);return <li key={row.stock_movement_id}><Link to={`/inventory/movements?ingredient_id=${row.ingredient_id}`}><div><strong>{item?.ingredient_name ?? `Nguyên liệu #${row.ingredient_id}`}</strong><small>{movementLabel(row)} · {dateTime(row.occurred_at)}</small></div><span className="inv-number">{row.direction==='IN'?'+':'−'}{quantity(row.quantity)} {item?.base_unit.unit_code ?? 'đơn vị cơ sở'}</span></Link></li>;})}</ul> : <EmptyState title="Chưa có hoạt động kho" description="Biến động xuất hiện sau khi chốt chứng từ." />}</Panel></div>
  <Panel title="Giá trị tồn theo lô"><div className="inv-summary"><div><strong style={{fontSize:24}}>{money(inventoryValue(data.lots))}</strong><p className="inv-muted">Lượng còn lại × đơn giá cơ sở từng lô, gồm cả hàng chưa khả dụng.</p></div>{can('viewReports') && <Link className="inv-button secondary" to="/inventory/reports">Xem báo cáo kho</Link>}</div></Panel><p className="inv-muted">Cập nhật {dateTime(data.loadedAt)} · Làm mới sau giao dịch để đối chiếu tình trạng kho mới nhất.</p>
  </>}</>;
}
export function AlertsPage() {
  const { can } = useInventoryAuth();
  const ordersAllowed = can('viewPurchaseOrders');
  const stocktakesAllowed = can('viewStocktakes');
  const [params,setParams]=useSearchParams(); const query=useInsights(); const type=params.get('type')??'';
  const extra=useQuery(`alerts:orders-stocktakes:${ordersAllowed}:${stocktakesAllowed}`,async signal=> { const [ordered, partial, drafts]=await Promise.all([ordersAllowed ? collect<PurchaseOrder>('/purchasing/purchase-orders',{status:'ORDERED'},signal) : [],ordersAllowed ? collect<PurchaseOrder>('/purchasing/purchase-orders',{status:'PARTIALLY_RECEIVED'},signal) : [],stocktakesAllowed ? get<Page<unknown>>('/inventory/stocktakes',{status:'DRAFT',limit:1,offset:0},signal) : null]);return {overdue:[...ordered,...partial].filter(order=>order.expected_delivery_date && order.expected_delivery_date<todayISO()),drafts:drafts?.total ?? null}; });
  const data=query.data;
  const alerts=data ? [
    ...data.empty.map(row=>({key:`empty-${row.ingredient_id}`,type:'stock',status:'OUT_OF_STOCK',title:row.ingredient_name,description:`Không còn lượng khả dụng · Tổng tồn ${quantity(row.current_quantity)} ${row.ingredient?.base_unit.unit_code}`,to:`/inventory/stock?ingredient_id=${row.ingredient_id}`,action:'Xem tồn'})),
    ...data.low.map(row=>({key:`low-${row.ingredient_id}`,type:'stock',status:'LOW',title:row.ingredient_name,description:`Khả dụng ${quantity(row.available_quantity)} / tối thiểu ${quantity(row.ingredient?.minimum_stock_qty)} ${row.ingredient?.base_unit.unit_code}`,to:`/inventory/stock?ingredient_id=${row.ingredient_id}`,action:'Xem tồn'})),
    ...[...data.expired,...data.expiring].map(lot=>({key:`lot-${lot.stock_lot_id}`,type:data.expired.includes(lot)?'expired':'expiry',status:data.expired.includes(lot)?'EXPIRED':'EXPIRING_14',title:`Lô ${lot.lot_code}`,description:`${data.ingredients.find(item=>item.ingredient_id===lot.ingredient_id)?.ingredient_name} · Hạn ${date(lot.expiry_date)}`,to:`/inventory/lots/${lot.stock_lot_id}`,action:'Xem lô'})),
    ...(data.counting?[{key:'counting',type:'stocktake',status:'IN_PROGRESS',title:`${data.counting} phiếu đang kiểm kê`,description:'Tiếp tục số đếm đang thực hiện.',to:'/inventory/stocktakes?status=IN_PROGRESS',action:'Tiếp tục kiểm kê'}]:[]),
    ...(extra.data?.drafts?[{key:'drafts',type:'stocktake',status:'DRAFT',title:`${extra.data.drafts} phiếu kiểm kê nháp`,description:'Chọn lô và bắt đầu kiểm kê.',to:'/inventory/stocktakes?status=DRAFT',action:'Mở phiếu nháp'}]:[]),
    ...(extra.data?.overdue??[]).map(order=>({key:`order-${order.purchase_order_id}`,type:'order',status:order.status,title:order.purchase_order_number,description:`Quá ngày dự kiến nhận ${date(order.expected_delivery_date)}; chưa nhận đủ.`,to:`/inventory/purchase-orders/${order.purchase_order_id}`,action:'Xem đơn mua'})),
  ].filter(item=>!type||item.type===type):[];
  return <><PageHeader title="Trung tâm cảnh báo" description="Cảnh báo được tính lại từ tình trạng tồn và chứng từ hiện tại." /><Panel><div className="inv-tabs" role="group" aria-label="Loại cảnh báo">{[['','Tất cả'],['stock','Tồn thấp / hết hàng'],['expiry','Cận hạn'],['expired','Hết hạn'],['order','Đơn quá hạn'],['stocktake','Kiểm kê']].filter(([value]) => (value !== 'order' || ordersAllowed) && (value !== 'stocktake' || stocktakesAllowed)).map(([value,label])=><button key={value} aria-pressed={type===value} className={type===value?'active':''} onClick={()=>setParams(value?{type:value}:{})}>{label}</button>)}</div>{(query.loading||extra.loading)&&<LoadingState/>}{query.error&&<ErrorPanel error={query.error} onRetry={query.refresh}/>}{extra.error&&<ErrorPanel error={extra.error} onRetry={extra.refresh}/>}{data&&!query.loading&&<>{alerts.length?<ul className="inv-worklist">{alerts.map(item=><li key={item.key}><Link to={item.to}><div><Badge status={item.status}/><strong style={{marginLeft:10}}>{item.title}</strong><small>{item.description}</small></div><span>{item.action} →</span></Link></li>)}</ul>:<EmptyState title="Không có cảnh báo trong nhóm này" description="Kiểm tra lại sau khi có giao dịch mới."/>}</>}</Panel></>;
}
interface ReportRow { ingredient_id:number; name:string; unit:string; incoming:string; outgoing:string; consumption:string }
export function ReportsPage() {
  const [range,setRange]=useState<{from:string;to:string}|null>(null);
  const [page,setPage]=useState(1);
  const query=useQuery(`report:${JSON.stringify(range)}`,async signal=> {
    if (!range) return null;
    if (!range.from||!range.to||range.from>range.to) throw new Error('Chọn khoảng ngày hợp lệ.');
    if ((Date.parse(range.to)-Date.parse(range.from))/86400000>92) throw new Error('Chọn khoảng báo cáo không quá 93 ngày để giới hạn dữ liệu tải.');
    const [movements,ingredients]=await Promise.all([collect<Movement>('/inventory/stock-movements',{occurred_from:`${range.from}T00:00:00+07:00`,occurred_to:`${range.to}T23:59:59.999999+07:00`},signal),collect<import('../types/catalog').Ingredient>('/inventory/ingredients',{},signal)]);
    const rows=new Map<number,ReportRow>();
    movements.forEach(movement=>{const ingredient=ingredients.find(item=>item.ingredient_id===movement.ingredient_id);const row=rows.get(movement.ingredient_id)??{ingredient_id:movement.ingredient_id,name:ingredient?.ingredient_name??`#${movement.ingredient_id}`,unit:ingredient?.base_unit.unit_code??'đơn vị cơ sở',incoming:'0',outgoing:'0',consumption:'0'};if(movement.direction==='IN')row.incoming=addDecimal(row.incoming,movement.quantity);else row.outgoing=addDecimal(row.outgoing,movement.quantity);if(movement.movement_type==='CONSUMPTION'&&movement.direction==='OUT')row.consumption=addDecimal(row.consumption,movement.quantity);rows.set(row.ingredient_id,row);});
    return {rows:[...rows.values()],movements:movements.length};
  });
  return <><PageHeader title="Báo cáo kho" description="Tổng hợp nhập, xuất và tiêu hao theo nguyên liệu trong khoảng ngày đã chọn." actions={<Link className="inv-button secondary" to="/inventory/stock">Báo cáo tồn hiện tại</Link>}/><Panel title="Phạm vi báo cáo"><form className="inv-toolbar" onSubmit={event=>{event.preventDefault();const data=new FormData(event.currentTarget);setPage(1);setRange({from:String(data.get('from')),to:String(data.get('to'))});}}><Field label="Từ ngày"><input name="from" type="date" required defaultValue={todayISO()}/></Field><Field label="Đến ngày"><input name="to" type="date" required defaultValue={todayISO()}/></Field><button className="inv-button" disabled={query.loading&&!!range}>Lập báo cáo</button></form><p className="inv-note">Nhập/xuất gồm mọi loại biến động theo chiều giao dịch. Tiêu hao món là phần xuất có loại CONSUMPTION. Không cộng số lượng khác đơn vị. Chưa có tồn đầu kỳ hoặc giá lịch sử đủ để tính báo cáo giá trị nhập–xuất–tồn.</p></Panel>
  {query.loading&&range&&<LoadingState/>}{query.error&&<ErrorPanel error={query.error} onRetry={query.refresh}/>}{!range&&<EmptyState title="Chọn khoảng ngày để lập báo cáo" description="Tải tối đa 1.000 biến động trong phạm vi đã chọn; không hiển thị báo cáo từ dữ liệu thiếu."/>}{query.data&&!query.loading&&!query.error&&<Panel title={`${query.data.rows.length} nguyên liệu · ${query.data.movements} biến động`} actions={<><button className="inv-button secondary" onClick={()=>downloadCsv(`bao-cao-kho-${range?.from}-${range?.to}.csv`,['Nguyên liệu','Đơn vị','Nhập','Xuất','Trong đó tiêu hao món'],query.data!.rows.map(row=>[row.name,row.unit,row.incoming,row.outgoing,row.consumption]))}>Xuất CSV đầy đủ</button><button className="inv-button secondary" onClick={()=>window.print()}>In trang</button></>}>
  {query.data.rows.length?<div className="inv-table-wrap"><table className="inv-table"><caption>{date(range?.from)} – {date(range?.to)} · Giờ Việt Nam</caption><thead><tr><th>Nguyên liệu</th><th>Đơn vị</th><th>Nhập</th><th>Xuất</th><th>Tiêu hao món</th></tr></thead><tbody>{query.data.rows.slice((page-1)*20,page*20).map(row=><tr key={row.ingredient_id}><td>{row.name}</td><td>{row.unit}</td><td className="numeric">{quantity(row.incoming)}</td><td className="numeric">{quantity(row.outgoing)}</td><td className="numeric">{quantity(row.consumption)}</td></tr>)}</tbody></table></div>:<EmptyState title="Không có biến động trong khoảng ngày"/>}<Pagination page={page} total={query.data.rows.length} pageSize={20} onChange={setPage}/></Panel>}</>;
}
