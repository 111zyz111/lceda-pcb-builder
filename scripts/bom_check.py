#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bom_check.py — BOM / CPL 一致性与位号冲突检查

用法：
    python bom_check.py bom.csv
    python bom_check.py bom.csv cpl.csv
    python bom_check.py bom.csv cpl.csv --json
    python bom_check.py bom.csv --expect-designators J1,J2,U1

BOM CSV 需含「位号」列；其余列（型号/封装/数量/LCSC C号）有则检查、无则跳过。
CPL CSV 需含「位号」列；有坐标/层/旋转列则校验格式。
"""

import argparse
import csv
import json
import re
import sys

REF_ALIASES = ["位号", "设计位号", "designator", "ref", "refdes", "reference",
               "元件", "位号/元件", "part", "零件"]
# 注意：不要把 Comment / Value / 型号 当位号列——它们是器件值，不是位号。
MODEL_ALIASES = ["型号", "model", "mpn", "part number", "value", "comment",
                 "值", "器件型号", "description"]
PKG_ALIASES = ["封装", "footprint", "package", "pkg"]
CSC_ALIASES = ["lcsc", "c号", "c 号", "cnumber", "lcsc c号", "立创编号"]
QTY_ALIASES = ["数量", "qty", "quantity", "个数"]
X_ALIASES = ["x", "mid x", "posx", "x(mm)", "坐标x", "x坐标"]
Y_ALIASES = ["y", "mid y", "posy", "y(mm)", "坐标y", "y坐标"]
LAYER_ALIASES = ["层", "layer", "side", "top/bottom", "层面"]
ROT_ALIASES = ["旋转", "rotation", "rot", "角度"]

DESIGNATOR_RE = re.compile(r"^[A-Za-z]{1,4}[0-9]+[A-Za-z0-9]*$")


def load(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        rdr = csv.reader(f)
        rows = [r for r in rdr if any(c.strip() for c in r)]
    if not rows:
        raise ValueError("%s 是空文件" % path)
    header = [c.strip() for c in rows[0]]
    data = [ [c.strip() for c in r] for r in rows[1:] ]

    def col(names):
        for n in names:
            for i, h in enumerate(header):
                if h.lower() == n.lower():
                    return i
        return None

    return header, data, col


def main(argv=None):
    ap = argparse.ArgumentParser(description="BOM/CPL 一致性与位号检查")
    ap.add_argument("bom")
    ap.add_argument("cpl", nargs="?", default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--expect-designators", default=None,
                    help="逗号分隔的必备位号清单（如 J1,J2,U1）")
    a = ap.parse_args(argv)

    issues = []   # (severity, code, detail)

    try:
        hdr, rows, col = load(a.bom)
    except Exception as e:
        print("读取失败: %s" % e, file=sys.stderr)
        return 2

    i_ref = col(REF_ALIASES)
    if i_ref is None:
        print("BOM 缺少位号列。表头=%r" % hdr, file=sys.stderr)
        return 2
    i_model = col(MODEL_ALIASES)
    i_pkg = col(PKG_ALIASES)
    i_csc = col(CSC_ALIASES)
    i_qty = col(QTY_ALIASES)

    bom = []
    for r in rows:
        if len(r) <= i_ref or not r[i_ref]:
            continue
        ref = r[i_ref]
        rec = {
            "ref": ref,
            "model": r[i_model] if i_model is not None and len(r) > i_model else "",
            "package": r[i_pkg] if i_pkg is not None and len(r) > i_pkg else "",
            "csc": r[i_csc] if i_csc is not None and len(r) > i_csc else "",
            "qty": r[i_qty] if i_qty is not None and len(r) > i_qty else "",
        }
        bom.append(rec)

    # 1. 位号格式
    for rec in bom:
        if not DESIGNATOR_RE.match(rec["ref"]):
            issues.append(("Major", "BAD_DESIGNATOR",
                           "位号 %r 不符合 字母+数字 格式" % rec["ref"]))

    # 2. 位号重复
    seen = {}
    for rec in bom:
        seen[rec["ref"]] = seen.get(rec["ref"], 0) + 1
    for ref, n in sorted(seen.items()):
        if n > 1:
            issues.append(("Major", "DUP_DESIGNATOR",
                           "位号 %s 在 BOM 中出现 %d 次" % (ref, n)))

    # 3. 必填字段
    for rec in bom:
        if i_model is not None and not rec["model"]:
            issues.append(("Major", "NO_MODEL",
                           "位号 %s 缺型号/值" % rec["ref"]))
        if i_pkg is not None and not rec["package"]:
            issues.append(("Minor", "NO_PACKAGE",
                           "位号 %s 缺封装" % rec["ref"]))
        if i_csc is not None and not rec["csc"]:
            issues.append(("Question", "NO_CSC",
                           "位号 %s 缺 LCSC C 号（投贴片必须补）" % rec["ref"]))

    # 4. 数量
    if i_qty is not None:
        for rec in bom:
            q = rec["qty"]
            if q and not q.isdigit():
                issues.append(("Minor", "BAD_QTY",
                               "位号 %s 数量 %r 非正整数" % (rec["ref"], q)))
            elif q and q.isdigit() and int(q) < 1:
                issues.append(("Minor", "BAD_QTY",
                               "位号 %s 数量 %s < 1" % (rec["ref"], q)))

    # 5. 必备位号
    if a.expect_designators:
        have = {r["ref"] for r in bom}
        for d in [x.strip() for x in a.expect_designators.split(",") if x.strip()]:
            if d not in have:
                issues.append(("Critical", "MISSING_DESIGNATOR",
                               "必备位号 %s 不在 BOM 中" % d))

    # 6. CPL 对账
    cpl_summary = None
    if a.cpl:
        try:
            chdr, crows, ccol = load(a.cpl)
        except Exception as e:
            issues.append(("Critical", "CPL_UNREADABLE", str(e)))
            chdr, crows, ccol = [], [], (lambda n: None)
        ci_ref = ccol(REF_ALIASES)
        if ci_ref is None:
            issues.append(("Critical", "CPL_NO_REF", "CPL 缺少位号列。表头=%r" % chdr))
        else:
            cpl_refs = [r[ci_ref] for r in crows if len(r) > ci_ref and r[ci_ref]]
            bom_refs = [r["ref"] for r in bom]
            sb, sc = set(bom_refs), set(cpl_refs)
            for d in sorted(sb - sc):
                issues.append(("Major", "IN_BOM_NOT_CPL",
                               "位号 %s 在 BOM 有、CPL 无（不会被贴片）" % d))
            for d in sorted(sc - sb):
                issues.append(("Major", "IN_CPL_NOT_BOM",
                               "位号 %s 在 CPL 有、BOM 无" % d))
            ci_x, ci_y, ci_layer = ccol(X_ALIASES), ccol(Y_ALIASES), ccol(LAYER_ALIASES)
            for r in crows:
                if len(r) <= ci_ref or not r[ci_ref]:
                    continue
                ref = r[ci_ref]
                if ci_x is not None and len(r) > ci_x and r[ci_x]:
                    try:
                        float(r[ci_x])
                    except ValueError:
                        issues.append(("Minor", "BAD_X", "位号 %s X 坐标 %r 非数值" % (ref, r[ci_x])))
                if ci_y is not None and len(r) > ci_y and r[ci_y]:
                    try:
                        float(r[ci_y])
                    except ValueError:
                        issues.append(("Minor", "BAD_Y", "位号 %s Y 坐标 %r 非数值" % (ref, r[ci_y])))
                if ci_layer is not None and len(r) > ci_layer and r[ci_layer]:
                    lv = r[ci_layer].strip().lower()
                    if not any(t in lv for t in ("top", "bottom", "顶", "底", "t", "b")):
                        issues.append(("Minor", "BAD_LAYER",
                                       "位号 %s 层 %r 无法识别" % (ref, r[ci_layer])))
            cpl_summary = {"cpl_designators": len(set(cpl_refs)),
                           "bom_designators": len(set(bom_refs))}

    counts = {}
    for sev, _, _ in issues:
        counts[sev] = counts.get(sev, 0) + 1

    report = {
        "ok": not counts,
        "bom_designators": len({r["ref"] for r in bom}),
        "cpl": cpl_summary,
        "issue_counts": counts,
        "issues": [{"severity": s, "code": c, "detail": d} for s, c, d in issues],
    }

    if a.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1

    print("[BOM/CPL 检查]")
    print("  BOM 位号数 %d" % report["bom_designators"])
    if cpl_summary:
        print("  CPL 位号数 %d" % cpl_summary["cpl_designators"])
    if not issues:
        print("\n  结果: PASS —— 无问题")
        return 0
    order = {"Critical": 0, "Major": 1, "Minor": 2, "Question": 3}
    for sev, code, detail in sorted(issues, key=lambda x: order[x[0]]):
        print("  [%-8s] %-18s %s" % (sev, code, detail))
    print("\n  结果: FAIL —— %d 项问题" % len(issues))
    return 1


if __name__ == "__main__":
    sys.exit(main())
