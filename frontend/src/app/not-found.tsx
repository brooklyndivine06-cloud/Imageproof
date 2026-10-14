import Link from "next/link";

import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-xl px-4 py-24 text-center sm:px-6">
      <h1 className="text-3xl font-semibold">Page not found</h1>
      <p className="mt-3 text-muted-foreground">The page you are looking for does not exist.</p>
      <Button asChild className="mt-6"><Link href="/">Back to ImageProof</Link></Button>
    </div>
  );
}
