import type { Metadata } from "next";

import { PrivacyLive } from "@/components/site/privacy-live";

export const metadata: Metadata = { title: "Privacy" };

const sections = [
  {
    title: "What happens to your image",
    body: [
      "When you press Analyze, your browser sends the file to this site’s server over an encrypted connection (HTTPS in a correctly deployed instance). The server decodes it in memory, runs the analysis and returns the result. The image is not written to disk by default, is not given a public URL, and is discarded when the response is sent.",
      "ImageProof cannot promise that nothing ever remains anywhere. Operating systems may swap memory, and the hosting provider or any reverse proxy in front of the server may keep its own request logs. Those are controlled by whoever operates this deployment.",
    ],
  },
  {
    title: "What is logged",
    body: [
      "Server logs record a request ID, the request path, the response status, how long it took and, for completed analyses, the file format, size and resulting category. They do not record image content, file names, metadata or your IP address in application logs.",
    ],
  },
  {
    title: "Metadata",
    body: [
      "Only technically relevant metadata fields are returned to you: camera make and model, exposure settings, dates and software. GPS location, serial numbers, owner and author names and similar personal fields are detected but withheld, so they are neither shown nor stored.",
    ],
  },
  {
    title: "External inference providers",
    body: [
      "Some deployments run the detection model on the same server. Others send the image to an external inference provider. If this deployment does, the provider receives your image, applies its own retention and logging policies, and ImageProof does not control them. By default only decoded pixels are sent, so embedded metadata does not leave the server. The box below states what this deployment does.",
    ],
  },
  {
    title: "What stays in your browser",
    body: [
      "Your theme preference is saved in your browser. Analysis history is off by default; if you turn it on, a short summary of each result (file name, assessment, score, model name and time) is saved in this browser’s local storage only. Images, thumbnails and metadata are never saved, and turning history off deletes it. PDF reports and copied summaries are created in your browser and are not sent anywhere.",
      "ImageProof does not use accounts, advertising or analytics cookies.",
    ],
  },
  {
    title: "Retention settings",
    body: [
      "Server-side retention of uploads is none by default. The only retention you control is local history, which you can switch off and clear at any time from the history button in the header.",
    ],
  },
];

export default function PrivacyPage() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-14 sm:px-6">
      <h1 className="text-4xl font-semibold">Privacy notice</h1>
      <p className="mt-4 text-lg leading-relaxed text-muted-foreground">
        ImageProof is built to analyze an image and forget it. This page says what that means in practice, and what it does not.
      </p>

      <div className="mt-10"><PrivacyLive /></div>

      <div className="mt-12 space-y-10">
        {sections.map((s) => (
          <section key={s.title} aria-labelledby={s.title.replace(/\W+/g, "-")}>
            <h2 id={s.title.replace(/\W+/g, "-")} className="text-xl font-semibold">{s.title}</h2>
            <div className="mt-3 space-y-3 text-[15px] leading-relaxed text-muted-foreground">
              {s.body.map((p) => <p key={p}>{p}</p>)}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
