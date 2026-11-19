"use client";

import { ErrorFallback } from "@/features/workspace/error-boundary";

export default function ErrorPage({ retry }: { error: Error & { digest?: string }; retry: () => void }) {
  return <ErrorFallback onRetry={retry} />;
}
