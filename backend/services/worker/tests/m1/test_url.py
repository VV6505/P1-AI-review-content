import pytest

from worker.m1.url import InvalidUrlError, normalize_page_url, normalize_product_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://example.com", "https://example.com"),
        ("https://example.com/", "https://example.com"),  # bỏ / cuối ở URL gốc
        ("  https://example.com/  ", "https://example.com"),  # cắt khoảng trắng hai đầu
        ("HTTPS://EXAMPLE.COM", "https://example.com"),  # hạ chữ thường scheme + host
        ("http://example.com", "https://example.com"),  # http đổi thành https
        ("http://example.com:80/pricing", "https://example.com/pricing"),  # port mặc định của http
        ("https://example.com:443/", "https://example.com"),
        ("https://example.com:8443/app", "https://example.com:8443/app"),  # port khác giữ
        ("https://www.example.com/", "https://www.example.com"),  # giữ www.
        # Giữ path và chữ hoa/thường của path (product theo path, qa-log #10)
        ("https://github.com/features/Copilot/", "https://github.com/features/Copilot"),
        ("https://www.notion.com/product/AI", "https://www.notion.com/product/AI"),
        ("https://example.com/a#section", "https://example.com/a"),  # bỏ fragment
        # Bỏ tham số theo dõi, giữ query khác và sắp theo tên
        ("https://example.com/?utm_source=x&utm_medium=y", "https://example.com"),
        ("https://example.com/p?ref=abc&fbclid=1&gclid=2&UTM_Campaign=z", "https://example.com/p"),
        ("https://example.com/p?b=2&utm_source=x&a=1", "https://example.com/p?a=1&b=2"),
        ("https://example.com/p?id=7", "https://example.com/p?id=7"),
        # IDN sang punycode
        ("https://bücher.de/", "https://xn--bcher-kva.de"),
        ("https://[2001:db8::1]:8080/x", "https://[2001:db8::1]:8080/x"),
    ],
)
def test_normalize_product_url(raw: str, expected: str) -> None:
    assert normalize_product_url(raw) == expected


def test_hai_url_khac_dang_cung_mot_product() -> None:
    a = normalize_product_url("HTTP://Example.com:80/Pricing/?utm_source=ads#top")
    b = normalize_product_url("https://example.com/Pricing")
    assert a == b


def test_khac_path_la_hai_product_khac_nhau() -> None:
    assert normalize_product_url("https://github.com/features/copilot") != normalize_product_url(
        "https://github.com/features/actions"
    )


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "example.com",  # thiếu scheme
        "ftp://example.com",
        "javascript:alert(1)",
        "mailto:a@example.com",
        "https://",
        "https:///path",
        "https://user:pass@example.com",
        "https://user@example.com",
        "https://exa mple.com",
        "https://example.com:notaport",
        "https://example.com:99999",
    ],
)
def test_url_khong_hop_le(raw: str) -> None:
    with pytest.raises(InvalidUrlError):
        normalize_product_url(raw)


def test_normalize_page_url_bo_query_va_slash_cuoi() -> None:
    assert normalize_page_url("HTTPS://Example.com/Pricing/?a=1#x") == "https://example.com/Pricing"
    assert normalize_page_url("https://example.com") == "https://example.com/"
    assert normalize_page_url("https://example.com/") == "https://example.com/"
