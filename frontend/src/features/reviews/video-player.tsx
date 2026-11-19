"use client";

import Image from "next/image";
import { useRef, useState } from "react";
import { LoaderCircle, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { activeSegmentAt, formatTime, type TranscriptSegment } from "./types";

export function VideoPlayer({ src, poster, title, transcript, portrait = false, safeZone = false }: { portrait?: boolean; safeZone?: boolean; src: string; poster: string; title: string; transcript: TranscriptSegment[] }) {
  const video = useRef<HTMLVideoElement>(null);
  const [seconds, setSeconds] = useState(0);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [captions, setCaptions] = useState(true);
  const activeIndex = activeSegmentAt(transcript, seconds);
  const active = transcript[activeIndex];

  function seek(start: number) {
    if (!video.current || failed) return;
    video.current.currentTime = start;
    setSeconds(start);
  }
  function retry() {
    setFailed(false);
    setLoading(true);
    video.current?.load();
  }

  return (
    <div className={`video-layout ${portrait ? "portrait-video" : ""}`}>
      <section aria-label="Video review">
        <div className="video-stage" aria-busy={loading && !failed}>
          <video ref={video} src={src} poster={poster} controls playsInline preload="auto" aria-label={title}
            onLoadStart={() => setLoading(true)} onLoadedData={() => setLoading(false)} onCanPlay={() => setLoading(false)}
            onPlaying={() => setLoading(false)} onWaiting={() => setLoading(true)} onSeeking={() => setLoading(true)} onSeeked={() => { setLoading(false); setSeconds(video.current?.currentTime ?? 0); }}
            onTimeUpdate={(event) => setSeconds(event.currentTarget.currentTime)} onEnded={() => { setLoading(false); setSeconds(video.current?.currentTime ?? 0); }}
            onError={() => { setFailed(true); setLoading(false); }}>
            Trình duyệt của bạn không hỗ trợ video HTML5.
          </video>
          {loading && !failed && <div className="video-loading" role="status"><LoaderCircle className="spin" size={28} /><span>Đang tải video…</span></div>}
          {safeZone && <div className="safe-zone" aria-hidden="true"><span>SAFE ZONE</span></div>}
          {captions && active && !failed && <div className="transcript-overlay" aria-hidden="true">{active.text}</div>}
          {failed && <div className="video-error" role="alert"><p>Không thể phát video. Hãy kiểm tra kết nối hoặc nguồn video.</p><Button variant="outline" onClick={retry}><RotateCcw size={16} /> Thử tải video lại</Button></div>}
        </div>
        <div className="video-toolbar"><span>Video có thể xem bằng điều khiển bên dưới.</span><Button variant="outline" aria-pressed={captions} onClick={() => setCaptions(!captions)}>{captions ? "Ẩn" : "Hiện"} transcript</Button></div>
      </section>
      <section className="transcript-panel" aria-label="Transcript theo thời gian">
        <h2>{portrait ? "Danh sách scene" : "Transcript"}</h2><p>Chọn một đoạn để chuyển đến thời điểm tương ứng.</p>
        {transcript.length ? <ol>{transcript.map((segment, index) => (
          <li key={`${segment.start}-${index}`}><button type="button" className={index === activeIndex ? "active" : ""} aria-current={index === activeIndex ? "true" : undefined} disabled={failed || loading} onClick={() => seek(segment.start)}>
            <time>{formatTime(segment.start)}{portrait ? ` – ${formatTime(segment.end)}` : ""}</time><span>{segment.text}{portrait && <><Image width={240} height={135} src="/media/feature-evidence.svg" alt={`Hình minh họa scene ${index + 1}`} /><small>Voiceover TTS · screenshot mock</small></>}</span>
          </button></li>
        ))}</ol> : <p>Video này chưa có transcript.</p>}
      </section>
    </div>
  );
}
