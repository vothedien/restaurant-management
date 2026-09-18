import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe,it,expect,vi } from 'vitest';
import { createMemoryRouter, Link, RouterProvider } from 'react-router-dom';
import { useMutation } from './useMutation';
import { useQuery } from './useQuery';
import { useUnsavedChanges } from './useUnsavedChanges';

describe('inventory request lifecycle',()=>{
  it('blocks a second mutation before React has rendered pending state, then refreshes queries',async()=>{
    let resolve!: (value:string)=>void;const mutation=vi.fn(()=>new Promise<string>(done=>{resolve=done;}));const load=vi.fn(async()=> 'server value');
    function Harness(){const query=useQuery('test',load);const action=useMutation();return <><div>{query.data}</div><button onClick={()=>{void action.run(mutation);void action.run(mutation);}}>Send</button>{action.pending&&<p>Pending</p>}</>;}
    render(<Harness/>);await screen.findByText('server value');fireEvent.click(screen.getByText('Send'));expect(mutation).toHaveBeenCalledTimes(1);expect(screen.getByText('Pending')).toBeInTheDocument();await act(async()=>resolve('ok'));await waitFor(()=>expect(load).toHaveBeenCalledTimes(2));
  });
  it('ignores a stale response after a filter changes and aborts the old query',async()=>{
    let resolveOld!: (value:string)=>void;let oldSignal:AbortSignal|undefined;
    function Harness({name}:{name:string}){const query=useQuery(name,signal=>name==='old'?new Promise<string>(resolve=>{oldSignal=signal;resolveOld=resolve;}):Promise.resolve('new data'));return <p>{query.data??'Loading'}</p>;}
    const view=render(<Harness name="old"/>);view.rerender(<Harness name="new"/>);await screen.findByText('new data');expect(oldSignal?.aborted).toBe(true);await act(async()=>resolveOld('stale data'));expect(screen.queryByText('stale data')).not.toBeInTheDocument();
  });
  it('keeps navigation on the editor when unsaved-change confirmation is declined',async()=>{
    const confirm=vi.spyOn(window,'confirm').mockReturnValue(false);
    function Editor(){useUnsavedChanges(true);return <Link to="/next">Leave</Link>;}
    const router=createMemoryRouter([{path:'/',element:<Editor/>},{path:'/next',element:<p>Next page</p>}]);render(<RouterProvider router={router}/>);fireEvent.click(screen.getByText('Leave'));await waitFor(()=>expect(confirm).toHaveBeenCalledTimes(1));expect(screen.queryByText('Next page')).not.toBeInTheDocument();expect(router.state.location.pathname).toBe('/');
  });
  it('retains loaded data after a failed refresh so transactional editors remain mounted',async()=>{
    const load=vi.fn().mockResolvedValueOnce('saved document').mockRejectedValueOnce(new Error('network failed'));
    function Harness(){const query=useQuery<string>('preserve',load);return <><div>{query.data}</div><div>{query.error?.message}</div><button onClick={query.refresh}>Reload</button></>;}
    render(<Harness/>);await screen.findByText('saved document');fireEvent.click(screen.getByText('Reload'));await screen.findByText('network failed');expect(screen.getByText('saved document')).toBeInTheDocument();
  });
});
