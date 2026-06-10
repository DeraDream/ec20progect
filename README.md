# EC20 Manager

EC20/eSTK 可视化管理项目。

当前版本默认监听：

```text
http://服务器IP:7571
```

已提供多设备扫描与配置、EC20 状态、AT 终端和 eSTK APDU 通道。eSTK
配置文件下载与切换功能将在 LPA 接入后提供。

安装或更新完成后，终端会自动显示带真实服务器 IP 的 Web 访问地址。

## 一键运行

使用以下命令直接从 GitHub 安装：

```bash
curl -fsSL https://raw.githubusercontent.com/DeraDream/ec20progect/main/install.sh | sudo bash -s -- --install
```

安装成功后，随时执行以下命令唤起菜单：

```bash
sudo ec20
```

实时查看服务、eSIM 与 lpac 日志：

```bash
sudo ec20 --logs
```

日志文件位于 `/opt/ec20-manager/logs/ec20-manager.log`，Web 设备页面也提供只读“实时日志”终端。

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
- 默认从 `DeraDream/ec20progect` 的 `main` 分支下载最新版。
- 如需使用镜像或私有源码包，可设置 `EC20_SOURCE_ARCHIVE_URL`。
- 新功能需要额外环境时，必须同时更新 `install.sh` 中的
  `REQUIRED_COMMANDS` 和 `package_for_command()`。
- 更新流程会先执行新版本安装器的环境检查，再替换应用文件。

## 本地部署测试

在 Linux 中可跳过网络下载，直接以当前目录为源码安装：

```bash
sudo EC20_SOURCE_DIR="$PWD" bash install.sh --install
```
