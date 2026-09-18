import { useSearchParams } from 'react-router-dom';
import { catalogApi, catalogOptions } from '../api/catalog';
import { useQuery } from '../hooks/useQuery';
import { compareDecimal, normalizeDecimal } from '../utils/format';

export function useCatalogFilters() {
  const [params, setParams] = useSearchParams();
  const page = Math.max(1, Number(params.get('page')) || 1);
  const search = params.get('search') ?? '';
  const status = params.get('status') ?? '';
  function setFilter(name: string, value: string) {
    setParams(current => { const next = new URLSearchParams(current); if (value) next.set(name, value); else next.delete(name); if (name !== 'page') next.delete('page'); return next; }, { replace: true });
  }
  return { params, page, search, status, setFilter, clear: () => setParams({}), query: { page, search: search || undefined, status: status || undefined } };
}

export function useUnitOptions() {
  return useQuery('catalog:unit-options', signal => catalogOptions(page => catalogApi.units({ page, page_size: 100 }, signal)));
}

export function decimalError(value: string, places = 3, positive = false, maxDigits = 14): string | undefined {
  if (!value.trim()) return 'Vui lòng nhập giá trị.';
  if (!new RegExp(`^\\d+(?:[.,]\\d{1,${places}})?$`).test(value.trim())) return `Nhập số không âm, tối đa ${places} chữ số thập phân.`;
  const normalized = normalizeDecimal(value);
  if (positive && compareDecimal(normalized, '0') <= 0) return 'Giá trị phải lớn hơn 0.';
  if ((normalized.split('.')[0].replace(/^0+/, '') || '0').length > maxDigits - places) return 'Giá trị vượt giới hạn cho phép.';
  return undefined;
}
