# `site/` —— 「斐萃」公网引导页（Vercel 静态站）

**Vercel 部署配置：Root Directory = `site`**（Framework Preset = Other，无构建命令，纯静态）。
=> 线上根路径 `/` 即本目录的 `index.html`。

## 只放对公网公开的静态件

Vercel 静态部署会把 **Root Directory 下所有文件**当静态资源公开。
⇒ 本目录**只放**：`index.html` ＋ `assets/`（图标）＋ 本 README。
任何内部件（spec / readings / selftest / `.env*` / 源码 / 数据）**一件都不能进**；加文件前先自问「这个能不能挂公网」。

## 下载按钮

页内「下载最新版本」指向 **GitHub Releases**：
`https://github.com/cloud-cottage/feicui/releases/latest`
—— 仓里**发 Release 后自动生效**，无需再改页面。
页内唯一允许的 `href="#"` 类锚点是真正的页内锚点（`#guide`），其余外链一律写全 URL。

## 单一真源

引导页在仓内**只有这一份**（原 `webui/index.html` 已迁出并删除）。
不要为了「本地预览方便」在别处复制副本 —— 两份必然漂移。

本地预览：`cd site && python3 -m http.server 8899`
