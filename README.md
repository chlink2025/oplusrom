# OnePlus/OPPO ROM 下载项目

本项目提供了基于 oplusupdater 的 ROM 资源及下载工具。

## 📂 目录结构说明

* **links/**: 存放各机型 ROM 的原始下载链接。
* **updater**: 核心更新组件，目前来自[OplusUpdater-android](https://github.com/chlink2025/OplusUpdater-android) 开源项目中的OplusUpdater文件夹。

---

## ⚠️ ColorOS 16 下载特别说明

针对目前 **ColorOS 16** 带有 `downloadCheck` 参数的下载链接，直接请求将无法获取文件。其拥有一定验证机制

### **验证机制**
必须在请求头（Request Header）中包含特定的 `userid`。服务器校验该请求头后，会通过 **HTTP 302 Found** 状态码，将请求重定向至一个可供下载的动态链接。

### **必须的请求头**
* **Key**: `userid`
* **Value**: `oplus-ota|` (注意：必须包含末尾的竖线符号)

---

## 💻 命令行操作示范
### **1. 获取重定向链接 (curl --head)**
使用以下命令查看服务器返回的 `location` 字段：
```bash
curl --head -H "userid: oplus-ota|" "[替换为links内的URL]"
