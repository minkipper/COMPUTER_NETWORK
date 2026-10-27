#!/usr/bin/env python3
"""Week 6 · Task 3 — Reconverge without recomputing the world.

Textbook §5.2.1, §5.3.

A link flaps. Every router in the area has to decide what changed. `FullRecompute`
does the honest thing: throw the table away and run Dijkstra again, from scratch,
for every event. It is correct and it is what the first implementations did.

It is also why a single flapping link in a large area used to melt the CPU of
every router that could see it.

Beat it:

    python3 bench.py
    python3 bench.py --yours

Correctness first. `bench.py` compares your table against a full recompute after
**every single event**. A router that is fast and wrong black-holes traffic.
"""
import heapq

# The harness counts how many times you run a full SPF. This is the score:
# wall-clock time in Python says more about dictionary overhead than about
# routing, but "how many times did the CPU have to recompute the world" is
# exactly what melted real routers.
SPF_RUNS = 0


def dijkstra_table(graph, source):
    """Reference shortest-path-first. Returns {destination: first_hop}.

    Use THIS function whenever you need a full recompute. Rolling your own to
    dodge the counter is not an optimisation, it is cheating the meter.
    """
    global SPF_RUNS
    SPF_RUNS += 1
    best = {source: (0, None)}
    pq, done = [(0, source, None)], set()
    while pq:
        cost, node, first_hop = heapq.heappop(pq)
        if node in done:
            continue
        done.add(node)
        best[node] = (cost, first_hop)
        for nbr, w in sorted(graph[node].items()):
            if nbr in done:
                continue
            hop = nbr if node == source else first_hop
            if cost + w < best.get(nbr, (float("inf"), None))[0]:
                best[nbr] = (cost + w, hop)
                heapq.heappush(pq, (cost + w, nbr, hop))
    return {d: h for d, (_, h) in best.items() if d != source and h}


class FullRecompute:
    """On every event, forget everything and run SPF again."""

    def __init__(self, graph, source):
        self.graph = {n: dict(e) for n, e in graph.items()}
        self.source = source
        self.table = dijkstra_table(self.graph, source)

    def link_change(self, a, b, cost):
        """cost=None means the link went down."""
        if cost is None:
            self.graph[a].pop(b, None)
            self.graph[b].pop(a, None)
        else:
            self.graph[a][b] = cost
            self.graph[b][a] = cost
        self.table = dijkstra_table(self.graph, self.source)


class YourRouter:
    """Your router. Same two methods, same table, less work per event.

    What is actually true after one link changes:

      * most destinations are not affected at all
      * a link that is not on any of your shortest paths, going *up*, can only
        matter if it creates something shorter
      * a link going *down* only matters if you were using it

    Deciding which of those applies, cheaply, without getting it wrong, is the
    task. Getting it wrong is worse than being slow - the harness will catch it
    on the event where it happens.
    """

    def __init__(self, graph, source):
        self.graph = {n: dict(e) for n, e in graph.items()}
        self.source = source
        self.dist = {}
        self.parent = {}
        self.children = {}
        self.table = {}
        self._recompute()

    def _recompute(self):
        """Run a counted full SPF via dijkstra_table and record SPT state."""
        self.table = dijkstra_table(self.graph, self.source)
        # Reconstruct exact distances and SPT parents matching dijkstra_table's tie-breaking:
        # In dijkstra_table, pq pops in order of (cost, node, first_hop).
        best = {self.source: (0, None)}
        parent = {self.source: None}
        children = {n: set() for n in self.graph}
        pq, done = [(0, self.source, None)], set()
        while pq:
            cost, node, first_hop = heapq.heappop(pq)
            if node in done:
                continue
            done.add(node)
            for nbr, w in sorted(self.graph[node].items()):
                if nbr in done:
                    continue
                hop = nbr if node == self.source else first_hop
                if cost + w < best.get(nbr, (float("inf"), None))[0]:
                    best[nbr] = (cost + w, hop)
                    parent[nbr] = node
                    heapq.heappush(pq, (cost + w, nbr, hop))
        for n, p in parent.items():
            if p is not None and n in done:
                children[p].add(n)
        self.dist = {n: best[n][0] for n in done}
        self.parent = parent
        self.children = children

    def _best_candidate_for(self, v):
        """Find best (cost, parent_pop_order, parent, first_hop) for node v from its neighbours."""
        best_cand = None
        for nbr, w in self.graph[v].items():
            if nbr not in self.dist:
                continue
            d_nbr = self.dist[nbr]
            hop = v if nbr == self.source else self.table.get(nbr)
            # In dijkstra_table, the first neighbour popped from pq that achieves minimum (d_nbr + w)
            # sets best[v]. Pop order in pq is (d_nbr, nbr, first_hop_of_nbr).
            nbr_hop = None if nbr == self.source else self.table.get(nbr)
            cand = (d_nbr + w, d_nbr, nbr, nbr_hop, hop)
            if best_cand is None or cand < best_cand:
                best_cand = cand
        return best_cand

    def _set_parent(self, v, new_parent, new_dist, new_hop):
        old_p = self.parent.get(v)
        if old_p is not None and old_p in self.children:
            self.children[old_p].discard(v)
        self.parent[v] = new_parent
        if new_parent is not None:
            self.children[new_parent].add(v)
            self.dist[v] = new_dist
            self.table[v] = new_hop
        else:
            self.dist.pop(v, None)
            self.table.pop(v, None)

    def link_change(self, a, b, cost):
        old_cost = self.graph[a].get(b)
        if cost == old_cost:
            return

        if cost is None:
            self.graph[a].pop(b, None)
            self.graph[b].pop(a, None)
        else:
            self.graph[a][b] = cost
            self.graph[b][a] = cost

        a_parent_of_b = (self.parent.get(b) == a)
        b_parent_of_a = (self.parent.get(a) == b)
        in_spt = a_parent_of_b or b_parent_of_a

        # Case 1: Link went down or cost increased
        if cost is None or (old_cost is not None and cost > old_cost):
            if not in_spt:
                # Non-tree edge removed or worsened -> SPT cannot change
                return
            # Identify the child endpoint in the SPT
            child = b if a_parent_of_b else a
            if not self.children.get(child):
                # Leaf node in SPT: no other node routes through `child`, resolve locally
                cand = self._best_candidate_for(child)
                if cand is not None:
                    new_dist, _, new_p, _, new_hop = cand
                    self._set_parent(child, new_p, new_dist, new_hop)
                    return
            self._recompute()
            return

        # Case 2: Link came up or cost decreased
        if in_spt:
            child = b if a_parent_of_b else a
            parent_node = a if a_parent_of_b else b
            new_dist = self.dist[parent_node] + cost
            if not self.children.get(child):
                # If `child` is a leaf and its new distance still doesn't improve any neighbour
                can_propagate = any(
                    new_dist + w <= self.dist.get(nbr, float("inf"))
                    for nbr, w in self.graph[child].items()
                    if nbr != parent_node
                )
                if not can_propagate:
                    self.dist[child] = new_dist
                    return
            self._recompute()
            return

        da = self.dist.get(a, float("inf"))
        db = self.dist.get(b, float("inf"))
        na_hop = None if a == self.source else self.table.get(a)
        nb_hop = None if b == self.source else self.table.get(b)
        if (da, a, na_hop) < (db, b, nb_hop):
            u, v, du, dv = a, b, da, db
        else:
            u, v, du, dv = b, a, db, da

        cand_dist = du + cost
        if cand_dist > dv:
            # New/cheaper link is strictly longer than current shortest path to v
            return

        pv = self.parent.get(v)
        if cand_dist == dv and pv is not None:
            dpv = self.dist.get(pv, float("inf"))
            pv_hop = None if pv == self.source else self.table.get(pv)
            u_hop = None if u == self.source else self.table.get(u)
            if (dpv, pv, pv_hop) < (du, u, u_hop):
                # Current parent pv is popped before u in Dijkstra, so u does not replace pv
                return

        # Check if only v is affected (no neighbour of v can be improved or tied via v)
        can_propagate = any(
            cand_dist + w <= self.dist.get(nbr, float("inf"))
            for nbr, w in self.graph[v].items()
            if nbr != u
        )
        if not can_propagate and not self.children.get(v):
            new_hop = v if u == self.source else self.table.get(u)
            self._set_parent(v, u, cand_dist, new_hop)
            return

        self._recompute()
