"use client";

import { Copy } from "lucide-react";

import { useSheltie } from "@/lib/store";
import { strings } from "@/lib/strings";

/** A command or value shown in monospace with a copy button, e.g. the token command or a split DNS address. */
export function CopyText({ text, what }: { text: string; what: string }) {
  const { toast } = useSheltie();
  return (
    <span className="cluster">
      <code className="mono">{text}</code>
      <button
        type="button"
        className="btn btn--ghost btn--sm btn--icon"
        aria-label={strings.actions.copy(what)}
        onClick={() => {
          navigator.clipboard?.writeText(text).then(() => toast({ tone: "ok", title: strings.actions.copied }));
        }}
      >
        <Copy size={14} aria-hidden="true" />
      </button>
    </span>
  );
}
