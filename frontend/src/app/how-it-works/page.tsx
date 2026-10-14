import type { Metadata } from "next";

import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";

export const metadata: Metadata = { title: "How it works" };

const sources = [
  {
    title: "Visual classifier",
    body: "A pretrained image-classification model looks at the pixels and outputs a score for each label it knows. The score is compared with two thresholds to give Likely AI-Generated, Likely Camera-Captured or Inconclusive. It is the main basis for the assessment.",
  },
  {
    title: "Metadata",
    body: "EXIF, XMP and text fields embedded in the file: camera make and model, exposure settings, dates, editing software. Some AI tools also write their prompts or settings into files. Metadata is easy to copy, edit and strip, so it is shown as supporting context. Missing metadata is normal and is never treated as a sign of AI generation.",
  },
  {
    title: "Provenance (C2PA Content Credentials)",
    body: "Some cameras, editors and AI services attach a cryptographically signed record of how an image was made and edited. ImageProof verifies the signature and reports what the record says. Credentials that validate against a trusted signer and declare AI generation can override the classifier; everything else is reported without changing the assessment.",
  },
  {
    title: "Visual forensics",
    body: "Measurements of noise, frequency content, JPEG compression and error levels. They describe the image and can help a specialist, but no threshold for them has been validated, so they never influence the assessment.",
  },
];

const education = [
  {
    q: "What is AI-generated imagery?",
    a: "Images produced by generative models such as diffusion models or GANs from a text prompt or another input. No camera recorded a real scene, although the output can look like a photograph.",
  },
  {
    q: "What is a manipulated photograph?",
    a: "A real photograph that was changed after capture: retouching, compositing, removing or adding objects, or altering colors. Manipulation has existed for as long as photography. A manipulated photo is not AI-generated, and ImageProof’s classifier is not built to find or locate edits.",
  },
  {
    q: "AI generation versus AI-assisted editing",
    a: "Generation creates the whole image from a model. AI-assisted editing uses AI inside an otherwise real photo: generative fill, object removal, sky replacement, upscaling or face retouching. Phones also apply computational photography such as HDR and night mode, which is not generation. A whole-image classifier may call a lightly AI-edited photo camera-like. Content Credentials, when present, can record such edits.",
  },
  {
    q: "What is image provenance?",
    a: "Provenance is the documented history of an image: who made it, with what, and what was done to it afterwards. The C2PA standard embeds that history as a signed manifest. A valid signature shows the record is intact and who signed it, not that the content is true, and the record disappears when a platform or tool strips it.",
  },
  {
    q: "Why can detectors be wrong?",
    a: "Detectors learn patterns from the generators and photographs in their training data. New generators, unusual subjects, illustrations, heavy denoising or HDR, resizing, re-compression and screenshots all shift those patterns. Scores are also usually uncalibrated and can be confident when wrong. Errors go both ways: real photos flagged as AI, and AI images passed as camera-captured.",
  },
  {
    q: "Using a result responsibly",
    a: "Treat the assessment as one lead among several. Ask for the original file, look for Content Credentials, check where the image first appeared, and consider who benefits from the claim. Do not use a single detector result as the sole basis for an editorial, legal, academic or other consequential decision.",
  },
];

export default function HowItWorksPage() {
  return (
    <div className="mx-auto max-w-4xl px-4 py-14 sm:px-6">
      <h1 className="text-4xl font-semibold">How ImageProof works</h1>
      <p className="mt-4 max-w-2xl text-lg leading-relaxed text-muted-foreground">
        ImageProof examines four kinds of evidence independently and shows them side by side. It does not blend them into one opaque score.
      </p>

      <section aria-labelledby="sources" className="mt-12">
        <h2 id="sources" className="text-2xl font-semibold">The four evidence sources</h2>
        <dl className="mt-6 divide-y divide-border border-y border-border">
          {sources.map((s) => (
            <div key={s.title} className="grid gap-2 py-5 md:grid-cols-[14rem_1fr] md:gap-8">
              <dt className="font-medium">{s.title}</dt>
              <dd className="text-sm leading-relaxed text-muted-foreground">{s.body}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section aria-labelledby="decision" className="mt-14">
        <h2 id="decision" className="text-2xl font-semibold">How the assessment is decided</h2>
        <ol className="mt-5 list-decimal space-y-3 pl-5 text-[15px] leading-relaxed text-muted-foreground marker:font-medium marker:text-foreground">
          <li className="pl-2">The classifier’s score for the “AI-generated” label is compared with two thresholds. At or above the upper threshold: Likely AI-Generated. At or below the lower threshold: Likely Camera-Captured. In between: Inconclusive.</li>
          <li className="pl-2">If the image is very small, the classifier is unreliable, so a confident verdict is withheld and the result is Inconclusive. Low resolution and heavy compression are shown as reliability factors.</li>
          <li className="pl-2">Verified Content Credentials from a trusted signer that declare AI generation take precedence, because they are the signer’s own verifiable statement. Untrusted or unsigned declarations, embedded generator text and missing metadata never change the category. They are shown as separate evidence, and conflicts are flagged.</li>
          <li className="pl-2">If the service cannot analyze the image (no model configured, model offline, unreadable file), the result is Unable to Analyze and no assessment is generated.</li>
        </ol>
      </section>

      <section aria-labelledby="learn" className="mt-14">
        <h2 id="learn" className="text-2xl font-semibold">Understanding AI images and authenticity</h2>
        <Accordion type="single" collapsible className="mt-4 border-t border-border">
          {education.map((e) => (
            <AccordionItem key={e.q} value={e.q}>
              <AccordionTrigger>{e.q}</AccordionTrigger>
              <AccordionContent className="max-w-prose leading-relaxed">{e.a}</AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </section>
    </div>
  );
}
