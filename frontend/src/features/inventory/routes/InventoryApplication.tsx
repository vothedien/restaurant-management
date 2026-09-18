import { Route, Routes } from 'react-router-dom';
import { InventoryAuthProvider } from '../auth/InventoryAuthProvider';
import { InventoryAuthGuard } from '../auth/InventoryGuards';
import { InventoryLoginPage } from '../auth/InventoryLoginPage';
import { InventoryLayout } from '../layouts/InventoryLayout';
import InventoryRoutes from './InventoryRoutes';
import '../inventory.css';
import '../layouts/InventoryLayout.css';

export default function InventoryApplication() {
  return <InventoryAuthProvider><Routes><Route path="login" element={<InventoryLoginPage />} /><Route element={<InventoryAuthGuard />}><Route element={<InventoryLayout />}><Route path="*" element={<InventoryRoutes />} /></Route></Route></Routes></InventoryAuthProvider>;
}
