import { Ban, Camera, CircleHelp, Sparkles, type LucideIcon } from "lucide-react";

import type { Category } from "@/lib/types";

export interface CategoryStyle {
  variant: "ai" | "camera" | "inconclusive" | "unable";
  text: string;
  soft: string;
  fill: string;
  Icon: LucideIcon;
}

export const CATEGORY_STYLE: Record<Category, CategoryStyle> = {
  likely_ai_generated: { variant: "ai", text: "text-verdict-ai", soft: "bg-verdict-ai-soft", fill: "bg-verdict-ai", Icon: Sparkles },
  likely_camera_captured: { variant: "camera", text: "text-verdict-camera", soft: "bg-verdict-camera-soft", fill: "bg-verdict-camera", Icon: Camera },
  inconclusive: { variant: "inconclusive", text: "text-verdict-inconclusive", soft: "bg-verdict-inconclusive-soft", fill: "bg-verdict-inconclusive", Icon: CircleHelp },
  unable_to_analyze: { variant: "unable", text: "text-verdict-unable", soft: "bg-verdict-unable-soft", fill: "bg-verdict-unable", Icon: Ban },
};
