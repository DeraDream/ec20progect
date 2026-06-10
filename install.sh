#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_NAME="ec20-manager"
INSTALL_DIR="${EC20_INSTALL_DIR:-/opt/${PROJECT_NAME}}"
BIN_PATH="${EC20_BIN_PATH:-/usr/local/bin/ec20}"
SERVICE_NAME="${PROJECT_NAME}.service"
SOURCE_ARCHIVE_URL="${EC20_SOURCE_ARCHIVE_URL:-https://github.com/DeraDream/ec20progect/archive/refs/heads/main.tar.gz}"

# Keep every required command here. When a feature adds a dependency, update
# this list and package_for_command() so both installs and upgrades receive it.
REQUIRED_COMMANDS=(curl tar unzip systemctl python3)

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
    unzip) printf 'unzip' ;;
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

ensure_lpac() {
  local machine pattern metadata download_url archive target binary library_path check_output
  if command -v lpac >/dev/null 2>&1 && [[ -x "$(command -v lpac)" ]]; then
    check_output="$(lpac --help 2>&1 || true)"
    if lpac_output_is_healthy "${check_output}"; then
      ok "lpac 环境检查通过"
      return
    fi
    warn "现有 lpac 无法正常启动，将重新安装"
  fi

  machine="$(uname -m)"
  case "${machine}" in
    x86_64|amd64) pattern="^lpac-linux-x86_64\\.zip$" ;;
    aarch64|arm64) pattern="^lpac-linux-aarch64\\.zip$" ;;
    *) die "lpac 暂不支持当前 CPU 架构：${machine}" ;;
  esac
  target="${INSTALL_DIR}/tools/lpac"
  archive="$(mktemp)"
  metadata="$(mktemp)"
  mkdir -p "${target}"
  log "正在获取 lpac 最新版本..."
  curl --fail --location --retry 3 \
    --output "${metadata}" "https://api.github.com/repos/estkme-group/lpac/releases/latest"
  download_url="$(python3 -c 'import json,re,sys; data=json.load(open(sys.argv[1])); pattern=re.compile(sys.argv[2],re.I); print(next((a["browser_download_url"] for a in data.get("assets",[]) if pattern.search(a["name"])),""))' "${metadata}" "${pattern}")"
  rm -f "${metadata}"
  [[ -n "${download_url}" ]] || die "未找到匹配当前架构的 lpac Linux 安装包"
  log "正在安装 lpac..."
  curl --fail --location --retry 3 --output "${archive}" "${download_url}"
  rm -rf "${target:?}/"*
  unzip -q "${archive}" -d "${target}"
  rm -f "${archive}"
  binary="$(find "${target}" -type f -name lpac -print -quit)"
  [[ -n "${binary}" ]] || die "lpac 安装包中未找到可执行文件"
  chmod 755 "${binary}"
  library_path="$(find "${target}" -type f -name '*.so*' -printf '%h\n' |
    sort -u | paste -sd: -)"
  cat >"/usr/local/bin/lpac" <<EOF
#!/usr/bin/env bash
export LD_LIBRARY_PATH="${library_path:-${target}}:\${LD_LIBRARY_PATH:-}"
exec "${binary}" "\$@"
EOF
  chmod 755 /usr/local/bin/lpac
  if command -v ldd >/dev/null 2>&1; then
    check_output="$(LD_LIBRARY_PATH="${library_path:-${target}}" ldd "${binary}" 2>&1 || true)"
    if grep -q 'not found' <<<"${check_output}"; then
      printf '%s\n' "${check_output}" >&2
      die "lpac 缺少动态库，请查看以上检查结果"
    fi
  fi
  check_output="$(lpac --help 2>&1 || true)"
  lpac_output_is_healthy "${check_output}" || {
    printf '%s\n' "${check_output}" >&2
    die "lpac 无法启动或动态库不兼容"
  }
  ok "lpac 安装并检查通过"
}

ensure_lpac_qmi() {
  local machine pattern metadata download_url archive target binary check_output
  machine="$(uname -m)"
  case "${machine}" in
    x86_64|amd64) pattern="^lpac-linux-x86_64-with-qmi\\.zip$" ;;
    aarch64|arm64) pattern="^lpac-linux-aarch64-with-qmi\\.zip$" ;;
    *) return ;;
  esac
  target="${INSTALL_DIR}/tools/lpac-qmi"
  archive="$(mktemp)"
  metadata="$(mktemp)"
  mkdir -p "${target}"
  curl --fail --location --retry 3 --output "${metadata}" \
    "https://api.github.com/repos/estkme-group/lpac/releases/latest" || {
      rm -f "${metadata}" "${archive}"
      warn "无法获取 lpac QMI 发布信息，跳过可选 QMI 后端"
      return
    }
  download_url="$(python3 -c 'import json,re,sys; data=json.load(open(sys.argv[1])); pattern=re.compile(sys.argv[2],re.I); print(next((a["browser_download_url"] for a in data.get("assets",[]) if pattern.search(a["name"])),""))' "${metadata}" "${pattern}")"
  rm -f "${metadata}"
  [[ -n "${download_url}" ]] || { warn "未找到 lpac QMI 安装包"; return; }
  log "正在安装可选的 lpac QMI 后端..."
  curl --fail --location --retry 3 --output "${archive}" "${download_url}" || {
    rm -f "${archive}"
    warn "lpac QMI 下载失败，跳过可选 QMI 后端"
    return
  }
  rm -rf "${target:?}/"*
  unzip -q "${archive}" -d "${target}" || {
    rm -f "${archive}"
    warn "lpac QMI 安装包解压失败，跳过可选 QMI 后端"
    return
  }
  rm -f "${archive}"
  binary="$(find "${target}" -type f -name lpac -print -quit)"
  [[ -n "${binary}" ]] || { warn "lpac QMI 安装包无可执行文件"; return; }
  chmod 755 "${binary}"
  cat >"/usr/local/bin/lpac-qmi" <<EOF
#!/usr/bin/env bash
exec "${binary}" "\$@"
EOF
  chmod 755 /usr/local/bin/lpac-qmi
  check_output="$(lpac-qmi --help 2>&1 || true)"
  if ! lpac_output_is_healthy "${check_output}"; then
    warn "lpac QMI 后端与系统 libqmi 不兼容；AT 后端仍可正常使用"
  else
    ok "lpac QMI 后端安装完成"
  fi
}

lpac_output_is_healthy() {
  local output="${1,,}"
  [[ -n "${output}" &&
    "${output}" != *"error while loading shared libraries"* &&
    "${output}" != *"symbol lookup error"* &&
    "${output}" != *"undefined symbol"* ]]
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

  python3 -m py_compile "${INSTALL_DIR}/app/backend/ec20.py" "${INSTALL_DIR}/app/backend/lpac.py" \
    "${INSTALL_DIR}/app/backend/runtime_log.py" "${INSTALL_DIR}/app/backend/server.py" ||
    die "后端 Python 语法检查失败"
  install -m 644 "${service_source}" "/etc/systemd/system/${SERVICE_NAME}"
  systemctl daemon-reload
  systemctl enable "${SERVICE_NAME}"
  systemctl restart "${SERVICE_NAME}"
  local healthy="false"
  local attempt
  for attempt in {1..10}; do
    if systemctl is-active --quiet "${SERVICE_NAME}" &&
      curl --fail --silent --max-time 2 http://127.0.0.1:7571/api/health >/dev/null; then
      healthy="true"
      break
    fi
    sleep 1
  done
  if [[ "${healthy}" != "true" ]]; then
    journalctl -u "${SERVICE_NAME}" -n 30 --no-pager >&2 || true
    die "Web 服务健康检查失败，以上为服务日志"
  fi
}

get_web_ip() {
  local address=""
  address="$(hostname -I 2>/dev/null | tr ' ' '\n' | awk -F. '
    /^10\./ {print; exit}
    /^192\.168\./ {print; exit}
    /^172\./ && $2 >= 16 && $2 <= 31 {print; exit}
  ')"
  [[ -n "${address}" ]] || address="$(hostname -I 2>/dev/null | tr ' ' '\n' |
    awk '!/^$/ && !/^127\./ && !/^169\.254\./ && !/^198\.(18|19)\./ {print; exit}')"
  printf '%s' "${address:-127.0.0.1}"
}

deploy_from_source() {
  local source_root="$1"
  local mode="$2"
  local new_app="${INSTALL_DIR}/.app-new"

  [[ -d "${source_root}/app" ]] || die "源码中缺少 app 目录"
  ensure_environment

  mkdir -p "${INSTALL_DIR}/data" "${INSTALL_DIR}/logs" "${INSTALL_DIR}/backups"
  ensure_lpac
  ensure_lpac_qmi
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
  source_root="$(download_source "${work_dir}")"

  # Run the downloaded installer's deployment path so a new release can add
  # environment requirements before its application files are activated.
  EC20_INSTALL_DIR="${INSTALL_DIR}" EC20_BIN_PATH="${BIN_PATH}" \
    bash "${source_root}/install.sh" --deploy-from "${source_root}" "${mode}"
  rm -rf "${work_dir}"
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

show_logs() {
  local log_file="${INSTALL_DIR}/logs/ec20-manager.log"
  mkdir -p "$(dirname "${log_file}")"
  touch "${log_file}"
  printf '实时日志：%s（按 Ctrl+C 退出）\n' "${log_file}"
  tail -n 200 -f "${log_file}"
}

show_ports() {
  printf '\n串口设备：\n'
  for device in /dev/ttyUSB* /dev/ttyACM*; do
    [[ -e "${device}" ]] || continue
    printf '%-24s -> %s\n' "${device}" "$(readlink -f "${device}")"
  done
  printf '\n稳定串口别名：\n'
  if [[ -d /dev/serial/by-id ]]; then
    for device in /dev/serial/by-id/*; do
      [[ -e "${device}" ]] || continue
      printf '%-60s -> %s\n' "${device}" "$(readlink -f "${device}")"
    done
  else
    printf '无 /dev/serial/by-id 目录\n'
  fi
  printf '\nUSB 串口驱动：\n'
  for tty_path in /sys/class/tty/ttyUSB* /sys/class/tty/ttyACM*; do
    [[ -e "${tty_path}" ]] || continue
    printf '%-16s %s\n' "$(basename "${tty_path}")" "$(readlink -f "${tty_path}/device")"
  done
}

show_menu() {
  while true; do
    printf '\n========== EC20 管理菜单 ==========\n'
    printf '1. 安装脚本\n2. 更新脚本\n3. 卸载脚本\n4. 查看实时日志\n5. 查看串口设备\n6. 退出\n'
    read -r -p "请选择 [1-6]：" choice
    case "${choice}" in
      1) install_or_update install ;;
      2)
        [[ -f "${INSTALL_DIR}/install.sh" ]] || die "尚未安装，请先选择 1"
        install_or_update update
        ;;
      3) uninstall_project ;;
      4) show_logs ;;
      5) show_ports ;;
      6) exit 0 ;;
      *) warn "请输入 1、2、3、4、5 或 6" ;;
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
    --logs) show_logs ;;
    --ports) show_ports ;;
    "") show_menu ;;
    *) die "未知参数：$1" ;;
  esac
}

main "$@"
