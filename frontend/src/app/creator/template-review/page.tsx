"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { VideoTemplatePreview } from "@/features/video-template/preview";
import type { Ratio } from "@/features/video-template/model";

export default function Page() {
  const [ratio, setRatio] = useState<Ratio>("9:16"), [preset, setPreset] = useState("cinematic");
  const [renderVersion, setRenderVersion] = useState<string | null>(null);
  const rendersReady = renderVersion !== null;
  const router = useRouter();
  useEffect(() => {
    let alive = true;
    void fetch("/video-template/s03-centered/manifest.json", { cache: "no-store" }).then(async response => {
      if (!response.ok) return;
      const manifest: unknown = await response.json();
      if (alive && manifest && typeof manifest === "object") setRenderVersion("renderedAt" in manifest && typeof manifest.renderedAt === "string" ? manifest.renderedAt : "local");
    }).catch(() => {});
    return () => { alive = false; };
  }, []);
  return <div className="template-review-page">
    <h1>Xem trước template video</h1>
    <p>Bản ngang chuyển giữa khung lớn và phần chỉ dẫn. Bản dọc giữ clip ở giữa.</p>
    <div className="template-review-controls">
      <div className="template-ratio-choices" role="group" aria-label="Tỷ lệ khung hình">
        <button type="button" aria-pressed={ratio === "16:9"} onClick={() => setRatio("16:9")}><span className="ratio-icon ratio-wide" />Ngang 16:9</button>
        <button type="button" aria-pressed={ratio === "9:16"} onClick={() => setRatio("9:16")}><span className="ratio-icon ratio-tall" />Dọc 9:16</button>
      </div>
      <label>Phong cách cảnh <select aria-label="Phong cách cảnh" value={preset} onChange={event => setPreset(event.target.value)}><option value="cinematic">Điện ảnh tối giản</option><option value="animation">Hoạt hình đồ họa</option><option value="vintage">Cổ điển</option></select></label>
      {rendersReady && <a href="#rendered-scene-videos">Xem cả hai video có giọng ↓</a>}
      <Link href="/creator/create">Về tạo video</Link>
    </div>
    <VideoTemplatePreview ratio={ratio} preset={preset} handoff close={() => router.push("/creator/create")} />
    {rendersReady && <section id="rendered-scene-videos" className="template-rendered-section" aria-label="Video đã xuất">
      <h2>Hai video mẫu PDFCraft · có giọng đọc</h2>
      <p>Đây là dữ liệu thử của template dùng chung. Đổi project bằng gói M2 trong phần Kiểm tra bàn giao và tư liệu; các MP4 mẫu bên dưới giữ nội dung PDFCraft.</p>
      <div className="template-rendered-pair">{(["16x9", "9x16"] as const).map(output => <figure className={output === "9x16" ? "is-portrait" : "is-landscape"} key={output}>
        <figcaption>{output === "16x9" ? "Ngang 16:9 · 1920 × 1080" : "Dọc 9:16 · 1080 × 1920"}</figcaption>
        <video data-output-ratio={output} controls playsInline preload="metadata" poster={`/video-template/s03-centered/${output}.png?v=${encodeURIComponent(renderVersion ?? "local")}`} src={`/video-template/s03-centered/${output}.mp4?v=${encodeURIComponent(renderVersion ?? "local")}`} />
        <a href={`/video-template/s03-centered/${output}.mp4`} download={`PDFCraft-s03-${output}.mp4`}>Tải bản {output === "16x9" ? "ngang 16:9" : "dọc 9:16"}</a>
      </figure>)}</div>
    </section>}
  </div>;
}
