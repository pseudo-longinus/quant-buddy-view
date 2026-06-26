# 模板路由（线上优先）

模板已**统一走在线接口**，本目录不再存放模板文件，只说明路由。

## 线上公共模板（首选）

用户提到**模板市场 / 官方模板 / 公共模板 / 已发布模板**时：

1. `python scripts/static_page.py templates` —— 列出在线公共模板（普通用户只见 `published`）。
2. `python scripts/static_page.py template '{"page_id":"page_xxx"}'` —— 看某模板详情，拿 `download_url`。
3. 直连 `download_url`（OSS）取回 HTML，替换标的、文案、公式包凭证后，再 `upload` 成用户自己的页面。

详见 [tools/static_page.md](../tools/static_page.md) 的 `templates` / `template` 小节。

## 离线参考模板（兜底 / 开发源）

线上接口不可用，或用户要一个具体页面形态但未指明公共模板时，从 **[`../examples/`](../examples/README.md)** 挑最贴近的形态起步。

## 公共页头页尾组件

所有落地页共用的页头、页尾、刷新按钮、分享海报弹层等，由 **[`../assets/share-shell/`](../assets/share-shell/README.md)** 提供（是公共组件，不是模板）。
