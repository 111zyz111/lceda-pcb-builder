#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selftest.py — 本 skill 脚本的回归自测（零依赖）

在临时目录造夹具，跑 pcbcalc / netlist_check / bom_check / release_audit，
验证通过用例与失败用例都被正确判定。

用法：
    python tests/run_selftest.py
"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
SCRIPTS = os.path.join(SKILL, "scripts")

FAILURES = []
PASSED = 0


def run(args):
    p = subprocess.run([sys.executable] + args, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def check(name, cond, detail=""):
    global PASSED
    if cond:
        PASSED += 1
        print("  PASS  %s" % name)
    else:
        FAILURES.append((name, detail))
        print("  FAIL  %s   %s" % (name, detail))


def w(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def test_pcbcalc():
    print("[pcbcalc]")
    rc, out = run([os.path.join(SCRIPTS, "pcbcalc.py"), "--help"])
    check("--help", rc == 0 and "pcbcalc" in out.lower(), "rc=%d" % rc)

    rc, out = run([os.path.join(SCRIPTS, "pcbcalc.py"),
                   "trace", "--current", "1.5", "--copper", "1oz"])
    check("trace 解析 1oz", rc == 0 and "0.5255" in out, out[-200:])

    rc, out = run([os.path.join(SCRIPTS, "pcbcalc.py"),
                   "trace", "--current", "1.5", "--copper", "3oz"])
    check("trace 拒绝 3oz", rc != 0, "应报错")

    rc, out = run([os.path.join(SCRIPTS, "pcbcalc.py"),
                   "divider", "--vin", "12", "--r1", "10k", "--r2", "2k"])
    check("divider 12/10k/2k = 2V", "2 V" in out, out[-200:])

    rc, out = run([os.path.join(SCRIPTS, "pcbcalc.py"),
                   "thermal-ldo", "--vin", "12", "--vout", "5",
                   "--iout", "0.3", "--rth", "60"])
    check("thermal-ldo 2.1W", "2.1 W" in out, out[-200:])

    rc, out = run([os.path.join(SCRIPTS, "pcbcalc.py"),
                   "rc", "--r", "10k", "--c", "100n"])
    check("rc fc≈159Hz", "159" in out, out[-200:])

    rc, out = run([os.path.join(SCRIPTS, "pcbcalc.py"),
                   "battery", "--mah", "2000", "--ma", "150"])
    check("battery 13.33h", "13.33" in out, out[-200:])


NET_TABLE = """位号,引脚,网络,MCU引脚名,备注
J1,1,GND,,
J1,2,+3V3,,
J1,3,OV_SCL,,
J1,4,FIFO_WRST,,
J1,5,OV_SDA,,
J1,6,FIFO_RRST,,
U1,1,VM,,
U1,2,IN1,,
U1,3,IN2,,
U1,8,GND,,
U1,9,GND,EP
TP1,1,+5V,,
TP1,3,GND,,
"""

NET_GOOD = """网络,位号,引脚
GND,J1,1
GND,U1,8
GND,U1,9
GND,TP1,3
+3V3,J1,2
OV_SCL,J1,3
FIFO_WRST,J1,4
OV_SDA,J1,5
FIFO_RRST,J1,6
VM,U1,1
IN1,U1,2
IN2,U1,3
+5V,TP1,1
"""

NET_BAD = """网络,位号,引脚
GND,J1,1
GND,U1,8
GND,U1,9
GND,TP1,3
+3V3,J1,2
OV_SCL,J1,3
FIFO_WRST,J1,4
OV_SDA,J1,5
FIFO_RRST,J1,6
VM,U1,1
IN1,U1,2
IN2,U1,99
+5V,TP1,1
GND,TP1,99
"""


def test_netlist(tmp):
    print("[netlist_check]")
    nt = os.path.join(tmp, "nt.csv")
    good = os.path.join(tmp, "good.csv")
    bad = os.path.join(tmp, "bad.csv")
    w(nt, NET_TABLE); w(good, NET_GOOD); w(bad, NET_BAD)

    rc, out = run([os.path.join(SCRIPTS, "netlist_check.py"), nt, good])
    check("0 差异 PASS", rc == 0 and "PASS" in out, out[-300:])

    rc, out = run([os.path.join(SCRIPTS, "netlist_check.py"), nt, bad])
    check("3 差异 FAIL", rc == 1 and "FAIL" in out and "仅权威源有" in out, out[-300:])

    rc, out = run([os.path.join(SCRIPTS, "netlist_check.py"), nt, bad, "--json"])
    try:
        j = json.loads(out)
        ok = (not j["ok"]
              and len(j["only_in_net_table"]) == 1
              and len(j["only_in_netlist"]) == 2)
    except Exception as e:
        ok = False
        j = {"err": str(e)}
    check("JSON 结构正确", ok, str(j)[:300])

    # alias：核心板在权威源叫 J1、网表叫 J2 时
    alias_csv = os.path.join(tmp, "alias.csv")
    w(alias_csv, NET_GOOD.replace("J1,", "J2,"))
    rc, out = run([os.path.join(SCRIPTS, "netlist_check.py"), nt, alias_csv,
                   "--alias", "J2=J1"])
    check("--alias J2=J1 PASS", rc == 0 and "PASS" in out, out[-300:])

    # 方向写反应失败
    rc, out = run([os.path.join(SCRIPTS, "netlist_check.py"), nt, alias_csv,
                   "--alias", "J1=J2"])
    check("--alias 方向写反会 FAIL", rc == 1, out[-200:])


BOM = """Comment,Designator,Footprint,LCSC Part,Qty
10k,R1,R_0603,C25804,10
100nF,C1,C_0603,C14663,10
AT8236,U1,SOP-8-EP,,1
Header 2x9,CN1,HDR_2X9,,1
"""

CPL = """Designator,Mid X,Mid Y,Layer,Rotation
R1,10.5,20.0,Top,0
C1,12.0,20.0,Top,0
U1,15.0,25.0,Top,90
CN1,30.0,25.0,Top,0
"""

BOM_BAD = """位号,型号,封装,LCSC,数量
R1,10k,0603,C25804,10
R1,10k,0603,C25804,10
U1,AT8236,SOP-8-EP,,1
,unknown,0603,C1,1
ZZ,AT8236,0603,,0
"""

CPL_BAD = """位号,X,Y,层,旋转
R1,10.5,20.0,Top,0
U1,abc,25.0,Top,90
"""


def test_bom(tmp):
    print("[bom_check]")
    b = os.path.join(tmp, "bom.csv"); c = os.path.join(tmp, "cpl.csv")
    bb = os.path.join(tmp, "bombad.csv"); cb = os.path.join(tmp, "cplbad.csv")
    w(b, BOM); w(c, CPL); w(bb, BOM_BAD); w(cb, CPL_BAD)

    rc, out = run([os.path.join(SCRIPTS, "bom_check.py"), b, c])
    check("BOM/CPL 一致 PASS", rc == 0 and "PASS" in out, out[-300:])

    rc, out = run([os.path.join(SCRIPTS, "bom_check.py"), b])
    check("单 BOM：Comment 不当位号", rc == 0, out[-300:])

    rc, out = run([os.path.join(SCRIPTS, "bom_check.py"), bb, cb])
    check("重复位号/坏坐标被检出",
          rc == 1 and "DUP_DESIGNATOR" in out and "BAD_X" in out, out[-300:])

    rc, out = run([os.path.join(SCRIPTS, "bom_check.py"), b,
                   "--expect-designators", "R1,U1,ZZ9"])
    check("缺必备位号报 Critical",
          rc == 1 and "MISSING_DESIGNATOR" in out and "ZZ9" in out, out[-300:])


def _mk_gerber(d, with_paste=False):
    os.makedirs(d, exist_ok=True)
    w(os.path.join(d, "b-top.gtl"), "G04 Top Copper *\nM02*\n")
    w(os.path.join(d, "b-bot.gbl"), "G04 Bottom Copper *\nM02*\n")
    w(os.path.join(d, "b-ts.gts"), "G04 Top Soldermask *\nM02*\n")
    w(os.path.join(d, "b-bs.gbs"), "G04 Bottom Soldermask *\nM02*\n")
    w(os.path.join(d, "b-tsilk.gto"), "G04 Top Overlay *\nM02*\n")
    w(os.path.join(d, "b-bsilk.gbo"), "G04 Bottom Overlay *\nM02*\n")
    w(os.path.join(d, "b-outline.gko"), "G04 Board Outline *\nM02*\n")
    w(os.path.join(d, "drill.drl"), "M48\nINCH,TZ\n%\nM30\n")
    if with_paste:
        w(os.path.join(d, "b-tp.gtp"), "G04 Top Paste *\nM02*\n")
        w(os.path.join(d, "b-bp.gbp"), "G04 Bottom Paste *\nM02*\n")


def test_release(tmp):
    print("[release_audit]")
    g = os.path.join(tmp, "g-good"); b = os.path.join(tmp, "g-bad")
    _mk_gerber(g, with_paste=True)
    _mk_gerber(b, with_paste=False)
    os.remove(os.path.join(b, "b-outline.gko"))
    os.remove(os.path.join(b, "drill.drl"))

    rc, out = run([os.path.join(SCRIPTS, "release_audit.py"), g, "--layers", "2"])
    check("完整目录 PASS", rc == 0 and "无问题" in out, out[-300:])
    check("顶层铜未误判为底层", "顶层铜              b-top.gtl" in out, out[:600])

    rc, out = run([os.path.join(SCRIPTS, "release_audit.py"), b])
    check("缺板框/钻孔报 NO-GO",
          rc == 1 and "NO-GO" in out and "MISSING_LAYER" in out, out[-300:])

    rc, out = run([os.path.join(SCRIPTS, "release_audit.py"), g, "--layers", "4"])
    check("4 层缺内层被检出", "MISSING_INNER" in out, out[-300:])

    rc, out = run([os.path.join(SCRIPTS, "release_audit.py"), g, "--json"])
    try:
        j = json.loads(out)
        ok = j["ok"] and len(j["must_review_manually"]) >= 5
    except Exception as e:
        j = {"err": str(e)}; ok = False
    check("JSON 含人工复核项", ok, str(j)[:200])


def main():
    print("lceda-pcb-builder 脚本回归自测")
    print("=" * 60)
    with tempfile.TemporaryDirectory() as tmp:
        test_pcbcalc()
        test_netlist(tmp)
        test_bom(tmp)
        test_release(tmp)
    print("=" * 60)
    print("通过 %d 项，失败 %d 项" % (PASSED, len(FAILURES)))
    if FAILURES:
        print("\n失败详情:")
        for n, d in FAILURES:
            print("  - %s: %s" % (n, d[:400]))
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
