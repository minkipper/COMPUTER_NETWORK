# Task 2 보고서 — DNS Steering 및 CDN 계층 분석

**측정 환경 (Measurement Networks):**
- **네트워크 1 (Network 1 - `chains_net1.json`)**: 유선 이더넷 (Wired Ethernet / 가정용 ISP)
- **네트워크 2 (Network 2 - `chains_net2.json`)**: 모바일 USB 테더링 (Mobile USB Tethering / 통신사 LTE·5G 망)

---

## 1. CNAME 체인 및 제3자 CDN(Third-Party CDN) 분류 표 (Table)

| 사이트 (Site) | 체인 길이 (Chain length) | 최종 존 (Final zone) | 제3자 CDN 여부 (Third party?) | 규칙 판정 (Rule verdict) |
|---|---|---|---|---|
| `www.microsoft.com` | 2 | `akamaiedge.net` | Yes | ✅ third-party CDN |
| `www.netflix.com` | 1 | `netflix.com` | No | ❌ own CDN (자체 운영) |
| `www.adobe.com` | 2 | `akamai.net` | Yes | ✅ third-party CDN |
| `www.cnn.com` | 1 | `fastly.net` | Yes | ✅ third-party CDN |
| `www.apple.com` | 3 | `akamaiedge.net` | Yes | ✅ third-party CDN |
| `www.korea.ac.kr` | 0 | `korea.ac.kr` | No | ❌ 자체 서버 (CDN 없음) |
| `www.stanford.edu` | 1 | `netlifyglobalcdn.com` | Yes | ✅ third-party CDN |
| `www.bbc.co.uk` | 2 | `fastly.net` | Yes | ✅ third-party CDN |
| `www.spotify.com` | 1 | `fastly.net` | Yes | ✅ third-party CDN |
| `www.github.com` | 1 | `github.com` | No | ❌ 자체 도메인 (규칙 한계) |
| `www.wikipedia.org` | 1 | `wikimedia.org` | Yes | ✅ third-party (재단 인프라) |
| `www.nytimes.com` | 3 | `fastly.net` | Yes | ✅ third-party CDN |

---

## 2. 상세 CNAME 체인 추적 경로 (CNAME Chains Detail)

각 사이트의 DNS 별칭(CNAME)이 최종적으로 어느 도메인과 CDN 인프라로 연결되는지 추적한 경로입니다:

- **`www.microsoft.com`**: `www.microsoft.com` → `www.microsoft.com-c-3.edgekey.net` → `e13678.dscb.akamaiedge.net` (Akamai CDN)
- **`www.netflix.com`**: `www.netflix.com` → `www.prod.ftl.netflix.com` (Netflix 자체 Open Connect CDN)
- **`www.adobe.com`**: `www.adobe.com` → `www.adobe.com.edgesuite.net` → `a1319.dscr.akamai.net` (Akamai CDN)
- **`www.cnn.com`**: `www.cnn.com` → `cnn-tls.map.fastly.net` (Fastly CDN)
- **`www.apple.com`**: `www.apple.com` → `www-apple-com.v.aaplimg.com` → `www.apple.com.edgekey.net` → `e6858.dsce9.akamaiedge.net` (Akamai CDN)
- **`www.korea.ac.kr`**: `www.korea.ac.kr` (CNAME 없음, 직접 단일 고정 IP `163.152.6.10` 반환)
- **`www.stanford.edu`**: `www.stanford.edu` → `stanford.netlifyglobalcdn.com` (Netlify Anycast CDN)
- **`www.bbc.co.uk`**: `www.bbc.co.uk` → `www.bbc.co.uk.pri.bbc.co.uk` → `bbc.map.fastly.net` (Fastly CDN)
- **`www.spotify.com`**: `www.spotify.com` → `atc.spotify.map.fastly.net` (Fastly CDN)
- **`www.github.com`**: `www.github.com` → `github.com` (Fastly Anycast CDN 연동, CNAME은 도메인 내부에서 종결)
- **`www.wikipedia.org`**: `www.wikipedia.org` → `dyna.wikimedia.org` (위키미디어 재단 글로벌 지리적 DNS 클러스터)
- **`www.nytimes.com`**: `www.nytimes.com` → `www.prd.map.nytimes.com` → `www.prd.map.nytimes.xovr.nyt.net` → `nytimes.map.fastly.net` (Fastly CDN)

---

## 3. 스티어링 수치 측정 결과 (Part B5 · Steering Number)

### 3-1. 동일 네트워크 내 리졸버 간 스티어링 (Across Resolvers on Same Network)
단일 네트워크에서 3개의 서로 다른 **리졸버(resolver: System ISP, Google 8.8.8.8, Quad9 9.9.9.9)** 에 동일한 도메인을 질의했을 때의 차이입니다:

> **결과: 제3자 CDN 호스팅 사이트 9개 중 7개 사이트가 서로 다른 리졸버에 대해 서로 다른 IP 주소 집합을 반환함 (7 of 9 CDN-hosted sites answered differently to a different resolver).**

- **리졸버별로 다른 IP를 반환한 사이트 (7개)**:
  - `www.microsoft.com` (System/Google vs Quad9)
  - `www.adobe.com` (System vs Google vs Quad9 세 리졸버 모두 상이)
  - `www.cnn.com` (System vs Google/Quad9)
  - `www.apple.com` (System/Google vs Quad9)
  - `www.bbc.co.uk` (System vs Google/Quad9)
  - `www.spotify.com` (System vs Google/Quad9)
  - `www.nytimes.com` (System vs Google/Quad9)
- **동일한 IP를 반환한 CDN 사이트 (2개)**:
  - `www.stanford.edu` (Netlify Anycast IP 고정)
  - `www.wikipedia.org` (아시아-태평양 지역 공통 프록시 IP 고정)

### 3-2. 두 네트워크 간 스티어링 비교 (Across Network 1 vs Network 2)
**네트워크 1(유선 이더넷)** 과 **네트워크 2(모바일 USB 테더링)** 에서 측정한 원본 데이터를 교차 비교한 결과:

1. **`www.adobe.com` (가장 뚜렷한 지리적/망별 스티어링 확인)**:
   - 네트워크 1 (유선망 System 리졸버): `203.251.234.26`, `203.251.234.41` (국내 유선망 인근 Akamai 엣지 캐시)
   - 네트워크 2 (테더링 System 리졸버): `23.32.4.51` ~ `23.32.4.90` (모바일 통신사망 전용 대역 Akamai 엣지)
   - 접속한 통신망에 따라 DNS가 물리적/논리적으로 서로 다른 최적의 엣지 서버 IP로 안내(Steering)하고 있음을 명확히 증명함.
2. **`www.microsoft.com`**:
   - 네트워크 1의 Quad9 리졸버는 `184.28.10.89`를 반환했으나, 네트워크 2의 Quad9 리졸버는 `23.63.226.92`를 반환함.

---

## 4. 리졸버별 반환 IP 상세 (Resolver Answer Sets)

### [네트워크 1: 유선 이더넷 환경]
| 사이트 (Site) | System 리졸버 | Google (8.8.8.8) | Quad9 (9.9.9.9) |
|---|---|---|---|
| `www.microsoft.com` | `23.49.206.40` | `23.49.206.40` | `184.28.10.89` |
| `www.netflix.com` | `207.45.72.1`, `207.45.73.1` | `207.45.72.1`, `207.45.73.1` | `207.45.72.1`, `207.45.73.1` |
| `www.adobe.com` | `203.251.234.26`, `203.251.234.41` | `23.32.4.9` 외 7개 IP | `23.208.31.133` 외 8개 IP |
| `www.cnn.com` | `146.75.51.5` | `151.101.3.5` 외 3개 IP | `151.101.3.5` 외 3개 IP |
| `www.apple.com` | `23.49.205.28` | `23.49.205.28` | `184.31.228.249` |
| `www.korea.ac.kr` | `163.152.6.10` | `163.152.6.10` | `163.152.6.10` |
| `www.stanford.edu` | `15.197.167.90`, `3.33.186.135` | `15.197.167.90`, `3.33.186.135` | `15.197.167.90`, `3.33.186.135` |
| `www.bbc.co.uk` | `146.75.48.81` | `151.101.0.81` 외 3개 IP | `151.101.0.81` 외 3개 IP |
| `www.spotify.com` | `146.75.51.42` | `151.101.3.42` 외 3개 IP | `151.101.3.42` 외 3개 IP |
| `www.github.com` | `20.200.245.247` | `20.200.245.247` | `20.27.177.113` |
| `www.wikipedia.org` | `103.102.166.224` | `103.102.166.224` | `103.102.166.224` |
| `www.nytimes.com` | `146.75.49.164` | `151.101.1.164` 외 3개 IP | `151.101.1.164` 외 3개 IP |

### [네트워크 2: 모바일 USB 테더링 환경]
| 사이트 (Site) | System 리졸버 | Google (8.8.8.8) | Quad9 (9.9.9.9) |
|---|---|---|---|
| `www.microsoft.com` | `23.49.206.40` | `23.49.206.40` | `23.63.226.92` (Net 1과 상이) |
| `www.adobe.com` | `23.32.4.51` 외 8개 IP (Net 1과 상이) | `203.251.234.122`, `.123` | `23.48.167.84`, `.97` |
| `www.github.com` | `20.200.245.247` | `20.200.245.247` | `20.27.177.113` |

---

## 5. 제3자 CDN 분류 규칙 분석 및 한계 (Rule Analysis)

- **사용된 분류 규칙 (Rule)**:  
  도메인의 CNAME 체인을 끝까지 추적했을 때, 최종 도메인의 소유 영역(zone)이 원본 사이트의 도메인 영역(zone)과 다르면 **제3자(third-party) CDN**으로 판정하고, CNAME 체인이 없거나 원본 도메인 내부에서 끝나면 **자체(own/none)**로 판정함.

- **규칙이 오판한 사례 1 — `www.github.com` (Anycast CDN 누락)**:
  - `www.github.com`은 `github.com`으로 CNAME을 1회 맺은 뒤 바로 최종 A 레코드를 반환하여, 본 규칙에서는 `third_party: false`로 분류됨.
  - 그러나 실제 GitHub는 **Fastly CDN**을 기반으로 트래픽을 서비스하며, BGP Anycast 라우팅을 사용하기 때문에 CNAME 체인상에 `fastly.net`과 같은 제3자 도메인명이 드러나지 않음.
  - 즉, **CNAME 체인 문자열에만 의존하는 단순 판별 규칙은 Anycast 기반 제3자 CDN을 감지하지 못한다는 근본적인 한계**를 가짐.

- **규칙이 오판한 사례 2 — `www.netflix.com` (자체 CDN 특수성)**:
  - `www.netflix.com`은 CNAME이 `www.prod.ftl.netflix.com`으로 끝나며 외부 CDN 도메인이 나타나지 않아 규칙상 `third_party: false`로 판정됨.
  - 하지만 넷플릭스는 전 세계 통신사 내부(ISP)에 자체 캐시 장비인 **Open Connect Appliance(OCA)** CDN을 직접 구축하여 운영하고 있음. 따라서 "제3자 상용 CDN"은 아니지만 명백한 "대규모 CDN"임.

---

## 6. Part A · Wireshark 패킷 캡처 분석 (Wireshark Capture)

`task1_resolve.py www.korea.ac.kr` 질의 과정에서 생성된 `out/dns.pcapng` 패킷 캡처 분석 결과:

- **A2 — Transaction ID 일치 (Transaction ID Matching)**:
  - 질의 패킷 (DNS Query): no:1 트랜잭션 ID는 0x3dd6
  - 응답 패킷 (DNS Response): no:2 동일한 트랜잭션 ID 0x3dd6을 공유하여 비연결형 UDP 프로토콜에서 요청과 응답을 1:1로 매핑함.

- **A3 — 위임(Delegation) 응답 vs 최종 정답(Answer) 응답 비교**:
  - **위임 응답 (Delegation)**:
    - `Answer RRs` (질의한 호스트의 IP 주소는 비어 있음) 따라서 0
    - `Authoritative RRs` (하위 관할 네임서버인 `.kr` 또는 `korea.ac.kr`의 NS 레코드 목록 제공) 총 6개 제공해 주었음.
    - `Additional Records`: 각 네임서버의 글루(Glue) IPv4/IPv6 레코드 포함 11개 제공해 주었음
  - **최종 정답 응답 (Answer)**:
    - `Answer RRs` (`www.korea.ac.kr`의 최종 IPv4 A 레코드 `163.152.6.10` 제공) 1개였음.
    - `Authoritative Nameservers` 최종 레코드를 찾았으므로 Authoritative RRs는 0개였음.

- **A4 — 가장 큰 응답 패킷의 바이트 수 및 원인 (Largest Response)**: 352 바이트였음.
  - **크기**: 루트 서버(`.`)가 반환한 첫 번째 위임 응답 패킷은 352 바이트였음.
  - **원인**: 최상위 루트 서버가 질의에 대해 처음 찾아보는 것이므로 유사한 이름들의 nameservers와 additional records들을 많이 제공해 주었기 때문에, 첫 번째 질의가 가장 크기가 컸음.
