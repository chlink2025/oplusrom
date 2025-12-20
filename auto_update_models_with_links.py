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

def run_updater(ota_version, region="CN", mode=0, proxy=None):
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

        new_ota = body.get("realOtaVersion", "")
        if not new_ota:
            return None

        rom_link = "无"
        components = body.get("components", [])
        for comp in components:
            packets = comp.get("componentPackets", {})
            manual_url = packets.get("manualUrl", "")
            if manual_url:
                comp_name = comp.get("componentName", "")
                if comp_name == "my_stock":
                    rom_link = manual_url
                    break
                if rom_link == "无":
                    rom_link = manual_url

        return {
            "otaVersion": new_ota,
            "versionName": body.get("versionName", "未知"),
            "realAndroidVersion": body.get("realAndroidVersion", "未知"),
            "realOsVersion": body.get("realOsVersion", "未知"),
            "realVersionName": body.get("realVersionName", "未知"),
            "securityPatch": body.get("securityPatch", "未知"),
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

    # 为当前文件夹在 links_root_dir 下创建同名子文件夹
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

        coloros_version = info["realVersionName"] if info["realVersionName"] != "未知" else info["realOsVersion"]

        new_line = f"{new_ota}  # ColorOS: {coloros_version}"
        with open(txt_file, "a", encoding="utf-8") as f:
            f.write(new_line + "\n")

        # === 生成 ROM 链接文件 ===
        safe_version_name = coloros_version.replace("/", "_").replace("\\", "_").replace(":", "_").replace("*", "_").replace("?", "_").replace("\"", "_").replace("<", "_").replace(">", "_").replace("|", "_")
        link_file = os.path.join(target_links_dir, f"{safe_version_name}.txt")

        with open(link_file, "w", encoding="utf-8") as f:
            f.write(info["romDownloadLink"] + "\n")
            # 如果 realOsVersion 包含 "ColorOS 16"，添加提示
            if "ColorOS 16" in info["realOsVersion"]:
                f.write("//下载此链接请在请求头中加入名字为userid内容为oplus-ota|的请求头\n")

        # 更新 latest-update.txt
        info_file = os.path.join(folder_dir, "latest-update.txt")
        with open(info_file, "w", encoding="utf-8") as f:
            f.write(f"本地更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"最新 OTA 版本: {new_ota}\n")
            f.write(f"版本名称: {info['versionName']}\n")
            f.write(f"Android 版本: {info['realAndroidVersion']}\n")
            f.write(f"ColorOS 版本: {coloros_version}\n")
            f.write(f"安全补丁: {info['securityPatch']}\n")
            f.write(f"ROM 下载链接: {info['romDownloadLink']}\n")
            f.write(f"更新日志链接: {info['descriptionUrl']}\n")

        print(f"发现新版本 → {new_ota} ({coloros_version})")
        if "ColorOS 16" in info["realOsVersion"]:
            print("   此版本为 ColorOS 16，已在链接文件中添加下载提示")
        print(f"   ROM 链接已保存至: links/{folder_name}/{safe_version_name}.txt")
        updated = True

    if not updated:
        print(f"文件夹 {folder_name} 无新版本")

def main():
    parser = argparse.ArgumentParser(description="批量更新 OTA 版本，ROM 链接保存至 links/ 下对应文件夹，ColorOS 16 版本添加下载提示")
    parser.add_argument("root_dir", nargs="?", default="models", help="包含 ota-version.txt 的文件夹根目录（默认: models）")
    parser.add_argument("--links_dir", default="links", help="ROM 链接存储根目录（默认: links，与 models 同级）")
    parser.add_argument("--region", default="CN", help="地区（默认 CN）")
    parser.add_argument("--mode", type=int, default=0, help="模式: 0=稳定, 1=测试（默认 0）")
    parser.add_argument("-p", "--proxy", default=None, help="代理（如 http://127.0.0.1:7890）")

    args = parser.parse_args()

    root_dir = args.root_dir
    links_root_dir = args.links_dir

    if not os.path.isdir(root_dir):
        print(f"错误：目录 {root_dir} 不存在")
        sys.exit(1)

    os.makedirs(links_root_dir, exist_ok=True)

    print("开始批量更新所有文件夹")
    print(f"模型目录: {root_dir}")
    print(f"ROM 链接存储目录: {links_root_dir}")
    print(f"地区: {args.region} | 模式: {args.mode} | 代理: {args.proxy or '无'}")
    print("=" * 80)

    for item in sorted(os.listdir(root_dir)):
        folder_dir = os.path.join(root_dir, item)
        if os.path.isdir(folder_dir):
            process_folder(folder_dir, links_root_dir, args.region, args.mode, args.proxy)

    print("\n所有文件夹处理完成！ColorOS 16 版本的链接文件已添加下载提示")

if __name__ == "__main__":
    main()
