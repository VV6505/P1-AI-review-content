import type { Metadata } from "next";
import { PricePage } from "@/features/marketing/pricing";

export const metadata: Metadata = {
  title: "Price — Reviewlab",
  description: "Khám phá các gói minh họa Free, Creator và Pro của Reviewlab.",
};

export default function Page() {
  return <PricePage />;
}
