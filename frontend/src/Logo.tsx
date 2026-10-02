// AdVera mark (docs/design/advera_logo): an "A" of a signal path over two nodes.
export function Logo({ size = 32 }: { size?: number }) {
  return (
    <svg viewBox="0 0 40 40" width={size} height={size} fill="none" aria-hidden="true">
      <rect x="0.75" y="0.75" width="38.5" height="38.5" rx="10" fill="#181E29" stroke="#2E3A4D" strokeWidth="1.5" />
      <path d="M12 28L20 12L28 28" stroke="#38BDF8" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M15 22H25" stroke="#818CF8" strokeWidth="2" strokeLinecap="round" />
      <circle cx="20" cy="18" r="2.5" fill="#38BDF8" />
      <circle cx="12" cy="28" r="1.5" fill="#818CF8" />
      <circle cx="28" cy="28" r="1.5" fill="#818CF8" />
    </svg>
  );
}
