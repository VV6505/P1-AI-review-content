import Link from "next/link";

export default function NotFound() {
  return <section className="empty-list"><h1>Không tìm thấy trang</h1><p>Kiểm tra đường dẫn hoặc quay lại workspace.</p><Link href="/">Về tổng quan</Link></section>;
}
