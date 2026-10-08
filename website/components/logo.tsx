// Same mark as the dashboard (src/components/ui/logo.tsx). Colors come from --brand-* tokens.
export function Logo({ size = 32 }: { size?: number }) {
  return (
    <svg className="logo" width={size} height={size} viewBox="0 0 64 64" role="img" aria-label="Meerkat">
      <rect className="logo__bg" width="64" height="64" rx="16" />
      <rect className="logo__ground" x="10" y="54" width="44" height="3" rx="1.5" />
      <path className="logo__tail" d="M25 52c-4 1-8 1.5-11 3.5" fill="none" strokeWidth="3.2" strokeLinecap="round" />
      <path className="logo__fur" d="M24 55c-1.6-7-1.8-14 .4-21 1.4-4.4 3.9-7.6 7-9.2l5.2 1.4c2.2 4.2 2.8 9.6 2.2 15.5-.6 5.4-2.2 10-4.4 13.3Z" />
      <path className="logo__fur" d="M28.5 18.2c0-4.6 3.6-8 8-8 3.3 0 5.6 1.8 7.1 4.6l4.4 2.3c.9.5.9 1.7 0 2.2l-4.5 2.1c-1.4 3-4 4.8-7.3 4.8-4.4 0-7.7-3.4-7.7-8Z" />
      <circle className="logo__fur-dark" cx="31.2" cy="11.8" r="2.3" />
      <ellipse className="logo__mask" cx="38.6" cy="16.6" rx="2.6" ry="1.9" />
      <circle className="logo__eye" cx="39" cy="16.4" r="0.9" />
      <circle className="logo__mask" cx="48.2" cy="18.4" r="1.4" />
      <path className="logo__fur-dark" d="M35.6 31.2c1.8-.4 3.6.2 4.4 1.4.4.7-.1 1.5-.9 1.4-1.4-.2-2.6-.1-3.8.4-.8.3-1.6-.3-1.4-1.1.2-.9.8-1.7 1.7-2.1Z" />
    </svg>
  );
}
