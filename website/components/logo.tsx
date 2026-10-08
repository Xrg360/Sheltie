// Same mark as the dashboard (src/components/ui/logo.tsx). Colors come from --brand-* tokens.
export function Logo({ size = 32 }: { size?: number }) {
  return (
    <svg className="logo" width={size} height={size} viewBox="0 0 64 64" role="img" aria-label="Labwarden">
      <rect className="logo__bg" width="64" height="64" rx="16" />
      <path className="logo__shield" d="M32 9l18 6.5V30c0 11.6-7.4 20.2-18 24.5C21.4 50.2 14 41.6 14 30V15.5Z" />
      <path className="logo__pulse" d="M20 32h7l3.5-8 5 16 3.5-8H44" fill="none" strokeWidth="3.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
