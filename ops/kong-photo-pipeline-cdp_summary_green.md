# 玺爱影像管线探针 · 自动摘要（green 跑）

- 跑的时间：2026-09-20T18:25:29+0800
- Chrome：Chrome/153.0.8010.52（自建 headless，pid=44138，profile=/tmp/xiai-probe-profile-kong，调试口=9333）
- 回退注入（强制 toBlob 产 PNG）：True
- 解释器：/Library/Developer/CommandLineTools/usr/bin/python3

## 断言清单（phase1，33 条，失败 0 条）

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
- [PASS] `square-webp` ② 3000×1200 → 方形（width == height ≤ 2048）；强制 PNG 回退模式下产物如实为 image/png（真 PNG 签名）
  - {"forcePngMode":true,"inputBytes":75149,"inputSize":"3000 × 1200","outputSize":"1200 × 1200","outputBytes":417488,"mime":"image/png","magic":{"length":417488,"head4":"PNG","head12":"\u0000\u0000\u0000\r","isRiff":false,"isWebp":false,"isPng":true,"first12Hex":"89504e470d0a1a0a0000000d"}}
- [PASS] `downsample` ② 降采样：2600×2600 → 2048×2048（最长边 ≤ 2048）
  - {"inputBytes":131832,"inputSize":"2600 × 2600","outputSize":"2048 × 2048","outputBytes":1290250,"mime":"image/png"}
- [PASS] `custom-crop` ② 自定义 crop（模拟用户拖拽/缩放后的方框）被如实执行：side=800 ⇒ 800×800
  - {"width":800,"height":800,"bytes":83833}
- [PASS] `upload-1` 上传（处理后二进制）成功并返回行（mime＝image/png）
  - {"forcePngMode":true,"ok":true,"id":"ph-mu9o7e8o-y4m81","mime":"image/png","message":"实物照片已上传"}
- [PASS] `upload-2` 第二张上传成功（id 不同、无覆盖）
  - {"id1":"ph-mu9o7e8o-y4m81","id2":"ph-mu9o7e9q-on4kj","ok2":true,"message2":"实物照片已上传"}
- [PASS] `row-meta` 元数据行只带标量（width/height/bytes/sha256/mime），**不含 image dataURL**
  - {"id":"ph-mu9o7e8o-y4m81","sealId":"XAI-0001","stamp_id":"XAI-0001","user_id":"u-13900001234","note":"自测：非方形大图 → 方形 WebP","file_name":"photo-3000x1200.jpg","status":"APPROVED","mime":"image/png","width":1200,"height":1200,"bytes":417488,"sha256":"8407ac61c5997b19a062426216530c5bb78449dd1907540795ec9bec9ee32368","storage":"indexeddb","storage_key":"photo:ph-mu9o7e8o-y4m81","created_at":"2026-09-20T10:25:31.614Z"}
- [PASS] `fallback-png` ⑤ 编码回退（toBlob 强制产出 PNG）⇒ 产出 mime 如实为 image/png（不假称 webp）且字节魔数为真 PNG 签名
  - {"mime":"image/png","bytes":244283,"width":512,"height":512,"inputSize":"600 × 600","magic":{"length":244283,"head4":"PNG","head12":"\u0000\u0000\u0000\r","isRiff":false,"isWebp":false,"isPng":true,"first12Hex":"89504e470d0a1a0a0000000d"},"message":"当前浏览器未能编码 image/webp，已按实际格式 image/png 入库"}
- [PASS] `fallback-row-mime` ⑤ 编码回退的大产物能入库，且元数据 mime 如实为 image/png（不冒充 webp）
  - {"initialBytes":2832092,"finalBytes":2832092,"finalSize":"2048 × 2048","mime":"image/png","reencodeRounds":0,"magic":{"length":2832092,"head4":"PNG","head12":"\u0000\u0000\u0000\r","isRiff":false,"isWebp":false,"isPng":true,"first12Hex":"89504e470d0a1a0a0000000d"},"upload":{"ok":true,"rowBytes":2832092,"rowMime":"image/png","message":"实物照片已上传"}}
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
  - {"legacyDataUrlLength":230078,"beforeMigrationDataImageHits":1,"migration":{"ok":true,"migrated":1,"total":5,"leftovers":0,"message":"已把 1 条旧格式实物照片（整张 dataURL 直存 localStorage）迁入本地影像库，localStorage 只留元数据"},"migrationAgain":{"ok":true,"migrated":0,"total":5,"leftovers":0,"message":"无需迁移：实物照片已全部为「元数据 + 二进制分层」形态"},"rowAfter":{"id":"ph-legacy-selftest","sealId":"XAI-0001","stamp_id":"XAI-0001","user_id":"u-13900001234","note":"自测：旧格式行（整张 dataURL 直存 localStorage）","file_name":"legacy.png","status":"APPROVED","created_at":"2026-09-20T10:25:32.061Z","mime":"image/png","width":400,"height":300,"bytes":172541,"sha256":"dd7b8e6fce7d354c81d3d96334a855253eb20c840ce075f82db5c9f78c63a761","storage":"indexeddb","storage_key":"photo:ph-legacy-selftest","migrated_at":"2026-09-20T10:25:32.074Z","migrated_from":"localStorage:dataUrl"},"rowHasImageField":false,"binaryReadOk":true,"binaryBytes":172541,"digestM
- [PASS] `legacy-idempotent` ③ 迁移幂等（再跑一次零写入、零改动）
  - {"ok":true,"migrated":0,"total":5,"leftovers":0,"message":"无需迁移：实物照片已全部为「元数据 + 二进制分层」形态"}
- [PASS] `ac33-no-dataimage` ③ localStorage 无任何 `data:image` 命中
  - {"hits":0,"keys":[]}
- [PASS] `ac33-max-value` ③ localStorage 单值 < 64 KiB（判负阈值 65,536 字符）
  - max=4948 (4.83 KiB) @ xiai:v1:faces
- [PASS] `ac33-total` ③ localStorage 总量 < 512 KiB
  - total=12377 (12.09 KiB)
- [PASS] `ac33-photos-key` ③ `xiai:v1:photos` 只存元数据（长度远小于 64 KiB 且无 data:image）
  - length=2134 (2.08 KiB)
- [PASS] `idb-binary` ③ 二进制在 IndexedDB 且可读回：sha256 与元数据一致、字节数与元数据一致、每行都无 image 字段
  - [{"id":"ph-mu9o7e0n-39klv","readOk":true,"digestMatchesRow":true,"bytesMatch":true,"metaOnlyOnRow":true,"bytesLength":1258291},{"id":"ph-mu9o7e8o-y4m81","readOk":true,"digestMatchesRow":true,"bytesMatch":true,"metaOnlyOnRow":true,"bytesLength":417488},{"id":"ph-mu9o7e9q-on4kj","readOk":true,"digestMatchesRow":true,"bytesMatch":true,"metaOnlyOnRow":true,"bytesLength":1290250},{"id":"ph-mu9o7eez-hk99e","readOk":true,"digestMatchesRow":true,"bytesMatch":true,"metaOnlyOnRow":true,"bytesLength":2832092},{"id":"ph-legacy-selftest","readOk":true,"digestMatchesRow":true,"bytesMatch":true,"metaOnlyOnRow":true,"bytesLength":172541}]
- [PASS] `idb-keys` ③ IndexedDB 键口径为 `photo:<照片 id>`，每行一条二进制（含迁移过来的历史行）
  - ["photo:ph-legacy-selftest","photo:ph-mu9o7e0n-39klv","photo:ph-mu9o7e8o-y4m81","photo:ph-mu9o7e9q-on4kj","photo:ph-mu9o7eez-hk99e"]
- [PASS] `no-browser-storage-in-views` 页面只经服务层取回二进制（本探针按同一路径 loadPhotoDataUrl 读回）
  - 见 ④ 渲染检查
- [PASS] `render-service` ④ 画廊渲染路径：按 id 从数据层取回二进制并转 dataURL（刷新前）
  - [{"id":"ph-legacy-selftest","ok":true,"mime":"image/png","bytes":172541,"prefix":"data:image/png;base64,iV","message":""},{"id":"ph-mu9o7eez-hk99e","ok":true,"mime":"image/png","bytes":2832092,"prefix":"data:image/png;base64,iV","message":""},{"id":"ph-mu9o7e9q-on4kj","ok":true,"mime":"image/png","bytes":1290250,"prefix":"data:image/png;base64,iV","message":""},{"id":"ph-mu9o7e8o-y4m81","ok":true,"mime":"image/png","bytes":417488,"prefix":"data:image/png;base64,iV","message":""},{"id":"ph-mu9o7e0n-39klv","ok":true,"mime":"image/jpeg","bytes":1258291,"prefix":"data:image/jpeg;base64,/","message":""}]

## AC-33 三阈值（关标签重开后实测）

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
  "maxValue": 4948,
  "maxKey": "xiai:v1:faces",
  "maxKiB": 4.83,
  "total": 12377,
  "totalKiB": 12.09,
  "photosKeyLength": 2134,
  "photosKeyKiB": 2.08,
  "photosHasDataImage": false
}
```

## AC-33 三阈值（整套跑完后的最终审计）

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
  "maxValue": 4948,
  "maxKey": "xiai:v1:faces",
  "maxKiB": 4.83,
  "total": 12774,
  "totalKiB": 12.47,
  "photosKeyLength": 2531,
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
      "created_at": "2026-09-20T10:25:32.061Z",
      "mime": "image/png",
      "width": 400,
      "height": 300,
      "bytes": 172541,
      "sha256": "dd7b8e6fce7d354c81d3d96334a855253eb20c840ce075f82db5c9f78c63a761",
      "storage": "indexeddb",
      "storage_key": "photo:ph-legacy-selftest",
      "migrated_at": "2026-09-20T10:25:32.074Z",
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
      "migrated_at": "2026-09-20T10:25:32.074Z",
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

## 网络捕获（全量）

```json
{
  "total_requests": 211,
  "internal_count": 211,
  "external_urls": [],
  "external_count": 0,
  "port_5196_urls": [],
  "square_crop_urls": [],
  "sample": [
    "http://127.0.0.1:5163/@vite/client",
    "http://127.0.0.1:5163/feicui/ops/kong-photo-pipeline-probe.js?t=1789899894455",
    "http://127.0.0.1:5163/node_modules/vite/dist/client/env.mjs",
    "http://127.0.0.1:5163/favicon.ico",
    "blob:http://127.0.0.1:5163/fc107be8-15c3-47bb-b5e0-1200605470f6",
    "http://127.0.0.1:5163/feicui/ops/kong-photo-pipeline-probe.html",
    "http://127.0.0.1:5163/@vite/client",
    "http://127.0.0.1:5163/feicui/ops/kong-photo-pipeline-probe.js?t=1789899894455",
    "http://127.0.0.1:5163/node_modules/vite/dist/client/env.mjs",
    "http://127.0.0.1:5163/favicon.ico",
    "http://127.0.0.1:5163/my/photos",
    "http://127.0.0.1:5163/@vite/client",
    "http://127.0.0.1:5163/src/main.js?t=1789899881245",
    "http://127.0.0.1:5163/node_modules/.vite/deps/vue.js?v=a54d50c2",
    "http://127.0.0.1:5163/src/App.vue?t=1789899881245",
    "http://127.0.0.1:5163/src/router/index.js?t=1789899881245",
    "http://127.0.0.1:5163/src/services/bootstrap.js?t=1789898280771",
    "http://127.0.0.1:5163/src/styles/tokens.css",
    "http://127.0.0.1:5163/src/styles/base.css",
    "http://127.0.0.1:5163/node_modules/vite/dist/client/env.mjs",
    "http://127.0.0.1:5163/node_modules/.vite/deps/chunk-GKNS7JV4.js?v=a54d50c2",
    "http://127.0.0.1:5163/node_modules/.vite/deps/vue-router.js?v=a54d50c2",
    "http://127.0.0.1:5163/src/components/AppHeader.vue?t=1789899881245",
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
    "bytes": 76615
  },
  "preview": {
    "status": "已就绪：3000 × 1200 px / 74.8 KB（image/jpeg）。拖动方框调整位置，拖四角或滚轮缩放，然后点「上传实物照片」。",
    "kind": "notice",
    "canvasPx": [
      360,
      360
    ],
    "uploadBtn": true
  },
  "upload": {
    "status": "实物照片已上传：74.8 KB → 363.2 KB（1200 × 1200，image/png），已在下方画廊中。",
    "cards": 6,
    "firstSrc": "data:image/png;base64,iVBORw0K"
  },
  "row": {
    "count": 6,
    "last": {
      "id": "ph-mu9o7qlu-sscsb",
      "sealId": "XAI-0001",
      "stamp_id": "XAI-0001",
      "user_id": "u-13900001234",
      "note": "",
      "file_name": "xiai-ui-normal.jpg",
      "status": "APPROVED",
      "mime": "image/png",
      "width": 1200,
      "height": 1200,
      "bytes": 371885,
      "sha256": "083116a196ccdd3233d9254f3e75c60d14c198e675806e265aa2563ce25dab3f",
      "storage": "indexeddb",
      "storage_key": "photo:ph-mu9o7qlu-sscsb",
      "created_at": "2026-09-20T10:25:47.643Z"
    }
  },
  "idb": {
    "photoKeys": [
      "photo:ph-legacy-selftest",
      "photo:ph-mu9o7e0n-39klv",
      "photo:ph-mu9o7e8o-y4m81",
      "photo:ph-mu9o7e9q-on4kj",
      "photo:ph-mu9o7eez-hk99e",
      "photo:ph-mu9o7qlu-sscsb"
    ],
    "sizes": [
      {
        "key": "photo:ph-mu9o7eez-hk99e",
        "bytes": 2832092,
        "head12": "89504e470d0a1a0a0000000d",
        "isPngMagic": true
      },
      {
        "key": "photo:ph-mu9o7qlu-sscsb",
        "bytes": 371885,
        "head12": "89504e470d0a1a0a0000000d",
        "isPngMagic": true
      }
    ]
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
      "id": "ph-mu9o7qlu-sscsb",
      "sealId": "XAI-0001",
      "stamp_id": "XAI-0001",
      "user_id": "u-13900001234",
      "note": "",
      "file_name": "xiai-ui-normal.jpg",
      "status": "APPROVED",
      "mime": "image/png",
      "width": 1200,
      "height": 1200,
      "bytes": 371885,
      "sha256": "083116a196ccdd3233d9254f3e75c60d14c198e675806e265aa2563ce25dab3f",
      "storage": "indexeddb",
      "storage_key": "photo:ph-mu9o7qlu-sscsb",
      "created_at": "2026-09-20T10:25:47.643Z"
    }
  }
}
```

### ui_upload_forced_png

```json
{}
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
    "正常档 预览就绪: AttributeError: 'str' object has no attribute 'get'",
    "正常档 上传结果: AttributeError: 'str' object has no attribute 'get'",
    "回退 PNG 档 预览就绪: AttributeError: 'str' object has no attribute 'get'",
    "回退 PNG 档 预览就绪: AttributeError: 'str' object has no attribute 'get'",
    "回退 PNG 档 预览就绪: AttributeError: 'str' object has no attribute 'get'",
    "回退 PNG 档 预览就绪: AttributeError: 'str' object has no attribute 'get'",
    "回退 PNG 档 预览就绪: AttributeError: 'str' object has no attribute 'get'",
    "回退 PNG 档 预览就绪: AttributeError: 'str' object has no attribute 'get'",
    "回退 PNG 档 预览就绪: AttributeError: 'str' object has no attribute 'get'",
    "回退 PNG 档 预览就绪: AttributeError: 'str' object has no attribute 'get'",
    "回退 PNG 档 预览就绪: AttributeError: 'str' object has no attribute 'get'",
    "回退 PNG 档 预览就绪: AttributeError: 'str' object has no attribute 'get'",
    "回退 PNG 档 预览就绪: AttributeError: 'str' object has no attribute 'get'",
    "回退 PNG 档 预览就绪: AttributeError: 'str' object has no attribute 'get'",
    "回退 PNG 档 预览就绪: AttributeError: 'str' object has no attribute 'get'",
    "回退 PNG 档 预览就绪: AttributeError: 'str' object has no attribute 'get'",
    "回退 PNG 档 预览就绪: AttributeError: 'str' object has no attribute 'get'",
    "回退 PNG 档 预览就绪: AttributeError: 'str' object has no attribute 'get'",
    "回退 PNG 档 预览就绪: AttributeError: 'str' object has no attribute 'get'",
    "回退 PNG 档 预览就绪: AttributeError: 'str' object has no attribute 'get'",
    "回退 PNG 档 预览就绪: AttributeError: 'str' object has no attribute 'get'",
    "回退 PNG 档 预览就绪: AttributeError: 'str' object has no attribute 'get'",
    "回退 PNG 档 预览就绪: AttributeError: 'str' object has no attribute 'get'",
    "回退 PNG 档 预览就绪: AttributeError: 'str' object has no attribute 'get'",
    "回退 PNG 档 预览就绪: AttributeError: 'str' object has no attribute 'get'",
    "回退 PNG 档 预览就绪: AttributeError: 'str' object has no attribute 'get'",
    "回退 PNG 档 预览就绪: AttributeError: 'str' object has no attribute 'get'",
    "回退 PNG 档 预览就绪: AttributeError: 'str' object has no attribute 'get'",
    "回退 PNG 档 预览就绪: AttributeError: 'str' object has no attribute 'get'",
    "回退 PNG 档 预览就绪: AttributeError: 'str' object has no attribute 'get'",
    "回退 PNG 档 预览就绪: AttributeError: 'str' object has no attribute 'get'",
    "回退 PNG 档 预览就绪: AttributeError: 'str' object has no attribute 'get'",
    "回退 PNG 档 预览就绪: AttributeError: 'str' object has no attribute 'get'",
    "回退 PNG 档 预览就绪: AttributeError: 'str' object has no attribute 'get'",
    "回退 PNG 档 预览就绪: AttributeError: 'str' object has no attribute 'get'",
    "回退 PNG 档 预览就绪: AttributeError: 'str' object has no attribute 'get'",
    "回退 PNG 档 预览就绪: AttributeError: 'str' object has no attribute 'get'",
    "回退 PNG 档 预览就绪: AttributeError: 'str' object has no attribute 'get'",
    "回退 PNG 档 预览就绪: AttributeError: 'str' object has no attribute 'get'",
    "回退 PNG 档 预览就绪: AttributeError: 'str' object has no attribute 'get'",
    "回退 PNG 档 预览就绪: Attrib
```
