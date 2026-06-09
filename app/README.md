# EC20 Manager Application

首版应用提供：

- 自动探测 `/dev/ttyUSB*`、`/dev/ttyACM*` 和 `/dev/serial/by-id/*`
- 多设备扫描、选择、配置保存和删除
- EC20 型号、IMEI、ICCID、运营商、信号及注册状态
- SIM 卡短信读取、发送和删除，支持 UCS2 中文短信
- 自定义 AT 指令终端
- USSD 交互终端
- 通过 lpac 管理 eSTK Profile：读取、下载、切换、禁用、改名和删除
- 中文响应式 Web 管理页面

服务默认监听 `0.0.0.0:7571`。持久配置写入 `/opt/ec20-manager/data`，
升级时不会删除该目录。
