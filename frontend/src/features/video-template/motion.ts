export type MotionBeat = { text: string; start: number; end: number; result?: boolean; side?: "left" | "right" };
export type SceneMotion = { introEnd: number; beats: MotionBeat[]; mode?: "adaptive" | "centered" };

/** Shared normalized contract used by both the M2 adapter and local BE handoffs. */
export function validateMotion(motion: SceneMotion, duration: number): SceneMotion {
  if (!Number.isFinite(motion.introEnd) || motion.introEnd < 0 || motion.introEnd > duration || !Array.isArray(motion.beats) || motion.beats.length > 24) throw new Error("Motion: intro hoặc danh sách chỉ dẫn không hợp lệ.");
  if (motion.mode !== undefined && !["adaptive", "centered"].includes(motion.mode)) throw new Error("Motion: kiểu bố cục chưa hỗ trợ.");
  let previousEnd = 0;
  const beats = motion.beats.map(beat => {
    if (typeof beat.text !== "string" || !beat.text.trim() || beat.text.length > 160) throw new Error("Motion: chỉ dẫn cần có chữ, tối đa 160 ký tự.");
    if (!Number.isFinite(beat.start) || !Number.isFinite(beat.end) || beat.start < previousEnd - .000001 || beat.start < motion.introEnd || beat.end <= beat.start || beat.end > duration + .000001) throw new Error("Motion: chỉ dẫn chồng nhau hoặc nằm ngoài thời lượng cảnh.");
    if (beat.result !== undefined && typeof beat.result !== "boolean" || beat.side !== undefined && !["left", "right"].includes(beat.side)) throw new Error("Motion: result/side không hợp lệ.");
    previousEnd = beat.end;
    return { ...beat };
  });
  return { ...motion, beats };
}
