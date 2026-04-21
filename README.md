<div align="center">

# SteamTools ALLinOne

一款面向 Windows 的 Steam 桌面工具整合项目，提供统一的 Electron 图形界面与 FastAPI 本地服务，集中处理常用的 Steam 辅助功能。

<p>
  <img src="https://img.shields.io/badge/platform-Windows-1677ff?style=for-the-badge" alt="Windows" />
  <img src="https://img.shields.io/badge/frontend-React%20%2B%20Electron-0f172a?style=for-the-badge" alt="React + Electron" />
  <img src="https://img.shields.io/badge/backend-FastAPI-059669?style=for-the-badge" alt="FastAPI" />
  <img src="https://img.shields.io/badge/license-GPLv3-f59e0b?style=for-the-badge" alt="GPLv3" />
</p>

</div>

## 项目简介

`SteamTools ALLinOne` 把多个分散的 Steam 相关功能整合到一个桌面应用里，目标是减少重复折腾，把常见操作集中到一个统一界面中完成。

当前项目采用：

- 前端：`React 19` + `Vite` + `Electron`
- 后端：`FastAPI` + `Uvicorn`
- 运行形态：本地桌面应用，前后端协同工作

## 功能概览

### 1. Manifest 下载与入库

- 支持按游戏名称或 `AppID` 搜索
- 支持下载任务进度与日志查看
- 支持自动入库与已入库内容清理
- 支持扫描本机已安装的 Steam 游戏

### 2. 修改器管理

- 支持按已安装游戏自动匹配可用修改器
- 支持版本列表整理、下载、缓存与启动
- 支持展示来源与哈希等基础安全信息

### 3. 补丁工具

- 提供资源检测与依赖下载入口
- 支持基础配置写入与状态检测
- 支持联机、用户、主配置、DLC 等参数管理
- 支持备份恢复与部分高级功能配置

### 4. Steam 工具箱

- 网络加速：按预设规则启用或关闭
- 账号切换：扫描本机 Steam 账号并快速切换
- 库存游戏：读取本地游戏库并执行挂机相关操作
- 本地令牌：管理 `TOTP / HOTP / Steam Guard` 验证码

## 界面模块

项目当前主要页面包括：

- `Manifest 下载`
- `修改器`
- `补丁工具`
- `Steam 工具箱`
- `设置`
- `开源许可声明`

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 桌面壳 | Electron |
| Web 前端 | React、Vite、Tailwind CSS、Lucide React |
| 本地 API | FastAPI、Uvicorn |
| 数据处理 | requests、BeautifulSoup、cloudscraper、py7zr、rarfile |
| 运行环境 | Windows、Node.js、Python |

## 项目结构

```text
SteamToolsALLinOne/
├─ app/                # Electron + React 前端
├─ backend/            # FastAPI 本地服务
├─ src/                # 旧有/补充脚本逻辑
├─ resources/          # 程序资源与工具文件
├─ data/               # 本地数据
├─ download/           # 下载输出
├─ backend-dist/       # 打包后的后端产物
├─ requirements.txt    # Python 依赖
└─ LICENSE             # GPLv3 许可证
```

## 本地开发

### 环境要求

- Windows 10 / 11
- `Node.js 20+`
- `Python 3.11+`
- `npm`

### 1. 安装后端依赖

```powershell
pip install -r requirements.txt
```

### 2. 安装前端依赖

```powershell
cd app
npm install
```

### 3. 启动前端开发环境

```powershell
cd app
npm run dev
```

### 4. 单独启动后端

```powershell
python -m backend.server
```

默认后端地址为：

```text
http://127.0.0.1:18765
```

## 构建

前端桌面包构建命令：

```powershell
cd app
npm run dist
```

便携版构建命令：

```powershell
cd app
npm run dist:portable
```

## 使用说明

- 本项目主要面向本地 Windows 环境，不保证跨平台行为一致
- 某些功能依赖本机 Steam 安装路径、注册表信息或管理员权限
- 网络加速等能力会修改系统级配置，使用前建议先了解其作用与影响

## 开源协议

本项目现以 [GNU General Public License v3.0](./LICENSE) 发布。

如果你分发修改版本，需遵循 GPLv3 的对应义务，包括但不限于：

- 保留原有版权与许可证声明
- 继续以 GPL 兼容方式开放修改后的源码
- 在分发时一并提供许可证文本

## 免责声明

本项目按“原样”提供，不附带任何明示或暗示担保。请在遵守相关平台规则、软件许可协议以及所在地法律法规的前提下使用。

## 致谢

项目界面中的开源声明已列出部分参考或使用到的上游项目，在此一并致谢相关作者与社区贡献者。
