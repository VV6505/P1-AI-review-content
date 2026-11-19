import type { Metadata } from "next";
import { AboutPage } from "@/features/marketing/about";

export const metadata: Metadata = {
  title: "About — Reviewlab",
  description: "Reviewlab — Không gian sáng tạo video giới thiệu sản phẩm cùng AI.",
};

export default function Page() {
  return <AboutPage />;
}
