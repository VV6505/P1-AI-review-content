import type { FactRef, Project } from "./model.ts";

type Script = {
  schema_version: string; concept: { title: string; angle: string }; audience: string;
  target_duration_s: number; estimated_duration_s?: number; hook: { text: string };
  scenes: { scene_id: string; role: string; visual_plan: { kind: string }; claims: { text: string; fact_refs: FactRef[]; segment_ids: string[] }[] }[];
};

/** Read the original, already validated M2 payload; never derive new product claims. */
export function contentReview(project: Project) {
  const payload = project.sourcePayload as Partial<Script> | null;
  if (payload?.schema_version !== "p1-ac-03.v1-draft") return null;
  const script = payload as Script;
  let start = 0;
  const scenes = project.scenes.map(scene => {
    const source = script.scenes.find(item => item.scene_id === scene.id)!;
    const row = { id: scene.id, start, end: start + scene.duration, duration: scene.duration,
      role: source.role, visual: source.visual_plan.kind, subtitle: scene.subtitle,
      narration: scene.segments.map(segment => ({ ...segment })),
      claims: source.claims.map(claim => ({ text: claim.text, refs: claim.fact_refs.map(ref => ({ ...ref })), segmentIds: [...claim.segment_ids] })), refs: scene.refs.map(ref => ({ ...ref })),
      wordCount: scene.segments.reduce((count, segment) => count + segment.text.trim().split(/\s+/u).length, 0) };
    start = row.end;
    return row;
  });
  const footageDuration = scenes.filter(scene => ["screen_recording", "screenshot"].includes(scene.visual)).reduce((sum, scene) => sum + scene.duration, 0);
  const consecutiveTextCards = scenes.some((scene, index) => scene.visual === "text_card" && scenes[index + 1]?.visual === "text_card");
  return { title: script.concept.title, angle: script.concept.angle, audience: script.audience,
    hook: script.hook.text, target: script.target_duration_s, estimated: script.estimated_duration_s,
    timeline: start, timing: project.timing, footageRatio: footageDuration / start, consecutiveTextCards, scenes };
}
