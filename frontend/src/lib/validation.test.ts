import { describe, expect, it, vi } from "vitest";

import { checkBasics, DEFAULT_LIMITS, sniffFormat, validateImageFile } from "./validation";

const bytes = (...n: number[]) => new Uint8Array(n);
const ascii = (s: string) => Array.from(s).map((c) => c.charCodeAt(0));

function fileOf(data: number[], name = "x.jpg", type = "image/jpeg", size?: number) {
  const f = new File([new Uint8Array(data)], name, { type });
  if (size !== undefined) Object.defineProperty(f, "size", { value: size });
  return f;
}

describe("sniffFormat", () => {
  it("detects JPEG, PNG and WebP from content", () => {
    expect(sniffFormat(bytes(0xff, 0xd8, 0xff, 0xe0))).toBe("JPEG");
    expect(sniffFormat(bytes(0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0))).toBe("PNG");
    expect(sniffFormat(bytes(...ascii("RIFF"), 1, 2, 3, 4, ...ascii("WEBP")))).toBe("WEBP");
  });
  it("rejects other formats", () => {
    expect(sniffFormat(bytes(...ascii("GIF89a"), 0, 0, 0, 0, 0, 0))).toBeNull();
    expect(sniffFormat(bytes(...ascii("RIFF"), 1, 2, 3, 4, ...ascii("WAVE")))).toBeNull();
    expect(sniffFormat(bytes())).toBeNull();
  });
});

describe("checkBasics", () => {
  it("rejects empty and oversized files", () => {
    expect(checkBasics({ size: 0, name: "a" }, DEFAULT_LIMITS)).toMatchObject({ ok: false, code: "empty_file" });
    expect(checkBasics({ size: DEFAULT_LIMITS.maxBytes + 1, name: "a" }, DEFAULT_LIMITS)).toMatchObject({ ok: false, code: "file_too_large" });
    expect(checkBasics({ size: 1000, name: "a" }, DEFAULT_LIMITS)).toBeNull();
  });
});

describe("validateImageFile", () => {
  const png = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 0];

  it("does not trust the file name or MIME type", async () => {
    const res = await validateImageFile(fileOf(ascii("not an image at all"), "photo.jpg", "image/jpeg"));
    expect(res).toMatchObject({ ok: false, code: "unsupported_media_type" });
  });

  it("enforces dimension limits", async () => {
    vi.stubGlobal("createImageBitmap", vi.fn().mockResolvedValue({ width: 32, height: 500, close: () => {} }));
    expect(await validateImageFile(fileOf(png, "a.png", "image/png"))).toMatchObject({ ok: false, code: "image_too_small" });
    vi.stubGlobal("createImageBitmap", vi.fn().mockResolvedValue({ width: 9000, height: 9000, close: () => {} }));
    expect(await validateImageFile(fileOf(png, "a.png", "image/png"))).toMatchObject({ ok: false, code: "image_too_large_dimensions" });
    vi.stubGlobal("createImageBitmap", vi.fn().mockRejectedValue(new Error("bad")));
    expect(await validateImageFile(fileOf(png, "a.png", "image/png"))).toMatchObject({ ok: false, code: "corrupt_image" });
  });

  it("accepts a valid image", async () => {
    vi.stubGlobal("createImageBitmap", vi.fn().mockResolvedValue({ width: 800, height: 600, close: () => {} }));
    expect(await validateImageFile(fileOf(png, "a.png", "image/png"))).toEqual({ ok: true, format: "PNG", width: 800, height: 600 });
  });
});
