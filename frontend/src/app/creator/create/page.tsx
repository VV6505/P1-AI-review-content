import { CreatorStudio } from "@/features/studio/creator";
import { LocalP1Entry } from "@/features/p1-local/entry";

export default function Page() {
  return process.env.P1_LOCAL_MODE === "1" ? <LocalP1Entry /> : <CreatorStudio />;
}
