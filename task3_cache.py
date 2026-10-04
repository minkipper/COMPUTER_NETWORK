#!/usr/bin/env python3
"""Week 3 · Task 3 — Beat the baseline cache.

Textbook §2.4.2 (caching) and §2.4.3 (TTL).

`BaselineCache` below works. It is also bad, in more than one way, and one of
its problems is worse than being slow. Find them, write `YourCache`, and prove
the improvement with the harness:

    python3 bench.py                 # baseline only
    python3 bench.py --yours         # baseline vs. yours, side by side

Rules
-----
* Do not change `bench.py`. If you need to change it to win, you are not
  winning. Say so in observation.md instead.
* `YourCache` must expose the same two methods as `BaselineCache`.
* Speed is not the only score. The harness also counts **stale answers** -
  times you served a record whose TTL had already run out. A cache that keeps
  everything forever is very fast and completely wrong.

Targets
-------
The baseline scores **325 upstream queries, 67.5% hit rate, 266 stale answers**.

  pass  : zero stale answers
  good  : zero stale, and no more upstream queries than the baseline
  strong: the above, plus you can say in observation.md **how few upstream
          queries a correct cache could possibly make on this workload, and
          why you cannot go below that number**

That last one is the real question. Read it before you start optimising -
it will tell you where to stop.
"""
import time


class BaselineCache:
    """A DNS cache that somebody wrote in a hurry.

    It caches. It is not correct, and it is not fast. Both are your problem.
    """

    FIXED_LIFETIME = 60          # seconds we keep anything, regardless of TTL

    def __init__(self, upstream):
        self.upstream = upstream  # upstream(name) -> (address, ttl)
        self.entries = []         # list of [name, address, stored_at]

    def lookup(self, name, now):
        """Return an address for `name`, asking upstream only if we have to."""
        for entry in self.entries:                      # linear scan
            if entry[0] == name:
                if now - entry[2] < self.FIXED_LIFETIME:
                    return entry[1]
                self.entries.remove(entry)
                break
        address, ttl = self.upstream(name)
        self.entries.append([name, address, now])
        return address

    def stats(self):
        return {"entries": len(self.entries)}


class YourCache:
    """Your cache.

    Same interface: __init__(upstream), lookup(name, now) -> address, stats().
    `upstream(name)` costs a network round trip and returns (address, ttl).
    The TTL is in seconds and it is the authoritative answer's own TTL -
    the baseline throws it away.
    """

    def __init__(self, upstream):
        self.upstream = upstream
        # name을 키로 하고, (address, expires_at) 튜플을 저장하는 딕셔너리
        self.cache = {}

    def lookup(self, name, now):
        """Return an address for `name`, asking upstream only if we have to."""
        # 1. 캐시에 해당 이름이 존재하는지 확인
        if name in self.cache:
            address, expires_at = self.cache[name]
            # 2. 현재 시각(now)이 만료 시각(expires_at) 이전이라면 캐시 Hit! (업스트림 요청 안 함)
            if now < expires_at:
                return address

        # 3. 캐시에 없거나, 만료된 경우 업스트림 호출
        address, ttl = self.upstream(name)
        
        # 4. 업스트림이 알려준 진짜 ttl을 이용해 만료 시각 계산 (저장 시각 + ttl)
        expires_at = now + ttl
        self.cache[name] = (address, expires_at)
        
        return address

    def stats(self):
        return {"entries": len(self.cache)}
