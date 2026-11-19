import type { Draft, Request } from "./model";
import { creatorDraft } from "./model";
export function requestDraft(request: Request): Draft {
  return creatorDraft({ sourceUrl: request.sourceUrl, preparedUrl: request.preparedUrl, prompt: request.prompt, opening: request.opening, notes: request.notes, projectId: request.projectId ?? request.id, requirementsReview: request.requirementsReview ? { ...request.requirementsReview } : null, model: request.model, references: request.references.map(file => ({ ...file })), productReview: request.productReview ? { ...request.productReview } : null, count: request.count, ratio: request.ratio, resolution: request.resolution, style: request.style, duration: request.duration, outputLanguage: request.outputLanguage, camera: request.camera, negativePrompt: request.negativePrompt });
}
export function projectHistory(requests: Request[]) {
  const projects = new Map<string, Request>();
  for (const request of requests) { const id = request.projectId ?? request.id; if (!projects.has(id)) projects.set(id, request); }
  return [...projects.entries()].map(([id, latest]) => ({ id, latest, title: new URL(latest.sourceUrl).hostname.replace(/^www\./, ""), count: requests.filter(r => (r.projectId ?? r.id) === id).length }));
}
