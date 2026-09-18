import { createContext } from 'react';
import type { InventoryCapability } from './permissions';
import type { InventoryCredentials, InventoryUser } from './types';

export interface InventoryAuthContextValue {
  status: 'loading' | 'anonymous' | 'authenticated';
  user: InventoryUser | null;
  unavailable: boolean;
  message?: string;
  deniedPath: string | null;
  can: (capability: InventoryCapability) => boolean;
  signIn: (credentials: InventoryCredentials) => Promise<void>;
  signOut: () => Promise<void>;
  retry: () => void;
  clearDenied: () => void;
}
export const InventoryAuthContext = createContext<InventoryAuthContextValue | null>(null);
