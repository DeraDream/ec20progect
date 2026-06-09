# EC20 Manager

EC20/eSTK 可视化管理项目。

当前版本安装后访问：

```text
http://服务器IP:7571
```

已提供 EC20 状态、短信收发、AT 终端和 eSTK APDU 通道。eSTK 配置文件
下载与切换功能将在 LPA 接入后提供。

安装完成后终端会显示 Web 访问令牌。令牌持久保存在
`/opt/ec20-manager/data/web.env`，更新不会改变它。

## 一键运行

将仓库发布到服务器后，把 `install.sh` 中的 `SOURCE_ARCHIVE_URL` 改为实际
源码压缩包地址。用户可执行：

```bash
curl -fsSL https://your-server.example/install.sh | sudo bash -s -- --install
```

安装成功后，随时执行以下命令唤起菜单：

```bash
sudo ec20
```

菜单功能：

1. 安装脚本
2. 更新脚本
3. 卸载脚本
4. 退出

## 目录约定

所有工程文件均位于 `/opt/ec20-manager`：

```text
/opt/ec20-manager/
├── app/          # 应用程序，更新时替换
├── backups/      # 上一个应用版本
├── data/         # 持久数据，更新时保留
├── logs/         # 日志，更新时保留
└── install.sh    # 最新管理脚本
```

## 发布与环境依赖

- 源码压缩包必须包含根目录下的 `install.sh` 和 `app/`。
- 发布前必须配置 `SOURCE_ARCHIVE_URL`，也可在运行时设置
  `EC20_SOURCE_ARCHIVE_URL`。
- 新功能需要额外环境时，必须同时更新 `install.sh` 中的
  `REQUIRED_COMMANDS` 和 `package_for_command()`。
- 更新流程会先执行新版本安装器的环境检查，再替换应用文件。

## 本地部署测试

在 Linux 中可跳过网络下载，直接以当前目录为源码安装：

```bash
sudo EC20_SOURCE_DIR="$PWD" bash install.sh --install
```
