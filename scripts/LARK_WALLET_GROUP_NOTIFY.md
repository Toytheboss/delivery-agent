# Lark 钱包地址日报（推送到已有群）

群：**项目方地址推送 FormToLark**  
`chat_id`: `oc_74ee8d69f6c00ff153bd78c301545a7f`

## 行为

- Bot 运行期间轮询「项目方钱包地址搜集」新行  
- **每天 00:00（Asia/Shanghai，晚上 12 点）** 向该群推送一次日报：  
  - 统计的是**刚结束的那一天**新增项目数  
  - 地址填写数量（各地址字段非空合计）  
  - 项目明细列表  
- 首次启动会基线已有数据，**不会**把历史项目算进「今天」

## 配置

```yaml
workflow:
  lark_digest_enabled: true
  lark_digest_chat_id: "oc_74ee8d69f6c00ff153bd78c301545a7f"
  lark_digest_hour: 0   # 0 = 午夜；若改 22 则是当天 22:00 报「当天」
```

## 手动补发今天日报（测试）

```bash
cd "/Users/roy/Documents/Delivery/Delivery Agent"
source .venv/bin/activate
python - <<'PY'
import asyncio
from dotenv import load_dotenv
load_dotenv('.env')
from bot.config_loader import load_config
from bot.workflow_lark_wallet_group import run_lark_daily_digest_once

async def main():
    cfg = load_config()
    # force_date 用于测试：强制按某天统计并发送（会更新 last_digest_date）
    ok = await run_lark_daily_digest_once(cfg, force_date=None)
    # 若今天已发过，可临时删 data/lark_wallet_digest_state.json 里的 last_digest_date 再测
    print('sent', ok)

asyncio.run(main())
PY
```

## 说明

不再「每条新建一个群」。人已在推送群里、机器人已进群即可。
