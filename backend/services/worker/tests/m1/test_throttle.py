import asyncio

from tests.m1.fakes import FakeClock
from worker.m1.crawl.throttle import Throttle


def test_cach_nhau_it_nhat_1_giay_moi_host() -> None:
    clock = FakeClock()
    throttle = Throttle(1.0, clock=clock, sleep=clock.sleep)

    async def go() -> None:
        for i in range(5):
            await throttle.wait(f"https://a.com/p{i}", "page")
        await throttle.wait("https://b.com/", "page")  # host khác không phải chờ
        await throttle.wait("https://a.com/robots.txt", "robots")  # robots, sitemap cũng tính

    asyncio.run(go())
    observed = throttle.min_observed_interval()
    assert observed["a.com"] is not None and observed["a.com"] >= 1.0
    assert observed["b.com"] is None  # chỉ 1 request
    assert len(throttle.log) == 7


def test_crawl_delay_lon_hon_1_giay_thi_theo_robots() -> None:
    clock = FakeClock()
    throttle = Throttle(1.0, clock=clock, sleep=clock.sleep)
    throttle.set_interval("a.com", 3.0)
    throttle.set_interval("b.com", 0.2)  # nhỏ hơn mức tối thiểu thì vẫn là 1 giây

    async def go() -> None:
        for _ in range(3):
            await throttle.wait("https://a.com/", "page")
            await throttle.wait("https://b.com/", "page")

    asyncio.run(go())
    observed = throttle.min_observed_interval()
    assert observed["a.com"] is not None and observed["a.com"] >= 3.0
    assert observed["b.com"] is not None and observed["b.com"] >= 1.0
