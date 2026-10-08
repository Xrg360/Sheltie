"use client";

import { useEffect } from "react";

// Renders ```mermaid blocks in docs. Loaded only on pages that contain diagrams.
export function Mermaid() {
  useEffect(() => {
    let cancelled = false;
    import("mermaid").then(({ default: mermaid }) => {
      if (cancelled) return;
      const dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
      mermaid.initialize({ startOnLoad: false, theme: dark ? "dark" : "neutral", securityLevel: "strict" });
      mermaid.run({ querySelector: "pre.mermaid" });
    });
    return () => {
      cancelled = true;
    };
  }, []);
  return null;
}
