import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { Analyzer } from "@/components/analyzer/analyzer";

const steps = [
  { n: "1", title: "Upload", text: "Choose or drop a JPG, PNG or WebP image. It is checked in your browser first, then again on the server." },
  { n: "2", title: "Analyze", text: "The server runs a pretrained classifier, reads metadata, verifies any Content Credentials and measures forensic signals." },
  { n: "3", title: "Review", text: "You get an assessment, the evidence behind it, and a plain statement of what it can and cannot tell you." },
];

export default function HomePage() {
  return (
    <>
      <Analyzer />
      <section aria-labelledby="steps-heading" className="mx-auto mt-20 max-w-6xl px-4 sm:px-6">
        <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
          <h2 id="steps-heading" className="max-w-md text-2xl font-semibold">An analysis in three steps</h2>
          <Link href="/how-it-works" className="inline-flex items-center gap-1.5 text-sm font-medium text-brand hover:underline">
            How it works, and how to read a result <ArrowRight className="size-4" aria-hidden />
          </Link>
        </div>
        <ol className="mt-8 grid gap-px overflow-hidden rounded-xl border border-border bg-border md:grid-cols-3">
          {steps.map((s) => (
            <li key={s.n} className="space-y-2 bg-card p-6">
              <span className="num text-sm font-semibold text-brand">Step {s.n}</span>
              <h3 className="text-lg font-semibold">{s.title}</h3>
              <p className="text-sm leading-relaxed text-muted-foreground">{s.text}</p>
            </li>
          ))}
        </ol>
        <p className="mt-8 max-w-3xl text-sm leading-relaxed text-muted-foreground">
          No AI-image detector is infallible. New generators, heavy compression, screenshots and editing can all fool a classifier in both directions,
          and a missing metadata field or missing Content Credentials proves nothing. ImageProof therefore reports its evidence and its uncertainty
          instead of a single confident number.
        </p>
      </section>
    </>
  );
}
