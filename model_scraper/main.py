#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI模型价格抓取主程序
从指定网页抓取模型价格数据，并导出到各自的Excel表格中
"""

import sys
import os

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scrapers.doubao_scraper import DoubaoScraper
from scrapers.qwen_scraper import QwenScraper
from scrapers.minimax_scraper import MinimaxScraper
from utils.excel_exporter import ExcelExporter


def main():
    print("=" * 70)
    print("AI模型价格抓取程序")
    print("=" * 70)
    print("数据来源：")
    print("  1. 千问: https://help.aliyun.com/zh/model-studio/model-pricing")
    print("  2. 豆包: https://docs.volcengine.com/docs/ark/model-pricing")
    print("  3. MiniMax: https://platform.minimax.cn/docs/guides/pricing-paygo")
    print("=" * 70)

    # 创建输出目录
    output_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(output_dir, exist_ok=True)

    # 初始化导出器
    exporter = ExcelExporter()

    # 存储所有平台的数据
    all_data = []

    # 1. 抓取千问模型价格
    try:
        qwen_scraper = QwenScraper()
        qwen_models = qwen_scraper.scrape()
        all_data.append({
            "platform_name": qwen_scraper.platform_name,
            "url": qwen_scraper.url,
            "models": qwen_models
        })
    except Exception as e:
        print(f"  ✗ 千问抓取失败: {e}")

    # 2. 抓取豆包模型价格
    try:
        doubao_scraper = DoubaoScraper()
        doubao_models = doubao_scraper.scrape()
        all_data.append({
            "platform_name": doubao_scraper.platform_name,
            "url": doubao_scraper.url,
            "models": doubao_models
        })
    except Exception as e:
        print(f"  ✗ 豆包抓取失败: {e}")

    # 3. 抓取MiniMax模型价格
    try:
        minimax_scraper = MinimaxScraper()
        minimax_models = minimax_scraper.scrape()
        all_data.append({
            "platform_name": minimax_scraper.platform_name,
            "url": minimax_scraper.url,
            "models": minimax_models
        })
    except Exception as e:
        print(f"  ✗ MiniMax抓取失败: {e}")

    # 统计总数
    total_count = sum(len(item["models"]) for item in all_data)
    print(f"\n共抓取到 {total_count} 个模型数据")

    # 导出到Excel
    if all_data and total_count > 0:
        print("\n正在导出到Excel...")
        try:
            exporter.export_all(all_data, output_dir)
            print("\n导出完成：")
            for item in all_data:
                print(f"  - {item['platform_name']}: {len(item['models'])} 个模型")
        except Exception as e:
            print(f"  ✗ 导出失败: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("\n未抓取到任何数据，请检查网络连接或网页结构是否变化")

    print("=" * 70)


if __name__ == "__main__":
    main()