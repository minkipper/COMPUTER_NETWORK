# 6주차 실습 관찰 보고서 (Week 6 Lab Observations)

## Task 1 · 수동 링크 상태 라우팅 및 포워딩 테이블 (Link State by Hand)
1. **동일 비용 최단 경로(Equal-Cost Paths) 발생 시 Tie-Breaking 규칙과 실제 라우터의 동작**:
   - 구현한 [`forwarding_table()`](file:///C:/Users/minki/OneDrive/Desktop/%EC%BB%B4%ED%93%A8%ED%84%B0%EB%84%A4%ED%8A%B8%EC%9B%8C%ED%81%AC_%EA%B3%BC%EC%A0%9C/2026-lecture-network-practice-main/w06-routing/task1_linkstate.py#L62-L95)에서는 우선순위 큐(`heapq`)의 비교 키를 `(cost, first_hop, node)` 튜플로 구성하여, 동일한 최단 비용을 가진 두 경로가 경합할 때 **사전순(Lexicographical order)으로 가장 앞서는 첫 번째 홉(`first_hop`)을 결정론적으로 선택**하도록 설계했습니다.
   - 반면 실제 OSPF 라우터는 단일 인터페이스로만 트래픽을 고정(Pinning)하지 않고, 동점인 여러 다음 홉을 포워딩 테이블(FIB)에 모두 설치하는 **ECMP(Equal-Cost Multi-Path)** 라우팅을 수행합니다(Task 2의 FRR 라우팅 테이블에서도 2개의 `via` 엔트리가 동시에 설치됨을 확인). 이때 패킷 단위로 경로를 교차하면 TCP 세그먼트 순서 역전(Out-of-order delivery)이 발생하므로, 실제 라우터는 패킷의 **5-튜플(출발지/목적지 IP, 출발지/목적지 포트, 프로토콜)을 해싱**하여 동일한 플로우(Flow)는 같은 홉으로 보내고 전체 트래픽은 여러 링크로 분산합니다.
2. **노드 `u`에서 목적지 `w`로 가는 다음 홉(`first_hop`)이 `w`가 아닌 이유**:
   - `u`와 `w` 사이에 직접 연결된 인접 링크 `u-w`가 존재하지만 그 링크 비용은 `5`인 반면, `x`와 `y`를 경유하는 우회 경로 `u -> x -> y -> w`의 누적 비용은 `1 + 1 + 1 = 3`으로 더 저렴합니다.
   - 링크 상태 라우팅(Dijkstra)은 단순 인접성(Adjacency)이나 홉 수가 아니라 **경로 비용의 총합이 최소인 최단 경로**를 선택하므로, `u`는 목적지 `w`로 가는 패킷을 직접 링크 `w`가 아닌 최단 경로상의 첫 번째 인접 이웃인 **`x`** 인터페이스로 내보냅니다.
3. **`u-x` 링크 단절 후 다음 홉이 변경된 목적지와 유지된 목적지**:
   - **변경되지 않은 목적지**: **`v`** (기존에도 직접 링크 `u-v`의 비용이 `2`로 최단이었으므로 단절 후에도 다음 홉 `v`를 그대로 유지).
   - **변경된 목적지**: **`w`, `x`, `y`, `z` 4개 모두 `x`에서 `v`로 변경**되었습니다. `u-x` 링크가 끊어지면서 기존에 `x`를 첫 홉으로 경유하던 모든 최단 경로가 무효화되었고, `x`(비용 4: `u-v-x`), `y`(비용 5: `u-v-x-y`), `z`(비용 7: `u-v-x-y-z`)는 모두 `v`를 경유하도록 우회했습니다. 특히 목적지 `w`는 `u-w` 직접 경로(비용 5)와 `u-v-w` 경유 경로(비용 `2 + 3 = 5`)가 동점을 이루었으나, 앞서 정의한 사전순 Tie-breaking 규칙(`'v' < 'w'`)에 따라 다음 홉이 `v`로 결정되었습니다.

---

## Task 2 · 실제 네트워크 경로 추적 및 OSPF 재수렴 측정 (Break a Real Network and Time the Repair)

### Part A · 외부 라우팅 경로 추적 (`out/traceroute.txt`)
1. **A2 — 국내 경로(`www.korea.ac.kr`, `163.152.6.10`)가 로컬/캠퍼스 망을 빠져나가는 홉**:
   - Hop 1(`172.18.48.1`, WSL2 Hyper-V 가상 게이트웨이, `0.21 ms`)과 Hop 2(`192.168.0.1`, 로컬 공유기 게이트웨이, `0.66 ms`)를 거쳐, **Hop 3(`39.127.58.1`, `9.90 ms`)**에서 로컬 사설망을 빠져나가 외부 ISP(LG U+ 가입자 집선 라우터) 공인망으로 진입합니다. 이후 ISP 내부 백본 홉(Hop 4 `180.67.119.241` ~ Hop 8 `110.9.3.41`)을 거쳐 Hop 9(`163.152.4.140`, `5.69 ms`)에서 고려대학교 경계 라우터로 진입한 뒤 Hop 10(`www.korea.ac.kr`, `163.152.6.10`, `5.83 ms`)에 도달합니다.
2. **A3 — 해외 경로(`www.stanford.edu` / `cs.stanford.edu`)가 바다(태평양)를 건너는 구간과 해저 케이블**:
   - 기본 `www.stanford.edu`(`15.197.167.90` / `3.33.186.135`)는 현재 AWS Global Accelerator(Anycast CDN) 뒤에 호스팅되어 있어 서울 리전 엣지(Hop 15 `afa7f374f51cc8991.awsglobalaccelerator.com`, `4.17 ms`)에서 종단되었고, 실제 미국 캘리포니아 스탠퍼드 캠퍼스에 위치한 `cs.stanford.edu`(`171.64.64.64`)를 추적하여 태평양 횡단 구간을 관측했습니다.
   - **태평양 횡단 홉**: **Hop 9(`as6939.equinix-hong-kong.core2.hkg2.he.net`, `36.255.56.8`, 지연시간 `41.0 ms` / 동경 `core1.tyo1.he.net`)에서 Hop 10(`100ge0-0-0-30.core2.sjc2.he.net`, `184.104.194.37`, 지연시간 `146.9 ms`)**으로 넘어가는 단일 홉에서 RTT가 **`41.0 ms` $\rightarrow$ `146.9 ms`로 약 `+105.9 ms` 급증**합니다. 이후 Hop 11(`be10.core1.pao1.he.net`, 팔로알토, `149.4 ms`)을 거쳐 스탠퍼드 캠퍼스(`171.64.64.64`, `146.5 ms`)에 도착합니다.
   - **시사하는 해저 케이블**: 호스트 네임의 도시 코드(`hkg2`/`tyo1` $\rightarrow$ `sjc2`/`pao1`)와 약 `106 ms`의 광섬유 전파 지연(왕복 약 18,000~20,000 km)을 통해, Hurricane Electric(AS6939) 백본이 운용하는 동아시아(도쿄/홍콩) $\leftrightarrow$ 미국 서부(산호세/로스앤젤레스) 간 **태평양 횡단 해저 광케이블(FASTER, Jupiter, 또는 Unity/PLCN 해저 케이블 시스템)**을 통과했음을 알 수 있습니다.
3. **A4 — Anycast 주소(`1.1.1.1`)의 홉 수와 레플리카(Replica) 위치**:
   - 총 **13홉** 만에 도달했으며, 최종 RTT는 약 **`5.8 ~ 6.5 ms`**에 불과합니다(Hop 8 `39.120.253.58` $\rightarrow$ Hop 9~10 `211.45.68.x` $\rightarrow$ Hop 11 `211.56.189.126` $\rightarrow$ Hop 12 `141.101.82.9` $\rightarrow$ Hop 13 `one.one.one.one`).
   - 빛의 광섬유 내 전파 속도(약 $200\text{ km/ms}$)를 고려할 때 왕복 `6 ms`의 지연시간은 물리적 거리가 수백 km 이내임을 의미하므로, BGP Anycast 라우팅이 전 세계에서 가장 가까운 **대한민국 서울(ICN) 소재 Cloudflare 로컬 엣지 데이터센터 레플리카**로 패킷을 안내했음을 보여줍니다.
4. **A5 — 일부 홉에서 `* * *`가 출력되는 서로 다른 두 가지 원인과 차이점**:
   - **① 중간 경유 라우터의 Control-Plane ICMP Rate-Limiting / 무응답 설정** (예: `1.1.1.1`의 Hop 11 일부, `cs.stanford.edu`의 Hop 3~5 및 Hop 7): 라우터의 하드웨어 데이터 평면(ASIC)은 TTL이 남아 있는 일반 패킷을 정상적으로 다음 홉으로 포워딩하지만, 라우터 CPU(제어 평면)를 보호하기 위해 `TTL=0` 만료 패킷에 대한 `ICMP Time Exceeded` 응답 생성을 제한하거나 차단하는 경우입니다. 이 경우 **이후 홉들에서는 다시 정상적으로 응답이 출력**됩니다.
   - **② 목적지 경계 방화벽(Firewall) 또는 보안 장비의 프로브 프로토콜 차단** (예: 기본 UDP `traceroute` 시 Hop 9 이후 끝까지 `* * *`가 연속되는 현상): 리눅스 기본 `traceroute`가 사용하는 높은 번호의 UDP 포트(`33434+`) 패킷을 방화벽이 비정상 트래픽으로 간주하여 폐기(Drop)하기 때문에 이후 모든 홉에서 응답이 오지 않는 문제입니다. 실제로 동일한 목적지에 대해 웹 트래픽 포트인 `TCP 443`(`traceroute -T -p 443`)이나 ICMP Echo(`-I`)를 사용하면 방화벽을 통과해 최종 목적지까지 정상 응답을 확인할 수 있습니다.

---

### Part B & C · OSPF 재수렴 시간 측정 및 비교 (`out/route-before.txt`, `out/route-after.txt`, `out/reconverge.txt`)
1. **B2 — 직접 연결되지 않은 원격 서브넷 학습 확인**:
   - 삼각형 토폴로지(`net_a: 172.21.0.0/16 [r1-r3]`, `net_b: 172.19.0.0/16 [r1-r2]`, `net_c: 172.20.0.0/16 [r2-r3]`)가 완전 수렴한 후 [`out/route-before.txt`](file:///C:/Users/minki/OneDrive/Desktop/%EC%BB%B4%ED%93%A8%ED%84%B0%EB%84%A4%ED%8A%B8%EC%9B%8C%ED%81%AC_%EA%B3%BC%EC%A0%9C/2026-lecture-network-practice-main/w06-routing/out/route-before.txt)를 확인한 결과, 세 라우터 모두 자신과 직접 연결되지 않은 건너편 링크를 비용 `20`(`10 + 10`)의 OSPF 경로(`O>*`) 및 2개의 ECMP 다음 홉으로 정확히 학습했습니다:
     - `r1`: 직접 연결 없는 `172.20.0.0/16`(`r2-r3`)을 `[110/20] via 172.19.0.3 (eth1)` 및 `via 172.21.0.3 (eth0)`으로 학습
     - `r2`: 직접 연결 없는 `172.21.0.0/16`(`r1-r3`)을 `[110/20] via 172.19.0.2 (eth1)` 및 `via 172.20.0.2 (eth0)`으로 학습
     - `r3`: 직접 연결 없는 `172.19.0.0/16`(`r1-r2`)을 `[110/20] via 172.20.0.3 (eth0)` 및 `via 172.21.0.2 (eth1)`으로 학습
2. **B4 — 링크 단절(`cut`) 시 측정된 재수렴 시간과 설정 파일(`frr.conf`)의 Hello/Dead Interval 정합성**:
   - [`topology/r1/frr.conf`](file:///C:/Users/minki/OneDrive/Desktop/%EC%BB%B4%ED%93%A8%ED%84%B0%EB%84%A4%ED%8A%B8%EC%9B%8C%ED%81%AC_%EA%B3%BC%EC%A0%9C/2026-lecture-network-practice-main/w06-routing/topology/r1/frr.conf)는 `frr defaults traditional`을 사용하며 별도의 타이머 오버라이드가 없으므로, OSPF 브로드캐스트 네트워크 표준 기본값인 **`Hello Interval = 10s`, `Dead Interval = 40s`, `Wait Timer = 40s`**가 적용됩니다(`vtysh -c "show ip ospf interface eth1"` 출력으로 확인).
   - `r1`에서 `ip link set eth1 down`을 실행했을 때 두 가지 계층의 감지가 일어납니다:
     - **로컬 커널 이벤트 및 우회 LSA 플러딩 (약 `2초` 소요)**: 인터페이스가 내려간 당사자인 `r1`은 리눅스 커널(Netlink)로부터 즉시 `eth1 down` 알림을 받아 자신의 `172.19.0.0/16` 직접 연결을 해제하고(`[110/10]` $\rightarrow$ `[110/30] via 172.21.0.3, eth0`), 살아있는 `r3`(`eth0`) 쪽으로 갱신된 Type-1 Router-LSA를 즉시 플러딩합니다. 그 결과 SPF의 양방향 연결성 검사(Two-Way Check)에 의해 `r2`와 `r3`도 약 `2초` 만에 `r1-r2` 경유 ECMP 다음 홉을 테이블에서 제거합니다([`out/route-after.txt`](file:///C:/Users/minki/OneDrive/Desktop/%EC%BB%B4%ED%93%A8%ED%84%B0%EB%84%A4%ED%8A%B8%EC%9B%8C%ED%81%AC_%EA%B3%BC%EC%A0%9C/2026-lecture-network-practice-main/w06-routing/out/route-after.txt)).
     - **OSPF Dead Interval 만료에 의한 인접성 해제 (약 `31 ~ 40초` 소요)**: 반면 Docker 브리지(`net_b`)에 연결된 상대편 `r2`의 `eth0` 인터페이스는 물리적 캐리어(Link Carrier)가 여전히 `UP` 상태이므로, `r2`의 인접 이웃 테이블(`show ip ospf neighbor`)에서 `1.1.1.1`(`r1`)이 완전히 사라지기까지는 마지막 Hello 수신 시점으로부터 **`Dead Interval`인 `40초`(실측 잔여 타이머 약 `31~40초`)**가 만료될 때까지 기다려야 합니다. 만약 우회 경로가 없거나 스위치 너머에서 패킷만 유실되는 Silent Failure가 발생하면 네트워크는 이 **30~40초 동안 완전히 단절(Black-hole)**됩니다.
3. **B5 — 링크 복구(`restore`)와 링크 단절(`cut`)의 재수렴 시간이 비대칭인 이유**:
   - **단절(Going down)**은 "이웃으로부터 메시지가 오지 않음(Absence of Hellos)"을 통해 감지해야 하므로, 일시적인 패킷 손실로 인해 라우팅 테이블이 출렁이는(Flapping) 것을 막기 위해 Hello 주기의 4배인 **Dead Interval(40초)** 동안 기다리는 보수적인 타임아웃 메커니즘을 따릅니다.
   - 반면 **복구(Coming back up)**는 "메시지의 도착(Presence of Hellos)"이라는 명시적 사건으로 시작됩니다. 인터페이스가 `up`되면 즉시 Hello 패킷을 주고받아 이웃을 발견하고 Database Description(DBD) 및 LSA 교환(`ExStart` $\rightarrow$ `Exchange` $\rightarrow$ `Loading` $\rightarrow$ `Full`)을 능동적으로 수행하므로 Dead Timer를 기다릴 필요가 없습니다(단, 브로드캐스트 세그먼트에서 기존 DR/BDR이 모두 없는 초기 기동 시에는 DR 선출을 위한 `Wait Timer 40초`가 소요되어 초기 수렴에 약 25~30초가 걸립니다).
4. **C3 — 링크 비용 변경(`cost`: `10` $\rightarrow$ `100`)이 링크 단절보다 훨씬 빠른 이유**:
   - `r1`의 `eth0`(`net_a`) 비용을 `10`에서 `100`으로 올렸을 때, `r1`의 라우팅 테이블은 `172.21.0.0/16` 경로를 직접 연결(`eth0`, 비용 100) 대신 `r2-r3` 우회 경로(`[110/30] via 172.19.0.3, eth1`)로 바꾸고 `172.20.0.0/16`의 `eth0` ECMP 경로를 제거하는 데 단 **`708 ms` (1초 미만)**밖에 걸리지 않았습니다.
   - **이유**: 링크 장애는 먼저 **"고장이 났다는 사실 자체를 감지(Failure Detection, 수십 초의 Dead Interval)"**해야 하지만, 비용 변경은 이미 `Full` 인접성이 맺어진 상태에서 관리자가 설정을 바꾸는 즉시 라우터가 새로운 Type-1 Router-LSA를 생성하여 인접 라우터로 **플러딩(Flooding)하고 SPF만 재실행**하면 되기 때문에 네트워크 전파 지연과 SPF 연산 시간(수백 ms)만 소요됩니다.

---

## Task 3 · 전체 재계산 없는 빠른 재수렴 구현 (Reconverge Without Recomputing the World)
1. **이벤트 사이에 추가로 유지하는 상태 정보와 메모리 비용**:
   - [`YourRouter`](file:///C:/Users/minki/OneDrive/Desktop/%EC%BB%B4%ED%93%A8%ED%84%B0%EB%84%A4%ED%8A%B8%EC%9B%8C%ED%81%AC_%EA%B3%BC%EC%A0%9C/2026-lecture-network-practice-main/w06-routing/task3_reconverge.py#L75-L216)는 기본 그래프(`self.graph`)와 포워딩 테이블(`self.table`) 외에, 현재의 **최단 경로 트리(Shortest-Path Tree, SPT)** 상태를 나타내는 세 가지 딕셔너리를 유지합니다:
     1. `self.dist` (`{node: cost}`): 출발 라우터(`source`)로부터 각 노드까지의 최단 경로 비용
     2. `self.parent` (`{node: parent_node}`): SPT 상에서 각 노드의 직전 부모 노드 (어떤 링크가 현재 SPT에 사용 중인지 $\mathcal{O}(1)$에 판별)
     3. `self.children` (`{node: set_of_children}`): SPT 상에서 각 노드의 자식 노드 집합 (특정 노드가 SPT의 리프(Leaf) 노드인지 $\mathcal{O}(1)$에 판별)
   - **메모리 비용**: 세 자료구조 모두 라우터(노드) 개수 $V$에 대해 노드당 딱 1개의 항목만 저장하고(`children`의 모든 집합 원소 합도 트리 간선 수인 $V-1$개), 간선 수 $E$에는 비례하지 않으므로 추가 메모리 복잡도는 **$\mathcal{O}(V)$**입니다. 400개 라우터 기준 약 1,200개의 딕셔너리 엔트리(수십 KB 미만)라는 극소량의 메모리만 소비합니다.
2. **세 가지 링크 이벤트 케이스 처리 방식과 전체 SPF를 강제하는 경우**:
   - **① 링크 단절(`cost=None`) 또는 비용 증가(`cost > old_cost`)**: 해당 링크 `(a, b)`가 현재 SPT에 속해 있지 않다면(`parent[a] != b` 이고 `parent[b] != a`), 사용하지도 않던 간선이 사라지거나 비싸진 것이므로 최단 경로 트리는 절대 변하지 않습니다(즉시 무시). 만약 SPT 간선이지만 자식 노드가 **리프(Leaf) 노드**(`children[child]`가 비어 있음)라면 다른 어떤 노드도 이 노드를 경유하지 않으므로, 해당 리프 노드의 인접 이웃들만 $\mathcal{O}(\text{deg}(v))$로 스캔하여 새 부모와 최단 거리를 국소 갱신하고 전체 SPF를 생략합니다.
   - **② 비-SPT 링크 활성화(`up`) 또는 비용 감소(`cost < old_cost`)**: 두 끝점 중 출발지에 더 가까운 쪽을 `u`, 먼 쪽을 `v`라 할 때, 새로 단축된 우회 비용 `dist[u] + cost`가 기존 최단 거리 `dist[v]`보다 크다면(`du + cost > dv`, 혹은 동점이더라도 기존 부모의 우선순위가 더 높다면) 더 짧은 경로를 만들지 못하므로 전체 SPF 없이 즉시 무시합니다. 만약 `du + cost <= dv`로 `v`의 경로가 개선되더라도 `v`가 리프 노드이고 개선된 거리 `cand_dist + w`가 `v`의 다른 어떤 이웃의 기존 최단 거리도 단축시키지 못한다면 `v` 하나만 국소 갱신하고 SPF를 생략합니다.
   - **③ 여전히 전체 SPF(`_recompute()`)를 강제하는 이벤트**:
     - 자식을 거느린 **SPT 내부 간선(Internal Tree Edge, Non-leaf)**이 끊어지거나 비용이 증가하여 하위 서브트리 전체의 경로를 재탐색해야 할 때
     - 링크 비용 감소(또는 신규 링크 연결)로 인해 단축된 거리가 단일 리프 노드에 그치지 않고 **주변 이웃 노드들로 연쇄 전파(`cand_dist + w <= dist[nbr]`)**될 때
   - 이를 통해 1,000번의 이벤트 모두에서 정확도 100%(`wrong after 0 event(s)`)를 유지하면서 전체 SPF 횟수를 **1,001회에서 178회로 82% 절감(`strong` 등급)**했습니다([`out/bench.txt`](file:///C:/Users/minki/OneDrive/Desktop/%EC%BB%B4%ED%93%A8%ED%84%B0%EB%84%A4%ED%8A%B8%EC%9B%8C%ED%81%AC_%EA%B3%BC%EC%A0%9C/2026-lecture-network-practice-main/w06-routing/out/bench.txt)).
3. **R5 — Python 실행 시간(Wall time)은 Baseline보다 약간 느림에도 실제 라우터에서 이 방식이 올바른 선택인 이유**:
   - **Python에서 Wall time이 더 걸린 이유 (`0.89s` vs `0.65s`)**: 과제 규격(R2)상 수정할 수 없는 채점용 [`dijkstra_table()`](file:///C:/Users/minki/OneDrive/Desktop/%EC%BB%B4%ED%93%A8%ED%84%B0%EB%84%A4%ED%8A%B8%EC%9B%8C%ED%81%AC_%EA%B3%BC%EC%A0%9C/2026-lecture-network-practice-main/w06-routing/task3_reconverge.py#L30-L53)은 오직 `{dest: first_hop}`만 반환하고 `dist`와 `parent`를 반환하지 않기 때문에, [`YourRouter._recompute()`](file:///C:/Users/minki/OneDrive/Desktop/%EC%BB%B4%ED%93%A8%ED%84%B0%EB%84%A4%ED%8A%B8%EC%9B%8C%ED%81%AC_%EA%B3%BC%EC%A0%9C/2026-lecture-network-practice-main/w06-routing/task3_reconverge.py#L99-L125)가 호출되는 178번의 경우마다 카운터 집계용 `dijkstra_table()` 호출에 더해 SPT 상태(`dist`, `parent`, `children`)를 기록하기 위한 작업이 중복 수행되었고, 매 이벤트마다 Python 레벨의 딕셔너리/집합 관리 오버헤드가 추가되었기 때문입니다.
   - **실제 라우터에서 여전히 필수적인 이유**:
     1. 실제 라우터(C/C++ 구현체)에서는 단일 SPF 실행 과정에서 `dist`, `parent`, `first_hop`이 동시에 기록되므로 중복 연산이 전혀 없습니다.
     2. 무엇보다 실제 라우터에서 가장 부족하고 치명적인 자원은 **제어 평면(Control-Plane) CPU 사이클과 하드웨어 FIB(TCAM/SRAM) 갱신 대역폭**입니다. 대규모 OSPF 영역에서 불안정한 링크 하나가 초당 수십 번씩 플래핑(Flapping)할 때 매번 전체 SPF와 하드웨어 포워딩 테이블(FIB) 전체 재설치를 수행하면, 라우터 CPU 사용률이 100%로 고정되어 **정상적인 다른 이웃들과의 OSPF Hello 및 BGP Keepalive 패킷조차 처리하지 못하게 되고, 이로 인해 주변 라우터들의 Dead Timer가 연쇄 만료되면서 네트워크 전체가 붕괴(Meltdown)**합니다. 따라서 전체 SPF와 FIB 갱신의 82%를 사전 차단하는 증분 판단 기법은 실제 라우터의 생존과 안정성에 절대적으로 필수적입니다.
