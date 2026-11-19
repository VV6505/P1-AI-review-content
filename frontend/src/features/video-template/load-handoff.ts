import { readMedia } from "./frame";
import { fromSceneHandoff } from "./scene-handoff";

export const s03HandoffUrl = "/2026-10-26_s03-feature-clip/scene-s03.json";

async function metadata(blob: Blob, video: boolean): Promise<{ width: number; height: number; duration: number }> {
  const element = document.createElement(video ? "video" : "audio"), url = URL.createObjectURL(blob);
  try {
    return await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("Không đọc được metadata tư liệu trong 5 giây.")), 5000);
      element.onloadedmetadata = () => { clearTimeout(timer); resolve({ width: video ? (element as HTMLVideoElement).videoWidth : 0, height: video ? (element as HTMLVideoElement).videoHeight : 0, duration: element.duration }); };
      element.onerror = () => { clearTimeout(timer); reject(new Error("Không giải mã được tư liệu bàn giao.")); };
      element.preload = "metadata"; element.src = url;
    });
  } finally { element.removeAttribute("src"); element.load(); URL.revokeObjectURL(url); }
}

export async function loadS03Handoff() {
  const response = await fetch(s03HandoffUrl, { cache: "no-store" });
  if (!response.ok) throw new Error("Chưa có bộ s03: đặt thư mục 2026-10-26_s03-feature-clip vào public của FE.");
  const raw: unknown = await response.json();
  // Validate paths and timing before any media request. Read the actual video size
  // before converting source pixels; this pilot's README specifies 1920 × 1080.
  const checked = fromSceneHandoff(raw, { width: 1920, height: 1080 });
  const media: Record<string, string> = {};
  for (const asset of checked.assets) {
    const result = await fetch(`/2026-10-26_s03-feature-clip/${asset.id}`);
    if (!result.ok) throw new Error(`Thiếu tư liệu bàn giao: ${asset.id}`);
    const blob = await result.blob(), info = await metadata(blob, asset.kind === "video");
    if (asset.kind === "video") {
      if (info.width !== 1920 || info.height !== 1080 || checked.scenes[0].parts.some(p => p.end > info.duration + .01)) throw new Error("Clip bàn giao không khớp kích thước/điểm cắt.");
    } else {
      const segment = checked.scenes[0].segments.find(s => s.audioId === asset.id)!;
      if (Math.abs(info.duration - (segment.end - segment.start)) > .02) throw new Error(`Audio không khớp timing: ${asset.id}`);
    }
    const type = asset.kind === "video" ? "video/mp4" : "audio/wav";
    media[asset.id] = await readMedia(new File([blob], asset.id.split("/").at(-1)!, { type }), asset.kind);
  }
  return { project: checked, media };
}
