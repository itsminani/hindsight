/** Small shared UI pieces: logo, status pill, page header and dialog. Toasts come from Sonner. */
import { type ReactNode, useEffect } from "react";
import type { Schemas } from "../api/client";

/** The Hindsight mark: a line that dips, then rises past where it was sold. */
export function Logo({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="1" y="1" width="22" height="22" rx="5" stroke="currentColor" strokeWidth="1.6" />
      <path
        d="M5 15.5 9 11l3 2.5L19 6"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="9" cy="11" r="1.6" fill="currentColor" />
    </svg>
  );
}

const STATUS_TEXT: Record<Schemas["Report"]["status"], string> = {
  pending: "Calculating",
  done: "Ready",
  failed: "Failed",
};

/** A report's status as a coloured pill; "pending" shows a small spinner. */
export function StatusPill({ status }: { status: Schemas["Report"]["status"] }) {
  return (
    <span className={`pill ${status}`}>
      {status === "pending" && <span className="spin" aria-hidden="true" />}
      {STATUS_TEXT[status]}
    </span>
  );
}

/** Page title, optional subtitle and breadcrumb, with actions on the right. */
export function PageHead({
  title,
  subtitle,
  crumb,
  actions,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  crumb?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="page-head">
      <div>
        {crumb}
        <h1>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {actions && <div className="row">{actions}</div>}
    </div>
  );
}

/** A modal dialog; Escape or a click on the backdrop closes it. */
export function Dialog({
  title,
  children,
  footer,
  onClose,
}: {
  title: string;
  children: ReactNode;
  footer: ReactNode;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="dialog" role="dialog" aria-modal="true" aria-label={title}>
        <div className="dialog-body">
          <h2>{title}</h2>
          {children}
        </div>
        <div className="dialog-foot">{footer}</div>
      </div>
    </div>
  );
}
