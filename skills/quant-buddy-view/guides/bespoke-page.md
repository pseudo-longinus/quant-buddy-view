# Guide · 手搓 bespoke 页（自由排版 + 共享取数内核）

> 场景：`build_dashboard` 的通用 panel 满足不了——你要的是有版式设计感、自定义 SVG/交互的那种页面
> （像商品期货研报、泡沫监测终端、个股画像卡）。**呈现自由发挥，但"拿数据"这层别再各写各的。**

## 三条生产路，先选对

| 路 | 怎么做 | 何时用 |
|---|---|---|
| **在线模板** `static_page.py templates` / `template` | 先找公共模板，下载 HTML 后替换标的、文案和公式包凭证 | 个股画像、估值体检、异动榜、选股看板等固定页面形态 |
| **快路** `build_dashboard` | 写 `spec.json`，声明式出 line/bar/number/table | 没有合适在线模板，但标准看板足够 |
| **手搓 bespoke**（本剧本） | Agent 直接写 HTML/CSS/SVG，数据层调**取数内核** | 在线模板和快路都做不出的自定义版式/交互 |

> 快路里那套"取数 + 清洗 + 容错"已经写对了一份（内联在生成的 HTML 里）。手搓页够不着它，
> 所以单独抽了一份同口径的 **取数内核** `assets/data-kernel.js` 给手搓页用——**别再自己抄 `fetch`/解包逻辑**。
> 手搓只负责主体内容。公共 shell 不是页面模板；不要复制 demo 样式或另起一套页头、页尾、二维码、刷新按钮。

## 核心原则：分层

- **公共外壳（固定统一）**：页头、页尾、刷新按钮、分享海报弹层、复制/下载 PNG —— 全交给 `assets/share-shell/`。
- **数据层（往死里统一）**：怎么连服务器、读流、解包、清洗缺口、出错怎么喊 —— 全交给内核，一份，改一处全好。
- **呈现层（完全自由）**：页面长什么样、用什么图形、配色版式 —— 你随意，内核不管。
- **环境配置（保持灵活）**：取数地址 `endpoint` 由你按环境填（测试/正式），内核不写死。

## 五步接入

1. 先查在线模板；没有合适模板时，才写 bespoke 主体 HTML。
2. 主体 HTML 放入 `QB_SHARED_*` 占位，并调用 `QBShareShell.init({ onRefresh: load, getPosterData })`。
3. 填 `CONFIG = { endpoint, package_id, signature }`；地址按测试/正式环境填写。
4. 用 `QB.query(CONFIG)` 取数，再用 `QB.series` / `QB.lastValue` / `QB.topValues` 解包。
5. 用 `compile_bespoke_page.py` 编译发布，脚本会内联 share shell、logo、qr-mini 和 data-kernel。

```js
const CONFIG = { endpoint, package_id, signature };

async function load() {
  const out = await QB.query(CONFIG);
  const px = QB.series(out, "px", { dropZero: true });
  const chg = QB.lastValue(out, "chg");
  const leaders = QB.topValues(out, "GAIN").slice(0, 5);
  return { px, chg, leaders };
}
```

> 发布是自包含 HTML，所以不要手工保留 `<script src>` 外链。用 `python scripts/compile_bespoke_page.py @params.json` 编译，编译器负责内联公共组件和运行时资产。

## 数据契约：产出形态 → 用哪个内核函数

公式包每个产出按其 `read_mode` 回来一种形态，对应一个解包函数：

| 产出形态（read_mode） | 长相 | 取它用 | 说明 |
|---|---|---|---|
| `range_data` | `{dates:[], values:[]}` | `QB.series(out,k,{dropZero})` → `[{d,v}]` | 序列/折线；`QB.values(...)` 只要数值数组 |
| `last_day_stats`（1维序列） | `{last_value:{date, value}}` | `QB.lastValue(out,k)` / `QB.lastDate(out,k)` | 单值卡；注册时不要写 `last_value` read_mode |
| `last_day_stats` | `{date, top_values:[{asset,name,value}]}` | `QB.topValues(out,k)` / `QB.statDate(out,k)` | 截面榜单 |

日期整数 `YYYYMMDD` → `QB.fmtDate(d)` 出 `'YYYY-MM-DD'`（分隔符可换：`QB.fmtDate(d,'.')`）。

## 两个必须记住的坑（内核已替你处理，但你要会用对）

1. **价格的假 0**：平台数据缺口时会喂 `0`。价格/成交额这种"不可能为 0"的序列，取数时**开 `{dropZero:true}`**，
   否则会画出一条掉到 0 的假线还不报错（这就是"假成功"）。
   ——但**涨跌幅/收益率的 0 是合法平盘值，绝不能 dropZero**。按数据含义选。
2. **出错就喊,别画假图**：`QB.query` 在 HTTP 失败 / 服务端报错 / 三件套没填时会 `throw`。
   页面必须 `try/catch`，把 `e.message` 显式塞进一个"错误槽"展示，**不要 catch 后当无事发生继续画**。

## 发布前自查（手搓页最容易翻车的三处）

- [ ] **地址协议**：页面要发布到 `https://` 的话，`endpoint` 必须也是 `https://`。
      填了 `http://` 测试地址，本地能开、一发布到线上就被浏览器拦（mixed-content）。内核会 `console.warn` 提醒，但不强改。
- [ ] **价格序列开了 `dropZero`**：所有价格/成交额类折线，确认带了 `{dropZero:true}`。
- [ ] **错误槽接好了**：断网/换个错 `package_id` 试一次，确认页面显示"取数失败：…"而不是一片空白或假图。
- [ ] **公共 shell 接好了**：页头为 `QuantBuddy · 宽宝`，按钮为 `刷新数据 / 分享 / 开始使用`，页面正文不再保留旧的“手机扫码查看”二维码块。

## 前置硬门槛（与其它剧本一致）

手搓页用的公式包，**仍须先在 quant-buddy-skill 用 `runMultiFormulaBatchStream` 跑通确认出数、再 `register`**
（见 [SKILL.md](../SKILL.md) 硬规则 2）。手搓只改"呈现层"，不改"公式必须先验证"这条。
