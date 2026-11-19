"use client";

import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { usePreferences } from "@/features/studio/preferences";
import { useAuth } from "./provider";
import { DEMO_PASSWORD, loginDestination } from "./model";
import { ArrowLeft, Eye, EyeOff } from "lucide-react";

export function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const signup = mode === "signup";
  const router = useRouter();
  const { t } = usePreferences();
  const { account, ready, error: storageError, signIn, signUp } = useAuth();
  const [name, setName] = useState("");
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [pending, setPending] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (account) router.replace(loginDestination(new URLSearchParams(window.location.search).get("next"), account.role));
  }, [account, router]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    setPending(true); setError("");
    try {
      if (signup) await signUp(name, identifier, password, confirmation);
      else await signIn(identifier, password);
    } catch (cause) {
      const messages: Record<string, string> = {
        name: t("Tên cần từ 2 đến 80 ký tự.", "Use a name with 2–80 characters."),
        email: t("Nhập email hợp lệ.", "Enter a valid email."),
        password: t("Mật khẩu cần từ 8 đến 128 ký tự.", "Use a password with 8–128 characters."),
        confirmation: t("Mật khẩu xác nhận chưa khớp.", "The passwords do not match."),
        duplicate: t("Email này đã có tài khoản trên trình duyệt. Hãy đăng nhập.", "This email is already registered in this browser. Sign in instead."),
        credentials: t("Tài khoản hoặc mật khẩu chưa đúng.", "Incorrect account or password."),
      };
      setError(messages[cause instanceof Error ? cause.message : ""] ?? t("Không lưu được tài khoản mẫu. Kiểm tra bộ nhớ trình duyệt và thử lại.", "Could not save the demo account. Check browser storage and retry."));
    } finally { setPending(false); }
  }

  return <main id="main-content" className={`auth-page${signup ? " auth-signup" : ""}`} tabIndex={-1}>
    <div className="auth-atmosphere" aria-hidden="true"><span className="auth-bubble auth-page-bubble" /><span className="auth-star auth-page-star" /><span className="auth-star auth-page-star-small" /></div>
    <aside className="auth-story" aria-label={t("Giới thiệu Reviewlab", "About Reviewlab")}>
      <Link className="auth-brand" href="/" aria-label={t("Reviewlab — Trang chủ", "Reviewlab — Home")}>reviewlab<span>.</span></Link>
      <div className="auth-story-copy">
        <h2>{signup ? t("Cùng bắt đầu", "Start your") : t("Chào mừng đến với", "Welcome to")}<br /><span>{signup ? t("hành trình sáng tạo.", "creative journey.") : "Reviewlab."}</span></h2>
        <p>{t("Từ một sản phẩm. Đến câu chuyện của riêng bạn.", "From one product. To a story of your own.")}</p>
      </div>
      <div className="auth-art" aria-hidden="true">
        <span className="auth-bubble auth-bubble-one" /><span className="auth-bubble auth-bubble-two" /><span className="auth-bubble auth-bubble-three" />
        <span className="auth-star auth-star-one" /><span className="auth-star auth-star-two" /><span className="auth-star auth-star-three" />
        <Image src="/images/auth-ai-video.png" alt="" fill sizes="(max-width: 800px) 1px, (max-width: 1180px) 45vw, 560px" loading="eager" className="auth-illustration" />
      </div>
    </aside>
    <div className="auth-content">
      <div className="auth-topline">
        <Link className="auth-brand auth-mobile-brand" href="/" aria-label={t("Reviewlab — Trang chủ", "Reviewlab — Home")}>reviewlab<span>.</span></Link>
        <Link className="auth-home" href="/"><ArrowLeft size={15} aria-hidden="true" />{t("Về trang chủ", "Back to home")}</Link>
      </div>
      <section className="auth-card" aria-labelledby="auth-title">
      <div className="auth-heading">
        <h1 id="auth-title">{signup ? t("Tạo tài khoản", "Create an account") : t("Chào mừng trở lại", "Welcome back")}</h1>
        <p>{signup ? t("Bắt đầu tạo video từ sản phẩm của bạn.", "Start creating videos from your products.") : t("Đăng nhập để tiếp tục các dự án của bạn.", "Sign in to continue your projects.")}</p>
      </div>
      <form className="auth-form" onSubmit={submit}>
        <fieldset disabled={!ready || storageError || pending}>
          {signup && <label>{t("Họ và tên", "Full name")}<input name="name" autoComplete="name" required minLength={2} maxLength={80} value={name} onChange={event => setName(event.target.value)} /></label>}
          <label>{signup ? "Email" : t("Tài khoản", "Account")}<input name={signup ? "email" : "identifier"} type={signup ? "email" : "text"} autoComplete={signup ? "email" : "username"} required maxLength={254} value={identifier} onChange={event => setIdentifier(event.target.value)} placeholder={signup ? "ban@example.com" : t("creator, admin hoặc email", "creator, admin or email")} /></label>
          <div className="auth-password-field"><label>{t("Mật khẩu", "Password")}<input aria-label={t("Mật khẩu", "Password")} name="password" type={showPassword ? "text" : "password"} autoComplete={signup ? "new-password" : "current-password"} required minLength={signup ? 8 : undefined} maxLength={128} value={password} onChange={event => setPassword(event.target.value)} /></label><button className="auth-password-toggle" type="button" aria-label={t(showPassword ? "Ẩn mật khẩu" : "Hiện mật khẩu", showPassword ? "Hide password" : "Show password")} aria-pressed={showPassword} onClick={() => setShowPassword(!showPassword)}>{showPassword ? <EyeOff size={17} aria-hidden="true" /> : <Eye size={17} aria-hidden="true" />}</button>{signup && <span className="field-hint">{t("Ít nhất 8 ký tự.", "At least 8 characters.")}</span>}</div>
          {signup && <label>{t("Xác nhận mật khẩu", "Confirm password")}<input name="confirmation" type="password" autoComplete="new-password" required maxLength={128} value={confirmation} onChange={event => setConfirmation(event.target.value)} /></label>}
          {(error || storageError) && <p role="alert" className="studio-error">{error || t("Không đọc được tài khoản mẫu đã lưu. Kiểm tra bộ nhớ trình duyệt.", "Could not read saved demo accounts. Check browser storage.")}</p>}
          <button className="primary-button" type="submit">{pending ? t("Đang xử lý…", "Please wait…") : signup ? t("Tạo tài khoản", "Create account") : t("Đăng nhập", "Sign in")}</button>
        </fieldset>
      </form>
      <p className="auth-switch">{signup ? t("Đã có tài khoản?", "Already have an account?") : t("Chưa có tài khoản?", "New here?")} <Link href={signup ? "/login" : "/signup"}>{signup ? t("Đăng nhập", "Sign in") : t("Đăng ký", "Sign up")}</Link></p>
      {!signup && <details className="auth-demo"><summary>{t("Dùng tài khoản mẫu", "Use a demo account")}</summary><p>Creator: creator<br />Admin: admin<br />{t("Mật khẩu", "Password")}: {DEMO_PASSWORD}</p></details>}
      <p className="auth-notice">{t("Bản xem thử. Tài khoản chỉ lưu trên trình duyệt này; hãy dùng mật khẩu mẫu.", "Preview. Accounts are stored only in this browser; use a demo password.")}</p>
      </section>
    </div>
  </main>;
}
