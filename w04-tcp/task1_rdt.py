#!/usr/bin/env python3
"""Week 4 · Task 1 — Build reliable delivery on top of an unreliable channel.

Textbook §3.4 (reliable data transfer) and §3.5 (TCP's sequence numbers).

`UnreliableChannel` below loses packets, reorders them, duplicates them, and
delays them. It is the network as §3.4 models it. Your job is to move a file
across it and have the bytes arrive intact and in order.

That is the whole of TCP's reliability story with the congestion control taken
out, and it is worth building once by hand before you ever trust a socket again.

    python3 task1_rdt.py --verify
"""
import argparse, hashlib, random

PAYLOAD = 8            # bytes per packet - small, so you see the sequencing


class UnreliableChannel:
    """Loses 10%, duplicates 3%, reorders, and delays. Deterministic by seed.

    You may not make it nicer. You may not read its internals. It is the only
    way your sender can reach your receiver.
    """

    def __init__(self, seed=246, loss=0.10, dup=0.03, reorder=0.10):
        self.rng = random.Random(seed)
        self.loss, self.dup, self.reorder = loss, dup, reorder
        self.wire = []          # packets in flight, in no particular order
        self.stats = {"sent": 0, "lost": 0, "duplicated": 0, "delivered": 0}

    def send(self, packet):
        """Hand a packet to the network. It may never come out."""
        self.stats["sent"] += 1
        if self.rng.random() < self.loss:
            self.stats["lost"] += 1
            return
        copies = 2 if self.rng.random() < self.dup else 1
        self.stats["duplicated"] += copies - 1
        for _ in range(copies):
            if self.rng.random() < self.reorder and self.wire:
                self.wire.insert(self.rng.randrange(len(self.wire)), packet)
            else:
                self.wire.append(packet)

    def receive(self):
        """Take the next packet out, or None if the network has nothing."""
        if not self.wire:
            return None
        self.stats["delivered"] += 1
        return self.wire.pop(0)


class Sender:
    def __init__(self, data_channel, ack_channel, data):
        self.data_channel = data_channel
        self.ack_channel = ack_channel

        # [R1] PAYLOAD 크기(8바이트) 단위로 데이터를 분할하고 번호(seq) 부여
        self.chunks = [data[i:i + PAYLOAD] for i in range(0, len(data), PAYLOAD)]
        self.total_chunks = len(self.chunks)
        
        self.seq = 0               # 현재 전송 중인 Sequence Number
        self.timer = 0             # [R4] 타임아웃 측정을 위한 타이머
        self.TIMEOUT = 8           # 적절한 타임아웃 threshold (스텝 단위)

    def step(self):
        """Do one unit of work. Return False when you believe you are done."""
        # 모든 덩어리의 ACK 수신이 끝난 경우 (종료)
        if self.seq >= self.total_chunks:
            return False

        # [R4] ACK 채널(down)로부터 들어오는 ACK 수신 확인
        # 채널에 쌓여있는 ACK들을 모두 비우며 최신 ACK를 확인
        while True:
            ack = self.ack_channel.receive()
            if ack is None:
                break
            # ACK 패킷 구조: (ack_seq,)
            ack_seq = ack[0]
            # [R3] 수신기가 "내가 기대하는 패킷"의 ACK를 보내왔다면 다음 패킷으로 진행
            if ack_seq == self.seq:
                self.seq += 1
                self.timer = 0     # 타이머 리셋

        # 전송 완료 체크
        if self.seq >= self.total_chunks:
            return False

        # [R4] 타임아웃 발생 시 재전송 / 매 스텝 최초 전송
        if self.timer == 0 or self.timer >= self.TIMEOUT:
            # 데이터 패킷 구조: (seq, payload)
            packet = (self.seq, self.chunks[self.seq])
            self.data_channel.send(packet)
            self.timer = 0

        self.timer += 1
        return True


class Receiver:
    def __init__(self, data_channel, ack_channel):
        self.data_channel = data_channel
        self.ack_channel = ack_channel
        
        self.expected_seq = 0      # [R2] 순서대로 재조합하기 위해 기대하는 Sequence Number
        self.received_chunks = {}  # 수신한 데이터 조각 저장용 (bytearray 대신 dict 활용)

    def step(self):
        # [R2] Data 채널(up)로부터 패킷 수신
        while True:
            packet = self.data_channel.receive()
            if packet is None:
                break

            seq, payload = packet

            # [R2] 기대하던 순서의 패킷이 도착한 경우
            if seq == self.expected_seq:
                self.received_chunks[seq] = payload
                self.expected_seq += 1
                # [R4] 수신 성공 ACK 전송
                self.ack_channel.send((seq,))

            # [R3] 이미 받은 이전 순서의 패킷이 다시 도착한 경우 (중복 패킷)
            elif seq < self.expected_seq:
                # 데이터를 다시 추가하지 않고, Sender가 다음으로 넘어가도록 ACK 재전송
                self.ack_channel.send((seq,))

            # [R2, R3] 미래의 패킷이 먼저 도착했거나(Reordering) 잘못된 패킷인 경우
            else:
                # 무시하되, 마지막으로 제대로 전달받았던 패킷의 ACK를 응답
                if self.expected_seq > 0:
                    self.ack_channel.send((self.expected_seq - 1,))

    def data(self):
        """The bytes reassembled so far."""
        # [R2] Sequence Number 순서대로 bytes 결합하여 반환
        result = bytearray()
        for i in range(self.expected_seq):
            result.extend(self.received_chunks[i])
        return bytes(result)


# ------------------------------------------------------------------- harness
def verify(seed=246, size=2000, max_steps=200_000):
    original = bytes(random.Random(seed).getrandbits(8) for _ in range(size))
    up, down = UnreliableChannel(seed), UnreliableChannel(seed + 1)

    # Data goes out over `up`, ACKs come back over `down`. Both are unreliable.
    sender = Sender(up, down, original)
    receiver = Receiver(up, down)

    for _ in range(max_steps):
        alive = sender.step()
        receiver.step()
        if not alive and len(receiver.data() or b"") >= size:
            break

    got = receiver.data() or b""
    ok = hashlib.sha256(got).hexdigest() == hashlib.sha256(original).hexdigest()
    print(f"  bytes    sent {size}   received {len(got)}")
    print(f"  channel  {up.stats}")
    print(f"  result   {'IDENTICAL' if ok else 'CORRUPTED OR INCOMPLETE'}")
    return 0 if ok else 1


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--verify", action="store_true")
    p.add_argument("--seed", type=int, default=246)
    a = p.parse_args()
    raise SystemExit(verify(a.seed) if a.verify else p.print_help())