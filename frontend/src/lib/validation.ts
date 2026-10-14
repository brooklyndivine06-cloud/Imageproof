export interface UploadLimits {
  maxBytes: number;
  minSide: number;
  maxPixels: number;
}

export const DEFAULT_LIMITS: UploadLimits = { maxBytes: 10 * 1024 * 1024, minSide: 64, maxPixels: 40_000_000 };

export const ACCEPT_ATTR = ".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp";
export const SUPPORTED_LABEL = "JPG, JPEG, PNG or WebP";

export type SniffedFormat = "JPEG" | "PNG" | "WEBP";

/** Detects the format from the first bytes of the file; names and MIME types are not trusted. */
export function sniffFormat(bytes: Uint8Array): SniffedFormat | null {
  if (bytes.length >= 3 && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff) return "JPEG";
  const png = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];
  if (bytes.length >= 8 && png.every((b, i) => bytes[i] === b)) return "PNG";
  const ascii = (from: number, text: string) => text.split("").every((c, i) => bytes[from + i] === c.charCodeAt(0));
  if (bytes.length >= 12 && ascii(0, "RIFF") && ascii(8, "WEBP")) return "WEBP";
  return null;
}

export type ValidationResult =
  | { ok: true; format: SniffedFormat; width: number; height: number }
  | { ok: false; code: string; message: string };

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function checkBasics(file: Pick<File, "size" | "name">, limits: UploadLimits): ValidationResult | null {
  if (file.size === 0) return { ok: false, code: "empty_file", message: "This file is empty." };
  if (file.size > limits.maxBytes) {
    return {
      ok: false,
      code: "file_too_large",
      message: `This file is ${formatBytes(file.size)}. The limit is ${formatBytes(limits.maxBytes)}.`,
    };
  }
  return null;
}

async function readDimensions(file: File): Promise<{ width: number; height: number } | null> {
  if (typeof createImageBitmap === "function") {
    try {
      const bitmap = await createImageBitmap(file);
      const dims = { width: bitmap.width, height: bitmap.height };
      bitmap.close();
      return dims;
    } catch {
      return null;
    }
  }
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      resolve({ width: img.naturalWidth, height: img.naturalHeight });
      URL.revokeObjectURL(url);
    };
    img.onerror = () => {
      resolve(null);
      URL.revokeObjectURL(url);
    };
    img.src = url;
  });
}

/** Client-side pre-check for fast feedback. The server repeats every check and is the authority. */
export async function validateImageFile(file: File, limits: UploadLimits = DEFAULT_LIMITS): Promise<ValidationResult> {
  const basic = checkBasics(file, limits);
  if (basic) return basic;

  const head = new Uint8Array(await file.slice(0, 16).arrayBuffer());
  const format = sniffFormat(head);
  if (!format) {
    return { ok: false, code: "unsupported_media_type", message: `This file is not a supported image. Use ${SUPPORTED_LABEL}.` };
  }

  const dims = await readDimensions(file);
  if (!dims) {
    return { ok: false, code: "corrupt_image", message: "This image could not be read. It may be corrupted." };
  }
  if (Math.min(dims.width, dims.height) < limits.minSide) {
    return {
      ok: false,
      code: "image_too_small",
      message: `This image is ${dims.width}×${dims.height} px. Both sides must be at least ${limits.minSide} px.`,
    };
  }
  if (dims.width * dims.height > limits.maxPixels) {
    return {
      ok: false,
      code: "image_too_large_dimensions",
      message: `This image is ${dims.width}×${dims.height} px, above the ${limits.maxPixels / 1_000_000} megapixel limit.`,
    };
  }
  return { ok: true, format, width: dims.width, height: dims.height };
}
