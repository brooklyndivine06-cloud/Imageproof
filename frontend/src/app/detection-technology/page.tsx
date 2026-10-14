import type { Metadata } from "next";

import { TechnologyLive } from "@/components/site/technology-live";

export const metadata: Metadata = { title: "Detection technology" };

const limits = [
  "A classifier only knows the generators and photographs it was trained on. Images from newer or different generators can pass as camera-captured.",
  "Real photographs that are heavily processed, denoised, HDR-merged, illustrated or screen-captured can be flagged as AI-generated.",
  "JPEG compression, resizing, cropping, filters and screenshots change the pixel-level cues detectors depend on.",
  "A raw score is not a probability. Unless a calibration was fitted on data resembling your images, “0.95” does not mean 95%.",
  "AI-assisted edits to a real photo are generally invisible to a whole-image classifier.",
  "Precision depends on how common AI images are among the images being checked, which an evaluation dataset may not reflect.",
];

export default function DetectionTechnologyPage() {
  return (
    <div className="mx-auto max-w-4xl px-4 py-14 sm:px-6">
      <h1 className="text-4xl font-semibold">Detection technology</h1>
      <p className="mt-4 max-w-2xl text-lg leading-relaxed text-muted-foreground">
        What this ImageProof server actually runs, how its decisions are made, and what has and has not been measured. The details below are read live
        from the server, not written in advance.
      </p>

      <div className="mt-12"><TechnologyLive /></div>

      <section aria-labelledby="pipeline" className="mt-14 space-y-4">
        <h2 id="pipeline" className="text-2xl font-semibold">Pipeline</h2>
        <ol className="list-decimal space-y-3 pl-5 text-[15px] leading-relaxed text-muted-foreground marker:font-medium marker:text-foreground">
          <li className="pl-2"><span className="font-medium text-foreground">Validation.</span> The format is identified from the file’s bytes, the image is fully decoded, and size, pixel-count and animation limits are enforced.</li>
          <li className="pl-2"><span className="font-medium text-foreground">Classification.</span> The orientation-corrected RGB image is passed to the configured model through a replaceable provider interface (self-hosted Hugging Face model or a hosted inference endpoint).</li>
          <li className="pl-2"><span className="font-medium text-foreground">Metadata.</span> EXIF, XMP, PNG text chunks and color profile are read with Pillow. Location, serial numbers and personal names are detected but withheld.</li>
          <li className="pl-2"><span className="font-medium text-foreground">Provenance.</span> The open-source C2PA SDK validates any embedded Content Credentials.</li>
          <li className="pl-2"><span className="font-medium text-foreground">Forensics.</span> Noise-residual statistics, Fourier-spectrum peaks, estimated JPEG quality and error-level analysis are measured and reported without interpretation thresholds.</li>
          <li className="pl-2"><span className="font-medium text-foreground">Assessment.</span> Thresholds on the classifier score decide the category, subject to the reliability and provenance rules described under How It Works.</li>
        </ol>
      </section>

      <section aria-labelledby="limits" className="mt-14 space-y-4">
        <h2 id="limits" className="text-2xl font-semibold">Known limitations of this kind of detector</h2>
        <ul className="list-disc space-y-2.5 pl-5 text-[15px] leading-relaxed text-muted-foreground">
          {limits.map((l) => <li key={l} className="pl-1">{l}</li>)}
        </ul>
      </section>
    </div>
  );
}
