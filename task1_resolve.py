#!/usr/bin/env python3
"""Week 3 · Task 1 — Build your own iterative resolver.

Textbook §2.4.2 - §2.4.3.

`dig +trace` walks root -> TLD -> authoritative for you. In this task you do
that walk yourself: start at a root server, read the delegation it returns,
ask the next server, and keep going until somebody answers authoritatively.

You may shell out to `dig` for the transport, or use a DNS library
(`dnspython` is in the container). Either is fine - what matters is that
*you* follow the delegations rather than letting a tool do it.

    python3 task1_resolve.py www.korea.ac.kr
    python3 task1_resolve.py --verify        # check yourself against dig

Pass condition
--------------
`--verify` resolves five names with your resolver and with `dig`, and the
addresses must agree. A name behind a CDN may legitimately return a different
address each time; the harness compares the *set of authoritative nameservers*
you ended at for those, not the address.
"""
import argparse, subprocess, sys

# Root servers. Everything starts here; there is no earlier step.
ROOT_SERVERS = [
    "198.41.0.4",       # a.root-servers.net
    "199.9.14.201",     # b.root-servers.net
    "192.33.4.12",      # c.root-servers.net
]

# (name, kind).  "stable" names must match dig exactly.  "cdn" names are served
# from many replicas and may legitimately give you a different address than dig
# got a second earlier - for those we only require that you reached an answer.
VERIFY_NAMES = [
    ("www.korea.ac.kr", "stable"),
    ("dns.google", "stable"),
    ("en.wikipedia.org", "stable"),
    ("www.stanford.edu", "stable"),
    ("www.microsoft.com", "cdn"),
]

class Resolver:
    """Your iterative resolver."""

    def _query(self, server, name):
        """Query server for name with +norecurse."""
        try:
            res = subprocess.run(
                ["dig", f"@{server}", name, "A", "+norecurse", "+time=2", "+tries=1"],
                capture_output=True, text=True, timeout=5
            )
        except Exception:
            return None

        if res.returncode != 0:
            return None

        data = {"answer": [], "authority": [], "additional": []}
        current_section = None

        for line in res.stdout.splitlines():
            line = line.strip()
            if line.startswith(";; ANSWER SECTION:"):
                current_section = "answer"
                continue
            elif line.startswith(";; AUTHORITY SECTION:"):
                current_section = "authority"
                continue
            elif line.startswith(";; ADDITIONAL SECTION:"):
                current_section = "additional"
                continue
            elif line.startswith(";;") or not line:
                current_section = None
                continue

            if current_section:
                parts = line.split()
                if len(parts) >= 5:
                    rname = parts[0]
                    rtype = parts[-2]
                    rval = parts[-1]
                    data[current_section].append((rname, rtype, rval))

        return data

    def resolve(self, name, depth=0, max_depth=20):
        if depth > max_depth:
            raise RuntimeError(f"Maximum recursion depth exceeded while resolving {name}")

        path = []
        name = name.rstrip(".")
        servers = list(ROOT_SERVERS)

        while True:
            response = None
            # R4: Try next server if one fails to respond
            for srv in servers:
                path.append(srv)
                resp = self._query(srv, name)
                if resp:
                    # Check if response actually has answer or authority
                    if resp["answer"] or resp["authority"]:
                        response = resp
                        break

            if not response:
                raise RuntimeError(f"No response received from any server: {servers}")

            # 1. Check ANSWER section for A record
            a_records = [val for rname, rtype, val in response["answer"] if rtype == "A" and val[0].isdigit()]
            if a_records:
                return a_records[0], path

            # 2. Check ANSWER section for CNAME (R5)
            cname_records = [val for rname, rtype, val in response["answer"] if rtype == "CNAME"]
            if cname_records:
                cname_target = cname_records[0].rstrip(".")
                addr, sub_path = self.resolve(cname_target, depth=depth + 1, max_depth=max_depth)
                return addr, path + sub_path

            # 3. Check AUTHORITY section for NS delegation
            ns_records = [val.rstrip(".") for rname, rtype, val in response["authority"] if rtype == "NS"]
            if not ns_records:
                raise RuntimeError(f"No answer and no delegation found for {name}")

            # Check ADDITIONAL section for glue records
            glue_ips = []
            for ns in ns_records:
                for rname, rtype, val in response["additional"]:
                    if rtype == "A" and val[0].isdigit():
                        if rname.rstrip(".").lower() == ns.lower():
                            glue_ips.append(val)

            if glue_ips:
                servers = glue_ips
            else:
                # R3: No glue! Resolve the NS name iteratively
                resolved_ns_ip = None
                for ns in ns_records:
                    try:
                        ns_ip, ns_path = self.resolve(ns, depth=depth + 1, max_depth=max_depth)
                        path.extend(ns_path)
                        resolved_ns_ip = ns_ip
                        break
                    except Exception:
                        continue

                if not resolved_ns_ip:
                    raise RuntimeError(f"Failed to resolve glue-less nameserver for {name}: {ns_records}")

                servers = [resolved_ns_ip]



# ------------------------------------------------------------------- harness
def dig_answer(name):
    """What the system resolver says, for comparison."""
    out = subprocess.run(["dig", "+short", name, "A"],
                         capture_output=True, text=True).stdout
    return [l for l in out.split() if l and l[0].isdigit()]


def verify():
    r, failures = Resolver(), 0
    for name, kind in VERIFY_NAMES:
        try:
            addr, path = r.resolve(name)
        except NotImplementedError:
            print("Nothing implemented yet - write Resolver.resolve first.")
            return 1
        except Exception as e:
            print(f"  FAIL  {name:<22} your resolver raised {e!r}")
            failures += 1
            continue
        expected = dig_answer(name)
        if addr in expected:
            note = ""
        elif kind == "cdn":
            note = "  <- differs, but this name is CDN-hosted. Explain it."
        else:
            note = "  <- should have matched"
            failures += 1
        print(f"  {'FAIL' if note.endswith('matched') else 'ok  '}  {name:<22} "
              f"you={addr:<16} dig={','.join(expected) or '-'}   "
              f"hops={len(path)}{note}")
    print(f"\n  {len(VERIFY_NAMES) - failures}/{len(VERIFY_NAMES)} ok")
    return 1 if failures else 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("name", nargs="?", default="www.korea.ac.kr")
    p.add_argument("--verify", action="store_true")
    a = p.parse_args()

    if a.verify:
        sys.exit(verify())

    addr, path = Resolver().resolve(a.name)
    for i, server in enumerate(path, 1):
        print(f"  {i}. asked {server}")
    print(f"\n  {a.name} -> {addr}")


if __name__ == "__main__":
    main()
