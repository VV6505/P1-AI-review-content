import { test } from "node:test";
import assert from "node:assert/strict";
import { decodedFrameTimes } from "../scripts/lib/template-capture.mjs";

test("decoder uses exact PTS at 30 fps boundaries instead of rounded log seconds", () => {
  const times = decodedFrameTimes("config in time_base: 1/15360\nn: 0 pts: 0 pts_time:0\nn: 1 pts: 262144 pts_time:17.0667\nn: 2 pts: 262656 pts_time:17.1");
  assert.equal(times[1], 512 / 30);
  assert.ok(times[1] <= 512 / 30, "frame 512 must not be mistaken for a future frame");
  assert.equal(times[2], 513 / 30);
});

test("decoder rejects missing, duplicate and negative timestamps", () => {
  for (const log of ["", "config in time_base: 1/0\nn: 0 pts: 0 pts_time:0", "config in time_base: 1/30\nn: 0 pts: -1 pts_time:-0.033", "config in time_base: 1/30\nn: 0 pts: 0 pts_time:0\nn: 1 pts: 0 pts_time:0"]) assert.throws(() => decodedFrameTimes(log));
});
