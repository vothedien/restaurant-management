import { Children, cloneElement, isValidElement, useEffect, useId, useRef, type InputHTMLAttributes, type ReactNode } from "react";
import { errorInfo } from "../utils/errors";
import { useInventoryAuth } from '../auth/useInventoryAuth';

const STATUS_LABELS: Record<string, string> = {
  ACTIVE: "Hoạt động", INACTIVE: "Ngừng hoạt động", SUSPENDED: "Tạm ngừng", DRAFT: "Nháp", PENDING_APPROVAL: "Chờ duyệt", APPROVED: "Đã duyệt", ORDERED: "Đã đặt hàng", PARTIALLY_RECEIVED: "Đã nhập một phần", RECEIVED: "Đã nhập đủ", CANCELLED: "Đã hủy", CONFIRMED: "Đã chốt", IN_PROGRESS: "Đang kiểm kê", COMPLETED: "Hoàn tất", DEPLETED: "Hết lô", BLOCKED: "Bị khóa", EXPIRED: "Hết hạn", RECEIPT: "Nhập hàng", CONSUMPTION: "Tiêu hao món", ADJUSTMENT: "Điều chỉnh / xuất", RETURN: "Hoàn trả", IN: "Nhập", OUT: "Xuất", LOW: "Dưới định mức", OUT_OF_STOCK: "Hết hàng", HEALTHY: "Đủ định mức", EXPIRING_3: "Hạn ≤ 3 ngày", EXPIRING_7: "Hạn ≤ 7 ngày", EXPIRING_14: "Hạn ≤ 14 ngày", NO_EXPIRY: "Không có hạn dùng", FRESH: "Còn hạn", COUNTED: "Đã kiểm", UNCOUNTED: "Chưa kiểm", MATCHED: "Khớp", DIFFERENCE: "Chênh lệch",
};
export function PageHeader({ title, description, actions }: {title: string; description?: string; actions?: ReactNode}) {
  return <header className="inv-page-header"><div><h1>{title}</h1>{description && <p>{description}</p>}</div>{actions && <div className="inv-actions">{actions}</div>}</header>;
}
export function Badge({ status }: {status: string}) {
  const tone = /CANCELLED|EXPIRED|OUT_OF_STOCK|BLOCKED|DIFFERENCE/.test(status) ? "danger" : /PENDING|PARTIALLY|PROGRESS|LOW|EXPIRING|UNCOUNTED|SUSPENDED/.test(status) ? "warning" : /^(ACTIVE|APPROVED|CONFIRMED|COMPLETED|RECEIVED|HEALTHY|FRESH|MATCHED|COUNTED)$/.test(status) ? "success" : "neutral";
  return <span className={`inv-badge ${tone}`}><span aria-hidden="true" className="inv-dot" />{STATUS_LABELS[status] ?? status}</span>;
}
export function ErrorPanel({ error, onRetry }: {error: unknown; onRetry?: () => void}) {
  if (!error) return null;
  const info = errorInfo(error);
  return <div className="inv-error" role="alert"><strong>{info.title}</strong><p>{info.message}</p>{info.requestId && <small>Mã yêu cầu: {info.requestId}</small>}{onRetry && <button type="button" className="inv-button secondary" onClick={onRetry}>Tải lại dữ liệu</button>}</div>;
}
export function EmptyState({ title, description, action }: {title: string; description?: string; action?: ReactNode}) {
  return <div className="inv-empty"><div className="inv-empty-mark" aria-hidden="true">—</div><h3>{title}</h3>{description && <p>{description}</p>}{action}</div>;
}
export function LoadingState() {
  return <div className="inv-skeleton" role="status" aria-label="Đang tải dữ liệu"><span className="inv-sr-only">Đang tải dữ liệu…</span>{[1, 2, 3, 4, 5].map(n => <div key={n} />)}</div>;
}
export function Panel({ title, children, actions }: {title?: string; children: ReactNode; actions?: ReactNode}) {
  return <section className="inv-panel">{(title || actions) && <div className="inv-panel-header">{title && <h2>{title}</h2>}{actions && <div className="inv-actions">{actions}</div>}</div>}{children}</section>;
}
export function Field({ label, error, children }: {label: string; error?: string; children: ReactNode}) {
  const id = useId();
  return <div className="inv-field"><label htmlFor={id}>{label}</label>{Children.map(children, child => {
    if (!isValidElement<InputHTMLAttributes<HTMLInputElement>>(child)) return child;
    if (child.type === 'input' || child.type === 'select' || child.type === 'textarea' || child.type === DecimalInput) {
      return cloneElement(child, { id, 'aria-invalid': error ? true : child.props['aria-invalid'], 'aria-describedby': error ? `${id}-error` : child.props['aria-describedby'] });
    }
    return child;
  })}{error && <span id={`${id}-error`} className="inv-field-error" role="alert">{error}</span>}</div>;
}
export function DecimalInput({ value, onChange, ...props }: Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "onChange"> & {value: string; onChange: (value: string) => void}) {
  return <input type="text" inputMode="decimal" autoComplete="off" {...props} value={value} onChange={event => onChange(event.target.value)} />;
}
export function CurrentActor({ label = 'Người thực hiện' }: { label?: string }) {
  const { user } = useInventoryAuth();
  return <div className="inv-current-actor"><span className="inv-muted">{label}</span><strong>{user?.displayName ?? 'Chưa xác thực tài khoản'}</strong></div>;
}
export function Modal({ title, open, onClose, children }: {title: string; open: boolean; onClose: () => void; children: ReactNode}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const element = dialog.current;
    if (!open || !element) return;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    if (!element.open) element.showModal();
    element.querySelector<HTMLElement>('input:not([type="checkbox"]):not([type="hidden"]):not(:disabled),select:not(:disabled),textarea:not(:disabled)')?.focus();
    return () => { if (element.open) element.close(); previousFocus?.focus(); };
  }, [open]);
  return <dialog ref={dialog} className="inv-modal" aria-labelledby={titleId} onCancel={event => { event.preventDefault(); onClose(); }}><div className="inv-modal-header"><h2 id={titleId}>{title}</h2><button type="button" aria-label="Đóng hộp thoại" className="inv-button secondary" onClick={onClose}>Đóng</button></div>{open && <div className="inv-modal-body">{children}</div>}</dialog>;
}
export function ConfirmDialog({open, title, children, onConfirm, onClose, pending}: {open: boolean; title: string; children: ReactNode; onConfirm: () => void; onClose: () => void; pending?: boolean}) {
  return <Modal open={open} title={title} onClose={() => { if (!pending) onClose(); }}><div className="inv-confirm-copy">{children}</div><div className="inv-actions inv-modal-actions"><button type="button" className="inv-button secondary" disabled={pending} onClick={onClose}>Quay lại</button><button type="button" className="inv-button" disabled={pending} onClick={onConfirm}>{pending ? "Đang xử lý…" : "Xác nhận"}</button></div></Modal>;
}
export function Pagination({page, total, pageSize, onChange}: {page: number; total: number; pageSize: number; onChange: (page: number) => void}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return <div className="inv-pagination"><span>{total ? `${(page - 1) * pageSize + 1}–${Math.min(page * pageSize, total)} / ${total}` : "0 kết quả"}</span><div className="inv-actions"><button type="button" className="inv-button secondary" disabled={page <= 1} onClick={() => onChange(page - 1)}>Trước</button><span>Trang {page} / {pages}</span><button type="button" className="inv-button secondary" disabled={page >= pages} onClick={() => onChange(page + 1)}>Sau</button></div></div>;
}
