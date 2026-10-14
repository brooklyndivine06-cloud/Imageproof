import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { makeResult, makeStatus } from "@/test/fixtures";
import { Analyzer } from "./analyzer";

class FakeXHR {
  static instances: FakeXHR[] = [];
  upload: { onprogress?: (e: unknown) => void; onload?: () => void } = {};
  status = 0;
  responseText = "";
  timeout = 0;
  responseType = "";
  onload?: () => void;
  onerror?: () => void;
  ontimeout?: () => void;
  onabort?: () => void;
  body: unknown;
  constructor() { FakeXHR.instances.push(this); }
  open() {}
  setRequestHeader() {}
  getResponseHeader() { return null; }
  send(body: unknown) { this.body = body; }
  abort() { this.onabort?.(); }
  respond(status: number, body: unknown) {
    this.status = status;
    this.responseText = JSON.stringify(body);
    this.upload.onload?.();
    this.onload?.();
  }
}

const PNG_BYTES = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 0, 0, 0, 0, 0]);
const pngFile = () => new File([PNG_BYTES], "sample.png", { type: "image/png" });

function mockStatus(status: unknown, ok = true) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok, status: ok ? 200 : 500, json: async () => status, text: async () => JSON.stringify(status), headers: new Headers() }));
}

beforeEach(() => {
  FakeXHR.instances = [];
  vi.stubGlobal("XMLHttpRequest", FakeXHR);
  vi.stubGlobal("createImageBitmap", vi.fn().mockResolvedValue({ width: 800, height: 600, close: () => {} }));
  URL.createObjectURL = vi.fn(() => "blob:preview");
  URL.revokeObjectURL = vi.fn();
  Element.prototype.scrollIntoView = vi.fn();
  window.matchMedia = vi.fn().mockReturnValue({ matches: false, addEventListener: () => {}, removeEventListener: () => {} }) as unknown as typeof window.matchMedia;
});
afterEach(() => vi.unstubAllGlobals());

async function chooseFile(user: ReturnType<typeof userEvent.setup>) {
  const input = await screen.findByLabelText("Choose an image file");
  await user.upload(input, pngFile());
}

describe("Analyzer", () => {
  it("shows the headline, the supported formats and the visible disclaimer", async () => {
    mockStatus(makeStatus());
    render(<Analyzer />);
    expect(screen.getByRole("heading", { level: 1, name: "Can You Trust This Image?" })).toBeInTheDocument();
    expect(screen.getByText(/do not constitute definitive proof of authenticity/)).toBeInTheDocument();
    expect(await screen.findByText(/JPG, JPEG, PNG or WebP/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Browse files" })).toBeInTheDocument();
  });

  it("uploads the file, shows the server's real result, and offers copy and PDF actions", async () => {
    mockStatus(makeStatus());
    const user = userEvent.setup();
    render(<Analyzer />);
    await chooseFile(user);

    const analyze = await screen.findByRole("button", { name: /Analyze image/ });
    await waitFor(() => expect(analyze).toBeEnabled());
    await user.click(analyze);

    expect(await screen.findByText(/Uploading image/)).toBeInTheDocument();
    const xhr = FakeXHR.instances.at(-1)!;
    expect((xhr.body as FormData).get("file")).toBeInstanceOf(File);
    act(() => xhr.respond(200, makeResult()));

    expect(await screen.findByRole("heading", { level: 2, name: /Likely AI-Generated/ })).toBeInTheDocument();
    expect(screen.getByText("Raw classifier output")).toBeInTheDocument();
    expect(screen.getByText(/Uncalibrated model score/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Copy summary/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Download PDF report/ })).toBeInTheDocument();
  });

  it("disables analysis and shows an unavailable state when no model is configured", async () => {
    mockStatus(makeStatus({ state: "not_configured", model: null, detail: "IMAGEPROOF_HF_MODEL_ID is not set." }));
    const user = userEvent.setup();
    render(<Analyzer />);
    expect(await screen.findByText("Detection model not configured")).toBeInTheDocument();
    await chooseFile(user);
    const analyze = await screen.findByRole("button", { name: /Analyze image/ });
    expect(analyze).toBeDisabled();
    expect(screen.queryByText("Likely AI-Generated")).not.toBeInTheDocument();
  });

  it("shows Unable to Analyze with guidance when the server returns an error", async () => {
    mockStatus(makeStatus());
    const user = userEvent.setup();
    render(<Analyzer />);
    await chooseFile(user);
    const analyze = await screen.findByRole("button", { name: /Analyze image/ });
    await waitFor(() => expect(analyze).toBeEnabled());
    await user.click(analyze);
    act(() => FakeXHR.instances.at(-1)!.respond(502, { error: { code: "analysis_failed", message: "The model failed.", details: null, retryable: true }, request_id: "req1" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to Analyze");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /Likely/ })).not.toBeInTheDocument();
  });

  it("rejects files that are not supported images before any upload", async () => {
    mockStatus(makeStatus());
    const user = userEvent.setup({ applyAccept: false });
    render(<Analyzer />);
    const input = await screen.findByLabelText("Choose an image file");
    await user.upload(input, new File(["hello world, not an image"], "notes.jpg", { type: "image/jpeg" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/not a supported image/);
    expect(FakeXHR.instances).toHaveLength(0);
  });

  it("lets the user remove a selected image", async () => {
    mockStatus(makeStatus());
    const user = userEvent.setup();
    render(<Analyzer />);
    await chooseFile(user);
    await user.click(await screen.findByRole("button", { name: /Remove/ }));
    expect(await screen.findByRole("button", { name: "Browse files" })).toBeInTheDocument();
  });
});
