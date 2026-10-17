#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""release_audit.py — 投板前制造文件完整性审计

只做机械检查（文件是否存在、能否解析、位号是否对得上）。
最终 go/no-go 结论由人下；本脚本必须列出「需人工复核项」。

用法：
    python release_audit.py <gerber目录> [--bom bom.csv] [--cpl cpl.csv]
    python release_audit.py <gerber目录> --json
    python release_audit.py <gerber目录> --board-outline outline.gbr

Gerber 识别按扩展名与内容启发式，命名因厂/因工具而异，找不到的层会报 MISSING_LAYER。
"""

import argparse
import json
import os
import re
import sys

# (key, 说明, 仅按扩展名匹配的候选, 内容/文件名特征正则候选)
# 扩展名表必须互不重叠，否则一个文件会同时命中顶层与底层。
LAYER_SPECS = [
    ("top_copper",   "顶层铜",       [".gtl", ".top", ".cmp"],
     [r"top.*(copper|cmp|signal)", r"\.gtl"]),
    ("bottom_copper", "底层铜",      [".gbl", ".bot", ".sol"],
     [r"(bot|bottom|sol).*(copper|signal)", r"\.gbl"]),
    ("top_solder",   "顶层阻焊",     [".gts", ".sts", ".smt"],
     [r"top.*(solder|soldermask|mask)", r"\.gts"]),
    ("bottom_solder", "底层阻焊",    [".gbs", ".sbs", ".smb"],
     [r"(bot|bottom).*(solder|soldermask|mask)", r"\.gbs"]),
    ("top_silk",     "顶层丝印",     [".gto", ".sst", ".plc"],
     [r"top.*(silk|overlay|legend)", r"\.gto"]),
    ("bottom_silk",  "底层丝印",     [".gbo", ".ssb", ".pls"],
     [r"(bot|bottom).*(silk|overlay|legend)", r"\.gbo"]),
    ("board_outline", "板框",        [".gko", ".gm1", ".gml", ".outline"],
     [r"board.*outline", r"keep-?out", r"\.gko", r"\.gm1"]),
    ("drill",        "钻孔",         [".drl", ".xln", ".nc", ".exc"],
     [r"M48", r"drill", r"INCH.*TZ", r"METRIC.*TZ"]),
    ("paste_top",    "顶层钢网",     [".gtp", ".crc", ".spt"],
     [r"top.*paste", r"\.gtp"]),
    ("paste_bottom", "底层钢网",     [".gbp", ".crs", ".spb"],
     [r"(bot|bottom).*paste", r"\.gbp"]),
]

# 内层命名（4 层及以上需要）
INNER_COPPER_RE = re.compile(r"(g\d{1,2}|in\d|inner|internal|layer\s*\d)", re.I)


def sniff(path):
    """读文件头，返回 (扩展名小写, 头部文本小写前 2000 字符)。"""
    ext = os.path.splitext(path)[1].lower()
    head = ""
    try:
        with open(path, "rb") as f:
            raw = f.read(4096)
        head = raw.decode("latin-1", "replace").lower()
    except Exception as e:
        head = "ERROR:%s" % e
    return ext, head


def classify(files):
    """两遍扫描：先按扩展名精确匹配，再用内容/文件名补缺，避免同文件重复命中。"""
    found = {}
    sniffs = [(p,) + sniff(p) for p in files]

    # 第一遍：扩展名（或钻孔的内容）匹配
    for p, ext, head in sniffs:
        name = os.path.basename(p).lower()
        for key, _desc, exts, pats in LAYER_SPECS:
            if key in found:
                continue
            if key == "drill":
                if ext in exts and any(re.search(x, head) for x in pats):
                    found[key] = [p]
            elif ext in exts:
                found[key] = [p]

    # 第二遍：内容/文件名特征（只补仍然缺失的层）
    for p, ext, head in sniffs:
        name = os.path.basename(p).lower()
        for key, _desc, exts, pats in LAYER_SPECS:
            if key in found:
                continue
            for pat in pats:
                if re.search(pat, head) or re.search(pat, name):
                    found[key] = [p]
                    break
    return found


def read_designators(path, aliases):
    import csv
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        rdr = csv.reader(f)
        rows = [r for r in rdr if any(c.strip() for c in r)]
    if not rows:
        raise ValueError("%s 空文件" % path)
    header = [c.strip().lower() for c in rows[0]]
    idx = None
    for a in aliases:
        if a in header:
            idx = header.index(a)
            break
    if idx is None:
        raise ValueError("%s 表头无位号列: %r" % (path, header))
    return {r[idx].strip() for r in rows[1:] if len(r) > idx and r[idx].strip()}


REF_ALIASES = ["位号", "designator", "ref", "refdes", "reference"]


def main(argv=None):
    ap = argparse.ArgumentParser(description="投板前制造文件审计")
    ap.add_argument("gerber_dir")
    ap.add_argument("--bom", default=None)
    ap.add_argument("--cpl", default=None)
    ap.add_argument("--board-outline", default=None,
                    help="单独指定板框文件（若无法从目录识别）")
    ap.add_argument("--layers", type=int, default=None,
                    help="声明铜层数（用于内层检查）")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    issues = []
    review = []

    if not os.path.isdir(a.gerber_dir):
        print("目录不存在: %s" % a.gerber_dir, file=sys.stderr)
        return 2

    allfiles = []
    for root, _dirs, names in os.walk(a.gerber_dir):
        for n in names:
            allfiles.append(os.path.join(root, n))
    if not allfiles:
        issues.append(("Critical", "EMPTY_DIR", "目录 %s 没有任何文件" % a.gerber_dir))

    found = classify(allfiles)

    for key, desc, _e, _p in LAYER_SPECS:
        if key not in found:
            if key in ("paste_top", "paste_bottom"):
                # 纯手焊板不需要钢网，投贴片才需要
                issues.append(("Minor", "MISSING_LAYER",
                               "缺少 %s (%s)——手焊可忽略，投贴片必须补" % (desc, key)))
            elif key in ("top_copper", "bottom_copper", "drill", "board_outline",
                         "top_solder", "bottom_solder"):
                issues.append(("Critical", "MISSING_LAYER", "缺少 %s (%s)" % (desc, key)))
            else:
                issues.append(("Major", "MISSING_LAYER", "缺少 %s (%s)" % (desc, key)))

    # 板框单独指定
    if a.board_outline and "board_outline" not in found:
        if os.path.isfile(a.board_outline):
            found["board_outline"] = [a.board_outline]
        else:
            issues.append(("Critical", "BAD_OUTLINE", "--board-outline 文件不存在"))

    # 重复/冲突：top_copper 与 bottom_copper 都命中 .gtl/.gbl 是常见误判
    for key in ("top_copper", "bottom_copper", "top_solder", "bottom_solder",
                "top_silk", "bottom_silk"):
        if key in found and len(found[key]) > 1:
            issues.append(("Minor", "AMBIGUOUS_LAYER",
                           "%s 命中多个文件: %s" % (key, [os.path.basename(x) for x in found[key]])))

    # 内层检查
    if a.layers and a.layers >= 4:
        inner = [p for p in allfiles if INNER_COPPER_RE.search(os.path.basename(p))]
        need = a.layers - 2
        if len(inner) < need:
            issues.append(("Critical", "MISSING_INNER",
                           "声明 %d 层，识别到 %d 个内层铜文件，需要 %d 个"
                           % (a.layers, len(inner), need)))

    # BOM/CPL 位号一致性
    bom_refs = cpl_refs = None
    try:
        if a.bom and os.path.isfile(a.bom):
            bom_refs = read_designators(a.bom, REF_ALIASES)
        if a.cpl and os.path.isfile(a.cpl):
            cpl_refs = read_designators(a.cpl, REF_ALIASES)
    except Exception as e:
        issues.append(("Critical", "BOM_CPL_READ", str(e)))

    if bom_refs is not None and cpl_refs is not None:
        for d in sorted(bom_refs - cpl_refs):
            issues.append(("Major", "IN_BOM_NOT_CPL",
                           "位号 %s 在 BOM 有、CPL 无" % d))
        for d in sorted(cpl_refs - bom_refs):
            issues.append(("Major", "IN_CPL_NOT_BOM",
                           "位号 %s 在 CPL 有、BOM 无" % d))

    # 必须人工复核项
    review.append("用独立 Gerber 查看器打开导出的文件目视复核（不要只看 EDA 视图）")
    review.append("确认板框被厂方正确识别为板框层，而非普通走线层")
    review.append("确认层数与叠层说明一致，内层顺序正确")
    if a.layers and a.layers >= 4:
        review.append("确认内电层分割、间距与过孔是否落在正确分区")
    review.append("确认阻焊/钢网/丝印扩展名与厂方要求一致")
    review.append("确认 BOM 中每个器件都有 LCSC C 号且非缺货")

    counts = {}
    for sev, _, _ in issues:
        counts[sev] = counts.get(sev, 0) + 1

    report = {
        "ok": not counts,
        "gerber_dir": os.path.abspath(a.gerber_dir),
        "files_scanned": len(allfiles),
        "layers_found": {k: [os.path.basename(x) for x in v]
                         for k, v in sorted(found.items())},
        "declared_layers": a.layers,
        "issue_counts": counts,
        "issues": [{"severity": s, "code": c, "detail": d} for s, c, d in issues],
        "must_review_manually": review,
    }

    if a.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1

    print("[投板放行审计] %s" % report["gerber_dir"])
    print("  扫描文件 %d 个" % len(allfiles))
    print("\n  识别到的层:")
    for key, desc, _e, _p in LAYER_SPECS:
        if key in found:
            print("    %-16s %s" % (desc, ", ".join(os.path.basename(x) for x in found[key])))
    if a.layers and a.layers >= 4:
        inner = [os.path.basename(p) for p in allfiles
                 if INNER_COPPER_RE.search(os.path.basename(p))]
        print("    %-16s %s" % ("内层铜", ", ".join(inner) if inner else "(未识别)"))

    if issues:
        order = {"Critical": 0, "Major": 1, "Minor": 2}
        print("\n  问题:")
        for sev, code, detail in sorted(issues, key=lambda x: order[x[0]]):
            print("    [%-8s] %-18s %s" % (sev, code, detail))
    else:
        print("\n  机械检查: 无问题")

    print("\n  必须人工复核:")
    for r in review:
        print("    - %s" % r)

    print()
    if counts.get("Critical"):
        print("  结论: NO-GO —— 有 %d 项 Critical" % counts["Critical"])
    elif counts.get("Major"):
        print("  结论: CONDITIONAL —— 有 %d 项 Major，需处理后复核" % counts["Major"])
    elif counts:
        print("  结论: CONDITIONAL —— 仅 Minor 项，知情后可投")
    else:
        print("  结论: 机械检查通过，人工复核后 go")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
