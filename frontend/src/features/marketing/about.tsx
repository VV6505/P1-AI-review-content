"use client";

import Image from "next/image";
import Link from "next/link";
import { ArrowUpRight, FileCheck2, Film, Lightbulb } from "lucide-react";
import { usePreferences } from "@/features/studio/preferences";
import { PublicLayout } from "./public-layout";

export function AboutPage() {
  const { t } = usePreferences();
  const values = [
    { icon: FileCheck2, title: t("Hiểu đúng sản phẩm", "Know your product"), text: t("Tập hợp và kiểm tra thông tin từ nguồn trước khi phát triển nội dung.", "Gather and review source information before developing your story.") },
    { icon: Lightbulb, title: t("Giữ góc nhìn riêng", "Keep your perspective"), text: t("Bạn chọn điều cần kể. AI hỗ trợ khám phá ý tưởng và cách thể hiện.", "You choose what to say. AI helps you explore ideas and ways to express them.") },
    { icon: Film, title: t("Tập trung sáng tạo", "Make room to create"), text: t("Thông tin, ý tưởng và video cùng nằm trong một không gian dự án.", "Keep product details, ideas and videos together in one project workspace.") },
  ];
  return <PublicLayout><main id="main-content" className="public-info-main public-container" tabIndex={-1}>
    <section id="about" className="public-about-intro" aria-labelledby="about-title">
      <div className="public-page-heading">
        <p className="public-page-label">{t("Về Reviewlab", "About Reviewlab")}</p>
        <h1 id="about-title">{t("Ý tưởng của bạn.", "Your imagination.")}<br /><span>{t("AI giúp thể hiện.", "A new way to create.")}</span></h1>
        <p>{t("Reviewlab là không gian sáng tạo video giới thiệu sản phẩm cùng AI. Từ một đường link, tìm hiểu sản phẩm và phát triển câu chuyện theo cách của bạn.", "Reviewlab is a space to create product videos with AI. Start with a link, get to know your product and develop a story in your own way.")}</p>
        <Link className="feature-link" href="/signup">{t("Bắt đầu câu chuyện của bạn", "Start your own story")}<ArrowUpRight size={16} aria-hidden="true" /></Link>
      </div>
      <div className="public-about-art" aria-hidden="true"><span className="public-about-orbit" /><Image src="/images/auth-ai-video.png" alt="" fill sizes="(max-width: 760px) 90vw, 450px" className="public-about-image" /></div>
    </section>
    <section className="public-about-values" aria-labelledby="about-values-title">
      <h2 id="about-values-title">{t("Đơn giản để bắt đầu. Tự do để sáng tạo.", "Simple to start. Free to explore.")}</h2>
      <div>{values.map(({ icon: Icon, title, text }) => <article key={title}><span className="public-value-icon"><Icon size={21} strokeWidth={1.5} aria-hidden="true" /></span><h3>{title}</h3><p>{text}</p></article>)}</div>
    </section>
    <section className="public-about-note" aria-label={t("Khám phá Reviewlab", "Explore Reviewlab")}><p>{t("Bắt đầu nhỏ, với một sản phẩm và một ý tưởng.", "Start small, with one product and one idea.")}</p><Link href="/price">{t("Khám phá các gói", "Explore the plans")}<ArrowUpRight size={15} aria-hidden="true" /></Link></section>
  </main></PublicLayout>;
}
