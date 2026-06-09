#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_NAME="ec20-manager"
INSTALL_DIR="${EC20_INSTALL_DIR:-/opt/${PROJECT_NAME}}"
BIN_PATH="${EC20_BIN_PATH:-/usr/local/bin/ec20}"
SERVICE_NAME="${PROJECT_NAME}.service"
SOURCE_ARCHIVE_URL="${EC20_SOURCE_ARCHIVE_URL:-https://github.com/DeraDream/ec20progect/archive/refs/heads/main.tar.gz}"

# Keep every required command here. When a feature adds a dependency, update
# this list and package_for_command() so both installs and upgrades receive it.
REQUIRED_COMMANDS=(curl tar systemctl python3)

log() { printf '\033[1;34m[EC20]\033[0m %s\n' "$*" >&2; }
ok() { printf '\033[1;32m[成功]\033[0m %s\n' "$*" >&2; }
warn() { printf '\033[1;33m[提示]\033[0m %s\n' "$*" >&2; }
die() { printf '\033[1;31m[错误]\033[0m %s\n' "$*" >&2; exit 1; }

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    die "请使用 root 用户运行，或执行：sudo bash install.sh"
  fi
}

detect_package_manager() {
  if command -v apt-get >/dev/null 2>&1; then
    PACKAGE_MANAGER="apt"
  elif command -v dnf >/dev/null 2>&1; then
    PACKAGE_MANAGER="dnf"
  elif command -v yum >/dev/null 2>&1; then
    PACKAGE_MANAGER="yum"
  elif command -v pacman >/dev/null 2>&1; then
    PACKAGE_MANAGER="pacman"
  elif command -v apk >/dev/null 2>&1; then
    PACKAGE_MANAGER="apk"
  else
    die "不支持当前 Linux 发行版：未找到 apt、dnf、yum、pacman 或 apk"
  fi
}

package_for_command() {
  local command_name="$1"
  case "${command_name}" in
    curl) printf 'curl' ;;
    tar) printf 'tar' ;;
    systemctl) printf 'systemd' ;;
    python3) printf 'python3' ;;
    *) printf '%s' "${command_name}" ;;
  esac
}

refresh_package_index() {
  case "${PACKAGE_MANAGER}" in
    apt) apt-get update ;;
    pacman) pacman -Sy --noconfirm ;;
    apk) apk update ;;
    dnf|yum) : ;;
  esac
}

install_package() {
  local package_name="$1"
  case "${PACKAGE_MANAGER}" in
    apt) DEBIAN_FRONTEND=noninteractive apt-get install -y "${package_name}" ;;
    dnf) dnf install -y "${package_name}" ;;
    yum) yum install -y "${package_name}" ;;
    pacman) pacman -S --noconfirm --needed "${package_name}" ;;
    apk) apk add --no-cache "${package_name}" ;;
  esac
}

ensure_environment() {
  local missing=()
  local command_name package_name

  detect_package_manager
  for command_name in "${REQUIRED_COMMANDS[@]}"; do
    command -v "${command_name}" >/dev/null 2>&1 || missing+=("${command_name}")
  done

  if ((${#missing[@]} == 0)); then
    ok "运行环境检查通过"
    return
  fi

  log "缺少环境：${missing[*]}"
  refresh_package_index
  for command_name in "${missing[@]}"; do
    package_name="$(package_for_command "${command_name}")"
    log "正在安装 ${package_name}..."
    install_package "${package_name}"
    command -v "${command_name}" >/dev/null 2>&1 ||
      die "${package_name} 安装后检查失败"
  done
  ok "所有运行环境已安装并检查通过"
}

find_source_root() {
  local base="$1"
  if [[ -f "${base}/install.sh" && -d "${base}/app" ]]; then
    printf '%s' "${base}"
    return
  fi

  local candidate
  candidate="$(find "${base}" -mindepth 1 -maxdepth 2 -type f -name install.sh -print -quit)"
  [[ -n "${candidate}" ]] || die "下载内容中没有找到 install.sh"
  dirname "${candidate}"
}

download_source() {
  local work_dir="$1"
  local archive="${work_dir}/source.tar.gz"

  if [[ -n "${EC20_SOURCE_DIR:-}" ]]; then
    [[ -f "${EC20_SOURCE_DIR}/install.sh" ]] || die "EC20_SOURCE_DIR 不是有效源码目录"
    printf '%s' "${EC20_SOURCE_DIR}"
    return
  fi

  log "正在下载最新版..."
  curl --fail --location --retry 3 --connect-timeout 15 \
    --output "${archive}" "${SOURCE_ARCHIVE_URL}"
  tar -xzf "${archive}" -C "${work_dir}"
  find_source_root "${work_dir}"
}

write_launcher() {
  cat >"${BIN_PATH}" <<EOF
#!/usr/bin/env bash
exec "${INSTALL_DIR}/install.sh" "\$@"
EOF
  chmod 755 "${BIN_PATH}"
}

install_service_if_present() {
  local service_source="${INSTALL_DIR}/app/deploy/${SERVICE_NAME}"
  if [[ ! -f "${service_source}" ]]; then
    warn "当前版本未提供 systemd 服务，跳过服务启动"
    return
  fi

  install -m 644 "${service_source}" "/etc/systemd/system/${SERVICE_NAME}"
  systemctl daemon-reload
  systemctl enable "${SERVICE_NAME}"
  systemctl restart "${SERVICE_NAME}"
}

get_web_ip() {
  local address=""
  if command -v ip >/dev/null 2>&1; then
    address="$(ip route get 1.1.1.1 2>/dev/null | awk '{for (i=1;i<=NF;i++) if ($i=="src") {print $(i+1); exit}}')"
  fi
  if [[ -z "${address}" ]]; then
    address="$(hostname -I 2>/dev/null | awk '{print $1}')"
  fi
  printf '%s' "${address:-127.0.0.1}"
}

deploy_from_source() {
  local source_root="$1"
  local mode="$2"
  local new_app="${INSTALL_DIR}/.app-new"

  [[ -d "${source_root}/app" ]] || die "源码中缺少 app 目录"
  ensure_environment

  mkdir -p "${INSTALL_DIR}/data" "${INSTALL_DIR}/logs" "${INSTALL_DIR}/backups"
  rm -rf "${new_app}"
  mkdir -p "${new_app}"
  cp -a "${source_root}/app/." "${new_app}/"

  if [[ -d "${INSTALL_DIR}/app" ]]; then
    rm -rf "${INSTALL_DIR}/backups/app-previous"
    mv "${INSTALL_DIR}/app" "${INSTALL_DIR}/backups/app-previous"
  fi
  mv "${new_app}" "${INSTALL_DIR}/app"
  install -m 755 "${source_root}/install.sh" "${INSTALL_DIR}/install.sh"
  write_launcher
  install_service_if_present

  ok "$([[ "${mode}" == "update" ]] && printf '更新' || printf '安装')完成"
  printf '工程目录：%s\n数据目录：%s\n菜单命令：ec20\n' \
    "${INSTALL_DIR}" "${INSTALL_DIR}/data"
  printf 'Web 地址：http://%s:7571\n' "$(get_web_ip)"
}

install_or_update() {
  local mode="$1"
  local work_dir source_root
  ensure_environment
  work_dir="$(mktemp -d)"
  trap 'rm -rf "${work_dir}"' RETURN
  source_root="$(download_source "${work_dir}")"

  # Run the downloaded installer's deployment path so a new release can add
  # environment requirements before its application files are activated.
  EC20_INSTALL_DIR="${INSTALL_DIR}" EC20_BIN_PATH="${BIN_PATH}" \
    bash "${source_root}/install.sh" --deploy-from "${source_root}" "${mode}"
}

uninstall_project() {
  local answer
  read -r -p "确定卸载 EC20 Manager？输入 YES 继续：" answer
  [[ "${answer}" == "YES" ]] || { warn "已取消卸载"; return; }

  if systemctl list-unit-files "${SERVICE_NAME}" >/dev/null 2>&1; then
    systemctl disable --now "${SERVICE_NAME}" 2>/dev/null || true
  fi
  rm -f "/etc/systemd/system/${SERVICE_NAME}" "${BIN_PATH}"
  systemctl daemon-reload

  read -r -p "是否同时删除数据目录 ${INSTALL_DIR}/data？输入 DELETE 删除：" answer
  if [[ "${answer}" == "DELETE" ]]; then
    rm -rf "${INSTALL_DIR}"
    ok "程序和数据已全部删除"
  else
    find "${INSTALL_DIR}" -mindepth 1 -maxdepth 1 \
      ! -name data ! -name logs -exec rm -rf {} +
    ok "程序已卸载，数据和日志已保留在 ${INSTALL_DIR}"
  fi
}

show_menu() {
  while true; do
    printf '\n========== EC20 管理菜单 ==========\n'
    printf '1. 安装脚本\n2. 更新脚本\n3. 卸载脚本\n4. 退出\n'
    read -r -p "请选择 [1-4]：" choice
    case "${choice}" in
      1) install_or_update install ;;
      2)
        [[ -f "${INSTALL_DIR}/install.sh" ]] || die "尚未安装，请先选择 1"
        install_or_update update
        ;;
      3) uninstall_project ;;
      4) exit 0 ;;
      *) warn "请输入 1、2、3 或 4" ;;
    esac
  done
}

main() {
  require_root
  case "${1:-}" in
    --deploy-from)
      [[ $# -eq 3 ]] || die "--deploy-from 参数错误"
      deploy_from_source "$2" "$3"
      ;;
    --install) install_or_update install ;;
    --update) install_or_update update ;;
    --uninstall) uninstall_project ;;
    "") show_menu ;;
    *) die "未知参数：$1" ;;
  esac
}

main "$@"
