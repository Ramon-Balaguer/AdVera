// The AdVera mark (docs/brand): one outlined triangle, the "A", with a teal bar, an amber spark
// and a few small triangles drifting off it, like the particles of the brain.
export function Logo({ size = 32 }: { size?: number }) {
  return (
    <svg viewBox="0 0 64 64" width={size} height={size} fill="none" aria-hidden="true">
      <path d="M32 9L55 51H9Z" stroke="#8052ff" strokeWidth="4.5" strokeLinejoin="round" />
      <path d="M21.5 38H42.5" stroke="#15846e" strokeWidth="3.5" strokeLinecap="round" />
      <path d="M32 23.5L36.4 31.2H27.6Z" fill="#ffb829" />
      <path d="M52.5 12.5L55.6 17.8H49.4Z" stroke="#2fd6a5" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M58.5 25L60.6 28.6H56.4Z" stroke="#ff4fa3" strokeWidth="1.4" strokeLinejoin="round" />
      <path d="M46 5L47.8 8.1H44.2Z" stroke="#3d8bff" strokeWidth="1.3" strokeLinejoin="round" />
    </svg>
  );
}
