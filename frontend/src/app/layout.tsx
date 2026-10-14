import type { Metadata, Viewport } from "next";
import { ThemeProvider } from "next-themes";
import "@fontsource-variable/inter";
import "./globals.css";

import { Footer } from "@/components/site/footer";
import { Header } from "@/components/site/header";
import { Toaster } from "@/components/ui/sonner";

export const metadata: Metadata = {
  title: { default: "ImageProof: image authenticity analysis", template: "%s | ImageProof" },
  description:
    "Analyze an image for signs of AI generation or camera capture. ImageProof reports classifier output, metadata, Content Credentials and forensic measurements separately, and is clear about uncertainty.",
  applicationName: "ImageProof",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f8fafb" },
    { media: "(prefers-color-scheme: dark)", color: "#0f1318" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="flex min-h-dvh flex-col">
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
          <Header />
          <main id="main" className="flex-1">{children}</main>
          <Footer />
          <Toaster />
        </ThemeProvider>
      </body>
    </html>
  );
}
