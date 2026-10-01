# 玺爱影像管线探针 · 自动摘要（plain_green 跑，no-injection=True）

- 跑的时间：2026-09-20T18:45:11+0800
- Chrome：Chrome/153.0.8010.52（自建 headless，pid=80811，profile=/tmp/xiai-probe-profile-kong，调试口=9333）
- 回退注入（强制 toBlob 产 PNG，`XIAI_FORCE_PNG`）：False
- 解释器：/Library/Developer/CommandLineTools/usr/bin/python3（3.9.6）
- 格式判定的尺子：**产品真源** `src/utils/image.js::sniffBytesMime`（探针 bundle 内 + `kong-image-truth-bridge.js`），**无自建魔数副本**

## 断言清单（合并口径：合计 41 条 = phase1 33 条 + 印面图路径(phase3) 8 条；失败 0 条）

- 计数自洽：33 + 8 = 41（清单实长 41）⇒ OK
- 合并来源：probe_phase1(刷新前快照) + __XIAI_PROBE_RESULTS__(刷新后页面全局) + __XIAI_PROBE__.phase3()；去重键 `id`
- 为什么必须合并：phase1 刷新前快照 33 条，`Page.reload` 后页面全局只剩 8 条（phase2 只读不写、phase3 只写回自己的 8 条）

- [PASS] `login` 普通用户登录成功（手机号 + 验证码 1234）
  - 
- [PASS] `acl` 未登录上传被拒（数据层拒绝）
  - {"ok":false,"reason":"UNAUTHENTICATED","message":"请先登录后再上传实物照片"}
- [PASS] `limit-over` ① 1.2 MB 文件被拒（可读提示含真实大小与上限）
  - 照片过大：所选文件 1.20 MB，上限 1.00 MB（1 MB）。请换一张更小的图，或先用手机/系统自带的压缩再上传。
- [PASS] `limit-under` ① 900 KB 文件通过（类型与上限校验）
  - {"bytes":923276,"w":1052,"h":1052}
- [PASS] `limit-basis` ① 判据是**文件字节**（900 KB 文件的 base64 串长达 1231036 字符 > 1 MB 上限，仍通过；旧 base64 长度口径必拒）
  - {"PHOTO_MAX_BYTES":1048576,"PHOTO_MAX_LENGTH":1048576,"IMAGE_LIMITS_maxInputBytes":1048576,"oldRuleWouldReject":true,"base64Length":1231036,"base64OverOneMiB":true,"passedWithBase64OverLimit":true}
- [PASS] `limit-const` ① 上限常量＝1 MB 且不再以 base64 长度为准（PHOTO_MAX_BYTES = PHOTO_MAX_LENGTH = 1048576）
  - PHOTO_MAX_BYTES=1048576 PHOTO_MAX_LENGTH=1048576
- [PASS] `artifact-const` ① 产物侧独立上限存在且更宽（IMAGE_LIMITS.maxStoredBytes ≥ 4 MB、> 输入上限；服务层同源同值）
  - {"IMAGE_LIMITS_maxInputBytes":1048576,"IMAGE_LIMITS_maxStoredBytes":4194304,"IMAGE_LIMITS_maxStoredMiB":4,"PHOTO_ARTIFACT_MAX_BYTES":4194304,"PHOTO_MAX_BYTES":1048576,"reencodeRoundsMax":3}
- [PASS] `artifact-accept-1p2mb` ① 1.2 MB 的**产物**不再被「输入 1 MB」闸拒（产物侧另有更宽上限）
  - {"bytes":1258291,"ok":true,"rowBytes":1258291,"rowMime":"image/jpeg","message":"实物照片已上传"}
- [PASS] `artifact-over-reject` ① 超出**产物侧**上限才拒，且文案＝「本机影像生成失败」（不再甩「照片过大…请换一张更小的图」）
  - {"bytes":6291456,"ok":false,"reason":"ARTIFACT_TOO_LARGE","message":"本机影像生成失败：处理后影像 6.00 MB 超过入库上限 4.00 MB。这与「所选文件 ≤ 1 MB」的输入上限是两回事；请重试，或改用支持 WebP 编码的浏览器后再上传。","misleadingClause":false}
- [PASS] `text-split` ① 两类失败文案分开：①「你选的图太大」（输入超限）②「本机影像生成失败」（产物超限）
  - {"输入超限":"照片过大：所选文件 1.20 MB，上限 1.00 MB（1 MB）。请换一张更小的图，或先用手机/系统自带的压缩再上传。","产物超限":"本机影像生成失败：处理后影像 6.00 MB 超过入库上限 4.00 MB。这与「所选文件 ≤ 1 MB」的输入上限是两回事；请重试，或改用支持 WebP 编码的浏览器后再上传。"}
- [PASS] `square-webp` ② 3000×1200 → 方形 + WebP（width == height ≤ 2048、mime image/webp、RIFF/WEBP magic）
  - {"forcePngMode":false,"inputBytes":75149,"inputSize":"3000 × 1200","outputSize":"1200 × 1200","outputBytes":14992,"mime":"image/webp","bytesReading":{"length":14992,"productMime":"image/webp","productMimeOfBytes":"src/utils/image.js::sniffBytesMime","first12Hex":"52494646883a000057454250"}}
- [PASS] `downsample` ② 降采样：2600×2600 → 2048×2048（最长边 ≤ 2048）
  - {"inputBytes":131832,"inputSize":"2600 × 2600","outputSize":"2048 × 2048","outputBytes":37430,"mime":"image/webp"}
- [PASS] `custom-crop` ② 自定义 crop（模拟用户拖拽/缩放后的方框）被如实执行：side=800 ⇒ 800×800
  - {"width":800,"height":800,"bytes":5476}
- [PASS] `upload-1` 上传（处理后二进制）成功并返回行（mime＝image/webp）
  - {"forcePngMode":false,"ok":true,"id":"ph-mu9owpm7-6qo37","mime":"image/webp","message":"实物照片已上传"}
- [PASS] `upload-2` 第二张上传成功（id 不同、无覆盖）
  - {"id1":"ph-mu9owpm7-6qo37","id2":"ph-mu9owpma-8e4cr","ok2":true,"message2":"实物照片已上传"}
- [PASS] `row-meta` 元数据行只带标量（width/height/bytes/sha256/mime），**不含 image dataURL**
  - {"id":"ph-mu9owpm7-6qo37","sealId":"XAI-0001","stamp_id":"XAI-0001","user_id":"u-13900001234","note":"自测：非方形大图 → 方形 WebP","file_name":"photo-3000x1200.jpg","status":"APPROVED","mime":"image/webp","width":1200,"height":1200,"bytes":14992,"sha256":"a51a82442a0e64dd042add92f92b5ac971036953ee260e460f31af7f43e35c27","storage":"indexeddb","storage_key":"photo:ph-mu9owpm7-6qo37","created_at":"2026-09-20T10:45:12.752Z"}
- [PASS] `fallback-png` ⑤ 编码回退（toBlob 强制产出 PNG）⇒ 产出 mime 如实为 image/png（不假称 webp）且**产品真源按字节**同样判出 image/png
  - {"mime":"image/png","bytes":244283,"width":512,"height":512,"inputSize":"600 × 600","bytesReading":{"length":244283,"productMime":"image/png","productMimeOfBytes":"src/utils/image.js::sniffBytesMime","first12Hex":"89504e470d0a1a0a0000000d"},"message":"当前浏览器未能编码 image/webp，已按实际格式 image/png 入库"}
- [PASS] `fallback-row-mime` ⑤ 编码回退的大产物能入库，且元数据 mime 如实为 image/png（不冒充 webp；产品真源按字节同上）
  - {"initialBytes":2832092,"finalBytes":2832092,"finalSize":"2048 × 2048","mime":"image/png","reencodeRounds":0,"bytesReading":{"length":2832092,"productMime":"image/png","productMimeOfBytes":"src/utils/image.js::sniffBytesMime","first12Hex":"89504e470d0a1a0a0000000d"},"upload":{"ok":true,"rowBytes":2832092,"rowMime":"image/png","message":"实物照片已上传"}}
- [PASS] `artifact-reencode-bounded` ① 产物超上限 ⇒ **有界降质重编**（轮数 ≥1 且 ≤ 硬上界），压进上限后照常入库（不拒用户）
  - {"ok":true,"bytes":75195,"initialBytes":2832092,"reencodeRounds":3,"size":"256 × 256","mime":"image/png","message":"当前浏览器未能编码 image/webp，已按实际格式 image/png 入库；产物超过入库上限 200.0 KB，已自动降质重编 3 轮：2.70 MB → 73.4 KB"}
- [PASS] `artifact-reencode-limit` ① 重编到硬上界仍超限 ⇒ 才拒；文案为「本机影像生成失败/过大」，**不得**再甩「照片过大…请换一张更小的图」
  - {"ok":false,"reason":"ARTIFACT_TOO_LARGE","bytes":0,"reencodeRounds":3,"message":"本机影像生成失败：已自动降质重编 3 轮，产出仍有 73.4 KB，超过入库上限 1.0 KB。这与「所选文件 ≤ 1 MB」的输入上限是两回事；请重试，或改用支持 WebP 编码的浏览器后再上传。","misleadingClause":false}
- [PASS] `decode-fail` ⑤ 解码失败（声称 image/png 的文本文件）⇒ 可读错误、不冒充
  - 图片解码失败（文件可能已损坏或不是可用的图片），请换一张再试
- [PASS] `type-fail` ⑤ 非图片类型（text/plain）⇒ 可读错误
  - 这不是图片文件（类型 text/plain），请选择 JPG / PNG / WebP 图片
- [PASS] `service-not-image` ⑤ 服务层按字节魔数拒绝非图片内容（不采信声称的 mime）
  - 这不是可用的图片内容（无法识别图片格式），请重新选择图片文件（声称类型 image/webp）
- [PASS] `legacy-migrate` ③ 老库就地纠正：旧格式行（dataURL 直存）被迁进影像库，行内只剩元数据
  - {"legacyDataUrlLength":230078,"beforeMigrationDataImageHits":1,"migration":{"ok":true,"migrated":1,"total":5,"leftovers":0,"message":"已把 1 条旧格式实物照片（整张 dataURL 直存 localStorage）迁入本地影像库，localStorage 只留元数据"},"migrationAgain":{"ok":true,"migrated":0,"total":5,"leftovers":0,"message":"无需迁移：实物照片已全部为「元数据 + 二进制分层」形态"},"rowAfter":{"id":"ph-legacy-selftest","sealId":"XAI-0001","stamp_id":"XAI-0001","user_id":"u-13900001234","note":"自测：旧格式行（整张 dataURL 直存 localStorage）","file_name":"legacy.png","status":"APPROVED","created_at":"2026-09-20T10:45:13.173Z","mime":"image/png","width":400,"height":300,"bytes":172541,"sha256":"dd7b8e6fce7d354c81d3d96334a855253eb20c840ce075f82db5c9f78c63a761","storage":"indexeddb","storage_key":"photo:ph-legacy-selftest","migrated_at":"2026-09-20T10:45:13.186Z","migrated_from":"localStorage:dataUrl"},"rowHasImageField":false,"binaryReadOk":true,"binaryBytes":172541,"digestM
- [PASS] `legacy-idempotent` ③ 迁移幂等（再跑一次零写入、零改动）
  - {"ok":true,"migrated":0,"total":5,"leftovers":0,"message":"无需迁移：实物照片已全部为「元数据 + 二进制分层」形态"}
- [PASS] `ac33-no-dataimage` ③ localStorage 无任何 `data:image` 命中
  - {"hits":0,"keys":[]}
- [PASS] `ac33-max-value` ③ localStorage 单值 < 64 KiB（判负阈值 65,536 字符）
  - max=4948 (4.83 KiB) @ xiai:v1:faces
- [PASS] `ac33-total` ③ localStorage 总量 < 512 KiB
  - total=12376 (12.09 KiB)
- [PASS] `ac33-photos-key` ③ `xiai:v1:photos` 只存元数据（长度远小于 64 KiB 且无 data:image）
  - length=2133 (2.08 KiB)
- [PASS] `idb-binary` ③ 二进制在 IndexedDB 且可读回：sha256 与元数据一致、字节数与元数据一致、每行都无 image 字段
  - [{"id":"ph-mu9owp84-mqh0f","readOk":true,"digestMatchesRow":true,"bytesMatch":true,"metaOnlyOnRow":true,"bytesLength":1258291},{"id":"ph-mu9owpm7-6qo37","readOk":true,"digestMatchesRow":true,"bytesMatch":true,"metaOnlyOnRow":true,"bytesLength":14992},{"id":"ph-mu9owpma-8e4cr","readOk":true,"digestMatchesRow":true,"bytesMatch":true,"metaOnlyOnRow":true,"bytesLength":37430},{"id":"ph-mu9owprm-og6ll","readOk":true,"digestMatchesRow":true,"bytesMatch":true,"metaOnlyOnRow":true,"bytesLength":2832092},{"id":"ph-legacy-selftest","readOk":true,"digestMatchesRow":true,"bytesMatch":true,"metaOnlyOnRow":true,"bytesLength":172541}]
- [PASS] `idb-keys` ③ IndexedDB 键口径为 `photo:<照片 id>`，每行一条二进制（含迁移过来的历史行）
  - ["photo:ph-legacy-selftest","photo:ph-mu9owp84-mqh0f","photo:ph-mu9owpm7-6qo37","photo:ph-mu9owpma-8e4cr","photo:ph-mu9owprm-og6ll"]
- [PASS] `no-browser-storage-in-views` 页面只经服务层取回二进制（本探针按同一路径 loadPhotoDataUrl 读回）
  - 见 ④ 渲染检查
- [PASS] `render-service` ④ 画廊渲染路径：按 id 从数据层取回二进制并转 dataURL（刷新前）
  - [{"id":"ph-legacy-selftest","ok":true,"mime":"image/png","bytes":172541,"prefix":"data:image/png;base64,iV","message":""},{"id":"ph-mu9owprm-og6ll","ok":true,"mime":"image/png","bytes":2832092,"prefix":"data:image/png;base64,iV","message":""},{"id":"ph-mu9owpma-8e4cr","ok":true,"mime":"image/webp","bytes":37430,"prefix":"data:image/webp;base64,U","message":""},{"id":"ph-mu9owpm7-6qo37","ok":true,"mime":"image/webp","bytes":14992,"prefix":"data:image/webp;base64,U","message":""},{"id":"ph-mu9owp84-mqh0f","ok":true,"mime":"image/jpeg","bytes":1258291,"prefix":"data:image/jpeg;base64,/","message":""}]
- [PASS] `seals-artifact-const` A 印面图**产物侧**上限与照片路径**同源同值**（4 MiB；输入上限仍 1 MB；旧导出保留为兼容别名）
  - {"FACE_IMAGE_ARTIFACT_MAX_BYTES":4194304,"PHOTO_ARTIFACT_MAX_BYTES":4194304,"STORED_MAX_BYTES":4194304,"IMAGE_LIMITS_maxStoredBytes":4194304,"IMAGE_LIMITS_maxInputBytes":1048576,"FACE_IMAGE_MAX_BYTES_compatAlias":1048576,"maxReencodeRounds":3}
- [PASS] `seals-replace-ok` A 正常小产物 ⇒ 印面图重新上传**成功**（reason 空、指向更新为新影像、旧影像行保留不删）
  - {"exported":{"ok":true,"mime":"image/webp","bytes":6238,"size":"512 × 512","bytesReading":{"length":6238,"productMime":"image/webp","productMimeOfBytes":"src/utils/image.js::sniffBytesMime","first12Hex":"524946465618000057454250"}},"result":{"ok":true,"reason":"","faceImageId":"img-0001f-2","previousFaceImageId":"img-0001f","imageMime":"image/webp","message":"印面图已替换：影像编号 img-0001f → img-0001f-2；旧影像行与二进制保留未删。新影像 512 × 512 · image/webp · 6238 字节"},"faceImageIdAfter":"img-0001f-2","oldImageRowKept":true,"imageRowCount":14}
- [PASS] `seals-replace-mime-honest` A 入库元数据 mime ＝**产品真源按字节**判出的格式（不采信声称值、不冒充 webp）
  - {"rowMime":"image/webp","productMime":"image/webp"}
- [PASS] `seals-artifact-over-reject` A 注入「产物 > 4 MiB」⇒ 拒且 reason ＝ ARTIFACT_TOO_LARGE、文案＝「本机影像生成失败」，**不含**「请换一张更小的图」
  - {"injectedBytes":4194305,"injectedMiB":4,"capBytes":4194304,"ok":false,"reason":"ARTIFACT_TOO_LARGE","message":"本机影像生成失败：印面图处理后 4.00 MB 超过入库上限 4.00 MB。这与「所选文件 ≤ 1 MB」的输入上限是两回事；请重试，或改用支持 WebP 编码的浏览器后再上传。","misleadingClause":false,"faceImageIdUnchanged":true}
- [PASS] `seals-artifact-over-no-halfwrite` A 产物超限被拒时**不留半成品**：印面指向与影像行数均不变
  - {"faceImageIdUnchanged":true,"imageRowCount":14}
- [PASS] `seals-fallback-png-accepted` A 回退 PNG 大产物（>1 MB 旧闸、<4 MiB 新上限）⇒ **入库成功**（旧实现在此必判 TOO_LARGE 并甩误导文案）
  - {"artifactBytes":2832092,"artifactMiB":2.7,"mime":"image/png","reencodeRounds":0,"overOldInputGate":true,"underNewArtifactCap":true,"accepted":true,"reason":"","message":"印面图已替换：影像编号 img-0001f-2 → img-0001f-3；旧影像行与二进制保留未删。新影像 2048 × 2048 · image/png · 2832092 字节"}
- [PASS] `seals-input-over-rejected-by-pipeline` A 输入超 1 MB ⇒ 由管线（`loadImageFile`）拒，文案＝「所选文件…（上限 1 MB）」（输入侧口径，与产物侧分开）
  - {"fileBytes":1258291,"ok":false,"message":"照片过大：所选文件 1.20 MB，上限 1.00 MB（1 MB）。请换一张更小的图，或先用手机/系统自带的压缩再上传。","mentionsSelectedFile":true,"isInputSideWording":true}
- [PASS] `seals-not-image-still` A 放宽产物上限**不放松**「是不是图片」：认不出的字节仍拒（reason ＝ NOT_IMAGE）
  - {"reason":"NOT_IMAGE","message":"这不是可用的图片内容（无法识别图片格式），请重新选择 JPG / PNG / WebP 图片（声称类型 image/webp）"}

## 印面图「重新上传」路径读数（seals.js，本单 A 项）

```json
{
  "consts": {
    "FACE_IMAGE_ARTIFACT_MAX_BYTES": 4194304,
    "PHOTO_ARTIFACT_MAX_BYTES": 4194304,
    "STORED_MAX_BYTES": 4194304,
    "IMAGE_LIMITS_maxStoredBytes": 4194304,
    "IMAGE_LIMITS_maxInputBytes": 1048576,
    "FACE_IMAGE_MAX_BYTES_compatAlias": 1048576,
    "maxReencodeRounds": 3
  },
  "admin": {
    "ok": true,
    "id": "u-16601061656",
    "role": "admin"
  },
  "face": {
    "id": "fc-0001-f1",
    "faceImageIdBefore": "img-0001f"
  },
  "normal": {
    "exported": {
      "ok": true,
      "mime": "image/webp",
      "bytes": 6238,
      "size": "512 × 512",
      "bytesReading": {
        "length": 6238,
        "productMime": "image/webp",
        "productMimeOfBytes": "src/utils/image.js::sniffBytesMime",
        "first12Hex": "524946465618000057454250"
      }
    },
    "result": {
      "ok": true,
      "reason": "",
      "faceImageId": "img-0001f-2",
      "previousFaceImageId": "img-0001f",
      "imageMime": "image/webp",
      "message": "印面图已替换：影像编号 img-0001f → img-0001f-2；旧影像行与二进制保留未删。新影像 512 × 512 · image/webp · 6238 字节"
    },
    "faceImageIdAfter": "img-0001f-2",
    "oldImageRowKept": true,
    "imageRowCount": 14
  },
  "oversizeInjected": {
    "injectedBytes": 4194305,
    "injectedMiB": 4,
    "capBytes": 4194304,
    "ok": false,
    "reason": "ARTIFACT_TOO_LARGE",
    "message": "本机影像生成失败：印面图处理后 4.00 MB 超过入库上限 4.00 MB。这与「所选文件 ≤ 1 MB」的输入上限是两回事；请重试，或改用支持 WebP 编码的浏览器后再上传。",
    "misleadingClause": false,
    "faceImageIdUnchanged": true
  },
  "pngFallbackBig": {
    "artifactBytes": 2832092,
    "artifactMiB": 2.7,
    "mime": "image/png",
    "reencodeRounds": 0,
    "overOldInputGate": true,
    "underNewArtifactCap": true,
    "accepted": true,
    "reason": "",
    "message": "印面图已替换：影像编号 img-0001f-2 → img-0001f-3；旧影像行与二进制保留未删。新影像 2048 × 2048 · image/png · 2832092 字节"
  },
  "inputOver": {
    "fileBytes": 1258291,
    "ok": false,
    "message": "照片过大：所选文件 1.20 MB，上限 1.00 MB（1 MB）。请换一张更小的图，或先用手机/系统自带的压缩再上传。",
    "mentionsSelectedFile": true,
    "isInputSideWording": true
  },
  "notImage": {
    "reason": "NOT_IMAGE",
    "message": "这不是可用的图片内容（无法识别图片格式），请重新选择 JPG / PNG / WebP 图片（声称类型 image/webp）"
  },
  "sessionRestored": {
    "ok": true,
    "id": "u-13900001234"
  }
}
```

## AC-33 三阈值（关标签重开后实测）

- `data:image` 命中数 = **0**；localStorage 单值最大字符数 = **4950**（键 `xiai:v1:faces`，4.83 KiB，阈值 65,536）；总量 = **13298** 字符（12.99 KiB，阈值 512 KiB）
```json
{
  "keys": [
    "xiai:v1:users",
    "xiai:v1:faces",
    "xiai:v1:seals",
    "xiai:v1:photos",
    "xiai:v1:corrections",
    "xiai:v1:downloaded",
    "xiai:v1:seeded",
    "xiai:v1:session",
    "xiai:v1:images",
    "xiai:v1:points"
  ],
  "dataImageHits": 0,
  "dataImageKeys": [],
  "maxValue": 4950,
  "maxKey": "xiai:v1:faces",
  "maxKiB": 4.83,
  "total": 13298,
  "totalKiB": 12.99,
  "photosKeyLength": 2133,
  "photosKeyKiB": 2.08,
  "photosHasDataImage": false
}
```

## AC-33 三阈值（整套跑完后的最终审计）

- `data:image` 命中数 = **0**；localStorage 单值最大字符数 = **4950**（键 `xiai:v1:faces`，4.83 KiB）；总量 = **13695** 字符（13.37 KiB）
```json
{
  "keys": [
    "xiai:v1:users",
    "xiai:v1:faces",
    "xiai:v1:seals",
    "xiai:v1:photos",
    "xiai:v1:corrections",
    "xiai:v1:downloaded",
    "xiai:v1:seeded",
    "xiai:v1:session",
    "xiai:v1:images",
    "xiai:v1:points"
  ],
  "dataImageHits": 0,
  "dataImageKeys": [],
  "maxValue": 4950,
  "maxKey": "xiai:v1:faces",
  "maxKiB": 4.83,
  "total": 13695,
  "totalKiB": 13.37,
  "photosKeyLength": 2530,
  "photosKeyKiB": 2.47,
  "photosHasDataImage": false
}
```

## 旧行迁移读回（phase1 + 重开后）

```json
{
  "phase1_migration": {
    "legacyDataUrlLength": 230078,
    "beforeMigrationDataImageHits": 1,
    "migration": {
      "ok": true,
      "migrated": 1,
      "total": 5,
      "leftovers": 0,
      "message": "已把 1 条旧格式实物照片（整张 dataURL 直存 localStorage）迁入本地影像库，localStorage 只留元数据"
    },
    "migrationAgain": {
      "ok": true,
      "migrated": 0,
      "total": 5,
      "leftovers": 0,
      "message": "无需迁移：实物照片已全部为「元数据 + 二进制分层」形态"
    },
    "rowAfter": {
      "id": "ph-legacy-selftest",
      "sealId": "XAI-0001",
      "stamp_id": "XAI-0001",
      "user_id": "u-13900001234",
      "note": "自测：旧格式行（整张 dataURL 直存 localStorage）",
      "file_name": "legacy.png",
      "status": "APPROVED",
      "created_at": "2026-09-20T10:45:13.173Z",
      "mime": "image/png",
      "width": 400,
      "height": 300,
      "bytes": 172541,
      "sha256": "dd7b8e6fce7d354c81d3d96334a855253eb20c840ce075f82db5c9f78c63a761",
      "storage": "indexeddb",
      "storage_key": "photo:ph-legacy-selftest",
      "migrated_at": "2026-09-20T10:45:13.186Z",
      "migrated_from": "localStorage:dataUrl"
    },
    "rowHasImageField": false,
    "binaryReadOk": true,
    "binaryBytes": 172541,
    "digestMatches": true
  },
  "phase2_migrated_rows": [
    {
      "id": "ph-legacy-selftest",
      "migrated_from": "localStorage:dataUrl",
      "migrated_at": "2026-09-20T10:45:13.186Z",
      "rowHasImageField": false,
      "rowMime": "image/png",
      "rowBytes": 172541,
      "readOk": true,
      "bytesLength": 172541,
      "digestMatches": true
    }
  ]
}
```

## IndexedDB 二进制读数（格式判定调**产品真源** sniffBytesMime，并与元数据行对账）

```json
{
  "photoKeys": [
    "photo:ph-legacy-selftest",
    "photo:ph-mu9owp84-mqh0f",
    "photo:ph-mu9owpm7-6qo37",
    "photo:ph-mu9owpma-8e4cr",
    "photo:ph-mu9owprm-og6ll",
    "photo:ph-mu9owzan-xkzrf"
  ],
  "sizes": [
    {
      "key": "photo:ph-mu9owprm-og6ll",
      "bytes": 2832092,
      "head12": "89504e470d0a1a0a0000000d",
      "mimeByProduct": "image/png",
      "truthSource": "src/utils/image.js::sniffBytesMime",
      "metaMime": "image/png",
      "metaBytes": 2832092,
      "metaMatchesBinary": true
    },
    {
      "key": "photo:ph-mu9owzan-xkzrf",
      "bytes": 14438,
      "head12": "524946465e38000057454250",
      "mimeByProduct": "image/webp",
      "truthSource": "src/utils/image.js::sniffBytesMime",
      "metaMime": "image/webp",
      "metaBytes": 14438,
      "metaMatchesBinary": true
    }
  ],
  "truthSource": "src/utils/image.js::sniffBytesMime",
  "allKeysArePhoto": false
}
```

## 网络捕获（全量）

```json
{
  "total_requests": 169,
  "internal_count": 169,
  "external_urls": [],
  "external_count": 0,
  "port_5196_urls": [],
  "square_crop_urls": [],
  "sample": [
    "http://127.0.0.1:5163/@vite/client",
    "http://127.0.0.1:5163/feicui/ops/kong-photo-pipeline-probe.js?t=1789900640404",
    "http://127.0.0.1:5163/node_modules/vite/dist/client/env.mjs",
    "http://127.0.0.1:5163/favicon.ico",
    "blob:http://127.0.0.1:5163/ee9103a2-fc33-4a49-b547-f3f81e6c7cfd",
    "http://127.0.0.1:5163/feicui/ops/kong-photo-pipeline-probe.html",
    "http://127.0.0.1:5163/@vite/client",
    "http://127.0.0.1:5163/feicui/ops/kong-photo-pipeline-probe.js?t=1789900640404",
    "http://127.0.0.1:5163/node_modules/vite/dist/client/env.mjs",
    "http://127.0.0.1:5163/favicon.ico",
    "http://127.0.0.1:5163/my/photos",
    "http://127.0.0.1:5163/@vite/client",
    "http://127.0.0.1:5163/src/main.js?t=1789900616343",
    "http://127.0.0.1:5163/node_modules/.vite/deps/vue.js?v=a54d50c2",
    "http://127.0.0.1:5163/src/App.vue?t=1789900408028",
    "http://127.0.0.1:5163/src/router/index.js?t=1789900616343",
    "http://127.0.0.1:5163/src/services/bootstrap.js?t=1789898280771",
    "http://127.0.0.1:5163/src/styles/tokens.css?t=1789900596981",
    "http://127.0.0.1:5163/src/styles/base.css",
    "http://127.0.0.1:5163/node_modules/vite/dist/client/env.mjs",
    "http://127.0.0.1:5163/node_modules/.vite/deps/chunk-GKNS7JV4.js?v=a54d50c2",
    "http://127.0.0.1:5163/node_modules/.vite/deps/vue-router.js?v=a54d50c2",
    "http://127.0.0.1:5163/src/components/AppHeader.vue?t=1789900408028",
    "http://127.0.0.1:5163/src/components/AppSidebar.vue?t=1789895990204",
    "http://127.0.0.1:5163/@id/__x00__plugin-vue:export-helper"
  ]
}
```

## UI 三档真实读数

### ui_upload_normal

```json
{
  "input": {
    "path": "/tmp/xiai-ui-normal.jpg",
    "bytes": 73006
  },
  "preview": {
    "status": "已就绪：3000 × 1200 px / 71.3 KB（image/jpeg）。拖动方框调整位置，拖四角或滚轮缩放，然后点「上传实物照片」。",
    "kind": "notice",
    "canvasPx": [
      360,
      360
    ],
    "uploadBtn": true
  },
  "upload": {
    "status": "实物照片已上传：71.3 KB → 14.1 KB（1200 × 1200，image/webp），已在下方画廊中。",
    "cards": 6,
    "firstSrc": "data:image/webp;base64,UklGRl4"
  },
  "row": {
    "count": 6,
    "last": {
      "id": "ph-mu9owzan-xkzrf",
      "sealId": "XAI-0001",
      "stamp_id": "XAI-0001",
      "user_id": "u-13900001234",
      "note": "",
      "file_name": "xiai-ui-normal.jpg",
      "status": "APPROVED",
      "mime": "image/webp",
      "width": 1200,
      "height": 1200,
      "bytes": 14438,
      "sha256": "391f3d3650fd7fc3bc1bea8ac8d6020f82cb145bd080a6be9d44a1cace2a6820",
      "storage": "indexeddb",
      "storage_key": "photo:ph-mu9owzan-xkzrf",
      "created_at": "2026-09-20T10:45:25.300Z"
    }
  },
  "idb": {
    "photoKeys": [
      "photo:ph-legacy-selftest",
      "photo:ph-mu9owp84-mqh0f",
      "photo:ph-mu9owpm7-6qo37",
      "photo:ph-mu9owpma-8e4cr",
      "photo:ph-mu9owprm-og6ll",
      "photo:ph-mu9owzan-xkzrf"
    ],
    "sizes": [
      {
        "key": "photo:ph-mu9owprm-og6ll",
        "bytes": 2832092,
        "head12": "89504e470d0a1a0a0000000d",
        "mimeByProduct": "image/png",
        "truthSource": "src/utils/image.js::sniffBytesMime",
        "metaMime": "image/png",
        "metaBytes": 2832092,
        "metaMatchesBinary": true
      },
      {
        "key": "photo:ph-mu9owzan-xkzrf",
        "bytes": 14438,
        "head12": "524946465e38000057454250",
        "mimeByProduct": "image/webp",
        "truthSource": "src/utils/image.js::sniffBytesMime",
        "metaMime": "image/webp",
        "metaBytes": 14438,
        "metaMatchesBinary": true
      }
    ],
    "truthSource": "src/utils/image.js::sniffBytesMime",
    "allKeysArePhoto": false
  }
}
```

### ui_upload_input_over

```json
{
  "input": {
    "path": "/tmp/xiai-ui-over1mb.jpg",
    "bytes": 1894831
  },
  "status": {
    "status": "照片过大：所选文件 1.81 MB，上限 1.00 MB（1 MB）。请换一张更小的图，或先用手机/系统自带的压缩再上传。",
    "kind": "notice notice--error",
    "hasCanvas": false
  },
  "row": {
    "count": 6,
    "last": {
      "id": "ph-mu9owzan-xkzrf",
      "sealId": "XAI-0001",
      "stamp_id": "XAI-0001",
      "user_id": "u-13900001234",
      "note": "",
      "file_name": "xiai-ui-normal.jpg",
      "status": "APPROVED",
      "mime": "image/webp",
      "width": 1200,
      "height": 1200,
      "bytes": 14438,
      "sha256": "391f3d3650fd7fc3bc1bea8ac8d6020f82cb145bd080a6be9d44a1cace2a6820",
      "storage": "indexeddb",
      "storage_key": "photo:ph-mu9owzan-xkzrf",
      "created_at": "2026-09-20T10:45:25.300Z"
    }
  }
}
```

### ui_upload_forced_png

```json
{
  "skipped": "未设 XIAI_FORCE_PNG=1：本次跑的是真实编码路径（WebP 可用 ⇒ 走不到回退分支）"
}
```

### ui_upload_localStorage

```json
{}
```

### ui_upload_indexeddb

```json
{}
```

## 步骤异常（工具链，不并入产品缺陷）

```json
{
  "poll_predicate": [
    "关标签重开后渲染: AttributeError: 'str' object has no attribute 'get'",
    "正常档 预览就绪: AttributeError: 'str' object has no attribute 'get'",
    "正常档 上传结果: AttributeError: 'str' object has no attribute 'get'"
  ]
}
```
