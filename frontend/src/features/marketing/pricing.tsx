"use client";

import Link from "next/link";
import { ArrowUpRight, Plus } from "lucide-react";
import { usePreferences } from "@/features/studio/preferences";
import { initialStudio } from "@/features/studio/model";
import { PublicLayout } from "./public-layout";

export function PricingCards() {
  const { t, number } = usePreferences();
  return <div className="landing-price-grid">{initialStudio.plans.map(plan => <article className={`landing-price-card${plan.id === "creator" ? " is-featured" : ""}`} key={plan.id}>
    <div className="landing-price-heading"><h3>{plan.name}</h3>{plan.id === "creator" && <span>{t("Nổi bật", "Featured")}</span>}</div>
    <p className="landing-price-description">{plan.id === "free" ? t("Dành cho ý tưởng đầu tiên.", "For your first idea.") : plan.id === "creator" ? t("Cho nhịp sáng tạo mỗi ngày.", "For your everyday creative flow.") : t("Thêm không gian để khám phá.", "More room to explore.")}</p>
    <p className="landing-price-amount">{number(plan.price)}<span>VND</span></p>
    <p className="landing-price-tokens">{number(plan.tokens)} {t("token mẫu", "sample tokens")}</p>
    <Link className={plan.id === "creator" ? "primary-button" : "secondary-button"} href="/signup">{t("Khám phá bản xem thử", "Explore the preview")}<ArrowUpRight size={15} aria-hidden="true" /></Link>
  </article>)}</div>;
}

export function PricePage() {
  const { t } = usePreferences();
  const questions = [
    { title: t("Tôi có thể bắt đầu từ đâu?", "Where can I start?"), text: t("Tạo tài khoản hoặc dùng tài khoản mẫu ở trang đăng nhập để khám phá không gian sáng tạo.", "Create an account or use a demo account on the sign-in page to explore the creative workspace.") },
    { title: t("Các gói này đã mở bán chưa?", "Are these plans available to purchase?"), text: t("Chưa. Giá và token hiện là dữ liệu minh họa cho bản xem thử. Reviewlab chưa hỗ trợ thanh toán hay mua gói.", "Not yet. Prices and tokens are sample data for the preview. Payments and plan purchases are not available yet.") },
  ];
  return <PublicLayout><main id="main-content" className="public-info-main public-container" tabIndex={-1}>
    <header className="public-page-heading">
      <p className="public-page-label">{t("Bảng giá", "Pricing")}</p>
      <h1>{t("Một không gian.", "One creative space.")}<br /><span>{t("Cho từng nhịp sáng tạo.", "For every creative pace.")}</span></h1>
      <p>{t("Bắt đầu từ một ý tưởng. Chọn gói phù hợp với nhịp sáng tạo của bạn.", "Start with an idea. Find your space as your creative flow grows.")}</p>
    </header>
    <section id="price" className="public-page-pricing" aria-label={t("Các gói minh họa", "Sample plans")}>
      <PricingCards />
      <p className="public-pricing-note">{t("Giá và token là dữ liệu minh họa. Chưa hỗ trợ thanh toán.", "Prices and tokens are sample data. Payments are not available yet.")}</p>
    </section>
    <section className="public-faq" aria-labelledby="faq-title">
      <h2 id="faq-title">{t("Một vài điều cần biết.", "A few things to know.")}</h2>
      <div>{questions.map(question => <details key={question.title}><summary>{question.title}<Plus size={16} aria-hidden="true" /></summary><p>{question.text}</p></details>)}</div>
    </section>
  </main></PublicLayout>;
}
