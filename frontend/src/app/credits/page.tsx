import type { Metadata } from "next";
import { CreditsPage } from "@/features/marketing/credits";

export const metadata: Metadata = {
  title: "Ghi công / Credits — Reviewlab",
  description: "Ghi công các dự án phần mềm được sử dụng trong Reviewlab.",
};

export default function Credits() {
  return <CreditsPage />;
}
