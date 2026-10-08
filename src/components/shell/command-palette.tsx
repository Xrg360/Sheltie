"use client";

import { Bell, BellOff, Boxes, Globe, Keyboard, Moon, Plus, RefreshCw, Search, Sun } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

import { NAV } from "@/lib/nav";
import { useSheltie } from "@/lib/store";
import { strings } from "@/lib/strings";

type Command = { id: string; group: string; label: string; hint?: string; icon: ReactNode; run: () => void };

export function CommandPalette() {
  const { paletteOpen, setPaletteOpen, snapshot, act, prefs, setPrefs, refresh, setShortcutsOpen } = useSheltie();
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState(0);
  const dialog = useRef<HTMLDialogElement>(null);
  const input = useRef<HTMLInputElement>(null);

  const commands = useMemo<Command[]>(() => {
    const close = (fn: () => void) => () => {
      setPaletteOpen(false);
      fn();
    };
    const g = strings.search.groups;
    const list: Command[] = NAV.map((item) => {
      const Icon = item.icon;
      return { id: `nav:${item.href}`, group: g.pages, label: item.label, hint: `g ${item.key}`, icon: <Icon size={16} />, run: close(() => router.push(item.href)) };
    });
    list.push(
      { id: "add-monitor", group: g.actions, label: strings.monitors.add, icon: <Plus size={16} />, run: close(() => router.push("/monitors?add=1")) },
      snapshot?.status?.alerts_silenced
        ? { id: "resume", group: g.actions, label: strings.silence.resume, icon: <Bell size={16} />, run: close(() => void act("actions/alerts/resume", {}, { success: strings.silence.resumed })) }
        : { id: "silence-1h", group: g.actions, label: strings.silence.oneHour, icon: <BellOff size={16} />, run: close(() => void act("actions/alerts/silence", { minutes: 60 }, { success: strings.silence.done })) },
      { id: "theme", group: g.actions, label: `Switch to ${prefs.theme === "dark" ? "light" : "dark"} theme`, icon: prefs.theme === "dark" ? <Sun size={16} /> : <Moon size={16} />, run: close(() => setPrefs({ theme: prefs.theme === "dark" ? "light" : "dark" })) },
      { id: "refresh", group: g.actions, label: "Refresh now", icon: <RefreshCw size={16} />, run: close(() => void refresh()) },
      { id: "shortcuts", group: g.actions, label: strings.shortcuts.title, hint: "?", icon: <Keyboard size={16} />, run: close(() => setShortcutsOpen(true)) },
    );
    for (const site of snapshot?.sites?.sites ?? []) {
      list.push({ id: `site:${site.name}`, group: g.monitors, label: site.name, hint: site.up ? "up" : "down", icon: <Globe size={16} />, run: close(() => router.push(`/monitors?site=${encodeURIComponent(site.name)}`)) });
    }
    for (const container of snapshot?.docker?.containers ?? []) {
      list.push({ id: `container:${container.name}`, group: g.containers, label: container.name, hint: container.status, icon: <Boxes size={16} />, run: close(() => router.push(`/containers?q=${encodeURIComponent(container.name)}`)) });
    }
    return list;
  }, [snapshot, prefs.theme, act, refresh, router, setPaletteOpen, setPrefs, setShortcutsOpen]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return commands.filter((command) => command.group !== strings.search.groups.containers);
    return commands.filter((command) => `${command.label} ${command.group} ${command.hint ?? ""}`.toLowerCase().includes(needle));
  }, [commands, query]);

  useEffect(() => {
    const element = dialog.current;
    if (!element) return;
    if (paletteOpen && !element.open) {
      setQuery("");
      setIndex(0);
      element.showModal();
      window.setTimeout(() => input.current?.focus(), 0);
    }
    if (!paletteOpen && element.open) element.close();
  }, [paletteOpen]);

  useEffect(() => setIndex(0), [query]);

  function onKeyDown(event: React.KeyboardEvent) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setIndex((current) => Math.min(filtered.length - 1, current + 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setIndex((current) => Math.max(0, current - 1));
    } else if (event.key === "Enter") {
      event.preventDefault();
      filtered[index]?.run();
    }
  }

  let lastGroup = "";
  return (
    <dialog
      ref={dialog}
      className="palette"
      aria-label={strings.search.trigger}
      onClose={() => setPaletteOpen(false)}
      onClick={(event) => {
        if (event.target === dialog.current) setPaletteOpen(false);
      }}
    >
      <div className="palette__input">
        <Search size={18} aria-hidden="true" />
        <input
          ref={input}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder={strings.search.placeholder}
          aria-label={strings.search.placeholder}
          role="combobox"
          aria-expanded="true"
          aria-controls="palette-list"
          aria-activedescendant={filtered[index] ? `cmd-${index}` : undefined}
        />
        <kbd>esc</kbd>
      </div>
      <ul className="palette__list" id="palette-list" role="listbox" aria-label="Commands">
        {filtered.length === 0 ? <li className="palette__empty">{strings.search.empty}</li> : null}
        {filtered.map((command, position) => {
          const header = command.group !== lastGroup ? command.group : null;
          lastGroup = command.group;
          return (
            <li key={command.id} role="presentation">
              {header ? (
                <div className="palette__group" role="presentation">
                  {header}
                </div>
              ) : null}
              <div
                id={`cmd-${position}`}
                role="option"
                aria-selected={position === index}
                className="palette__item"
                onMouseEnter={() => setIndex(position)}
                onClick={() => command.run()}
              >
                {command.icon}
                <span>{command.label}</span>
                {command.hint ? <span className="palette__hint">{command.hint}</span> : null}
              </div>
            </li>
          );
        })}
      </ul>
    </dialog>
  );
}
