"use client";

import Link from "next/link";
import { ArrowLeft, ArrowUpRight, Code2 } from "lucide-react";
import { usePreferences } from "@/features/studio/preferences";
import { PublicLayout } from "./public-layout";

export function CreditsPage() {
  const { t } = usePreferences();
  return <PublicLayout><main id="main-content" className="credits-main public-container" tabIndex={-1}>
    <Link className="credits-back" href="/"><ArrowLeft size={15} aria-hidden="true" />{t("Về trang chủ", "Back to home")}</Link>
    <p className="landing-eyebrow">{t("NHỮNG NỀN TẢNG ĐỒNG HÀNH", "THE PROJECTS BEHIND THE WORK")}</p>
    <h1>{t("Ghi công", "Acknowledgements")}<span> / Credits</span></h1>
    <p className="credits-intro">{t("Reviewlab được xây dựng với sự hỗ trợ của cộng đồng phần mềm. Cảm ơn các tác giả và dự án đã đóng góp những công cụ nền tảng.", "Reviewlab is built with the support of the software community. Thank you to the authors and projects behind these tools.")}</p>
    <section className="credits-card" aria-labelledby="crawl4ai-title"><div className="credits-card-heading"><span className="credits-icon"><Code2 size={23} aria-hidden="true" /></span><div><h2 id="crawl4ai-title">Crawl4AI</h2><p>{t("Công cụ thu thập nội dung website", "Website content crawling tool")}</p></div><span className="credits-license">Apache-2.0</span></div>
      <blockquote lang="en">This product includes software developed by UncleCode (<a href="https://x.com/unclecode" target="_blank" rel="noopener noreferrer">https://x.com/unclecode</a>) as part of the Crawl4AI project (<a href="https://github.com/unclecode/crawl4ai" target="_blank" rel="noopener noreferrer">https://github.com/unclecode/crawl4ai</a>).</blockquote>
      <a className="credits-project" href="https://github.com/unclecode/crawl4ai" target="_blank" rel="noopener noreferrer">{t("Xem dự án Crawl4AI", "Visit Crawl4AI")}<ArrowUpRight size={15} aria-hidden="true" /></a>
    </section>
  </main></PublicLayout>;
}
