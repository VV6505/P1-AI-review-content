"""Prompt trích xuất `software`. Port từ `spikes/m1-crawl-extract/extract.py`, thêm conflicts."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Protocol

SYSTEM_PROMPT = """Bạn trích xuất fact về 1 sản phẩm phần mềm/AI từ các trang web đã crawl, \
thành JSON theo schema.

Quy tắc:
- Chỉ dùng thông tin có trong các trang nguồn. Không suy đoán, không dùng kiến thức bên ngoài.
- Mỗi fact ghi `source_id` của trang chứa nó và `evidence`: 1 đoạn trích NGUYÊN VĂN, liên tục, \
từ trang đó (copy đúng chữ, ≤ 200 ký tự). Không viết lại evidence.
- Evidence là MỘT đoạn liền, chép nguyên văn, không ghép, không sửa chữ.
- Evidence phải chứa chính giá trị của fact. `identity.name`: đoạn có đúng chữ tên sản phẩm \
(vd. "What is Acme?", "© 2026 Acme", tiêu đề có tên), không lấy slogan / mô tả không có tên. \
Mỗi plan: đoạn liên tục có CẢ tên plan VÀ giá, thường từ dòng tên plan tới dòng giá \
(vd. "### Pro\\nMost popular\\n$20 per month"). Tên và giá cách nhau quá 200 ký tự thì chọn \
chỗ khác có cả hai (bảng so sánh, FAQ). Mỗi usage_price: đoạn có tên và giá.
- `origin` luôn là "crawled".
- Giữ nguyên ngôn ngữ của trang nguồn cho tên và mô tả.
- features: tính năng cụ thể của sản phẩm (tối đa 15, quan trọng nhất trước). Gồm cả chương trình \
hoặc dịch vụ đi kèm mà trang giới thiệu thành một khối riêng (vd. bảng việc làm, thử thách / \
cuộc thi (Challenge), chương trình đối tác): mỗi khối 1 feature, `name` là tên khối, \
`description` là mô tả trên trang. Khối chỉ có tiêu đề hay vài dòng ngắn vẫn ghi, đừng bỏ qua; \
chương trình đối tác ghi 1 feature, evidence là đoạn mô tả hoặc nút kêu gọi của chương trình. \
Khối ngắn gồm 1 heading và 1 câu mô tả cũng là 1 feature: heading "Weekly Challenge" với câu \
"Take on weekly challenges, climb the leaderboard and win prizes." → `name` "Weekly Challenge", \
`description` là câu đó, evidence là heading kèm câu. Thử thách / cuộc thi (Challenge) mà trang \
chỉ có danh sách thẻ người học (tên, điểm) thì thẻ không phải mô tả: dùng khối có heading và câu \
mô tả về thử thách, nếu trang có.
- use_cases: tối đa 12. Trang có khối lộ trình / giải pháp theo phòng ban, ngành hay vai trò (vd. \
Sales, Marketing, Finance, HR): mỗi mục 1 use_case, `title` = tên phòng ban + tiêu đề của mục \
(vd. "Sales: Close deals faster with AI"). `evidence` là đoạn nguyên văn chứa kết quả kèm con số \
của mục đó (vd. "+35% more opportunities handled per week"), không chỉ tiêu đề.
- audiences: nhóm đối tượng trang nhắm tới (tối đa 6), vd. doanh nghiệp nhỏ, nhân viên theo \
phòng ban, cá nhân tìm việc, đối tác. `segment` là tên nhóm; `jtbd` là việc họ muốn làm, chỉ ghi \
khi trang nói rõ, không thì null. Trang có lộ trình riêng cho nhân viên theo phòng ban / vai \
trò thì ghi nhóm đó (1 mục, không liệt kê từng phòng ban): `segment` là tên nhóm đúng chữ trang \
dùng (vd. "Employees"), `jtbd` null, evidence là heading của khối kèm tên phòng ban đầu tiên (vd. \
"## Paths by team\\nSales"). Đúng nhóm nào trang nêu mới ghi.
- usp: điểm mạnh / bằng chứng mà trang tự công bố (tối đa 12). Số liệu thành tích của sản phẩm \
(lượt xem, người theo dõi, lượt tiếp cận, số thành viên, số người dùng, doanh thu…) ghi vào usp, \
MỖI SỐ LIỆU LÀ 1 MỤC RIÊNG: `text` bắt đầu bằng "Theo <tên sản phẩm> công bố:" rồi đúng 1 số \
kèm nhãn đứng NGAY SAU số đó trong nguồn, giữ nguyên chữ của nhãn (vd. "Theo Acme công bố: \
2M+ downloads"). Số đứng trước nhãn của nó, kể cả khi xuống dòng; số ở cuối một dòng thuộc \
nhãn ở dòng kế, KHÔNG thuộc nhãn ở đầu dòng đó (nguồn \"5M+\\n views 30K+\\n followers\" là \
"5M+ views" và "30K+ followers"). `evidence` là đoạn nguyên văn có số và nhãn của nó. Không \
làm tròn, không cộng các số với nhau. Câu có nhiều số dùng chung 1 nhãn (nguồn \"1,200+\\nactive \
members, +80 this year\") thì mỗi số vẫn 1 mục, giữ nhãn đầy đủ của câu nguồn: \"1,200+ active \
members\" và \"+80 this year (active members)\", evidence chứa cả hai phần của câu.
- Bộ đếm chỉ toàn số 0 (`0+`, `0%`, `0,00M+`) là chỗ giữ của hiệu ứng đếm số, không phải số liệu: \
bỏ qua, chỉ ghi số có giá trị thật.
- Số liệu về thị trường hay ngành, không nói về sản phẩm (vd. "70% doanh nghiệp chưa có đội đào \
tạo", "mỗi tuần ra mắt 50+ công cụ mới") không phải fact về sản phẩm: KHÔNG ghi vào trường nào.
- limitations: hạn chế, giới hạn dùng, điều kiện được ghi rõ (tối đa 8).
- Không tìm thấy thì để null hoặc danh sách rỗng.
- conflicts: khi 2 trang ghi KHÁC NHAU về cùng một thông tin (vd. số lượng công cụ, giá của cùng \
plan và chu kỳ, giới hạn dung lượng), KHÔNG chọn một giá trị. Ghi 1 mục conflicts: `field` là \
đường dẫn trường liên quan, `topic` là thông tin đó, `claims` là từng giá trị kèm `source_id` và \
`evidence` nguyên văn. Fact liên quan vẫn ghi đúng như từng trang. Không có thì để rỗng.

Quy tắc giá (pricing):
1. Tách giá niêm yết và khuyến mãi: `list_price` là giá thường; `promo_price` + `promo_terms` là \
giá khuyến mãi (vd. "tháng đầu"). Không ghi giá khuyến mãi vào `list_price`.
2. Không tự tính, không quy đổi (năm → tháng, đổi tiền). Giá là con số in trên trang. \
`price_text` chép nguyên văn.
3. `price_unit` (month | year | seat_month | seat_year | one_time) và `billing_cycle` (monthly | \
quarterly | yearly | one_time) là bắt buộc khi có giá. 1 plan có nhiều chu kỳ thì ghi nhiều dòng. \
Plan Free: `list_price` 0. Plan "Contact sales": `list_price` null, `price_unit` và \
`billing_cycle` null.
Sản phẩm hoàn toàn miễn phí, không có bảng giá: ghi 1 plan `name` "Free", `list_price` 0, \
`price_unit` month, `billing_cycle` monthly, `price_text` và `evidence` là câu khẳng định miễn \
phí trên trang (vd. "Hoàn toàn Miễn phí"); `free_plan` true với cùng evidence. Ca này evidence \
không cần tên plan.
4. `plans` chỉ chứa gói đăng ký. Giá theo token, theo giây video, theo credit đưa vào \
`usage_prices`.
5. `default_view`: tab / chu kỳ trang giá đang hiển thị (vd. "monthly"). `other_views`: các tab \
khác có trên trang nhưng nội dung chưa có trong nguồn.
Ví dụ đúng: trang ghi "Pro $17 per month with annual subscription discount ($200 billed up front), \
$20 if billed monthly" → 2 dòng: {name: Pro, list_price: 17, price_unit: month, billing_cycle: \
yearly} và {name: Pro, list_price: 20, price_unit: month, billing_cycle: monthly}. Không ghi \
16.67 (= 200/12)."""

MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
HEADER = re.compile(r"\A<!--.*?-->\s*", re.DOTALL)


def clean_for_llm(md: str) -> str:
    """Bỏ header, ảnh và URL đích của link (giữ chữ của link). URL dài tốn token, không có fact."""
    md = HEADER.sub("", md)
    md = MD_IMAGE.sub("", md)
    md = MD_LINK.sub(r"\1", md)
    lines = [ln.rstrip() for ln in md.splitlines()]
    return "\n".join(ln for ln in lines if ln.strip())


class PromptDoc(Protocol):
    source_id: str
    page_type: str
    url: str
    text: str


def build_prompt(product_name: str, docs: Sequence[PromptDoc]) -> str:
    parts = [f"Sản phẩm: {product_name}\n"]
    for d in docs:
        parts.append(
            f"=== SOURCE {d.source_id} | page_type: {d.page_type} | url: {d.url} ===\n{d.text}\n"
        )
    return "\n".join(parts)
