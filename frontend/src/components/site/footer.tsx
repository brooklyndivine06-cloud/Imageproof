import Link from "next/link";

import { Logo } from "@/components/site/logo";

export function Footer() {
  return (
    <footer className="mt-24 border-t border-border">
      <div className="mx-auto grid max-w-6xl gap-8 px-4 py-10 sm:px-6 md:grid-cols-[1.4fr_1fr]">
        <div className="space-y-3">
          <Logo className="text-base" />
          <p className="max-w-md text-sm text-muted-foreground">
            ImageProof reports evidence about how an image may have been made. Its results are estimates, not proof, and no detector can
            guarantee the origin of every image.
          </p>
        </div>
        <nav aria-label="Footer" className="grid grid-cols-2 gap-2 text-sm">
          <Link className="text-muted-foreground hover:text-foreground" href="/how-it-works">How it works</Link>
          <Link className="text-muted-foreground hover:text-foreground" href="/detection-technology">Detection technology</Link>
          <Link className="text-muted-foreground hover:text-foreground" href="/privacy">Privacy notice</Link>
          <Link className="text-muted-foreground hover:text-foreground" href="/#analyze">Analyze an image</Link>
        </nav>
      </div>
    </footer>
  );
}
