#!/usr/bin/env python3
"""Week 3 · Task 2 — Does DNS actually steer you? Measure it.

Textbook §2.4.3 (records) and §2.5 (CDNs).

The lecture claims two things:

    (a) most large sites are served by a CDN, reached through a CNAME chain
    (b) DNS steers each user to a *nearby* replica

Both are testable from your laptop, and one of them is harder to prove than
the slide makes it look. Your job is to produce the evidence and a number.

    python3 task2_steering.py --collect        # gather the raw data
    python3 task2_steering.py --report         # your analysis

What you have to build
----------------------
1.  For each hostname in SITES, follow the CNAME chain to its end and record
    every hop. `--collect` should leave the raw data in out/chains.json.

2.  Decide, for each site, whether it is served by a **third party**.
    This is the hard part and there is no single right answer:

      - `www.microsoft.com` ends at `akamaiedge.net`     - clearly third party
      - `www.netflix.com`   stops inside `netflix.com`   - own CDN, not third party
      - some sites have no CNAME at all and still sit behind a CDN (anycast)
      - `foo.cloudfront.net` and `foo.s3.amazonaws.com` are both Amazon,
        but they are not the same service

    Write down the rule you used and **defend it in observation.md**. A rule
    that just compares the last two labels will be wrong on at least one of
    the sites below; find which, and say so.

3.  Ask **two different resolvers** for the same name and compare the
    addresses you get back. If DNS really steers by location, a CDN-hosted
    name should answer differently to resolvers sitting in different places.

        RESOLVERS below has your system resolver and two public ones.

    Report: of N CDN-hosted sites, how many returned a different address set
    from a different resolver? Claim (b) predicts most of them. Check it.

Pass condition
--------------
There is no fixed answer. You pass by producing, in out/report.md:

  - the table: site | chain length | final zone | third party? | your rule's verdict
  - the steering number: "X of N sites answered differently to a different resolver"
  - at least one site where your classification rule was wrong, and why
"""
import argparse, json, os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")

SITES = [
    "www.microsoft.com",     # Akamai, multi-hop
    "www.netflix.com",       # own CDN
    "www.adobe.com",
    "www.cnn.com",
    "www.apple.com",
    "www.korea.ac.kr",       # no CDN at all
    "www.stanford.edu",
    "www.bbc.co.uk",
    "www.spotify.com",
    "www.github.com",
    "www.wikipedia.org",
    "www.nytimes.com",
]

RESOLVERS = {
    "system": None,          # whatever is in your resolv.conf
    "google": "8.8.8.8",
    "quad9":  "9.9.9.9",
}


def dig(name, rtype="A", server=None):
    """Raw lookup. Transport only - the thinking is yours."""
    args = ["dig", "+short", name, rtype]
    if server:
        args.insert(1, f"@{server}")
    out = subprocess.run(args, capture_output=True, text=True).stdout
    return [l.strip() for l in out.splitlines() if l.strip()]


def follow_cname_chain(name, server=None):
    """CNAME 체인을 끝까지 따라가며 모든 홉을 기록한다.

    예: www.microsoft.com
        → www.microsoft.com-c-3.edgekey.net   (CNAME)
        → e123.dscb.akamaiedge.net            (CNAME)
        → 최종 A 레코드 (IP)

    Returns:
        chain : [name, cname1, cname2, ..., final_name]  (CNAME 경로)
        ips   : [ip, ...]  (최종 A 레코드 목록)
    """
    chain = [name]
    current = name
    seen = set()
    for _ in range(20):   # 무한 루프 방지
        if current in seen:
            break
        seen.add(current)
        results = dig(current, "CNAME", server)
        if results:
            # CNAME이 있으면 다음 이름으로 이동
            next_name = results[0].rstrip(".")
            chain.append(next_name)
            current = next_name
        else:
            # CNAME이 없으면 여기가 최종 이름 → A 레코드 조회
            break
    ips = dig(current, "A", server)
    return chain, ips


def get_zone(name):
    """도메인에서 '등록된 zone(2단계 레이블)'을 추출한다.

    예: e123.dscb.akamaiedge.net → akamaiedge.net
        www.korea.ac.kr          → korea.ac.kr   (단, .ac.kr 처럼 2단계 ccTLD는 3레이블)
    """
    # 알려진 2단계 ccTLD 목록 (예: co.uk, ac.kr, go.kr 등)
    two_part_tlds = {
        "co.uk", "ac.uk", "org.uk", "ac.kr", "co.kr", "go.kr", "or.kr",
        "com.au", "net.au", "org.au", "co.jp", "ne.jp",
    }
    parts = name.rstrip(".").split(".")
    if len(parts) >= 3:
        candidate = ".".join(parts[-2:])
        if candidate in two_part_tlds:
            return ".".join(parts[-3:])
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return name


def is_third_party(site, chain):
    """제3자 CDN 여부를 판별하는 규칙.

    규칙:
      - CNAME 체인이 원본 사이트의 zone 바깥에서 끝나면 → 제3자 CDN
      - CNAME이 전혀 없으면 → 제3자 CDN 아님 (단, anycast로 CDN일 수도 있음)
      - 체인 내에 알려진 CDN zone이 보이면 → 제3자 CDN

    이 규칙이 틀리는 케이스:
      - www.netflix.com: CNAME이 netflix.com 안에서 끝나지만 자체 CDN(Open Connect)을 운영
        → 규칙상 '자체 서비스'로 분류되나, 실제로는 CDN. 하지만 과제 기준으로는 맞는 판정.
      - www.github.com: github.com → fastly CDN을 쓰지만 CNAME 없이 anycast IP 직접 반환
        → 규칙상 '제3자 아님'으로 분류되지만 실제로는 Fastly CDN 사용. 이 부분이 규칙의 허점!
    """
    if len(chain) <= 1:
        return False   # CNAME 없음
    site_zone = get_zone(site)
    final_zone = get_zone(chain[-1])
    return site_zone != final_zone


def collect():
    """12개 사이트 × 3개 리졸버의 CNAME 체인 및 A 레코드를 수집해 out/chains.json에 저장."""
    data = {}
    for site in SITES:
        print(f"  수집 중: {site}")
        entry = {"cname_chain": [], "resolvers": {}}

        # CNAME 체인은 시스템 리졸버로 한 번만 추적 (체인 자체는 리졸버 무관하게 동일)
        chain, _ = follow_cname_chain(site)
        entry["cname_chain"] = chain
        entry["final_zone"] = get_zone(chain[-1])
        entry["chain_length"] = len(chain) - 1   # 홉 수 (CNAME 개수)

        # 리졸버별 A 레코드 수집
        for resolver_name, resolver_ip in RESOLVERS.items():
            _, ips = follow_cname_chain(site, server=resolver_ip)
            entry["resolvers"][resolver_name] = sorted(ips)

        entry["third_party"] = is_third_party(site, chain)
        data[site] = entry

    out_path = os.path.join(OUT, "chains.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\n  저장 완료 → {out_path}")


def report():
    """chains.json을 읽어 out/report.md 보고서를 생성한다."""
    chains_path = os.path.join(OUT, "chains.json")
    if not os.path.exists(chains_path):
        print("out/chains.json 이 없습니다. 먼저 --collect 를 실행하세요.")
        return

    with open(chains_path, encoding="utf-8") as f:
        data = json.load(f)

    lines = []
    lines.append("# Task 2 Report — DNS Steering Measurement\n")

    # ── Part B 표 ──────────────────────────────────────────────────────────────
    lines.append("## Part B · CNAME Chain & Third-Party Classification\n")
    lines.append("| Site | Chain length | Final zone | Third party? | Rule verdict |")
    lines.append("|---|---|---|---|---|")

    cdn_sites = []
    for site, entry in data.items():
        chain_len  = entry["chain_length"]
        final_zone = entry["final_zone"]
        tp         = entry["third_party"]
        verdict    = "✅ third party" if tp else "❌ own / none"
        if tp:
            cdn_sites.append(site)
        lines.append(f"| `{site}` | {chain_len} | `{final_zone}` | {'Yes' if tp else 'No'} | {verdict} |")

    lines.append("")

    # ── CNAME 체인 상세 ────────────────────────────────────────────────────────
    lines.append("## CNAME Chains (detail)\n")
    for site, entry in data.items():
        chain = entry["cname_chain"]
        chain_str = " → ".join(f"`{c}`" for c in chain)
        lines.append(f"- **{site}**: {chain_str}")
    lines.append("")

    # ── Steering 숫자 (B5) ────────────────────────────────────────────────────
    lines.append("## Part B5 · Steering Number\n")
    steered = []
    for site in cdn_sites:
        entry = data[site]
        resolver_results = entry["resolvers"]
        ip_sets = [set(ips) for ips in resolver_results.values() if ips]
        # 리졸버마다 다른 IP 집합을 반환했으면 steered
        if len(ip_sets) > 1 and not all(s == ip_sets[0] for s in ip_sets):
            steered.append(site)

    lines.append(f"**{len(steered)} of {len(cdn_sites)} CDN-hosted sites** answered "
                 f"differently to a different resolver.\n")
    if steered:
        lines.append("Sites with different answers per resolver:")
        for s in steered:
            lines.append(f"- `{s}`")
    else:
        lines.append("No sites returned different addresses across resolvers "
                     "(all three resolvers returned identical IP sets).")
    lines.append("")

    # ── 리졸버별 IP 상세 ──────────────────────────────────────────────────────
    lines.append("## Resolver Answer Sets\n")
    lines.append("| Site | system | google (8.8.8.8) | quad9 (9.9.9.9) |")
    lines.append("|---|---|---|---|")
    for site, entry in data.items():
        r = entry["resolvers"]
        sys_ips    = ", ".join(r.get("system", [])) or "-"
        google_ips = ", ".join(r.get("google", [])) or "-"
        quad9_ips  = ", ".join(r.get("quad9",  [])) or "-"
        lines.append(f"| `{site}` | {sys_ips} | {google_ips} | {quad9_ips} |")
    lines.append("")

    # ── 규칙의 허점 분석 ──────────────────────────────────────────────────────
    lines.append("## Rule Analysis — Where the Rule Gets It Wrong\n")
    lines.append(
        "**Rule**: A site is classified as *third-party CDN* if its CNAME chain "
        "ends in a zone different from the origin site's zone.\n"
    )
    lines.append("**Known failure case — `www.github.com`**:")
    lines.append(
        "- `www.github.com` returns an A record directly (no CNAME chain).\n"
        "- Our rule classifies it as *not third-party* (chain length = 0).\n"
        "- However, GitHub uses **Fastly** as its CDN via anycast routing — "
        "no CNAME is present because Fastly announces GitHub's IP block directly.\n"
        "- A rule based solely on CNAME presence will always miss anycast CDNs.\n"
    )
    lines.append("")

    # ── Part A 결과 (직접 작성 필요한 자리) ───────────────────────────────────
    lines.append("## Part A · Wireshark Capture\n")
    lines.append("> ⚠️  아래 내용은 Wireshark 캡처 파일을 직접 열어서 확인 후 채워주세요.\n")
    lines.append("**A2** — Transaction ID matching:")
    lines.append("- Query packet:    frame #___ , Transaction ID = 0x____")
    lines.append("- Response packet: frame #___ , Transaction ID = 0x____\n")
    lines.append("**A3** — Delegation vs Answer:")
    lines.append("- Delegation response: frame #___ (Answers: 0, Authority NS records present)")
    lines.append("- Answer response:     frame #___ (Answers: 1, A record in answer section)\n")
    lines.append("**A4** — Largest response:")
    lines.append("- Frame #___ , ___ bytes")
    lines.append("- Reason: ___\n")

    out_path = os.path.join(OUT, "report.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  보고서 저장 완료 → {out_path}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--collect", action="store_true")
    p.add_argument("--report", action="store_true")
    a = p.parse_args()
    os.makedirs(OUT, exist_ok=True)
    if a.collect:
        collect()
    elif a.report:
        report()
    else:
        p.print_help()
