"use client";

import { Component, type ErrorInfo, type ReactNode } from "react";
import { Button } from "@/components/ui/button";

export function ErrorFallback({ onRetry }: { onRetry: () => void }) {
  function goHome() {
    // A full navigation recreates a failed provider/boundary; client routing would preserve it.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.assign("/");
  }
  return (
    <section className="error-fallback" role="alert">
      <h1>Không thể hiển thị nội dung</h1>
      <p>Đã có lỗi xảy ra. Bạn có thể thử lại hoặc quay về tổng quan.</p>
      <div><Button onClick={onRetry}>Thử lại</Button><Button variant="outline" onClick={goHome}>Về tổng quan</Button></div>
    </section>
  );
}

export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Workspace rendering error", error, info.componentStack);
  }
  render() {
    if (this.state.failed) return <ErrorFallback onRetry={() => this.setState({ failed: false })} />;
    return this.props.children;
  }
}
