// Browser-local preferences. Every access is wrapped: storage can be missing or blocked.

export type ThemePref = "system" | "light" | "dark";

export type Prefs = {
  theme: ThemePref;
  refreshMs: number;
  popups: boolean;
  desktop: boolean;
  pinned: string[];
  token: string;
};

export const DEFAULT_PREFS: Prefs = {
  theme: "system",
  refreshMs: 10_000,
  popups: true,
  desktop: false,
  pinned: [],
  token: "",
};

const PREFS_KEY = "meerkat.prefs";
const SNAPSHOT_KEY = "meerkat.snapshot";
const SEEN_KEY = "meerkat.seen";
const VISIT_KEY = "meerkat.lastVisit";

export function read<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

export function write(key: string, value: unknown): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Storage full or blocked: preferences simply do not persist.
  }
}

export function loadPrefs(): Prefs {
  const stored = read<Partial<Prefs>>(PREFS_KEY, {});
  // Migrate the action token from the previous UI.
  let legacyToken = "";
  try {
    legacyToken = window.localStorage.getItem("meerkatActionToken") || "";
  } catch {
    legacyToken = "";
  }
  return { ...DEFAULT_PREFS, token: legacyToken, ...stored };
}

export function savePrefs(prefs: Prefs): void {
  write(PREFS_KEY, prefs);
}

export const storageKeys = { snapshot: SNAPSHOT_KEY, seen: SEEN_KEY, visit: VISIT_KEY };

export function applyTheme(theme: ThemePref): void {
  const root = document.documentElement;
  if (theme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", theme);
}

/** Runs before first paint (inlined in layout.tsx) so there is no theme flash. */
export const THEME_BOOTSTRAP = `try{var p=JSON.parse(localStorage.getItem("${PREFS_KEY}")||"{}");if(p.theme==="light"||p.theme==="dark")document.documentElement.setAttribute("data-theme",p.theme)}catch(e){}`;
