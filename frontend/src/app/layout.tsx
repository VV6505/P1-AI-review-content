import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { WorkspaceShell } from "@/features/workspace/shell";
import { ErrorBoundary } from "@/features/workspace/error-boundary";
import { MockAuthProvider } from "@/features/auth/provider";
import { PreferencesProvider } from "@/features/studio/preferences";
import "./studio.css";
import "@/features/auth/auth.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin", "vietnamese"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Reviewlab — Video workspace",
  description: "Create product videos from a link",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="vi"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <ErrorBoundary>
          <PreferencesProvider><MockAuthProvider><WorkspaceShell>{children}</WorkspaceShell></MockAuthProvider></PreferencesProvider>
        </ErrorBoundary>
      </body>
    </html>
  );
}
