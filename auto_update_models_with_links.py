#!/usr/bin/env python3
import os
import sys
import json
import subprocess
import argparse
import re
from datetime import datetime

# 去除 ANSI 颜色码
ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

def strip_ansi_codes(text):
    return ANSI_ESCAPE.sub('', text)

def run_updater(ota_version, region="CN", mode="manual", proxy=None):
    cmd = ["./updater", ota_version, "--region", region, "--mode", str(mode)]
    if proxy:
        cmd += ["-p", proxy]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=60)
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"updater 执行失败: {e.stderr.strip()}")
        return None
    except subprocess.TimeoutExpired:
        print("updater 查询超时")
        return None
    except FileNotFoundError:
        print("错误：未找到 ./updater 可执行文件")
        sys.exit(1)

def parse_updater_output(raw_output):
    if not raw_output:
        return None
    clean_output = strip_ansi_codes(raw_output)
    try:
        data = json.loads(clean_output)
        body = data.get("body", {})

        # 优先使用 realOtaVersion
        new_ota = body.get("realOtaVersion") or body.get("otaVersion", "")
        if not new_ota:
            return None

        # 组件包处理：优先 my_stock
        rom_link = "无"
        components = body.get("components", [])
        for comp in components:
            packets = comp.get("componentPackets", {})
            manual_url = packets.get("manualUrl", "")
            if manual_url:
                comp_name = comp.get("componentName", "")
                if comp_name == "my_manifest":
                    rom_link = manual_url
                    break
                if rom_link == "无":
                    rom_link = manual_url

        # 版本字段优先级（与 Android App 完全一致）
        display_coloros = (
            body.get("realVersionName") or
            body.get("realOsVersion") or
            body.get("colorOSVersion") or
            body.get("osVersion") or
            "未知"
        )

        display_android = body.get("realAndroidVersion") or body.get("androidVersion") or "未知"

        security_patch = body.get("securityPatch") or body.get("securityPatchVendor") or "未知"

        published_time = body.get("publishedTime", 0)
        if published_time > 1000000000000:
            published_time //= 1000
        publish_str = datetime.fromtimestamp(published_time).strftime("%Y/%m/%d %H:%M:%S") if published_time else "未知"

        return {
            "otaVersion": new_ota,
            "versionName": body.get("versionName", "未知"),
            "realAndroidVersion": display_android,
            "colorOSVersion": display_coloros,
            "securityPatch": security_patch,
            "publishedTimeStr": publish_str,
            "descriptionUrl": body.get("description", {}).get("panelUrl", "无"),
            "romDownloadLink": rom_link,
        }
    except json.JSONDecodeError:
        print("JSON 解析失败（可能是无更新响应）")
        return None

def extract_ota_from_line(line):
    return line.split('#')[0].strip()

def process_folder(folder_dir, links_root_dir, region, mode, proxy):
    folder_name = os.path.basename(folder_dir)
    txt_file = os.path.join(folder_dir, "ota-version.txt")

    if not os.path.isfile(txt_file):
        print(f"跳过文件夹 {folder_name}：缺少 ota-version.txt")
        return

    target_links_dir = os.path.join(links_root_dir, folder_name)
    os.makedirs(target_links_dir, exist_ok=True)

    print(f"\n=== 处理文件夹：{folder_name} ===")
    print(f"   ROM 链接将保存至: {target_links_dir}/")

    updated = False

    while True:
        with open(txt_file, "r", encoding="utf-8") as f:
            lines = [line.rstrip() for line in f if line.strip()]

        if not lines:
            print("ota-version.txt 为空，停止")
            break

        current_line = lines[-1]
        current_ota = extract_ota_from_line(current_line)
        print(f"当前检查版本：{current_ota}")

        raw_output = run_updater(current_ota, region, mode, proxy)
        if not raw_output:
            print("查询失败，停止循环")
            break

        info = parse_updater_output(raw_output)
        if not info:
            print(f"文件夹 {folder_name} 已无更多更新（当前为最新）")
            break

        new_ota = info["otaVersion"]

        if new_ota == current_ota:
            print(f"文件夹 {folder_name} 已无更多更新")
            break

        coloros_version = info["colorOSVersion"]

        new_line = f"{new_ota}  # ColorOS: {coloros_version}"
        with open(txt_file, "a", encoding="utf-8") as f:
            f.write(new_line + "\n")

        # 生成链接文件
        safe_version_name = coloros_version.replace("/", "_").replace("\\", "_").replace(":", "_").replace("*", "_").replace("?", "_").replace("\"", "_").replace("<", "_").replace(">", "_").replace("|", "_")
        link_file = os.path.join(target_links_dir, f"{safe_version_name}.txt")

        with open(link_file, "w", encoding="utf-8") as f:
            f.write(info["romDownloadLink"] + "\n")
            if "ColorOS 16" in info["colorOSVersion"]:
                f.write("//下载此链接请在请求头中加入名字为userid内容为oplus-ota|的请求头\n")

        # 更新 latest-update.txt（内容更丰富，接近 App 显示）
        info_file = os.path.join(folder_dir, "latest-update.txt")
        with open(info_file, "w", encoding="utf-8") as f:
            f.write(f"本地更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"最新 OTA 版本: {new_ota}\n")
            f.write(f"版本名称: {info['versionName']}\n")
            f.write(f"Android 版本: {info['realAndroidVersion']}\n")
            f.write(f"ColorOS 版本: {coloros_version}\n")
            f.write(f"安全补丁: {info['securityPatch']}\n")
            f.write(f"发布时间: {info['publishedTimeStr']}\n")
            f.write(f"ROM 下载链接: {info['romDownloadLink']}\n")
            f.write(f"更新日志链接: {info['descriptionUrl']}\n")

        print(f"发现新版本 → {new_ota} ({coloros_version})")
        if "ColorOS 16" in coloros_version:
            print("   此版本为 ColorOS 16，已添加下载提示")
        print(f"   ROM 链接已保存至: links/{folder_name}/{safe_version_name}.txt")
        updated = True

    if not updated:
        print(f"文件夹 {folder_name} 无新版本")

def main():
    parser = argparse.ArgumentParser(description="批量更新 OTA 版本（优化字段优先级 + 更美观输出）")
    parser.add_argument("root_dir", nargs="?", default="models", help="包含 ota-version.txt 的文件夹根目录")
    parser.add_argument("--links_dir", default="links", help="ROM 链接存储根目录")
    parser.add_argument("--region", default="CN")
    parser.add_argument("--mode", default="manual")
    parser.add_argument("-p", "--proxy", default=None)

    args = parser.parse_args()

    root_dir = args.root_dir
    links_root_dir = args.links_dir

    if not os.path.isdir(root_dir):
        print(f"错误：目录 {root_dir} 不存在")
        sys.exit(1)

    os.makedirs(links_root_dir, exist_ok=True)

    print("开始批量更新（字段优先级与官方 App 一致）")
    print(f"模型目录: {root_dir} | ROM 链接目录: {links_root_dir}")
    print(f"地区: {args.region} | 模式: {args.mode} | 代理: {args.proxy or '无'}")
    print("=" * 80)

    for item in sorted(os.listdir(root_dir)):
        folder_dir = os.path.join(root_dir, item)
        if os.path.isdir(folder_dir):
            process_folder(folder_dir, links_root_dir, args.region, args.mode, args.proxy)

    print("\n所有文件夹处理完成！")

if __name__ == "__main__":
    main()
