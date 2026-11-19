import type { Metadata } from "next";
import { LandingPage } from "@/features/marketing/landing";

export const metadata: Metadata = {
  title: "Reviewlab — Creative with AI",
  description: "Sáng tạo video giới thiệu sản phẩm cùng AI. Từ đường link, thông tin sản phẩm đến ý tưởng video mang dấu ấn của bạn.",
};

export default function Home() {
  return <LandingPage />;
}
