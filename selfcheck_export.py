#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""feicui 汇入线 F1 自检脚本（可复跑）。

跑法：
    cd feicui && ./venv/bin/python selfcheck_export.py            # 全量自检
    cd feicui && ./venv/bin/python selfcheck_export.py --no-export  # 只读上一次的包做统计，不新导批次

覆盖：
  1. 现有 65 条整书导出 → 每本书一个 batch_id（包 JSONL 行数 / 影像复制数 / 盒内计数报告）
  2. §9.3 十七项字段的**必填覆盖率**（逐项分别报：present/total、%、哨兵占比、缺失原因）
  3. §9.4 五项计数在 feicui 侧可判定的部分 + 明确标注「待平台回执」的部分
  4. 既有 `stamps` 表在导出前后逐行 diff（证明现有管线与 65 条数据未被改动）
  5. 逻辑自测（沙箱 fixture，不动真实库）：必填齐备 ⇒ 进正式包；必填缺失 ⇒ DRAFT+拒收原因；
     §9.4 幂等（同 dedupe_key 重跑 ⇒ skipped）；dedupe_key 公式独立复算比对

输出：stdout 表格 + exports/selfcheck_report.json（机器可读）
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import export as X  # noqa: E402

ROOT = X.ROOT
LINE = "=" * 100


def jload(p: Path, default=None):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def read_jsonl(p: Path) -> list[dict]:
    out = []
    with open(p, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError as e:
                    raise SystemExit(f"{p}:{i} JSONL 解析失败：{e}")
    return out


# ---------------------------------------------------------------------------
# 真实数据部分
# ---------------------------------------------------------------------------


def run_real_exports(do_export: bool) -> tuple[list[dict], dict]:
    conn = X.connect()
    X.ensure_schema(conn)
    before = X.stamps_snapshot(conn)
    conn.close()

    if do_export:
        reports = X.export_all()
    else:
        reports = []
        for d in sorted(X.EXPORT_ROOT.glob("fb_*")):
            rp = d / "report.json"
            if rp.exists():
                reports.append(jload(rp))

    conn = X.connect()
    after = X.stamps_snapshot(conn)
    conn.close()
    integrity = {
        "stampsRowsBefore": len(before),
        "stampsRowsAfter": len(after),
        "stampsUnchanged": before == after,
        "diffSample": [
            {"before": b, "after": a}
            for b, a in zip(before, after) if b != a
        ][:3],
    }
    return reports, integrity


def package_facts(report: dict) -> dict:
    pkg = ROOT / report["package"]["dir"]
    seals = read_jsonl(pkg / report["package"]["sealsJsonl"])
    draft = read_jsonl(pkg / report["package"]["draftJsonl"])
    images = sorted((pkg / "images").glob("*")) if (pkg / "images").exists() else []
    return {"pkg": pkg, "seals": seals, "draft": draft, "images": images}


# ---------------------------------------------------------------------------
# 打印
# ---------------------------------------------------------------------------


def print_batch_table(facts: list[tuple[dict, dict]]) -> None:
    print(LINE)
    print("① 批次导出包（一本书 = 一个 batch_id）")
    print(LINE)
    hdr = f"{'batch_id':<26}{'book':<22}{'JSONL 正式':>10}{'DRAFT':>7}{'合计':>6}{'影像复制':>9}{'拒收':>6}{'已跳过':>7}{'待平台回执':>11}"
    print(hdr)
    for rep, f in facts:
        c = rep["counts"]["feicuiDecidable"]
        print(f"{rep['batchId']:<26}{rep['book']['bookKey']:<22}"
              f"{len(f['seals']):>10}{len(f['draft']):>7}{len(f['seals']) + len(f['draft']):>6}"
              f"{len(f['images']):>9}{c['rejectedRequiredMissing']:>6}"
              f"{c['skippedDuplicateCandidate']:>7}"
              f"{len(rep['counts']['awaitingPlatformReceipt']) - 1:>11}")
    print()
    for rep, f in facts:
        print(f"  · {rep['batchId']}  包目录 {rep['package']['dir']}")
        print(f"      sealCode 状态={rep['book']['shortCodeState']}  批次号占位={rep['book']['batchIdUsesPlaceholderShortCode']}  "
              f"coordDpi={rep['book']['coordDpi']}({rep['book']['coordDpiSource']})")
        print(f"      §9.4 计数：feicui 可判定={json.dumps(rep['counts']['feicuiDecidable'], ensure_ascii=False)}")
        print(f"      §9.4 计数：待平台回执={list(rep['counts']['awaitingPlatformReceipt'].keys())}")
        for w in rep["warnings"]:
            print(f"      ⚠ {w}")


def coverage_table(records: list[dict], title: str) -> dict:
    cov = X.coverage_of(records)
    print(LINE)
    print(title)
    print(LINE)
    print(f"{'#':<3}{'feicui 字段':<38}{'平台字段':<44}{'必填':<5}{'有值':>6}{'/总':>6}{'覆盖%':>8}{'非哨兵':>8}")
    for spec in X.FIELD_SPECS:
        c = cov[spec["key"]]
        flag = "必填" if spec["required"] else "选填"
        print(f"{spec['no']:<3}{spec['key']:<38}{spec['platform']:<44}{flag:<5}"
              f"{c['present']:>6}{c['total']:>6}{(c['presentPct'] if c['presentPct'] is not None else 0):>8.2f}"
              f"{c['presentNonSentinel']:>8}")
    print()
    print("  缺失原因（按项）:")
    for spec in X.FIELD_SPECS:
        c = cov[spec["key"]]
        if c["missing"]:
            print(f"    - #{spec['no']} {spec['key']}: 缺 {c['missing']}/{c['total']} → "
                  + json.dumps(c["missingReasons"], ensure_ascii=False))
    print()
    print("  必填项覆盖率（逐项，§9.3 必填口径）:")
    for spec in X.FIELD_SPECS:
        if not spec["required"]:
            continue
        c = cov[spec["key"]]
        print(f"    #{spec['no']:<3}{spec['key']:<38}{spec['platform']:<44}"
              f"{c['present']}/{c['total']} = {c['presentPct']}%  (非哨兵值 {c['presentNonSentinel']})")
    return cov


# ---------------------------------------------------------------------------
# 逻辑自测（沙箱，不动真实库）
# ---------------------------------------------------------------------------


def logic_selftest() -> list[dict]:
    results = []

    def check(name, ok, detail=""):
        results.append({"name": name, "ok": bool(ok), "detail": detail})
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

    print(LINE)
    print("④ 逻辑自测（沙箱 fixture：真实 yinpu.db 与 config/ 全不参与）")
    print(LINE)

    with tempfile.TemporaryDirectory(prefix="feicui_selftest_") as td:
        td = Path(td)
        cdir = td / "config"
        cdir.mkdir(parents=True)
        db = td / "yinpu.db"
        out = td / "exports"
        book = "自检样本 测试出版社 张三 ok.pdf"
        img = td / "face.png"
        from PIL import Image

        Image.new("RGB", (40, 40), (200, 40, 40)).save(img)  # 高红占比 → 白文
        img_sha = hashlib.sha256(img.read_bytes()).hexdigest()

        import sqlite3

        conn = sqlite3.connect(db)
        conn.execute(
            """CREATE TABLE stamps (id INTEGER PRIMARY KEY, pdf_name TEXT, page INTEGER, idx INTEGER,
               text TEXT, img_path TEXT, x1 REAL, y1 REAL, x2 REAL, y2 REAL)"""
        )
        conn.executemany(
            "INSERT INTO stamps (pdf_name,page,idx,text,img_path,x1,y1,x2,y2) VALUES (?,?,?,?,?,?,?,?,?)",
            [
                (book, 3, 1, "長樂之印", str(img), 100.0, 100.0, 200.0, 200.0),   # 必填齐备
                (book, 3, 0, "", str(img), 100.0, 400.0, 200.0, 500.0),           # 缺印名 ⇒ DRAFT
            ],
        )
        conn.commit()
        conn.close()

        (cdir / "templates.json").write_text(json.dumps({
            book: {
                "hsv_low": [0, 120, 70], "hsv_high": [10, 255, 255], "min_area": 800,
                "text_offset": [-120, 0, 110, 140], "density_min": 0.002, "density_max": 0.08,
                "page_range": [1, 10], "edge_enabled": True, "pad_ratio": 0.15,
                "default_dynasty": "测试朝", "default_seal_type": "NAME_SEAL",
                "default_seal_type_source": "fixture", "default_dynasty_source": "fixture",
                "style_red_ratio_threshold": 0.5,
            }
        }, ensure_ascii=False), encoding="utf-8")
        (cdir / "book_codes.json").write_text(json.dumps({
            "schema": "yinsuo.feicui.book_codes.v1",
            "books": {book: {"key": "FIX", "short_code": "FIXT", "issued": True,
                             "issued_at": "2026-01-01T00:00:00+08:00", "issued_by": "fixture",
                             "short_code_source": "fixture_issued"}},
        }, ensure_ascii=False), encoding="utf-8")
        (cdir / "book_geometry.json").write_text(json.dumps({
            "schema": "yinsuo.feicui.book_geometry.v1",
            "books": {"FIX": {"coord_dpi": 144, "coord_dpi_source": "fixture",
                              "pages_pt": {"3": [521.0, 734.0]}}},
        }, ensure_ascii=False), encoding="utf-8")

        env = dict(os.environ, FEICUI_DB=str(db), FEICUI_CONFIG_DIR=str(cdir), FEICUI_EXPORT_ROOT=str(out))
        cmd = [sys.executable, str(ROOT / "export.py"), "export", "--book", book, "--date", "20260101"]

        def run():
            p = subprocess.run(cmd, env=env, capture_output=True, text=True)
            if p.returncode != 0:
                raise SystemExit("fixture export 失败：\n" + p.stdout + p.stderr)
            return p.stdout.strip()

        out1 = run()
        pkgs = sorted(out.glob("fb_*"))
        check("沙箱产出 1 个批次包", len(pkgs) == 1, out1)

        pkg = pkgs[0]
        seals = read_jsonl(pkg / "seals.jsonl")
        draft = read_jsonl(pkg / "draft.jsonl")
        rep = jload(pkg / "report.json")

        check("必填齐备条目进正式包（seals.jsonl=1 行）", len(seals) == 1, f"draft={len(draft)} 行")
        check("必填缺失条目进 DRAFT（draft.jsonl=1 行）", len(draft) == 1)
        formal = seals[0] if seals else {}
        dr = draft[0] if draft else {}

        check("正式条目 reviewStatus=MACHINE_EXTRACTED", formal.get("reviewStatus") == "MACHINE_EXTRACTED",
              str(formal.get("reviewStatus")))
        check("正式条目 sealCode 已签发（书简码 issued=true）", formal.get("sealCode") == "FIXT-p0003-01",
              str(formal.get("sealCode")))
        check("DRAFT 条目带 missingRequired + reject 原因",
              dr.get("feicui", {}).get("missingRequired") == ["seal_name"]
              and any("MISSING_REQUIRED:seal_name" in r for r in dr.get("feicui", {}).get("draftReasons", [])),
              json.dumps(dr.get("feicui", {}).get("missingRequired"), ensure_ascii=False))

        a0 = (formal.get("assets") or [{}])[0]
        check("sha256 = 源文件实际 sha256", a0.get("sha256") == img_sha, str(a0.get("sha256"))[:16])
        check("尺寸/字节数/colorMode 齐备",
              all(a0.get(k) is not None for k in ("bytes", "width", "height", "colorMode")),
              f"{a0.get('width')}x{a0.get('height')} {a0.get('bytes')}B {a0.get('colorMode')}")
        check("朱白推断有值（含证据占比）",
              formal.get("sealStyle") in ("ZHU_WEN", "BAI_WEN")
              and formal["ext"]["sealStyleEvidence"]["redRatio"] is not None,
              f"{formal.get('sealStyle')} redRatio={formal['ext']['sealStyleEvidence']['redRatio']}")
        check("相对 bbox 与页几何齐备（coord_dpi 标定生效）",
              formal["bbox"]["relX1"] is not None and formal["bbox"]["pageWidthPt"] == 521.0,
              f"relX1={formal['bbox']['relX1']}")

        # dedupe_key 公式独立复算：sha256(sourceBook|page|quantize(bbox,1pt)|kind)
        q = tuple(int(round(v * 72.0 / 144)) for v in (100.0, 100.0, 200.0, 200.0))
        expect = hashlib.sha256(f"{formal.get('sourceBook')}|3|{q[0]},{q[1]},{q[2]},{q[3]}|FACE".encode()).hexdigest()
        check("dedupe_key = §9.4 公式独立复算值", formal.get("dedupeKey") == expect,
              f"{str(formal.get('dedupeKey'))[:16]} vs {expect[:16]}")

        c1 = rep["counts"]["feicuiDecidable"]
        check("计数报告：formal=1 / draft=1 / rejected=1 / insertedCandidate=1",
              (c1["formal"], c1["draftStaged"], c1["rejectedRequiredMissing"], c1["insertedCandidate"]) == (1, 1, 1, 1),
              json.dumps(c1, ensure_ascii=False))
        check("待平台回执项明确标注",
              set(rep["counts"]["awaitingPlatformReceipt"]) >= {"inserted", "updated", "skipped", "conflicted"})

        # 幂等：同 dedupe_key 再导一次（新 batch_id）⇒ skipped，不重复入库
        run()
        pkgs2 = sorted(out.glob("fb_*"))
        rep2 = jload(pkgs2[-1] / "report.json")
        c2 = rep2["counts"]["feicuiDecidable"]
        check("§9.4 幂等：重跑后 skippedDuplicateCandidate=1 / insertedCandidate=0",
              (c2["skippedDuplicateCandidate"], c2["insertedCandidate"]) == (1, 0),
              json.dumps({k: c2[k] for k in ("insertedCandidate", "skippedDuplicateCandidate")}, ensure_ascii=False))
        check("重跑批次号自增（fb_20260101_FIXT_02）", rep2["batchId"].endswith("_02"), rep2["batchId"])

    return results


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description="feicui 汇入线 F1 自检")
    ap.add_argument("--no-export", action="store_true", help="不新导批次，仅统计已有包")
    ap.add_argument("--skip-selftest", action="store_true", help="跳过沙箱逻辑自测")
    args = ap.parse_args()

    started = dt.datetime.now().astimezone()
    print(LINE)
    print(f"feicui 汇入线 F1 自检  {started.isoformat(timespec='seconds')}  工具版本 {X.TOOL_VERSION}")
    print(LINE)

    reports, integrity = run_real_exports(not args.no_export)
    facts = [(rep, package_facts(rep)) for rep in reports]

    print_batch_table(facts)

    all_lines: list[dict] = []
    for rep, f in facts:
        all_lines.extend(f["seals"])
        all_lines.extend(f["draft"])
    cov = coverage_table(all_lines, f"② §9.3 十七项字段覆盖率（样本＝{len(all_lines)} 条导出记录，含 DRAFT）")

    required = [s for s in X.FIELD_SPECS if s["required"]]
    req_cov = {s["key"]: cov[s["key"]] for s in required}
    print(LINE)
    print("③ 必填覆盖率汇总（逐项）")
    print(LINE)
    for s in required:
        c = req_cov[s["key"]]
        print(f"  {s['key']:<16} {c['present']:>3}/{c['total']:<3} = {c['presentPct']:>6.2f}%   非哨兵值 {c['presentNonSentinel']}")
    present_all = sum(1 for r in all_lines
                      if not r["feicui"]["missingRequired"])
    print(f"\n  必填齐备（可进正式包）的条目：{present_all}/{len(all_lines)}"
          f"   ⇒ 正式包 {sum(len(f['seals']) for _, f in facts)} 行 / DRAFT 暂存 {sum(len(f['draft']) for _, f in facts)} 行")

    print(LINE)
    print("⑤ 现有管线完整性（stamps 表导出前后逐行 diff）")
    print(LINE)
    print(f"  行数 before={integrity['stampsRowsBefore']} after={integrity['stampsRowsAfter']}  "
          f"逐行一致={integrity['stampsUnchanged']}"
          + ("" if integrity["stampsUnchanged"] else f"  差异样例={integrity['diffSample']}"))

    keys = X.check_field_key_paths(all_lines)
    print(LINE)
    print(f"⑥ §9.3 十七项键路径机械校验（逐行：值可为 null，键必须在） 行数={keys['linesChecked']}")
    print(LINE)
    for spec in X.FIELD_SPECS:
        k = keys["specs"][spec["key"]]
        print(f"  [{'PASS' if k['ok'] else 'FAIL'}] #{spec['no']:<3}{spec['key']:<16} ← {', '.join(k['paths'])}"
              + ("" if k["ok"] else f"  {k['problems']}"))
    print(f"  ⇒ 全部 17 项键路径齐备={keys['allOk']}")

    selftest = [] if args.skip_selftest else logic_selftest()
    ok_all = integrity["stampsUnchanged"] and keys["allOk"] and all(t["ok"] for t in selftest)

    out_report = {
        "generatedAt": started.isoformat(timespec="seconds"),
        "toolVersion": X.TOOL_VERSION,
        "batches": [
            {
                "batchId": rep["batchId"],
                "packageDir": rep["package"]["dir"],
                "jsonl": {"seals": len(f["seals"]), "draft": len(f["draft"])},
                "imagesCopied": len(f["images"]),
                "counts": rep["counts"],
                "draftReasonCounts": rep["draftReasonCounts"],
                "warnings": rep["warnings"],
                "book": rep["book"],
            }
            for rep, f in facts
        ],
        "coverage": cov,
        "requiredCoverage": {s["key"]: {"platform": s["platform"], **req_cov[s["key"]]} for s in required},
        "totals": {
            "recordsExported": len(all_lines),
            "formalLines": sum(len(f["seals"]) for _, f in facts),
            "draftLines": sum(len(f["draft"]) for _, f in facts),
            "imagesCopied": sum(len(f["images"]) for _, f in facts),
        },
        "fieldKeyPaths": keys,
        "pipelineIntegrity": integrity,
        "logicSelftest": selftest,
        "allChecksPassed": ok_all,
    }
    out_path = X.EXPORT_ROOT / "selfcheck_report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fp:
        json.dump(out_report, fp, ensure_ascii=False, indent=2)
    print(LINE)
    print(f"自检报告已写入 {X._rel(out_path)}；总判定：{'全部通过' if ok_all else '存在失败项'}")
    print(LINE)
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
