import { cn } from "@/lib/utils";

/** Image frame with registration marks at the corners, echoing a forensic contact sheet. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cn("size-7", className)} fill="none" aria-hidden>
      <path d="M4 11V6a2 2 0 0 1 2-2h5M21 4h5a2 2 0 0 1 2 2v5M28 21v5a2 2 0 0 1-2 2h-5M11 28H6a2 2 0 0 1-2-2v-5" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
      <path d="M9.5 20.5 14 15l3.5 4 2.5-3 3 4.5" stroke="var(--brand)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="20.5" cy="11.5" r="1.8" fill="var(--brand)" />
    </svg>
  );
}

export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5 text-[17px] font-semibold tracking-tight", className)}>
      <LogoMark />
      ImageProof
    </span>
  );
}
