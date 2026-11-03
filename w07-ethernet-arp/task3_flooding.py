#!/usr/bin/env python3
"""Week 7 · Task 3 — A switch that runs out of room.

Textbook §6.4.3.

A switch does not have room for every station on the network. Its forwarding
table sits in a fixed amount of fast memory, and when that fills, something has
to go. Whatever goes gets **flooded** the next time anyone sends to it - out of
every port, to every station that did not ask for it.

`NaiveSwitch` handles a full table the simplest way: throw out whichever entry
has been there longest. That is a perfectly reasonable first idea and it is
close to the worst thing you can do with this traffic.

    python3 bench.py
    python3 bench.py --yours

Correctness first: every frame whose destination is reachable must still reach
it. A switch that floods less because it delivers less is not a switch.
"""
from collections import OrderedDict


class NaiveSwitch:
    """Correct. Evicts the oldest entry, which is not the least useful one."""

    BROADCAST = "ff:ff:ff:ff:ff:ff"

    def __init__(self, ports, capacity):
        self.ports = ports
        self.capacity = capacity
        self.table = OrderedDict()                 # mac -> port, insertion order

    def handle(self, frame, in_port):
        src, dst, now = frame
        if src not in self.table and len(self.table) >= self.capacity:
            self.table.popitem(last=False)         # throw out the oldest arrival
        self.table[src] = in_port

        if dst == self.BROADCAST or dst not in self.table:
            return [p for p in range(self.ports) if p != in_port]
        out = self.table[dst]
        return [] if out == in_port else [out]


class YourSwitch:
    """Your switch. Same interface, same deliveries, far less flooding.

        __init__(ports, capacity)
        handle((src, dst, time), in_port) -> ports to forward out of

    `self.table` must exist and must never hold more than `capacity` entries.
    The harness checks this after every frame.

    What the baseline gets wrong: it decides what to keep by **when the entry
    arrived**, and that has nothing to do with whether it is about to be needed.
    On this trace a handful of stations carry most of the traffic, and the
    baseline keeps throwing them out to make room for stations that spoke once.

    Two questions worth separating:

      * which entry should leave when the table is full?
      * should learning a new source ever be *declined*?

    The second one is less obvious and is worth thinking about before you
    dismiss it.

    Note what you are NOT allowed to do: you cannot look at `where`, you cannot
    see the future, and you cannot hold more than `capacity` entries. Everything
    you know comes from the frames you have already handled.
    """

    BROADCAST = "ff:ff:ff:ff:ff:ff"

    def __init__(self, ports, capacity):
        self.ports = ports
        self.capacity = capacity
        self.table = {}       # mac -> port (never exceeds capacity)
        self.freq = {}        # mac -> observed traffic count (src + dst references)
        self.last_seen = {}   # mac -> timestamp for tie-breaking

    def handle(self, frame, in_port):
        src, dst, now = frame

        # Update traffic evidence from current frame
        self.freq[src] = self.freq.get(src, 0) + 1
        self.last_seen[src] = now
        if dst != self.BROADCAST:
            self.freq[dst] = self.freq.get(dst, 0) + 1

        # Source learning with LFU eviction + frequency-gated admission control
        if src in self.table:
            self.table[src] = in_port
        elif len(self.table) < self.capacity:
            self.table[src] = in_port
        else:
            # Table is full: find the resident with the lowest frequency (oldest on tie)
            victim = min(
                self.table,
                key=lambda m: (self.freq.get(m, 0), self.last_seen.get(m, 0.0)),
            )
            # Admission control: only evict victim if newcomer has proven higher frequency
            if self.freq[src] > self.freq.get(victim, 0):
                del self.table[victim]
                self.table[src] = in_port

        # Forwarding decision
        if dst == self.BROADCAST or dst not in self.table:
            return [p for p in range(self.ports) if p != in_port]

        self.last_seen[dst] = now
        out = self.table[dst]
        return [] if out == in_port else [out]
