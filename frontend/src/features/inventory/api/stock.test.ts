import { describe,it,expect,vi } from 'vitest';
import { collect } from './stock';
import { get } from './http';
vi.mock('./http',()=>({get:vi.fn()}));
describe('bounded report collections',()=>{
  it('fetches every page using real limit/offset contract',async()=>{
    vi.mocked(get).mockResolvedValueOnce({items:Array.from({length:100},(_,i)=>i),total:101,limit:100,offset:0}).mockResolvedValueOnce({items:[100],total:101,limit:100,offset:100});
    expect(await collect<number>('/inventory/stock')).toHaveLength(101);expect(get).toHaveBeenNthCalledWith(2,'/inventory/stock',{limit:100,offset:100},undefined);
  });
  it('rejects oversized collections instead of showing a partial KPI',async()=>{
    vi.mocked(get).mockResolvedValueOnce({items:[],total:1001,limit:100,offset:0});await expect(collect('/inventory/stock')).rejects.toThrow('vượt giới hạn');expect(get).toHaveBeenCalledTimes(1);
  });
  it('rejects totals changing during collection',async()=>{
    vi.mocked(get).mockResolvedValueOnce({items:Array.from({length:100},()=>1),total:101,limit:100,offset:0}).mockResolvedValueOnce({items:[1,2],total:102,limit:100,offset:100});await expect(collect('/inventory/stock')).rejects.toThrow('đã thay đổi');
  });
});
