import { useContext } from 'react';
import { InventoryAuthContext } from './context';

export function useInventoryAuth() {
  const context = useContext(InventoryAuthContext);
  if (!context) throw new Error('InventoryAuthProvider is required.');
  return context;
}
