"use client";

export default function GlobalError({ retry }: { error: Error & { digest?: string }; retry: () => void }) {
  function goHome() {
    // Root-layout failures require recreating the application rather than preserving its state.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.assign("/");
  }
  return (
    <html lang="vi"><body style={{ fontFamily: "system-ui", margin: 0, padding: "64px 24px", color: "#242424" }}>
      <h1>Không thể mở workspace</h1>
      <p>Hãy thử tải lại trang để tiếp tục.</p>
      <button onClick={retry} style={{ padding: "12px 20px", cursor: "pointer" }}>Thử lại</button>
      <p><button onClick={goHome}>Về tổng quan</button></p>
    </body></html>
  );
}
