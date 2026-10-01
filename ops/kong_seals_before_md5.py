#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重建 src/services/seals.js 的**改前**字节并算 md5（本单改动 = 三处 replacement，逆变换即原件）。

为什么这样做：本单动手时未先取改前 md5，而工程不是 git 仓库、无原件快照。
逆变换是**确定性**的（三处的 before/after 逐字取自实际 patch 调用），
所以重建结果应与改动前磁盘字节逐字节相同；本脚本在报告里如实标注这一点。
"""
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = "/Users/kevin/bistro/xiai/src/services/seals.js"

PATCHES = [
    # (after, before)  —— 逆变换：把 after 换回 before
    (
        "import { IMAGE_LIMITS, STORED_MAX_BYTES, describeBytes, sniffBytesMime } from '../utils/image.js'",
        "import { IMAGE_LIMITS, describeBytes, sniffBytesMime } from '../utils/image.js'",
    ),
    (
        """   ② **入参是浏览器端处理管线产出的二进制**（`utils/image.js` 的 `exportSquareImage`
      产物：方形 + WebP），本服务**不接收 dataURL**、不自写 canvas 处理；
      对上再兜一道**产物侧**上限与「是否真是图片」（按字节魔数判定，**不采信声称的 mime**）。
   ③ **两套上限，不得混用**（与 `photos.js` 同一口径，2026-09-20 修）：
      - **输入侧 1 MB**：判**用户选的原始文件字节**，判在 `utils/image.js` 的 `loadImageFile`，
        本服务不重复判、也不得拿这个数值去闸产物；
      - **产物侧 4 MiB**（`FACE_IMAGE_ARTIFACT_MAX_BYTES` ＝ `STORED_MAX_BYTES`
        ＝ `IMAGE_LIMITS.maxStoredBytes`，与 `photos.js` 的 `PHOTO_ARTIFACT_MAX_BYTES` **同源常量**）：
        判**处理后的二进制**。旧实现拿 1 MB 闸产物（同一病根）⇒ 浏览器编不出 WebP 回退 PNG
        （2048² ≈ 2.7 MB）时被自家闸拒，reason `TOO_LARGE`，且甩误导文案「请换一张更小的图…」，
        而用户根本没传大图——本单修掉（reason 改 `ARTIFACT_TOO_LARGE`，文案改成「本机影像生成失败」）。
        产物超限时的**降质重编**在 `utils/image.js` 的 `exportSquareImage` 里（≤3 轮），本服务只兜底拒。
   ④ **旧影像保留**：替换 ＝ 数据层「新增影像行 + 改印面指向」，本服务从不删旧影像。
   ⑤ 一律返回结构化结果（`{ok:false, reason, message}`），**不抛未捕获异常**。
   ============================================================================ */

/**
 * **产物侧**入库字节上限（＝ `utils/image.js` 的 `STORED_MAX_BYTES` ＝ `IMAGE_LIMITS.maxStoredBytes`，4 MiB）。
 *
 * 与 `photos.js` 的 `PHOTO_ARTIFACT_MAX_BYTES` **同源**（同一个导入常量，**不另写一份数值**）。
 * 为什么不能用 1 MB 闸产物：回退 PNG 的 2048² 实测 2.70–2.72 MiB（见 `utils/image.js` 注释），
 * 拿输入闸拒自家产物＝把**没传大图**的用户拒掉。
 */
export const FACE_IMAGE_ARTIFACT_MAX_BYTES = STORED_MAX_BYTES

/**
 * @deprecated 兼容别名（旧调用方仍在 import，**保留不删**）。
 * **语义已变**：历史上它＝**产物闸**（1 MB，`IMAGE_LIMITS.maxInputBytes`），
 * 即「拿输入上限闸处理后的二进制」这个病根本身；现更正为**输入侧**的文件字节上限
 * （`IMAGE_LIMITS.maxInputBytes`，1 MB）。输入侧判在 `utils/image.js` 的 `loadImageFile`；
 * **产物侧一律用 `FACE_IMAGE_ARTIFACT_MAX_BYTES`**（4 MiB）。新代码请直接读上面两个具名常量。
 */
export const FACE_IMAGE_MAX_BYTES = IMAGE_LIMITS.maxInputBytes""",
        """   ② **入参是浏览器端处理管线产出的二进制**（`utils/image.js` 的 `exportSquareImage`
      产物：方形 + WebP），本服务**不接收 dataURL**、不自写 canvas 处理；
      对上再兜一道 1 MB 与「是否真是图片」（按字节魔数判定，**不采信声称的 mime**）。
   ③ **旧影像保留**：替换 ＝ 数据层「新增影像行 + 改印面指向」，本服务从不删旧影像。
   ④ 一律返回结构化结果（`{ok:false, reason, message}`），**不抛未捕获异常**。
   ============================================================================ */

/** 印面图入库字节上限（＝管线口径 `IMAGE_LIMITS.maxInputBytes` ＝ 1 MB）。 */
export const FACE_IMAGE_MAX_BYTES = IMAGE_LIMITS.maxInputBytes""",
    ),
    (
        """ *     未指定印面 ⇒ `MISSING_FACE`；内容空 ⇒ `EMPTY_CONTENT`；
 *     **产物超上限（4 MiB）⇒ `ARTIFACT_TOO_LARGE`**（文案＝「本机影像生成失败」，与输入侧分开）；""",
        """ *     未指定印面 ⇒ `MISSING_FACE`；内容空 ⇒ `EMPTY_CONTENT`；超 1 MB ⇒ `TOO_LARGE`；""",
    ),
    (
        """  /* 产物侧兜底：判的是**处理后的二进制**（`FACE_IMAGE_ARTIFACT_MAX_BYTES`＝4 MiB），
     **不是**输入文件的 1 MB —— 后者判在 `utils/image.js` 的 `loadImageFile`（本服务不重复判）。
     文案必须与输入侧分开：这里说「本机影像生成失败」，**不得**再说「请换一张更小的图…」
     （用户没传大图，旧实现就是把这句话甩给回退 PNG 的用户）。 */
  if (bytes.length > FACE_IMAGE_ARTIFACT_MAX_BYTES) {
    return {
      ok: false,
      reason: 'ARTIFACT_TOO_LARGE',
      previousFaceImageId,
      message:
        `本机影像生成失败：印面图处理后 ${describeBytes(bytes.length)} 超过入库上限 ` +
        `${describeBytes(FACE_IMAGE_ARTIFACT_MAX_BYTES)}。` +
        '这与「所选文件 ≤ 1 MB」的输入上限是两回事；请重试，或改用支持 WebP 编码的浏览器后再上传。'
    }
  }""",
        """  if (bytes.length > FACE_IMAGE_MAX_BYTES) {
    return {
      ok: false,
      reason: 'TOO_LARGE',
      previousFaceImageId,
      message:
        `印面图过大：当前内容 ${describeBytes(bytes.length)}，上限 ${describeBytes(FACE_IMAGE_MAX_BYTES)}（1 MB）。` +
        '请换一张更小的图，或先用手机 / 系统自带的压缩再上传。'
    }
  }""",
    ),
]


def main():
    now = open(SRC, encoding="utf-8").read()
    original = now
    for after, before in PATCHES:
        if after not in original:
            print("!! 逆变换失配（after 片段未找到）：%s..." % after[:60].replace("\n", "\\n"))
            return 2
        original = original.replace(after, before, 1)
    out = os.path.join(HERE, "kong_seals_js_before_reconstructed.js")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(original)
    print("改后 src/services/seals.js  md5 = %s  (%d bytes)" % (hashlib.md5(now.encode("utf-8")).hexdigest(), len(now.encode("utf-8"))))
    print("改前（逆变换重建）          md5 = %s  (%d bytes)" % (hashlib.md5(original.encode("utf-8")).hexdigest(), len(original.encode("utf-8"))))
    print("重建件落盘：%s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
