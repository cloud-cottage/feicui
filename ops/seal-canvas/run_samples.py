#!/usr/bin/env python
"""「O 件成品化」10 张样张 · **证据复跑脚本**（Kong 单 · 2026-10-13）。

5 枚印 × 2 种主体口径（A＝印章本体紧致外接框 / B＝整幅原片）＝ **10 张成品**，
每张出 `PNG（预览）＋ TIFF（无损）＋ 「原片｜成品」对照图`。

算法实现：`server/app/seal_canvas.py`（纯函数 ＋ CLI，**唯一实现**）。

## 红线（本脚本自身）

* **只读 O 件**：先把选定的 O 件 `shutil.copy2` 到 **scratch**（`SEAL_CANVAS_SRC`），之后一律读 scratch 副本
  —— 因**目录键迁移正在并行执行**（实测：`7806350950/`→`9787806350959/`、`福庵印缀 原版 高清/`→`福庵印缀/`），
  且 O 件文件名（`P8-C1-R3-O.tiff`）**跨书会撞名**（同页同列同行号在不同书里都有）。
* **不写** `output/books/**`、不建 job、不写库、不删文件；产物只落本目录 `samples/`。

## 复跑

```bash
cd /Users/kevin/bistro/xiai/feicui
./venv/bin/python ops/seal-canvas/run_samples.py            # 默认读 scratch（缺失则按 DB 快照重取）
./venv/bin/python ops/seal-canvas/run_samples.py --refresh   # 强制从仓库 O 件重新拷贝到 scratch
```
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

from server.app import seal_canvas as sc  # noqa: E402

SCRATCH_DEFAULT = Path.home() / ".hermes/profiles/zang/cache/scratch/seal-canvas-work"
DB_SNAPSHOT_DEFAULT = SCRATCH_DEFAULT / "yinpu.snapshot.db"

# ── 选样表（5 枚印；**dup_kind IS NULL 全部核过**；覆盖 小/中/大/异形长条 ＋ 第三本书）
#    `db_img_path_tiff` ＝ 选样时**生产库快照**里的校正件路径（O 件 ＝ 把 `.tiff` 换成 `-O.tiff`）。
SAMPLES = [
    {
        "role": "small", "seal_id": 74, "caliber_note": "小印（126×130；朱文，印泥紧贴裁切边）",
        "pdf_name": "秦汉印典 上海书画 金怀英  1997 ok.pdf", "page": 8, "col": 1, "row": 3,
        "db_img_path_tiff": "output/books/7806350950/P8-C1-R3.tiff",
        "o_name": "P8-C1-R3-O.tiff", "o_size_expected": [126, 130], "dup_kind": None,
        "note": "原拟用 tmp.pdf p13 小印 —— 实测该页 O 件多为**全白/近白**（见 README §6 数据发现），改选此枚",
    },
    {
        "role": "medium", "seal_id": 389, "caliber_note": "中印（306×297；印泥占比 0.51）",
        "pdf_name": "秦印类编 检索版.pdf", "page": 36, "col": 2, "row": 6,
        "db_img_path_tiff": "output/books/秦印类编 检索版/P36-C2-R6.tiff",
        "o_name": "P36-C2-R6-O.tiff", "o_size_expected": [306, 297], "dup_kind": None,
        "note": "",
    },
    {
        "role": "large", "seal_id": 7990, "caliber_note": "大印（737×738；唯一有纸边余量的样本 margin=11）",
        "pdf_name": "福庵印缀 原版 高清.pdf", "page": 110, "col": 1, "row": 2,
        "db_img_path_tiff": "output/books/福庵印缀 原版 高清/P110-C1-R2.tiff",
        "o_name": "P110-C1-R2-O.tiff", "o_size_expected": [737, 738], "dup_kind": None,
        "note": "Zang 指定样本（「福庵 p110 那种 737×738」）",
    },
    {
        "role": "strip", "seal_id": 5863, "caliber_note": "异形长条（223×374 竖条；库内最长轴比 1.68）",
        "pdf_name": "秦印类编 检索版.pdf", "page": 663, "col": 1, "row": 3,
        "db_img_path_tiff": "output/books/秦印类编 检索版/P663-C1-R3.tiff",
        "o_name": "P663-C1-R3-O.tiff", "o_size_expected": [223, 374], "dup_kind": None,
        "note": "库内 `dup_kind IS NULL` 行**最长轴比仅 1.68**（无更极端长条）⇒ 以该枚代表「异形」",
    },
    {
        "role": "fifth", "seal_id": 7275, "caliber_note": "第五枚（255×186 横向；第三个书源）",
        "pdf_name": "黄牧甫印谱_(西泠印社)_(z-library.sk,_1lib.sk,_z-lib.sk).pdf", "page": 13, "col": 3, "row": 1,
        "db_img_path_tiff": "output/books/黄牧甫印谱/P13-C3-R1.tiff",
        "o_name": "P13-C3-R1-O.tiff", "o_size_expected": [255, 186], "dup_kind": None,
        "note": "",
    },
]


def resolve_and_copy(sample: dict, src_dir: Path, db_snapshot: Path, *, refresh: bool) -> dict:
    """把 O 件落到 scratch（**只读仓库**）。名字撞名 ⇒ 用**像素尺寸**对齐（`o_size_expected`）。"""
    dst = src_dir / f"{sample['role']}_{sample['seal_id']}_{sample['o_name']}"
    info: dict = {"scratch": str(dst)}
    if dst.is_file() and not refresh:
        info["source"] = "scratch_hit"
        return info
    cands: list[Path] = []
    first = REPO / sample["db_img_path_tiff"].replace(".tiff", "-O.tiff")
    if first.is_file():
        cands.append(first)
    cands += sorted(REPO.glob(f"output/books/*/{sample['o_name']}"))
    picked = None
    for c in cands:
        try:
            import numpy as np
            from PIL import Image
            with Image.open(c) as im:
                if list(im.size) == list(sample["o_size_expected"]):
                    picked = c
                    break
        except Exception:
            continue
    if picked is None:
        info["source"] = "MISSING"
        return info
    src_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(picked, dst)
    info["source"] = str(picked.relative_to(REPO))
    info["source_moved"] = bool(first.is_file() is False)
    return info


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="O 件成品化 10 张样张（证据复跑）")
    ap.add_argument("--src-dir", default=str(SCRATCH_DEFAULT / "src"))
    ap.add_argument("--db-snapshot", default=str(DB_SNAPSHOT_DEFAULT))
    ap.add_argument("--out", default=str(HERE / "samples"))
    ap.add_argument("--summary", default=str(HERE / "summary.json"))
    ap.add_argument("--refresh", action="store_true", help="强制重新从仓库拷贝 O 件到 scratch")
    ap.add_argument("--seed", type=int, default=sc.BG_SEED_DEFAULT)
    args = ap.parse_args(argv)

    src_dir = Path(args.src_dir).expanduser()
    inputs = []
    prov = []
    for s in SAMPLES:
        got = resolve_and_copy(s, src_dir, Path(args.db_snapshot), refresh=args.refresh)
        inputs.append({"name": f"{s['role']}{s['seal_id']}", "path": got.get("scratch", ""),
                       "meta": {**s, **got}})
        prov.append({**s, **got})

    summary = sc.run_batch(inputs, Path(args.out), calibers=list(sc.CALIBERS), seed=args.seed,
                           halo_policy=sc.HALO_POLICY_SEAL)
    summary["selection"] = prov
    summary["provenance"] = {
        "source_rule": "文档库 output/books/<目录键>/P<页>-C<列>-R<行>-O.tiff（-O ＝ 原始切片，未做颜色处理）",
        "scratch_dir": str(src_dir),
        "db_snapshot": str(Path(args.db_snapshot)),
        "filter": "stamps.dup_kind IS NULL（**已排除**去重标记件）",
        "migration_note": "选样时并行执行目录键迁移 ⇒ 全部样本已先拷到 scratch 再处理",
    }

    # ── 附加读数（**不加图片**）：B 口径 halo_policy="paper" 探针 ⇒ 供「晕染落点」待裁参考
    import numpy as np
    from PIL import Image
    probe = []
    for s, got in zip(SAMPLES, prov):
        p = Path(got.get("scratch", ""))
        if not p.is_file():
            continue
        arr = np.asarray(Image.open(p).convert("RGB"))
        row = {"name": f"{s['role']}{s['seal_id']}", "caliber": "B"}
        for pol in (sc.HALO_POLICY_SEAL, sc.HALO_POLICY_PAPER):
            r = sc.compose(arr, caliber=sc.CALIBER_B, halo_policy=pol, seed=args.seed)
            rd = r["readings"]
            row[pol] = {
                "band_px_on_paste_region": rd["halo"]["band_px_on_paste_region"],
                "effect_on_paste_region_mean_abs_delta_rgb": rd["halo"]["effect_on_paste_region_mean_abs_delta_rgb"],
                "max_abs_diff_over_paste_region": rd["freeze"]["max_abs_pixel_diff_vs_resampled_source"],
                "alpha_band_max": rd["halo"]["alpha_band_max"],
                "alpha_inside_mask_max": rd["halo"]["alpha_inside_mask_max"],
            }
        probe.append(row)
    summary["policy_probe_caliber_B"] = probe

    Path(args.summary).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── 人读表
    lines = ["# O 件成品化 · 10 张样张读数（run_samples.py）", ""]
    hdr = ("样本", "口径", "画布", "主体", "62%", "居中", "印区逐像素差", "往返SSIM", "背景印泥", "晕染内", "晕染max")
    lines.append("| " + " | ".join(hdr) + " |")
    lines.append("|" + "---|" * len(hdr))
    n_ok = 0
    for smp in summary["samples"]:
        if smp.get("error") or not smp.get("outputs"):
            lines.append(f"| {smp['name']} | – | **{smp.get('error','no output')}** |" + " |" * (len(hdr) - 3))
            continue
        for o in smp["outputs"]:
            if o.get("error"):
                lines.append(f"| {smp['name']} | {o['caliber']} | **{o['error']}** |" + " |" * (len(hdr) - 3))
                continue
            r = o["readings"]; c = r["composition"]; f = r["freeze"]; b = r["bg_no_seal"]; h = r["halo"]
            lines.append(
                f"| {smp['name']} | {o['caliber']} | {c['canvas_size'][0]}×{c['canvas_size'][1]} "
                f"| {c['subject_size'][0]}×{c['subject_size'][1]} | {c['subject_ratio_actual']:.4f} "
                f"| {c['center_offset_px']} | {f['max_abs_pixel_diff_vs_resampled_source']} "
                f"| {f['roundtrip_ssim_vs_source_crop']:.4f} | {b['ink_px_in_generated_background']} "
                f"| {h['alpha_inside_mask_max']} | {h['alpha_band_max']} |")
            n_ok += 1
    lines.append("")
    lines.append(f"合计样张：{n_ok} / {len(SAMPLES) * 2}")
    txt = "\n".join(lines)
    (HERE / "run_output.txt").write_text(txt + "\n", encoding="utf-8")
    print(txt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
