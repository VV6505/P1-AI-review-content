"""robots.txt theo RFC 9309: parse, quyết định allow/disallow, và chính sách khi tải lỗi."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urljoin, urlsplit

from worker.m1.config import CrawlSettings
from worker.m1.crawl.blocks import waf_challenge_response
from worker.m1.crawl.http import HttpClient
from worker.m1.crawl.throttle import Throttle
from worker.m1.models import RobotsSummary

Rule = tuple[str, str]  # ("allow" | "disallow", pattern)


@dataclass
class ParsedRobots:
    rules: list[Rule]
    crawl_delay: float | None
    sitemaps: list[str]
    group: str  # nhóm User-agent áp dụng: "own" | "*" | "none"


def parse_robots(text: str, ua_token: str) -> ParsedRobots:
    """Parse robots.txt. Trả rule áp cho UA của dự án, crawl-delay, sitemap và nhóm đã chọn.

    Không dùng urllib.robotparser vì nó không hỗ trợ wildcard `*`/`$` và lấy rule khớp đầu tiên
    thay vì rule khớp dài nhất.
    """
    groups: list[tuple[list[str], list[Rule], float | None]] = []
    agents: list[str] = []
    rules: list[Rule] = []
    delay: float | None = None
    sitemaps: list[str] = []
    last_was_agent = False
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = (x.strip() for x in line.split(":", 1))
        key = key.lower()
        if key == "sitemap":
            sitemaps.append(value)
        elif key == "user-agent":
            if not last_was_agent and agents:
                groups.append((agents, rules, delay))
                agents, rules, delay = [], [], None
            agents.append(value.lower())
            last_was_agent = True
            continue
        elif key in ("allow", "disallow") and agents:
            rules.append((key, value))
        elif key == "crawl-delay" and agents:
            try:
                delay = float(value)
            except ValueError:
                pass
        last_was_agent = False
    if agents:
        groups.append((agents, rules, delay))
    mine = [g for g in groups if ua_token in g[0]]
    chosen = mine or [g for g in groups if "*" in g[0]]
    merged_rules = [r for g in chosen for r in g[1]]
    delays = [g[2] for g in chosen if g[2] is not None]
    label = "own" if mine else ("*" if chosen else "none")
    return ParsedRobots(merged_rules, max(delays) if delays else None, sitemaps, label)


def _rule_regex(pattern: str) -> re.Pattern[str]:
    esc = re.escape(pattern).replace(r"\*", ".*")
    if esc.endswith(r"\$"):
        esc = esc[:-2] + "$"
    return re.compile("^" + esc)


def robots_decision(rules: list[Rule], url: str) -> tuple[bool, str]:
    """Rule khớp dài nhất thắng; bằng nhau thì allow thắng. Không rule nào khớp → được phép."""
    p = urlsplit(url)
    target = (p.path or "/") + (f"?{p.query}" if p.query else "")
    hits = [(k, v) for k, v in rules if v and _rule_regex(v).match(target)]
    if not hits:
        return True, "no_match"
    kind, value = max(hits, key=lambda kv: (len(kv[1]), kv[0] == "allow"))
    return kind == "allow", f"{kind}: {value}"


@dataclass
class Robots:
    host: str
    url: str
    status: int | None
    # parsed: đọc luật | allow_all: không có robots.txt (4xx) | unavailable: 5xx/429/timeout, như
    # cấm toàn bộ | waf_challenge: nhận được trang thử thách của WAF thay cho robots.txt
    policy: Literal["parsed", "allow_all", "unavailable", "waf_challenge"]
    fetched_at: str
    sitemaps: list[str] = field(default_factory=list)
    error: str = ""
    timed_out: bool = False
    group: str = ""
    rules: list[Rule] = field(default_factory=list)
    crawl_delay: float | None = None

    def decide(self, url: str) -> tuple[bool, str]:
        if self.policy == "allow_all":
            return True, f"allow_all (robots.txt {self.status})"
        if self.policy in ("unavailable", "waf_challenge"):
            return False, f"{self.policy} (robots.txt {self.status})"
        return robots_decision(self.rules, url)

    def summary(self) -> RobotsSummary:
        return RobotsSummary(
            host=self.host,
            url=self.url,
            status=self.status,
            policy=self.policy,
            group=self.group,
            crawl_delay=self.crawl_delay,
            sitemaps=self.sitemaps,
            fetched_at=self.fetched_at,
            error=self.error,
        )


async def fetch_robots(
    base: str, throttle: Throttle, http: HttpClient, settings: CrawlSettings
) -> Robots:
    """Tải robots.txt bằng UA dự án. Chính sách theo RFC 9309:

    - 2xx: đọc luật và tuân theo.
    - 4xx trừ 429 (kể cả 401/403): không có robots, được crawl.
    - 5xx, 429, timeout, lỗi mạng: coi như cấm toàn bộ (`unavailable`).
    - Trang thử thách của WAF: không nói gì về việc được phép → không crawl (`waf_challenge`).
    """
    url = urljoin(base, "/robots.txt")
    log = await throttle.wait(url, "robots")
    resp = await http.get(url)
    log.status = resp.status
    host = urlsplit(base).netloc
    if challenge := waf_challenge_response(resp):
        return Robots(host, url, resp.status, "waf_challenge", log.fetched_at, error=challenge)
    status = resp.status
    if status is not None and 200 <= status < 300:
        parsed = parse_robots(resp.body.decode("utf-8", errors="replace"), settings.ua_token)
        if parsed.crawl_delay:
            throttle.set_interval(host, parsed.crawl_delay)
        return Robots(
            host,
            url,
            status,
            "parsed",
            log.fetched_at,
            parsed.sitemaps,
            resp.error,
            group=parsed.group,
            rules=parsed.rules,
            crawl_delay=parsed.crawl_delay,
        )
    if status is not None and 400 <= status < 500 and status != 429:
        return Robots(host, url, status, "allow_all", log.fetched_at, error=resp.error)
    return Robots(
        host, url, status, "unavailable", log.fetched_at, error=resp.error, timed_out=resp.timed_out
    )
