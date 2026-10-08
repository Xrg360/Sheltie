"use client";

import { X } from "lucide-react";
import { useEffect, useRef } from "react";
import type { ReactNode } from "react";

import { strings } from "@/lib/strings";

/**
 * Native <dialog> gives focus trapping, Escape-to-close and an inert background for free.
 * variant "modal" = centered dialog, "sheet" = side panel on desktop and bottom sheet on mobile.
 */
export function Dialog({
  open,
  onClose,
  title,
  children,
  footer,
  variant = "modal",
  labelledBy,
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  variant?: "modal" | "sheet";
  labelledBy?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = labelledBy || `dialog-${variant}-title`;

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      className={variant}
      aria-labelledby={titleId}
      onClose={onClose}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === ref.current) onClose();
      }}
    >
      {open ? (
        <>
          <div className="dialog__head">
            <h2 className="dialog__title" id={titleId}>
              {title}
            </h2>
            <button type="button" className="btn btn--ghost btn--icon" aria-label={strings.actions.close} onClick={onClose}>
              <X size={18} aria-hidden="true" />
            </button>
          </div>
          <div className={variant === "sheet" ? "sheet__scroll" : undefined}>
            <div className="dialog__body">{children}</div>
            {footer ? <div className="dialog__foot">{footer}</div> : null}
          </div>
        </>
      ) : null}
    </dialog>
  );
}
