import { useState } from 'react';
import type { FormEvent } from 'react';
import { catalogApi } from '../api/catalog';
import { useInventoryAuth } from '../auth/useInventoryAuth';
import type { ConversionWrite, Unit, UnitConversion, UnitDimension, UnitWrite } from '../types/catalog';
import { Badge, ConfirmDialog, EmptyState, ErrorPanel, Field, Modal, PageHeader, Panel } from '../components/ui';
import { useQuery } from '../hooks/useQuery';
import { useMutation } from '../hooks/useMutation';
import { useUnsavedChanges } from '../hooks/useUnsavedChanges';
import { normalizeDecimal } from '../utils/format';
import { CatalogResult, CatalogSearch, DecimalField, FormActions, UnitSelect } from './CatalogShared';
import { decimalError, useCatalogFilters, useUnitOptions } from './CatalogHelpers';

const dimensions: Record<UnitDimension, string> = { MASS: 'Khối lượng', VOLUME: 'Thể tích', COUNT: 'Số lượng', LENGTH: 'Chiều dài', OTHER: 'Khác' };

export function UnitsPage() {
  const { can } = useInventoryAuth();
  const filter = useCatalogFilters();
  const [unitEditor, setUnitEditor] = useState<Unit | 'new' | null>(null);
  const [conversionEditor, setConversionEditor] = useState<UnitConversion | 'new' | null>(null);
  const [action, setAction] = useState<{ id: number; name: string; conversion: boolean } | null>(null);
  const mutation = useMutation();
  const tab = filter.params.get('tab') === 'conversions' ? 'conversions' : 'units';
  const query = useQuery(`units:${filter.page}:${filter.search}`, signal => catalogApi.units({ page: filter.page, search: filter.search || undefined }, signal));
  const conversions = useQuery(`unit-conversions:${filter.page}`, signal => catalogApi.conversions({ page: filter.page }, signal));
  const reload = () => { query.refresh(); conversions.refresh(); };
  const add = can('manageUnits') ? <button className="inv-button" onClick={() => tab === 'units' ? setUnitEditor('new') : setConversionEditor('new')}>{tab === 'units' ? 'Thêm đơn vị' : 'Thêm quy đổi'}</button> : undefined;
  return <><PageHeader title="Đơn vị & quy đổi" description="Đơn vị nhất quán giúp đặt hàng, định lượng và kiểm đếm chính xác." actions={add} />
    <div className="inv-tabs" role="group" aria-label="Danh mục đơn vị"><button className={`inv-button ${tab === 'units' ? '' : 'secondary'}`} onClick={() => filter.setFilter('tab', '')}>Đơn vị tính</button><button className={`inv-button ${tab === 'conversions' ? '' : 'secondary'}`} onClick={() => filter.setFilter('tab', 'conversions')}>Quy đổi đơn vị</button></div>
    {tab === 'units' ? <><Panel><CatalogSearch maxLength={80} value={filter.search} onChange={value => filter.setFilter('search', value)} /></Panel><CatalogResult query={query} page={filter.page} onPage={page => filter.setFilter('page', String(page))} empty={<EmptyState title={filter.search ? 'Không tìm thấy đơn vị phù hợp' : 'Chưa có đơn vị tính'} action={filter.search ? <button className="inv-button secondary" onClick={filter.clear}>Xóa bộ lọc</button> : add} />}>{data => <div className="inv-table-wrap"><table className="inv-table"><caption>Đơn vị tính</caption><thead><tr><th>Mã đơn vị</th><th>Tên</th><th>Nhóm</th><th>Trạng thái</th><th>Thao tác</th></tr></thead><tbody>{data.items.map(unit => <tr key={unit.unit_id}><td className="inv-code">{unit.unit_code}</td><td>{unit.unit_name}</td><td>{dimensions[unit.dimension]}</td><td><Badge status={unit.is_active ? 'ACTIVE' : 'INACTIVE'} /></td><td>{can('manageUnits') && <div className="inv-actions"><button className="inv-button secondary" onClick={() => setUnitEditor(unit)}>Sửa</button>{unit.is_active && <button className="inv-button secondary" onClick={() => { mutation.clearError(); setAction({ id: unit.unit_id, name: unit.unit_name, conversion: false }); }}>Ngừng dùng</button>}</div>}</td></tr>)}</tbody></table></div>}</CatalogResult></> : <><p className="inv-muted">Mỗi dòng là quy đổi trực tiếp một chiều. Công thức và xuất kho dùng đúng chiều từ đơn vị nhập sang đơn vị cơ sở.</p><CatalogResult query={conversions} page={filter.page} onPage={page => filter.setFilter('page', String(page))} empty={<EmptyState title="Chưa có quy đổi đơn vị" action={add} />}>{data => <div className="inv-table-wrap"><table className="inv-table"><caption>Quy đổi trực tiếp</caption><thead><tr><th>Đơn vị nguồn</th><th>Hệ số</th><th>Đơn vị đích</th><th>Thao tác</th></tr></thead><tbody>{data.items.map(row => <tr key={row.conversion_id}><td>1 {row.from_unit.unit_code}</td><td>= {normalizeDecimal(row.factor).replace('.', ',')}</td><td>{row.to_unit.unit_code}</td><td>{can('manageUnits') && <div className="inv-actions"><button className="inv-button secondary" onClick={() => setConversionEditor(row)}>Sửa</button><button className="inv-button danger" onClick={() => { mutation.clearError(); setAction({ id: row.conversion_id, name: `${row.from_unit.unit_code} → ${row.to_unit.unit_code}`, conversion: true }); }}>Xóa</button></div>}</td></tr>)}</tbody></table></div>}</CatalogResult></>}
    {can('manageUnits') && unitEditor && <UnitForm unit={unitEditor === 'new' ? undefined : unitEditor} onClose={() => setUnitEditor(null)} onSaved={() => { setUnitEditor(null); reload(); }} />}
    {can('manageUnits') && conversionEditor && <ConversionForm conversion={conversionEditor === 'new' ? undefined : conversionEditor} onClose={() => setConversionEditor(null)} onSaved={() => { setConversionEditor(null); reload(); }} />}
    <ConfirmDialog open={can('manageUnits') && !!action} title={action?.conversion ? 'Xóa quy đổi đơn vị?' : 'Ngừng sử dụng đơn vị?'} pending={mutation.pending} onClose={() => setAction(null)} onConfirm={() => { if (can('manageUnits') && action) void mutation.run(() => action.conversion ? catalogApi.deleteConversion(action.id) : catalogApi.deactivateUnit(action.id), () => { setAction(null); reload(); }); }}><p>{action?.name}: {action?.conversion ? 'quy đổi sẽ bị xóa. Các thao tác mới cần quy đổi này có thể bị từ chối. Định lượng và chứng từ đã lưu giữ nguyên.' : 'không còn được chọn cho các nghiệp vụ mới. Có thể kích hoạt lại bằng cách sửa đơn vị.'}</p>{mutation.error && <ErrorPanel error={mutation.error} />}</ConfirmDialog>
  </>;
}

function UnitForm({ unit, onClose, onSaved }: { unit?: Unit; onClose: () => void; onSaved: () => void }) {
  const { can } = useInventoryAuth();
  const initial: UnitWrite = unit ? { unit_code: unit.unit_code, unit_name: unit.unit_name, dimension: unit.dimension, is_active: unit.is_active } : { unit_code: '', unit_name: '', dimension: 'MASS', is_active: true };
  const [form, setForm] = useState(initial);
  const mutation = useMutation(); const dirty = JSON.stringify(form) !== JSON.stringify(initial); useUnsavedChanges(dirty);
  const close = () => { if (!mutation.pending && (!dirty || window.confirm('Bỏ thay đổi đơn vị chưa lưu?'))) onClose(); };
  const change = <K extends keyof UnitWrite>(key: K, value: UnitWrite[K]) => setForm(current => ({ ...current, [key]: value }));
  function submit(event: FormEvent) { event.preventDefault(); if (!can('manageUnits')) return; void mutation.run(() => catalogApi.saveUnit({ ...form, unit_code: form.unit_code.trim(), unit_name: form.unit_name.trim() }, unit?.unit_id), onSaved); }
  return <Modal title={unit ? 'Sửa đơn vị' : 'Thêm đơn vị'} open onClose={close}><form onSubmit={submit}><div className="inv-form-grid"><Field label="Mã đơn vị"><input autoFocus required pattern=".*\S.*" maxLength={20} value={form.unit_code} onChange={event => change('unit_code', event.target.value)} /></Field><Field label="Tên đơn vị"><input required pattern=".*\S.*" maxLength={80} value={form.unit_name} onChange={event => change('unit_name', event.target.value)} /></Field><Field label="Nhóm đơn vị"><select value={form.dimension} disabled={!!unit} onChange={event => change('dimension', event.target.value as UnitDimension)}>{Object.entries(dimensions).map(([value, name]) => <option key={value} value={value}>{name}</option>)}</select></Field><Field label="Đang hoạt động"><input type="checkbox" checked={form.is_active} onChange={event => change('is_active', event.target.checked)} /></Field></div>{unit && <p className="inv-muted">Nhóm đơn vị không thể thay đổi sau khi tạo. Hãy tạo đơn vị mới nếu cần nhóm khác.</p>}{mutation.error && <ErrorPanel error={mutation.error} />}<FormActions pending={mutation.pending} onClose={close} /></form></Modal>;
}

function ConversionForm({ conversion, onClose, onSaved }: { conversion?: UnitConversion; onClose: () => void; onSaved: () => void }) {
  const { can } = useInventoryAuth();
  const initial: ConversionWrite = conversion ? { from_unit_id: conversion.from_unit_id, to_unit_id: conversion.to_unit_id, factor: conversion.factor } : { from_unit_id: 0, to_unit_id: 0, factor: '' };
  const [form, setForm] = useState(initial); const [attempted, setAttempted] = useState(false);
  const units = useUnitOptions(); const mutation = useMutation();
  const dirty = JSON.stringify(form) !== JSON.stringify(initial); useUnsavedChanges(dirty);
  const close = () => { if (!mutation.pending && (!dirty || window.confirm('Bỏ quy đổi chưa lưu?'))) onClose(); };
  const source = units.data?.find(row => row.unit_id === form.from_unit_id); const destination = units.data?.find(row => row.unit_id === form.to_unit_id);
  const pairError = source && destination ? source.unit_id === destination.unit_id ? 'Đơn vị nguồn và đích phải khác nhau.' : source.dimension !== destination.dimension ? 'Quy đổi cần hai đơn vị cùng nhóm.' : undefined : undefined;
  function submit(event: FormEvent) { event.preventDefault(); if (!can('manageUnits')) return; setAttempted(true); if (pairError || decimalError(form.factor, 6, true, 18)) return; void mutation.run(() => catalogApi.saveConversion({ ...form, factor: normalizeDecimal(form.factor) }, conversion?.conversion_id), onSaved); }
  return <Modal title={conversion ? 'Sửa quy đổi' : 'Thêm quy đổi'} open onClose={close}><form onSubmit={submit}><div className="inv-form-grid"><UnitSelect label="Đơn vị nguồn" units={units.data ?? []} value={form.from_unit_id} onChange={value => setForm(current => ({ ...current, from_unit_id: value }))} /><UnitSelect label="Đơn vị đích" units={units.data ?? []} value={form.to_unit_id} onChange={value => setForm(current => ({ ...current, to_unit_id: value }))} /><DecimalField label="Hệ số quy đổi" value={form.factor} onChange={value => setForm(current => ({ ...current, factor: value }))} attempted={attempted} places={6} positive maxDigits={18} /></div>{pairError && <p role="alert">{pairError}</p>}{source && destination && !decimalError(form.factor, 6, true, 18) && !pairError && <p className="inv-summary">1 {source.unit_code} = {normalizeDecimal(form.factor).replace('.', ',')} {destination.unit_code}</p>}{units.error && <ErrorPanel error={units.error} onRetry={units.refresh} />}{mutation.error && <ErrorPanel error={mutation.error} />}<FormActions pending={mutation.pending || units.loading} onClose={close} /></form></Modal>;
}
