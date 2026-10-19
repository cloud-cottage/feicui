#!/usr/bin/env node
/**
 * fetch-downloads.mjs —— 构建前把桌面安装包拉到 `public/downloads/`，让引导页走**站内直链**。
 *
 * 背景（Kevin 2026-10-20 指令）：「在网页上直接给出两个操作系统的下载地址（不要再跳转 github）」。
 * 因此引导页两个主按钮指向 `/downloads/feicui-mac-s1.dmg` 与 `/downloads/feicui-win-s1.zip`，
 * 文件由本脚本在 `vite build` 之前从 GitHub **latest Release** 拉取、改名成 ASCII 落盘。
 *
 * 硬约束：Vercel 单文件上限 100 MB。
 *   - `feicui-mac-s1.dmg` ≈ 94 MB  ✅ 可站内直供
 *   - `feicui-mac-s2.dmg` ≈ 150 MB  ❌ 超限 ⇒ 不进网页，只留在 Release（页面小字引导线下索取）
 *   - `feicui-win-s1.zip` ≈ 94 MB  ✅ 可站内直供
 *
 * 行为约定：
 *   1. 目标文件已存在且 > CACHE_MIN_BYTES（50 MB）⇒ 跳过（缓存命中，重复构建不重复下载）。
 *   2. `FETCH_DOWNLOADS_SKIP=1` ⇒ 直接跳过（断网 / CI / 只想快速验证前端时用）。
 *   3. **任何失败都不阻断构建**：只打印警告，退出码恒为 0。
 *      代价是缺文件时按钮仍在、点击 404 —— 部署后请用下面的验收命令确认文件真在。
 *
 * 可选环境变量：
 *   GITHUB_TOKEN                —— 私有仓库或触发 API 限流时使用（公开仓库通常不需要）
 *   FETCH_DOWNLOADS_REPO        —— 覆盖仓库，默认 cloud-cottage/feicui
 *   FETCH_DOWNLOADS_SKIP=1      —— 跳过下载
 *   FETCH_DOWNLOADS_FORCE=1     —— 忽略缓存，强制重下
 *
 * 部署后验收：
 *   curl -sI https://feicui.xiai.plus/downloads/feicui-mac-s1.dmg   # 200 + content-length ≈ 94 MB
 *   curl -sI https://feicui.xiai.plus/downloads/feicui-win-s1.zip
 */

import { createWriteStream } from 'node:fs';
import { mkdir, rename, rm, stat } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { Readable } from 'node:stream';
import { pipeline } from 'node:stream/promises';

const HERE = dirname(fileURLToPath(import.meta.url));
const WEB_ROOT = join(HERE, '..');
const OUT_DIR = join(WEB_ROOT, 'public', 'downloads');

const REPO = process.env.FETCH_DOWNLOADS_REPO || 'cloud-cottage/feicui';
/** 单文件上限 100 MB 之下的安全线：缓存判定「这个文件是完整的」 */
const CACHE_MIN_BYTES = 50 * 1024 * 1024;
/** 同时守住「别把 150 MB 的 s2 误拉进网页」：超过就拒绝写入 */
const VERCEL_MAX_BYTES = 100 * 1024 * 1024;

/**
 * 要拉的两个包。`names` 按优先级匹配 Release 资产名 ——
 * 先 ASCII（现行约定），再中文（历史 tag 里的旧名），避免改名当口构建失败。
 */
const TARGETS = [
  {
    local: 'feicui-mac-s1.dmg',
    label: 'macOS 标准版',
    names: ['feicui-mac-s1.dmg', '斐萃-mac-s1.dmg', '斐萃-s1.dmg'],
  },
  {
    local: 'feicui-win-s1.zip',
    label: 'Windows 版',
    names: ['feicui-win-s1.zip', 'feicui-win.zip'],
  },
  // feicui-mac-s2.dmg（≈150 MB）**故意不在列表**：超 Vercel 100 MB 单文件上限。
];

const log = (...a) => console.log('[fetch-downloads]', ...a);
const warn = (...a) => console.warn('[fetch-downloads] ⚠️ ', ...a);

function apiHeaders() {
  const h = {
    Accept: 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
    'User-Agent': 'feicui-build-fetch-downloads',
  };
  if (process.env.GITHUB_TOKEN) h.Authorization = `Bearer ${process.env.GITHUB_TOKEN}`;
  return h;
}

async function fileSize(p) {
  try {
    return (await stat(p)).size;
  } catch {
    return -1;
  }
}

async function latestRelease() {
  const res = await fetch(`https://api.github.com/repos/${REPO}/releases/latest`, {
    headers: apiHeaders(),
  });
  if (!res.ok) throw new Error(`GitHub API ${res.status} ${res.statusText} (/releases/latest)`);
  return res.json();
}

async function download(url, dest) {
  const res = await fetch(url, { headers: { 'User-Agent': 'feicui-build-fetch-downloads' } });
  if (!res.ok || !res.body) throw new Error(`下载失败 ${res.status} ${res.statusText} ← ${url}`);
  const len = Number(res.headers.get('content-length') || 0);
  if (len > VERCEL_MAX_BYTES) {
    throw new Error(`资产 ${(len / 1048576).toFixed(1)} MB 超过 Vercel 单文件 100 MB 上限，拒绝写入`);
  }
  // 先写 .part 再 rename：中断不会留下半截文件被缓存判定当成「已存在」
  const tmp = `${dest}.part`;
  await mkdir(dirname(dest), { recursive: true });
  await pipeline(Readable.fromWeb(res.body), createWriteStream(tmp));
  await rename(tmp, dest);
  return fileSize(dest);
}

async function main() {
  if (process.env.FETCH_DOWNLOADS_SKIP === '1') {
    log('FETCH_DOWNLOADS_SKIP=1 ⇒ 跳过下载（页面按钮仍在，缺文件会 404）');
    return;
  }

  await mkdir(OUT_DIR, { recursive: true });

  // ── 1. 缓存判定 ──
  const pending = [];
  for (const t of TARGETS) {
    const dest = join(OUT_DIR, t.local);
    const size = await fileSize(dest);
    if (size > CACHE_MIN_BYTES && process.env.FETCH_DOWNLOADS_FORCE !== '1') {
      log(`缓存命中 ${t.local}（${(size / 1048576).toFixed(1)} MB，跳过）`);
    } else {
      if (size >= 0) warn(`${t.local} 只有 ${size} B（可能是半截文件）⇒ 重下`);
      pending.push(t);
    }
  }
  if (pending.length === 0) return void log('两个包都已就位');

  // ── 2. 查 latest Release ──
  let release;
  try {
    release = await latestRelease();
  } catch (e) {
    warn(`取 latest Release 失败：${e.message}`);
    warn(`未取得 ${pending.map((p) => p.local).join(' / ')}；构建继续，但这几个下载链接会 404`);
    return;
  }
  log(`latest Release = ${release.tag_name}（${release.assets?.length ?? 0} 个资产）`);

  const byName = new Map((release.assets || []).map((a) => [a.name, a]));

  // ── 3. 逐个下载 ──
  for (const t of pending) {
    const asset = t.names.map((n) => byName.get(n)).find(Boolean);
    if (!asset) {
      warn(`Release ${release.tag_name} 里找不到 ${t.label}（试过：${t.names.join(' / ')}）⇒ 跳过`);
      continue;
    }
    const dest = join(OUT_DIR, t.local);
    try {
      const size = await download(asset.browser_download_url, dest);
      log(`✅ ${asset.name} → downloads/${t.local}（${(size / 1048576).toFixed(1)} MB）`);
    } catch (e) {
      warn(`${t.local} 下载失败：${e.message}`);
      await rm(`${dest}.part`, { force: true }).catch(() => {});
    }
  }
}

main()
  .catch((e) => {
    // 兜底：绝不因下载问题让 vite build 挂掉
    warn(`未预期错误，已忽略以不阻断构建：${e?.message || e}`);
  })
  .finally(() => {
    log('完成（退出码 0，下载失败不阻断构建）');
    process.exit(0);
  });
