import type { Review } from "./types";

// These are FE fixtures, not AI results. The local video is an original, silent UI demo.
export const demoReviews: Review[] = [
  {
    id: "notion-workspace", product: "Notion", title: "Notion: organize notes and work",
    summary: "A sample video review workflow. Content, transcript and scores are illustrative demo data.",
    thumbnailUrl: "/media/notion-review.svg", videoUrl: "/media/workspace-demo.webm", score: 86, status: "completed",
    transcript: [
      { start: 0, end: 4, text: "Start with a workspace to organize product information." },
      { start: 4, end: 8, text: "Review the details and note what needs verification." },
      { start: 8, end: 12, text: "Edit the content before sharing. This is a demonstration." },
    ],
  },
  {
    id: "gamma-presentation", product: "Gamma", title: "Gamma: from idea to presentation",
    summary: "An illustrative content workflow. The video shows a demo workspace, not real Gamma footage or a verified review.",
    thumbnailUrl: "/media/gamma-review.svg", videoUrl: "/media/workspace-demo.webm", score: 91, status: "completed",
    transcript: [
      { start: 0, end: 4, text: "Gather ideas and inputs for your presentation." },
      { start: 4, end: 8, text: "Review the information before building your story." },
      { start: 8, end: 12, text: "Edit the draft and prepare to share your content." },
    ],
  },
  {
    id: "linear-projects", product: "Linear", title: "Linear: track your team's progress",
    summary: "Illustrative data for a project management review. Scores are not AI-generated or verified.",
    thumbnailUrl: "/media/linear-review.svg", videoUrl: "/media/workspace-demo.webm", score: 88, status: "completed",
    transcript: [
      { start: 0, end: 4, text: "Start with your team's tasks and goals." },
      { start: 4, end: 8, text: "Review the status and details that need updating." },
      { start: 8, end: 12, text: "Summarize progress for your team." },
    ],
  },
];

export function searchDemoReviews(query: string): Review[] {
  const normalize = (value: string) => value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/đ/g, "d").replace(/Đ/g, "D").toLowerCase();
  const words = normalize(query.trim()).split(/\s+/).filter(Boolean);
  return demoReviews.filter((review) => words.every((word) => normalize(`${review.title} ${review.product} ${review.summary}`).includes(word)));
}
