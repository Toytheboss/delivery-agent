# 项目方 Google 表单 →「项目方钱包地址搜集」自动同步

**目标：** 项目方提交表单后，自动新增/更新 Lark 表  
`项目方钱包地址搜集`（`tblj0FdKPrlc7PrM`）

表单：https://docs.google.com/forms/d/1bllA7I6Z6-ad0AE5TLICNmlrKRgPOl71aHiQevrcp-8/viewform  

Lark 写权限已验证可用（同一应用 `cli_aadabac98cb8ded0`）。

---

## 你需要做的（一次性，约 10 分钟）

> 这一步必须在 **Google 账号** 里配置，我无法替你点 Google 后台。

### 1. 关联回复表格
打开 Google 表单 → **回复** → 点绿色表格图标 → 创建/关联电子表格。

### 2. 粘贴脚本
打开该电子表格 → **扩展程序 → Apps Script** → 清空默认代码 →  
粘贴仓库文件：`scripts/google_form_to_lark.gs` 全文 → 保存。

### 3. 写入 Lark 密钥
Apps Script 左侧 **项目设置（齿轮）→ 脚本属性 → 添加属性**：

| 属性 | 值 |
|------|-----|
| `LARK_APP_ID` | 与 bot `.env` 里相同 |
| `LARK_APP_SECRET` | 与 bot `.env` 里相同 |

### 4. 核对字段映射
打开表单「问题」标题，对照脚本顶部的 `FIELD_MAP`：

- **左侧** = Google 表单问题标题（必须一字不差）
- **右侧** = Lark 列名

Lark 目标列目前是：
- Project name  
- Project logo  
- Contract Addresss/主网合约  
- Treasury Address  
- Fee Collector / Revenue Wallet Address  
- Multi-sig Threshold (Optional)  
- Grant Receiving Wallet (Optional)  
- MM / LP Wallet （Optional）  

若表单标题不同，只改 `FIELD_MAP` 左侧。

### 5. 添加触发器
Apps Script → **触发器（闹钟图标）→ 添加触发器**：

- 函数：`onFormSubmit`
- 事件来源：**从表单**
- 事件类型：**表单提交时**

### 6. 授权 + 测试
1. 手动运行一次 `authorizeLark`（允许授权；勿用结尾 `_` 的函数名，下拉列表会隐藏）  
2. 用表单提交一条测试数据  
3. 打开 Lark「项目方钱包地址搜集」看是否出现/更新该项目  

若没写入：Apps Script → **执行次数** 里看失败日志；常见原因是 `FIELD_MAP` 标题不一致。

---

## 行为说明

- 按 **Project name** 查找：已有则 **更新**，没有则 **新建**
- 同步成功后，bot 侧第 8 步会轮询该表；必填字段齐全时通知财务/运营/技术群

---

## 我无法代做的部分

无法登录你的 Google 表单后台安装脚本。你按上面做完后，发我一句「已配好」，我可以再帮你用 Lark API 核对是否出现测试行。
