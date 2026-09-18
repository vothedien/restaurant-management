import { describe,it,expect } from 'vitest';
import { addDecimal,compareDecimal,date,dateTime,expiryDays,expiryStatus,money,multiplyDecimal,normalizeDecimal,quantity,roundDecimal,subtractDecimal } from './format';
import { csvText } from './csv';
import { errorInfo } from './errors';
import { AxiosError } from 'axios';

describe('exact inventory quantities and formatting',()=>{
  it('keeps decimals exact including large values',()=>{
    expect(addDecimal('0.1','0.2')).toBe('0.3');
    expect(subtractDecimal('2.000','1.125')).toBe('0.875');
    expect(multiplyDecimal('99999999999.999','1000')).toBe('99999999999999');
    expect(compareDecimal('0','0.000')).toBe(0);
    expect(roundDecimal(multiplyDecimal('0.125','1.00'),2)).toBe('0.13');
  });
  it('normalizes Vietnamese decimal input without ambiguous thousands',()=>{
    expect(normalizeDecimal(' 001,250 ')).toBe('1.25');
    expect(()=>normalizeDecimal('1.000,25')).toThrow();
    expect(()=>normalizeDecimal('1e8')).toThrow();
    expect(()=>normalizeDecimal('')).toThrow();
    expect(quantity('1200.125')).toBe('1.200,125');
    expect(money('1234567.25')).toBe('1.234.567,25 ₫');
  });
  it('keeps date-only expiry stable and displays UTC instants in Vietnam',()=>{
    expect(date('2026-09-15')).toBe('15/09/2026');
    expect(dateTime('2026-09-14T18:00:00Z')).toContain('15/9/26');
    expect(expiryDays('2026-09-15','2026-09-15')).toBe(0);
    expect(expiryStatus('2026-09-14','2026-09-15')).toBe('EXPIRED');
    expect(expiryStatus('2026-09-18','2026-09-15')).toBe('EXPIRING_3');
    expect(expiryStatus('2026-09-22','2026-09-15')).toBe('EXPIRING_7');
    expect(expiryStatus('2026-09-29','2026-09-15')).toBe('EXPIRING_14');
    expect(expiryStatus(null)).toBe('NO_EXPIRY');
  });
  it('exports escaped CSV and neutralizes spreadsheet formulas',()=>{
    const csv=csvText(['Tên','Số'],[['=SUM(A1)','0'],['A,"B"','1.25']]);
    expect(csv).toContain('"\'=SUM(A1)"');expect(csv).toContain('"A,""B"""');expect(csv.startsWith('\uFEFF')).toBe(true);
  });
  it('preserves business conflict guidance without raw stack traces',()=>{
    const error=new AxiosError('request failed');
    Object.assign(error,{response:{status:409,data:{message:'Stock moved after counting started'},headers:{}}});
    expect(errorInfo(error).message).toContain('Tồn kho đã thay đổi');
    Object.assign(error,{response:{status:403,data:{message:'secret internal text'},headers:{}}});
    expect(errorInfo(error).message).toContain('không đủ quyền');expect(errorInfo(error).message).not.toContain('secret');
  });
});
