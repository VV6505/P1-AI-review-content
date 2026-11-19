"use client";

import Image from "next/image";
import Link from "next/link";
import { useState } from "react";
import { ArrowRight, ArrowUpRight, Check, FileCheck2, Film, Link2, Pause, Play } from "lucide-react";
import { usePreferences } from "@/features/studio/preferences";
import { PublicLayout } from "./public-layout";
import { PricingCards } from "./pricing";

function CreativeShowcase() {
  const { t } = usePreferences();
  const [ratio, setRatio] = useState("16:9");
  const [style, setStyle] = useState("minimal");
  const [playing, setPlaying] = useState(false);

  return <section className="creative-showcase" data-style={style} aria-labelledby="hero-title">
    <div className="showcase-stage">
      <h1 id="hero-title" className="showcase-title">{t("Creative — Sáng tạo video cùng AI", "Creative — Create videos with AI")}</h1>
      <div className={`showcase-film${ratio === "9:16" ? " is-portrait" : ""}${playing ? " is-playing" : ""}`} onContextMenu={event => event.preventDefault()}>
        <Image src="/images/creative-ai-transparent.png" alt={t("Chữ Creative bằng bạc và trắng, biểu tượng phát video cùng dải phim uốn lượn thể hiện sáng tạo với AI", "Pearl-white Creative lettering, a silver play symbol and a flowing filmstrip representing AI creativity")} fill sizes="(max-width: 760px) 80vw, 928px" loading="eager" className="showcase-product" draggable={false} onDragStart={event => event.preventDefault()} />
      </div>
    </div>

    <div className="showcase-copy">
      <h2>{t("Sản phẩm của bạn. Sáng tạo cùng AI.", "Your product. Reimagined with AI.")}</h2>
      <p>{t("Từ một đường link đến ý tưởng video giới thiệu sản phẩm. Chọn góc nhìn, phong cách và để câu chuyện mang dấu ấn của bạn.", "Turn a product link into a video idea. Choose an angle, set the style, and make the story your own.")}</p>
    </div>

    <div className="showcase-controls">
      <label className="showcase-choice"><span>{t("Phong cách", "Style")}</span><select aria-label={t("Phong cách minh họa", "Illustration style")} value={style} onChange={event => setStyle(event.target.value)}><option value="minimal">{t("Tối giản", "Minimal")}</option><option value="cinema">{t("Điện ảnh", "Cinema")}</option><option value="editorial">{t("Tạp chí", "Editorial")}</option></select></label>
      <label className="showcase-choice"><span>{t("Khung hình", "Format")}</span><select aria-label={t("Khung hình minh họa", "Illustration format")} value={ratio} onChange={event => setRatio(event.target.value)}><option value="16:9">16:9</option><option value="9:16">9:16</option></select></label>
      <button className="showcase-preview-button" type="button" aria-pressed={playing} aria-label={t(playing ? "Dừng chuyển động minh họa" : "Xem chuyển động minh họa", playing ? "Pause illustration animation" : "Play illustration animation")} onClick={() => setPlaying(!playing)}>{playing ? <Pause size={14} aria-hidden="true" /> : <Play size={14} aria-hidden="true" />}<span>{t(playing ? "Tạm dừng" : "Xem minh họa", playing ? "Pause" : "Preview")}</span></button>
      <Link className="showcase-start" href="/signup">{t("Bắt đầu sáng tạo", "Start creating")}<ArrowUpRight size={15} aria-hidden="true" /></Link>
    </div>
    <p className="showcase-caption">{t("Minh họa video sản phẩm", "Product video illustration")}</p>
  </section>;
}

export function LandingPage() {
  const { t } = usePreferences();
  const steps = [
    { icon: Link2, title: t("Thêm sản phẩm", "Add your product"), text: t("Dán link website hoặc trang sản phẩm để bắt đầu dự án video.", "Paste a website or product link to start your video project.") },
    { icon: FileCheck2, title: t("Kiểm tra thông tin", "Review the details"), text: t("Xem lại nguồn và chỉnh sửa thông tin. Một video tốt bắt đầu từ việc hiểu đúng sản phẩm.", "Review sources and edit the details. A good video starts with knowing the product.") },
    { icon: Film, title: t("Sáng tạo cùng AI", "Create with AI"), text: t("Phát triển ý tưởng, chọn phong cách và khung hình cho video giới thiệu sản phẩm.", "Develop your idea, then choose a style and format for your product video.") },
  ];

  return <PublicLayout>
    <main id="main-content" tabIndex={-1}>
      <CreativeShowcase />

      <section id="quy-trinh" className="landing-process public-container" aria-labelledby="process-title">
        <div className="landing-section-heading"><div><h2 id="process-title">{t("Từ sản phẩm", "From your product")}<br /><span>{t("đến ý tưởng video.", "to a video idea.")}</span></h2></div><p>{t("Một quy trình để tìm thông tin, phát triển nội dung và thử cách thể hiện mới cho sản phẩm của bạn.", "One workflow to gather details, develop a story and explore a fresh perspective on your product.")}</p></div>
        <ol className="landing-steps">{steps.map(({ icon: Icon, title, text }, index) => <li key={index}>
          <div className={`step-visual step-visual-${index + 1}`} aria-hidden="true">
            {index === 0 && <div className="step-link-preview"><span className="step-mini-product"><Image src="/images/creative-headphones.png" alt="" width={74} height={74} /></span><div className="step-link-field"><Link2 size={14} /><span>your-product.com</span><ArrowUpRight size={13} /></div></div>}
            {index === 1 && <div className="step-details-preview"><div className="step-detail-heading"><FileCheck2 size={17} /><span>{t("Thông tin sản phẩm", "Product details")}</span></div>{[0, 1, 2].map(line => <div className="step-detail-line" key={line}><span /><Check size={12} /></div>)}</div>}
            {index === 2 && <div className="step-video-preview"><div className="step-video-frame"><Image src="/images/creative-headphones.png" alt="" width={82} height={82} /><span><Play size={13} fill="currentColor" /></span></div><div className="step-video-timeline">{[16, 26, 12, 32, 20, 14, 28, 18, 24, 12, 22, 16].map((height, bar) => <i key={bar} style={{ height }} />)}</div></div>}
          </div>
          <div className="step-top"><span className="step-icon"><Icon size={17} strokeWidth={1.6} aria-hidden="true" /></span><span className="step-number">0{index + 1}</span></div><h3>{title}</h3><p>{text}</p>
        </li>)}</ol>
      </section>

      <section id="about" className="landing-features public-container" aria-labelledby="features-title">
        <span id="tinh-nang" className="section-anchor" aria-hidden="true" />
        <div className="landing-feature-copy"><h2 id="features-title">{t("Ý tưởng của bạn.", "Your imagination.")}<br /><span>{t("AI giúp thể hiện.", "A new way to create.")}</span></h2><p>{t("Reviewlab kết nối thông tin sản phẩm, ý tưởng và những lựa chọn video trong một không gian. Bạn chọn điều cần kể, AI hỗ trợ cách thể hiện.", "Reviewlab brings product details, ideas and video choices into one space. You choose the story; AI helps you explore how to tell it.")}</p><div className="feature-notes"><span><Check size={15} aria-hidden="true" />{t("Nội dung từ thông tin đã kiểm tra", "Content grounded in reviewed details")}</span><span><Check size={15} aria-hidden="true" />{t("Phong cách và khung hình do bạn chọn", "Your choice of style and format")}</span><span><Check size={15} aria-hidden="true" />{t("Ý tưởng và kết quả nằm trong từng dự án", "Ideas and results organized by project")}</span></div><Link className="feature-link" href="/signup">{t("Mở không gian sáng tạo", "Open your creative space")}<ArrowUpRight size={16} aria-hidden="true" /></Link></div>
        <div className="landing-source-preview">
          <div className="source-preview-orbit" aria-hidden="true" />
          <div className="source-sheet">
            <div className="source-sheet-heading"><span>{t("Thông tin sản phẩm", "Product details")}</span><Check size={15} aria-label={t("Đã xác nhận", "Confirmed")} /></div>
            <div className="source-product-row"><div className="source-product-photo"><Image src="/images/creative-headphones.png" alt="" width={72} height={72} /></div><div><strong>Studio Headphones</strong><span>{t("Tai nghe chụp tai", "Over-ear headphones")}</span></div></div>
            <p className="source-description">{t("Một thiết kế. Nhiều góc nhìn để kể.", "One design. More than one way to tell its story.")}</p>
            <div className="source-reference"><Link2 size={12} aria-hidden="true" /><span>example.com/studio-headphones</span></div>
          </div>
          <div className="source-video-card" aria-label={t("Minh họa ý tưởng video sản phẩm", "Product video idea illustration")}>
            <div className="source-video-top"><span>REVIEWLAB</span><span>9:16</span></div>
            <Image src="/images/creative-headphones.png" alt="" width={138} height={138} />
            <div className="source-video-copy"><small>{t("MỘT GÓC NHÌN MỚI", "A FRESH PERSPECTIVE")}</small><strong>{t("Âm thanh.", "Sound.")}<br />{t("Theo cách bạn thích.", "Your way.")}</strong></div>
            <span className="source-video-play" aria-hidden="true"><Play size={14} /></span>
          </div>
          <span className="source-preview-caption">{t("Một sản phẩm. Nhiều cách thể hiện.", "One product. New possibilities.")}</span>
        </div>
      </section>

      <section id="price" className="landing-pricing public-container" aria-labelledby="price-title">
        <div className="landing-section-heading"><div><h2 id="price-title">{t("Một không gian.", "One creative space.")}<br /><span>{t("Cho từng nhịp sáng tạo.", "For every creative pace.")}</span></h2></div><p>{t("Các gói dưới đây là dữ liệu minh họa. Giá chính thức và thanh toán chưa được triển khai.", "These are sample plans. Official pricing and payments are not available yet.")}</p></div>
        <PricingCards />
      </section>

      <section className="landing-cta public-container" aria-labelledby="cta-title"><div><h2 id="cta-title">{t("Đưa sản phẩm", "Bring your product")}<br /><span>{t("lên khung hình.", "into the picture.")}</span></h2><p>{t("Bắt đầu câu chuyện đầu tiên cùng Reviewlab.", "Start your first story with Reviewlab.")}</p></div><div className="cta-actions"><Link className="primary-button" href="/signup">{t("Bắt đầu sáng tạo", "Start creating")}<ArrowUpRight size={17} aria-hidden="true" /></Link><Link href="/login">{t("Đã có tài khoản? Đăng nhập", "Already a member? Sign in")}<ArrowRight size={14} aria-hidden="true" /></Link></div></section>
    </main>
  </PublicLayout>;
}
