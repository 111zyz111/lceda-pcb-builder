#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pcbcalc.py — PCB 确定性计算器（零依赖，纯标准库）

用途：把"心算"换成"可复现的计算"。所有结果是工程估算，不是保证值；
关键设计仍需厂方叠层或场仿真确认。

用法示例：
    python pcbcalc.py --help
    python pcbcalc.py trace --current 1.5 --rise 10 --layers 1 --copper 1oz
    python pcbcalc.py divider --vin 12 --r1 10k --r2 2k
    python pcbcalc.py thermal-ldo --vin 12 --vout 5 --iout 0.3 --rth 60
    python pcbcalc.py battery --mah 2000 --ma 150
    python pcbcalc.py rc --r 10k --c 100n
    python pcbcalc.py rl --r 10 --l 100u
    python pcbcalc.py shunt --i 2 --r 0.05 --rth 80
    python pcbcalc.py via --current 2 --drill 0.3 --plate 0.6
    python pcbcalc.py resistor-power --v 5 --r 1k
"""

import argparse
import math
import sys

# ---------------------------------------------------------------- 单位解析


def parse_value(s):
    """把 '10k' / '4.7u' / '100n' / '1M' / '2.2' 解析成 float（欧/法/亨）。"""
    s = str(s).strip()
    if not s:
        raise ValueError("空值")
    mult = {
        "f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "μ": 1e-6,
        "m": 1e-3, "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9, "T": 1e12,
    }
    # 处理 'R' 作为小数点（如 4R7 = 4.7）
    if "R" in s and any(c.isdigit() for c in s):
        head, _, tail = s.partition("R")
        if tail and head and all(c.isdigit() or c == "." for c in head):
            try:
                return float(head + "." + tail)
            except ValueError:
                pass
    for suf in ("f", "p", "n", "u", "µ", "μ", "m", "k", "K", "M", "G", "T"):
        if s.endswith(suf):
            body = s[: -len(suf)]
            # 'm' 结尾且 body 全是数字时可能是 '1m' = 1 milli，也可能是 1 米? 这里按 milli
            try:
                return float(body) * mult[suf]
            except ValueError:
                raise ValueError("无法解析数值: %r" % s)
    return float(s)


def fmt(v, unit="", scale=False):
    """scale=True 时对 Ω/F/H 等 SI 量自动加词头；温度/容量/长度一律不缩放。"""
    if not scale:
        if unit:
            return "%.4g %s" % (v, unit)
        return "%.4g" % v
    a = abs(v)
    if a == 0:
        return "0 " + unit
    if a >= 1e6:
        return "%.4g M%s" % (v / 1e6, unit)
    if a >= 1e3:
        return "%.4g k%s" % (v / 1e3, unit)
    if a >= 1:
        return "%.4g %s" % (v, unit)
    if a >= 1e-3:
        return "%.4g m%s" % (v * 1e3, unit)
    if a >= 1e-6:
        return "%.4g µ%s" % (v * 1e6, unit)
    if a >= 1e-9:
        return "%.4g n%s" % (v * 1e9, unit)
    return "%.4g p%s" % (v * 1e12, unit)


def out(label, value, unit="", note="", scale=False):
    print("  %-26s %s%s" % (label, fmt(value, unit, scale),
                            ("   # " + note) if note else ""))


def parse_copper(s):
    """'1oz' / '1' / '2oz' -> 1.0 / 2.0"""
    s = str(s).strip().lower().replace("oz", "").replace(" ", "")
    v = float(s)
    if v not in (1.0, 2.0):
        raise ValueError("copper 只支持 1oz 或 2oz，收到 %r" % s)
    return v


# ---------------------------------------------------------------- 走线载流

# IPC-2221: I = k * dT^0.44 * A^0.725 （A 单位 mil²）
# k: 外层 0.048, 内层 0.024
_TRACE_K_OUTER = 0.048
_TRACE_K_INNER = 0.024
_1OZ_MIL = 1.378  # 1 oz 铜 ≈ 1.378 mil ≈ 34.8 µm
_2OZ_MIL = 2.756


def trace_area_from_current(current, rise, inner):
    k = _TRACE_K_INNER if inner else _TRACE_K_OUTER
    return (current / (k * (rise ** 0.44))) ** (1 / 0.725)


def trace_width_mm(current, rise, layers, copper_oz):
    """返回所需线宽（mm）。layers: 外层并联层数; copper_oz: 1 或 2。"""
    copper_oz = float(copper_oz)
    if copper_oz not in (1.0, 2.0):
        raise ValueError("copper 只支持 1oz 或 2oz")
    thk_mil = _1OZ_MIL * copper_oz
    # 外层并联时把电流分摊
    per_layer = current / max(1, layers)
    area = trace_area_from_current(per_layer, rise, inner=False)
    width_mil = area / thk_mil
    return width_mil * 0.0254


def cmd_trace(a):
    copper = parse_copper(a.copper)
    w = trace_width_mm(a.current, a.rise, a.layers, copper)
    print("[走线宽度估算] IPC-2221 简化模型")
    print("  输入: I=%g A, ΔT=%g °C, 外层并联层数=%d, 铜厚=%goz" % (
        a.current, a.rise, a.layers, copper))
    out("所需最小线宽", w, "mm")
    k = _TRACE_K_OUTER
    thk = _1OZ_MIL * copper
    area = (w / 0.0254) * thk
    cap = k * (a.rise ** 0.44) * (area ** 0.725)
    out("该线宽单层载流能力(@ΔT)", cap, "A")
    if w < 0.15:
        print("  ! 低于常见厂方工艺下限（约 0.15 mm / 6 mil），需加层或加铜厚")
    if a.layers > 1:
        print("  ! 多层并联需保证各层电流路径等长且过孔充分，实际分流不均")
    print("  # 估算值。大电流/长时间工作请用厂方叠层或仿真复核。")


# ---------------------------------------------------------------- 分压


def cmd_divider(a):
    r1, r2 = parse_value(a.r1), parse_value(a.r2)
    vin = a.vin
    vout = vin * r2 / (r1 + r2)
    i = vin / (r1 + r2)
    print("[电阻分压]")
    out("R1 (上)", r1, "Ω", scale=True)
    out("R2 (下)", r2, "Ω", scale=True)
    out("Vout", vout, "V")
    out("分压比", vout / vin if vin else 0, "")
    out("支路电流", i * 1000, "mA")
    print("  # 负载效应未计入：若 Vout 端接低阻负载，实际值会偏离。")
    print("  # 分压器不适合做大功率电源，仅用于采样/反馈。")


# ---------------------------------------------------------------- 热


def cmd_thermal_ldo(a):
    vin, vout, iout = a.vin, a.vout, a.iout
    p = (vin - vout) * iout
    if a.iq is not None:
        p += a.iq * vin
    tj = a.tamb + p * a.rth
    print("[LDO 热估算]")
    out("耗散功率", p, "W")
    out("环境温度", a.tamb, "°C")
    out("RθJA", a.rth, "°C/W")
    out("估算结温", tj, "°C")
    margin = a.tjmax - tj
    out("相对 Tjmax 裕度", margin, "°C")
    if margin < 20:
        print("  ! 裕度不足 20 °C：换器件、加铜、加散热过孔，或降负载")
    if a.iq is None:
        print("  # 未计静态电流（Iq）功耗，实际略高；可用 --iq 指定")


def cmd_thermal_shunt(a):
    r = parse_value(a.r)
    i = a.i
    p = i * i * r
    tj = a.tamb + p * a.rth
    print("[采样电阻热估算]")
    out("阻值", r, "Ω", scale=True)
    out("电流", i, "A")
    out("耗散功率", p, "W")
    out("估算结温", tj, "°C")
    print("  # 采样电阻的温漂直接影响精度，大功率采样注意热设计与 Kelvin 连接。")


# ---------------------------------------------------------------- 电源/续航


def cmd_battery(a):
    hours = a.mah / a.ma if a.ma else 0
    print("[电池续航估算]")
    out("容量", a.mah, "mAh")
    out("负载电流", a.ma, "mA")
    out("理论时长", hours, "h")
    if a.eff is not None:
        out("按效率 %.0f%% 修正" % (a.eff * 100), hours * a.eff, "h")
        print("  # 效率用于 DC-DC 场景；LDO 用 (Vout/Vin) 折算更准")
    print("  # 未计低温衰减、自放电与老化；工程上建议留 30% 余量。")


def cmd_buck_inductor(a):
    vin, vout, iout, fsw = a.vin, a.vout, a.iout, a.fsw
    if vout >= vin:
        print("  ! Buck 要求 Vout < Vin")
        return
    duty = vout / vin
    # ΔIL 取 20~40% Iout，这里默认 30%
    ripple = 0.3 * iout
    l = (vin - vout) * duty / (ripple * fsw)
    print("[Buck 电感估算]")
    out("占空比", duty, "")
    out("纹波电流(30% Iout)", ripple, "A")
    out("所需电感", l * 1e6, "µH")
    sat = iout * 1.3
    out("饱和电流建议下限", sat, "A")
    print("  # 常用纹波比 20%~40%；提高频率可减小电感但增加开关损耗。")


# ---------------------------------------------------------------- 无源


def cmd_rc(a):
    r, c = parse_value(a.r), parse_value(a.c)
    fc = 1.0 / (2 * math.pi * r * c)
    print("[RC 截止频率]")
    out("R", r, "Ω", scale=True)
    out("C", c, "F", scale=True)
    out("fc", fc, "Hz")
    print("  # 一阶 RC 低通/高通 -3dB 点。实际衰减斜率 -20 dB/dec。")


def cmd_rl(a):
    r, l = parse_value(a.r), parse_value(a.l)
    fc = r / (2 * math.pi * l)
    print("[RL 截止频率]")
    out("R", r, "Ω", scale=True)
    out("L", l, "H", scale=True)
    out("fc", fc, "Hz")


def cmd_resistor_power(a):
    r = parse_value(a.r)
    if a.v is not None:
        p = a.v * a.v / r
        src = "V=%g V, R=%s" % (a.v, fmt(r, "Ω", scale=True))
    elif a.i is not None:
        p = a.i * a.i * r
        src = "I=%g A, R=%s" % (a.i, fmt(r, "Ω", scale=True))
    else:
        print("  ! 需要 --v 或 --i")
        return
    print("[电阻功率]")
    print("  输入: %s" % src)
    out("耗散功率", p, "W")
    print("  # 0603 约 1/10W、0805 约 1/8W、1206 约 1/4W（贴片常用值，请以厂方为准）")
    if p > 0.1:
        print("  ! 超过 0603 能力；按功率选封装并留 50% 裕度")
    print("  # 陶瓷电容电压降额：额定电压留 50%；电解/钽留 80%")


def cmd_via(a):
    # 简化：过孔载流 ≈ 孔壁铜面积 × 经验系数；按 1oz 镀铜估算
    drill, plate = a.drill, a.plate
    ring = (plate - drill) / 2.0
    wall_mm2 = math.pi * ((plate / 2.0) ** 2 - (drill / 2.0) ** 2)
    # 经验：1 oz 铜过孔每 mm² 孔壁铜约承载数安（量级估算，极粗糙）
    cap = wall_mm2 * 8.0
    print("[过孔载流估算（极粗略）]")
    out("钻孔直径", drill, "mm")
    out("焊盘直径", plate, "mm")
    out("环宽", ring, "mm")
    out("孔壁铜面积", wall_mm2, "mm²")
    out("估算载流", cap, "A")
    print("  ! 该模型极粗糙，仅用于量级判断；")
    print("  ! 大电流请用多过孔并联并靠厂方数据。")


# ---------------------------------------------------------------- CLI


def build_parser():
    p = argparse.ArgumentParser(
        prog="pcbcalc.py",
        description="PCB 确定性计算器 —— 禁止心算，一律跑这里",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = p.add_subparsers(dest="cmd")

    s = sub.add_parser("trace", help="走线宽度估算")
    s.add_argument("--current", type=float, required=True, help="电流 A")
    s.add_argument("--rise", type=float, default=10, help="允许温升 °C（默认10）")
    s.add_argument("--layers", type=int, default=1, help="外层并联层数（默认1）")
    s.add_argument("--copper", default="1oz", help="铜厚 1oz 或 2oz")
    s.set_defaults(func=cmd_trace)

    s = sub.add_parser("divider", help="电阻分压")
    s.add_argument("--vin", type=float, required=True)
    s.add_argument("--r1", required=True, help="上臂，接 Vin")
    s.add_argument("--r2", required=True, help="下臂，接 GND")
    s.set_defaults(func=cmd_divider)

    s = sub.add_parser("thermal-ldo", help="LDO 结温估算")
    s.add_argument("--vin", type=float, required=True)
    s.add_argument("--vout", type=float, required=True)
    s.add_argument("--iout", type=float, required=True, help="A")
    s.add_argument("--rth", type=float, required=True, help="RθJA °C/W")
    s.add_argument("--tamb", type=float, default=25)
    s.add_argument("--tjmax", type=float, default=125)
    s.add_argument("--iq", type=float, default=None, help="静态电流 A")
    s.set_defaults(func=cmd_thermal_ldo)

    s = sub.add_parser("thermal-shunt", help="采样电阻热估算")
    s.add_argument("--i", type=float, required=True)
    s.add_argument("--r", required=True)
    s.add_argument("--rth", type=float, default=80)
    s.add_argument("--tamb", type=float, default=25)
    s.set_defaults(func=cmd_thermal_shunt)

    s = sub.add_parser("battery", help="电池续航")
    s.add_argument("--mah", type=float, required=True)
    s.add_argument("--ma", type=float, required=True)
    s.add_argument("--eff", type=float, default=None)
    s.set_defaults(func=cmd_battery)

    s = sub.add_parser("buck-inductor", help="Buck 电感估算")
    s.add_argument("--vin", type=float, required=True)
    s.add_argument("--vout", type=float, required=True)
    s.add_argument("--iout", type=float, required=True)
    s.add_argument("--fsw", type=float, default=500000)
    s.set_defaults(func=cmd_buck_inductor)

    s = sub.add_parser("rc", help="RC 截止频率")
    s.add_argument("--r", required=True)
    s.add_argument("--c", required=True)
    s.set_defaults(func=cmd_rc)

    s = sub.add_parser("rl", help="RL 截止频率")
    s.add_argument("--r", required=True)
    s.add_argument("--l", required=True)
    s.set_defaults(func=cmd_rl)

    s = sub.add_parser("resistor-power", help="电阻功率")
    s.add_argument("--r", required=True)
    s.add_argument("--v", type=float, default=None)
    s.add_argument("--i", type=float, default=None)
    s.set_defaults(func=cmd_resistor_power)

    s = sub.add_parser("via", help="过孔载流估算")
    s.add_argument("--current", type=float, required=True)
    s.add_argument("--drill", type=float, required=True, help="mm")
    s.add_argument("--plate", type=float, required=True, help="mm")
    s.set_defaults(func=cmd_via)
    return p


def main(argv=None):
    p = build_parser()
    a = p.parse_args(argv)
    if not getattr(a, "cmd", None):
        p.print_help()
        return 0
    try:
        a.func(a)
    except Exception as e:
        print("计算失败: %s" % e, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
