"use client";

import { Copy, X } from "lucide-react";
import { useEffect, useState } from "react";

import { Dialog } from "@/components/ui/dialog";
import { StatusIcon } from "@/components/ui/status";
import { NAV } from "@/lib/nav";
import { useMeerkat } from "@/lib/store";
import { strings } from "@/lib/strings";

export function Toasts() {
  const { toasts, dismissToast } = useMeerkat();
  return (
    <div className="toasts" role="region" aria-live="polite" aria-label="Notifications">
      {toasts.map((toast) => (
        <div className="toast" key={toast.id} role={toast.tone === "bad" ? "alert" : "status"}>
          <StatusIcon tone={toast.tone === "info" ? "unknown" : toast.tone} size={18} />
          <div className="toast__text">
            <span className="toast__title">{toast.title}</span>
            {toast.body ? <span className="toast__body">{toast.body}</span> : null}
          </div>
          {toast.action ? (
            <button
              type="button"
              className="btn btn--sm"
              onClick={() => {
                toast.action?.run();
                dismissToast(toast.id);
              }}
            >
              {toast.action.label}
            </button>
          ) : null}
          <button type="button" className="btn btn--ghost btn--sm btn--icon" aria-label={strings.actions.close} onClick={() => dismissToast(toast.id)}>
            <X size={16} aria-hidden="true" />
          </button>
        </div>
      ))}
    </div>
  );
}

export function ConfirmDialog() {
  const { pendingConfirm, settleConfirm } = useMeerkat();
  return (
    <Dialog
      open={Boolean(pendingConfirm)}
      onClose={() => settleConfirm(false)}
      title={pendingConfirm?.title ?? ""}
      labelledBy="confirm-title"
      footer={
        <>
          <button type="button" className="btn" onClick={() => settleConfirm(false)}>
            {strings.actions.cancel}
          </button>
          <button type="button" className={`btn ${pendingConfirm?.danger ? "btn--danger" : "btn--primary"}`} onClick={() => settleConfirm(true)} autoFocus>
            {pendingConfirm?.confirmLabel ?? strings.actions.confirm}
          </button>
        </>
      }
    >
      {pendingConfirm?.body ? <p className="muted">{pendingConfirm.body}</p> : null}
    </Dialog>
  );
}

export function TokenDialog() {
  const { tokenRequest, settleToken, prefs, toast } = useMeerkat();
  const [value, setValue] = useState("");

  useEffect(() => {
    if (tokenRequest) setValue(prefs.token);
  }, [tokenRequest, prefs.token]);

  return (
    <Dialog
      open={Boolean(tokenRequest)}
      onClose={() => settleToken(null)}
      title={strings.actions.tokenTitle}
      labelledBy="token-title"
      footer={
        <>
          <button type="button" className="btn" onClick={() => settleToken(null)}>
            {strings.actions.cancel}
          </button>
          <button type="submit" form="token-form" className="btn btn--primary" disabled={!value.trim()}>
            {strings.actions.tokenSubmit}
          </button>
        </>
      }
    >
      <p className="muted">{strings.actions.tokenBody}</p>
      <div className="cluster">
        <code className="mono">{strings.actions.tokenCommand}</code>
        <button
          type="button"
          className="btn btn--ghost btn--sm btn--icon"
          aria-label="Copy command"
          onClick={() => {
            navigator.clipboard?.writeText(strings.actions.tokenCommand).then(() => toast({ tone: "ok", title: "Copied" }));
          }}
        >
          <Copy size={14} aria-hidden="true" />
        </button>
      </div>
      <form
        id="token-form"
        className="field"
        onSubmit={(event) => {
          event.preventDefault();
          if (value.trim()) settleToken(value.trim());
        }}
      >
        <label className="label" htmlFor="token-input">
          {strings.settings.token}
        </label>
        <input id="token-input" className="input mono" value={value} onChange={(event) => setValue(event.target.value)} autoComplete="off" spellCheck={false} autoFocus />
      </form>
    </Dialog>
  );
}

export function ShortcutsDialog() {
  const { shortcutsOpen, setShortcutsOpen } = useMeerkat();
  return (
    <Dialog open={shortcutsOpen} onClose={() => setShortcutsOpen(false)} title={strings.shortcuts.title} labelledBy="shortcuts-title">
      <div className="shortcuts">
        <span>{strings.shortcuts.palette}</span>
        <span className="cluster">
          <kbd>⌘</kbd>
          <kbd>K</kbd>
          <span className="subtle">or</span>
          <kbd>/</kbd>
        </span>
        {NAV.map((item) => (
          <ShortcutRow key={item.href} label={strings.shortcuts.goto(item.label)} keys={["g", item.key]} />
        ))}
        <ShortcutRow label={strings.shortcuts.help} keys={["?"]} />
      </div>
    </Dialog>
  );
}

function ShortcutRow({ label, keys }: { label: string; keys: string[] }) {
  return (
    <>
      <span>{label}</span>
      <span className="cluster">
        {keys.map((key) => (
          <kbd key={key}>{key}</kbd>
        ))}
      </span>
    </>
  );
}
