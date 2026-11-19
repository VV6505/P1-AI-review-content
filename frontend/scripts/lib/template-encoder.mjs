import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";

export function selectEncoder(ffmpeg, preference = "auto") {
  assert.ok(["auto", "cpu", "nvenc"].includes(preference), "encoder must be auto, cpu or nvenc");
  const gpu = ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "18", "-b:v", "0"];
  if (preference !== "cpu") {
    // Test the driver, not just whether this FFmpeg build lists the codec.
    const probe = spawnSync(ffmpeg, ["-v", "error", "-f", "lavfi", "-i", "color=s=1920x1080:r=30", "-frames:v", "3", "-an", ...gpu, "-pix_fmt", "yuv420p", "-f", "null", "-"], { windowsHide: true, encoding: "utf8", timeout: 15000 });
    if (!probe.error && probe.status === 0) return { name: "h264_nvenc", args: gpu };
    assert.notEqual(preference, "nvenc", `NVENC unavailable: ${probe.error?.message || probe.stderr}`);
  }
  return { name: "libx264", args: ["-c:v", "libx264", "-preset", "fast", "-crf", "18"] };
}
