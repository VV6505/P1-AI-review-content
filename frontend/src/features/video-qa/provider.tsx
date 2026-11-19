"use client";

import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { initialVideos, parseVideos, VIDEO_KEY, type VideoAsset, type VideoState } from "./model";

type VideoContextValue = VideoState & { ready: boolean; error: string; addVideo: (asset: VideoAsset) => void; updateVideo: (id: string, update: (asset: VideoAsset) => VideoAsset) => void };
const VideoContext = createContext<VideoContextValue | null>(null);
export function VideoProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState(initialVideos);
  const current = useRef(state);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let cancelled = false;
    Promise.resolve().then(() => {
      if (cancelled) return;
      try {
        const raw = localStorage.getItem(VIDEO_KEY);
        const restored = raw ? parseVideos(raw) : initialVideos;
        current.current = restored; setState(restored);
      } catch { setError("Không đọc được thư viện đã lưu. Dữ liệu cũ được giữ lại; kiểm tra bộ nhớ trình duyệt."); }
      setReady(true);
    });
    return () => { cancelled = true; };
  }, []);
  function addVideo(asset: VideoAsset) {
    if (!ready) throw new Error("Đang khôi phục thư viện.");
    const raw = localStorage.getItem(VIDEO_KEY);
    if (raw && parseVideos(raw).revision !== current.current.revision) throw new Error("Thư viện đã đổi ở tab khác. Tải lại trước khi lưu.");
    const next = { ...current.current, revision: current.current.revision + 1, assets: [asset, ...current.current.assets] };
    try { localStorage.setItem(VIDEO_KEY, JSON.stringify(next)); current.current = next; setState(next); setError(""); }
    catch { throw new Error("Không thể lưu video mới trong trình duyệt."); }
  }
  function updateVideo(id: string, update: (asset: VideoAsset) => VideoAsset) {
    if (!ready) throw new Error("Đang khôi phục thư viện.");
    try {
      const raw = localStorage.getItem(VIDEO_KEY);
      if (raw && parseVideos(raw).revision !== current.current.revision) throw new Error("Thư viện đã đổi ở tab khác. Tải lại trước khi lưu.");
      const asset = current.current.assets.find(item => item.review.id === id);
      if (!asset) throw new Error("Không tìm thấy video.");
      const nextAsset = update(asset);
      const next = { ...current.current, revision: current.current.revision + 1, assets: current.current.assets.map(item => item.review.id === id ? nextAsset : item) };
      localStorage.setItem(VIDEO_KEY, JSON.stringify(next));
      current.current = next; setState(next); setError("");
    } catch (cause) {
      const message = cause instanceof DOMException ? "Không thể lưu thư viện vào trình duyệt. Nội dung đang nhập được giữ lại; hãy kiểm tra bộ nhớ và thử lại." : cause instanceof Error ? cause.message : "Không lưu được thay đổi. Thử lại sau.";
      setError(message); throw new Error(message);
    }
  }
  return <VideoContext.Provider value={{ ...state, ready, error, updateVideo, addVideo }}>{children}</VideoContext.Provider>;
}
export function useVideos() {
  const value = useContext(VideoContext);
  if (!value) throw new Error("Missing VideoProvider");
  return value;
}
