#!/usr/bin/env python
"""惰性 `paddleocr` 替身的**语义等价**自测（OCR 路径未被破坏）——Kong / 斐萃收尾。

本单把 `import processor` 之前往 `sys.modules["paddleocr"]` 装了替身模块（`app/ocr_lazy.py`）。
这必然要回答一个问题：**OCR 路径还对不对？** 本脚本用「假真包」注入的方式给出证据，全程
**不加载**真 PaddleOCR 模型（不占内存、不联网、秒级完成）：

  ① 造一个假包 `paddleocr`（记录被调用的 args/kwargs）放在 `sys.path[0]`，遮蔽真包；
  ② 装替身 → `import processor`；
  ③ 断言 `processor.PaddleOCR is LazyPaddleOCR`（processor 拿到的是替身）；
  ④ 调 `processor._get_ocr()` → 断言替身**弹出自己**并 import 到**假真包**、用
     **原样 args/kwargs** 构造了它（`use_angle_cls=False, lang="ch"` 逐字不变）；
  ⑤ 断言 `_get_ocr()` 的缓存语义不变（第二次调用返回同一实例，假真包只被构造一次）；
  ⑥ 断言 `processor.AREA_SCALE` / `detect_stamp_regions` 仍在（检测口径未受影响）；
  ⑦ 反例：`FEICUI_SQUARE_NO_LAZY_OCR=1` 时**不装替身**（可回滚）。

用法：`server/.venv/bin/python server/selftest/verify_square_lazy_ocr.py`（无 cv2 依赖，纯 stdlib）
退出码 0 ＝ 全部通过。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
ROOT = SERVER_DIR.parent

# 子进程必须用 **worker 解释器**（`processor.py` 需要 cv2/pymupdf，接口层 server/.venv 里没有）；
# 外层脚本本身只要 stdlib ⇒ 用哪个解释器跑都可以。
WORKER_PY = ROOT / "venv" / "bin" / "python"

FAKE_PKG = '''"""假真包：只记录构造调用，不加载任何模型。"""
CALLS = []


class PaddleOCR:
    def __init__(self, *args, **kwargs):
        CALLS.append({"args": list(args), "kwargs": dict(kwargs)})
        self.is_fake_real = True

    def predict(self, img):
        return [{"fake": True}]
'''

CHILD = '''
import json, os, sys
fake_dir = sys.argv[1]
# 顺序要紧：先放 ROOT / SERVER_DIR，最后放假包 ⇒ 最终 sys.path = [假包, SERVER_DIR, ROOT, ...]
# （与 square_runner.py 的 sys.path 口径一致：SERVER_DIR 必须先于 ROOT，否则 `app` 会撞上 ROOT/app.py）
sys.path.insert(0, {root!r})
sys.path.insert(0, {server!r})
sys.path.insert(0, fake_dir)          # 遮蔽真 paddleocr
from app.ocr_lazy import LazyPaddleOCR, install_lazy_paddleocr, is_installed

installed = install_lazy_paddleocr()
import processor                      # 必须在装替身之后（真实调用顺序同 square_runner.py）
import paddleocr as po

res = {{"installed": installed, "is_installed": is_installed(),
       "shim_before_ocr": po.PaddleOCR is LazyPaddleOCR,
       "processor_cls_is_shim": processor.PaddleOCR is LazyPaddleOCR}}

inst1 = processor._get_ocr()
inst2 = processor._get_ocr()
res["cached_same_instance"] = inst1 is inst2
res["delegated_to_real"] = bool(getattr(inst1, "is_fake_real", False))
res["proxy_predict"] = inst1.predict(None)
res["calls"] = sys.modules["paddleocr"].CALLS
res["paddleocr_now_is_real"] = not is_installed()
res["area_scale_ok"] = abs(processor.AREA_SCALE - (400.0 / 144.0) ** 2) < 1e-12
res["detect_callable"] = callable(processor.detect_stamp_regions)
print("RESULT=" + json.dumps(res))
'''


def main() -> int:
    print("=" * 100)
    print("惰性 paddleocr 替身：OCR 路径语义等价自测（不加载真模型）")
    print(f"  SERVER_DIR={SERVER_DIR}   ROOT={ROOT}")
    print("=" * 100)
    tmp = Path(tempfile.mkdtemp(prefix="feicui_lazy_ocr_"))
    fails: list[str] = []
    try:
        pkg = tmp / "paddleocr"
        pkg.mkdir()
        (pkg / "__init__.py").write_text(FAKE_PKG, encoding="utf-8")
        script = tmp / "_child.py"
        script.write_text(CHILD.format(server=str(SERVER_DIR), root=str(ROOT)), encoding="utf-8")

        env = dict(os.environ)
        env.pop("FEICUI_SQUARE_NO_LAZY_OCR", None)
        proc = subprocess.run(
            [str(WORKER_PY), str(script), str(tmp)],
            capture_output=True,
            cwd=str(ROOT),
            env=env,
            timeout=120,
        )
        out = proc.stdout.decode("utf-8", "replace")
        line = next((ln for ln in out.splitlines() if ln.startswith("RESULT=")), None)
        if line is None:
            print(out[-2000:])
            print(proc.stderr.decode("utf-8", "replace")[-2000:])
            print("FAIL：子进程未产出 RESULT")
            return 1
        import json

        r = json.loads(line[len("RESULT="):])

        def check(ok, label, extra=""):
            print(f"  [{'PASS' if ok else 'FAIL'}] {label}{(' — ' + str(extra)) if extra else ''}")
            if not ok:
                fails.append(label)

        check(r["installed"] is True, "① 替身被装上", r["installed"])
        check(r["processor_cls_is_shim"], "② processor.PaddleOCR 解析到替身（不是真包）")
        check(
            r["calls"] == [{"args": [], "kwargs": {"use_angle_cls": False, "lang": "ch"}}],
            "③ _get_ocr() 用**原样** args/kwargs 构造了真类（use_angle_cls=False, lang=ch 逐字不变）",
            r["calls"],
        )
        check(r["delegated_to_real"], "④ 替身实例真的代理到真类实例（is_fake_real=True）")
        check(r["cached_same_instance"], "⑤ _get_ocr() 缓存语义不变（两次同一实例）")
        check(r["calls"] and len(r["calls"]) == 1, "⑥ 真类只被构造一次（未重复加载）")
        check(r["proxy_predict"] == [{"fake": True}], "⑦ 替身对任意方法透明转发（predict 可用）")
        check(r["paddleocr_now_is_real"], "⑧ OCR 被点用之后 sys.modules 里已换回真包")
        check(r["area_scale_ok"], "⑨ processor.AREA_SCALE 不变（＝(400/144)²）")
        check(r["detect_callable"], "⑩ processor.detect_stamp_regions 仍在（检测口径不受影响）")

        print("\n---- 反例：FEICUI_SQUARE_NO_LAZY_OCR=1 ⇒ 不装替身（可回滚）----")
        env2 = dict(env)
        env2["FEICUI_SQUARE_NO_LAZY_OCR"] = "1"
        proc2 = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; sys.path.insert(0, %r); from app.ocr_lazy import install_lazy_paddleocr, is_installed;"
                " print('OFF=' + str(install_lazy_paddleocr()), 'installed=' + str(is_installed()))"
                % str(SERVER_DIR),
            ],
            capture_output=True,
            cwd=str(ROOT),
            env=env2,
            timeout=60,
        )
        off_out = proc2.stdout.decode("utf-8", "replace").strip()
        check("OFF=False" in off_out and "installed=False" in off_out, "⑪ 开关生效：不装替身", off_out)

        print("=" * 100)
        if fails:
            print(f"结论：FAIL（{len(fails)} 项）→ {fails}")
            return 1
        print("结论：PASS —— 惰性替身对 OCR 路径语义等价，且可一键回滚")
        print("=" * 100)
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
