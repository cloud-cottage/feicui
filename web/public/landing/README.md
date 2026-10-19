# `web/public/landing/` —— 「斐萃」公网引导页（并入 Vue 站随 Vite 发布）

**（v1.42 起）** 本页随目录重组自仓根 `site/` 迁入 `web/public/landing/`（`git mv` 保历史）。
Vite 把 `web/public/` 原样拷进 `dist/` ⇒ 公网部署后走 **`/landing/`** 访问本页；
`web/index.html` 是 Vue 站 Vite 入口、在工程根不入子目录 ⇒ 同名不冲突。

**Vercel 部署口径**：原「Root Directory ＝ `site`、纯静态」的**控制台配置待改**——
引导页既已并入 Vue 站，控制台应改指 `web/`（Framework＝Vite、构建 `npm run build`、输出 `dist/`）。
部署参数以控制台为准，仓内**不引入 `vercel.json`**（spec §0.5.3：避免「仓内 ↔ 控制台」两处真源）。

## 只放对公网公开的静态件

静态部署会把 **部署目录下所有 git 跟踪文件**当静态资源公开。
⇒ 本目录**只放**：`index.html` ＋ `assets/`（图标）＋ 本 README。
任何内部件（spec / readings / selftest / `.env*` / 源码 / 数据）**一件都不能进**；加文件前先自问「这个能不能挂公网」。

## 下载按钮

页内「下载最新版本」指向 **GitHub Releases**：
`https://github.com/cloud-cottage/feicui/releases/latest`
—— 仓里**发 Release 后自动生效**，无需再改页面。
页内唯一允许的 `href="#"` 类锚点是真正的页内锚点（`#guide`），其余外链一律写全 URL。

## 单一真源

引导页在仓内**只有这一份**（迁变史：原 `webui/index.html` → 2026-10-17 `site/index.html` → 2026-10-19 本处 `web/public/landing/index.html`）。
不要为了「本地预览方便」在别处复制副本 —— 两份必然漂移。

本地预览：`cd web/public/landing && python3 -m http.server 8899`
