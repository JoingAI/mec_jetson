#!/usr/bin/env python3
"""在 /boot/extlinux/extlinux.conf 里新增/更新 LABEL y306-mixed-<profile>。

模板取自已有的 LABEL（优先 JetsonIO，其次 primary），只替换 OVERLAYS 里的
camera dtbo，保留该板原有的 board dtbo / FDT / APPEND，避免把 Y306 和 F306
的启动参数写错。
"""
import re
import sys

CONF = "/boot/extlinux/extlinux.conf"
CAM_RE = re.compile(r"camera-p3768-[A-Za-z0-9_.\-]+\.dtbo")


def main():
    if len(sys.argv) != 2:
        print("usage: extlinux-add.py <profile a|b|c>")
        return 2
    prof = sys.argv[1]
    label = "y306-mixed-%s" % prof
    dtbo = "/boot/tegra234-p3767-camera-p3768-y306-mixed-%s.dtbo" % prof

    s = open(CONF).read()
    blocks = re.split(r"\n(?=LABEL )", s)

    tmpl = None
    for pref in ("LABEL JetsonIO\n", "LABEL primary\n"):
        for b in blocks:
            if b.startswith(pref):
                tmpl = b
                break
        if tmpl:
            break
    if tmpl is None:
        print("ERR: 找不到可用的模板 label（JetsonIO/primary）")
        return 1

    overlays = re.search(r"^\s+OVERLAYS (.*)$", tmpl, re.M)
    if not overlays:
        print("ERR: 模板 label 没有 OVERLAYS 行")
        return 1
    items = [x.strip() for x in overlays.group(1).split(",") if x.strip()]
    keep = [x for x in items if not CAM_RE.search(x)]
    new_overlays = ",".join(keep + [dtbo])

    nb = tmpl
    nb = re.sub(r"^LABEL .*$", "LABEL " + label, nb, count=1, flags=re.M)
    nb = re.sub(r"^\s+MENU LABEL .*$",
                "      MENU LABEL Y306 mixed profile %s" % prof,
                nb, count=1, flags=re.M)
    nb = re.sub(r"^\s+OVERLAYS .*$", "      OVERLAYS " + new_overlays,
                nb, count=1, flags=re.M)

    out, replaced = [], False
    for b in blocks:
        if b.startswith("LABEL " + label + "\n"):
            out.append(nb.rstrip("\n") + "\n")
            replaced = True
        else:
            out.append(b)
    if not replaced:
        out.append(nb.rstrip("\n") + "\n")

    text = "\n".join(out)
    text = re.sub(r"^DEFAULT .*$", "DEFAULT " + label, text, count=1, flags=re.M)
    open(CONF, "w").write(text)
    print("LABEL %s -> %s" % (label, new_overlays))
    return 0


if __name__ == "__main__":
    sys.exit(main())
