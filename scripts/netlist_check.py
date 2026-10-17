#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""netlist_check.py — net-table.csv 与原理图网表的双向对账

用途：Gate 3 放行检查。把「设计意图权威源」和「图里实际连的」逐 (位号,引脚) 比对，
输出三类差异。必须 0 差异才进入 PCB 阶段。

用法：
    python netlist_check.py net-table.csv netlist.csv
    python netlist_check.py net-table.csv netlist.csv --json
    python netlist_check.py net-table.csv netlist.csv --alias J2=J1 --ignore-net NC

--alias 方向是「网表位号=权威源位号」：核心板在权威源里记 J1、网表里叫 J2 时，
写 --alias J2=J1 才能对上。

两个输入都支持两种列序，自动识别：
    位号,引脚,网络[,备注...]
    网络,位号,引脚[,备注...]
第一行必须是表头，且包含「位号/引脚/网络」三个列名（支持 ref/pin/net 等英文别名）。
"""

import argparse
import csv
import json
import sys

COL_ALIASES = {
    "ref": "ref", "designator": "ref", "位号": "ref", "元件": "ref", "代号": "ref",
    "pin": "pin", "引脚": "pin", "脚": "pin", "pin_number": "pin",
    "net": "net", "网络": "net", "netname": "net", "网络名": "net", "signal": "net",
}


def read_table(path):
    """读 CSV -> {(ref, pin): net}，并返回原始行数。"""
    rows = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        rdr = csv.reader(f)
        header = None
        for row in rdr:
            cells = [c.strip() for c in row]
            if not any(cells):
                continue
            if header is None:
                header = cells
                continue
            rows.append(cells)
    if header is None:
        raise ValueError("%s 是空文件" % path)

    idx = {}
    for i, name in enumerate(header):
        key = COL_ALIASES.get(name.lower())
        if key and key not in idx:
            idx[key] = i
    missing = [k for k in ("ref", "pin", "net") if k not in idx]
    if missing:
        raise ValueError(
            "%s 表头缺少列 %s；实际表头=%r（需包含 位号/引脚/网络）"
            % (path, missing, header))

    out = {}
    dups = []
    for cells in rows:
        if len(cells) <= max(idx.values()):
            raise ValueError("%s 有行长度不足表头: %r" % (path, cells))
        ref = cells[idx["ref"]]
        pin = cells[idx["pin"]]
        net = cells[idx["net"]]
        if not ref or not pin:
            continue
        key = (ref, pin)
        if key in out and out[key] != net:
            dups.append((key, out[key], net))
        out[key] = net
    return out, len(rows), dups


def main(argv=None):
    ap = argparse.ArgumentParser(description="net-table.csv 与网表的双向对账")
    ap.add_argument("net_table", help="权威源 net-table.csv")
    ap.add_argument("netlist", help="原理图导出的网表 CSV")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--alias", action="append", default=[],
                    help="位号别名映射，格式「网表位号=权威源位号」，"
                         "如核心板在权威源里叫 J1、网表里叫 J2，则写 --alias J2=J1")
    ap.add_argument("--ignore-net", action="append", default=[],
                    help="忽略这些网络（如 NC）")
    a = ap.parse_args(argv)

    alias = {}
    for spec in a.alias:
        if "=" not in spec:
            print("--alias 格式应为 A=B", file=sys.stderr)
            return 2
        k, v = spec.split("=", 1)
        alias[k.strip()] = v.strip()

    def canon(ref):
        return alias.get(ref, ref)

    ignore = {n.strip().upper() for n in a.ignore_net}

    try:
        want, n_want, dup_want = read_table(a.net_table)
        got, n_got, dup_got = read_table(a.netlist)
    except Exception as e:
        print("读取失败: %s" % e, file=sys.stderr)
        return 2

    for d in dup_want + dup_got:
        print("! 重复 (位号,引脚) 且网络不一致: %r  %s vs %s" % d)

    want = {k: v for k, v in want.items() if v.strip().upper() not in ignore}
    got = {(canon(r), p): v for (r, p), v in got.items()
           if v.strip().upper() not in ignore}

    only_want = sorted(k for k in want if k not in got)
    only_got = sorted(k for k in got if k not in want)
    diff_net = sorted(k for k in want if k in got and want[k] != got[k])

    ok = not (only_want or only_got or diff_net or dup_want or dup_got)

    report = {
        "ok": ok,
        "counts": {
            "net_table_rows": n_want,
            "net_table_edges": len(want),
            "netlist_rows": n_got,
            "netlist_edges": len(got),
        },
        "only_in_net_table": [
            {"ref": r, "pin": p, "net": want[(r, p)]} for r, p in only_want],
        "only_in_netlist": [
            {"ref": r, "pin": p, "net": got[(r, p)]} for r, p in only_got],
        "net_mismatch": [
            {"ref": r, "pin": p, "net_table": want[(r, p)], "netlist": got[(r, p)]}
            for r, p in diff_net],
        "duplicates": [
            {"key": list(d[0]), "first": d[1], "second": d[2]}
            for d in (dup_want + dup_got)],
    }

    if a.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if ok else 1

    print("[网表对账] %s  <->  %s" % (a.net_table, a.netlist))
    print("  权威源边数 %d / 网表边数 %d" % (len(want), len(got)))
    if only_want:
        print("\n  仅权威源有（设计意图连了但图里没连，或命名不一致）共 %d:" % len(only_want))
        for r, p in only_want:
            print("    %s.%s -> %s" % (r, p, want[(r, p)]))
    if only_got:
        print("\n  仅网表有（图里连了但权威源没记）共 %d:" % len(only_got))
        for r, p in only_got:
            print("    %s.%s -> %s" % (r, p, got[(r, p)]))
    if diff_net:
        print("\n  同名不同脚（最危险，通常是复制错位）共 %d:" % len(diff_net))
        for r, p in diff_net:
            print("    %s.%s  权威源=%s  网表=%s" % (r, p, want[(r, p)], got[(r, p)]))
    if dup_want or dup_got:
        print("\n  重复 (位号,引脚):")
        for d in (dup_want + dup_got):
            print("    %r  %s vs %s" % (list(d[0]), d[1], d[2]))

    print()
    if ok:
        print("  结果: PASS —— 0 差异")
        return 0
    print("  结果: FAIL —— 有 %d 项差异，必须先查清再进 PCB 阶段"
          % (len(only_want) + len(only_got) + len(diff_net)))
    print("  排查顺序: 1) 命名/位号不一致  2) 核心板拆分（用 --alias）  "
          "3) 真的接错")
    return 1


if __name__ == "__main__":
    sys.exit(main())
