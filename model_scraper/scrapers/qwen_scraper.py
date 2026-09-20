#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
千问（Alibaba Bailian）模型价格抓取器
数据来源：https://help.aliyun.com/zh/model-studio/model-pricing
只抓取中国区域（华北2-北京）的模型数据

抓取策略：
- 不通过表头识别模型
- 保持原表结构，每个表格单独存储到一个工作表
- 少加工或不加工，尽量保留原始数据
- Model ID 如果有多行，只取第一行（真正的Model ID）
- 正确处理2行表头的情况
- 正确处理 colspan 和 rowspan，支持单元格合并
"""

from typing import List, Dict, Any
from utils.scraper import BaseScraper
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class QwenScraper(BaseScraper):
    """千问模型价格抓取器（中国区域）"""

    # 中国区域标识
    CHINA_REGION_KEYWORDS = [
        "华北2（北京）", "华北2", "cn-beijing", "cn-hangzhou",
        "中国内地", "中国", "内地", "北京", "上海", "杭州", "深圳"
    ]
    # 跳过非中国区域的标识
    SKIP_REGIONS = [
        "美国（弗吉尼亚）", "美国", "弗吉尼亚", "Virginia",
        "新加坡", "Singapore",
        "德国（法兰克福）", "德国", "法兰克福", "Frankfurt",
        "日本（东京）", "日本", "东京", "Tokyo",
        "英国（伦敦）", "英国", "伦敦", "London",
        "中国香港", "香港", "Hong Kong",
        "亚太", "海外", "国际", "global", "oversea",
        "us-east", "us-west", "ap-southeast", "ap-northeast",
        "eu-central", "eu-west", "me-central",
    ]

    def __init__(self):
        super().__init__(
            url="https://help.aliyun.com/zh/model-studio/model-pricing",
            platform_name="阿里云百炼（千问）"
        )
        self.region = "中国（华北2-北京）"

    def scrape(self) -> List[Dict[str, Any]]:
        """
        抓取千问模型价格数据（仅中国区域）

        Returns:
            模型数据列表，每个表格的数据是一个独立的section
        """
        print(f"\n正在抓取 {self.platform_name} 模型价格数据 [{self.region}]...")
        soup = self.fetch_page()
        if soup is None:
            return []

        tables = []

        # 查找页面中的所有标题和表格
        all_elements = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'table'])

        # 当前所在的章节标题（用于命名工作表）
        current_section_title = "模型列表"
        # 当前是否在非中国区域
        in_skip_region = False
        # 表格索引（用于区分同名表格）
        table_count = 0

        for element in all_elements:
            if element.name in ['h1', 'h2', 'h3', 'h4', 'h5']:
                # 提取章节标题
                title_text = self.clean_text(element.get_text())

                if title_text and len(title_text) < 100:
                    # 检查是否为区域标识
                    is_china_region = any(
                        kw in title_text for kw in self.CHINA_REGION_KEYWORDS
                    )
                    is_skip_region = any(
                        skip in title_text for skip in self.SKIP_REGIONS
                    )

                    # 优先判断为中国区域
                    if is_china_region and not is_skip_region:
                        in_skip_region = False
                        current_section_title = title_text
                    elif is_skip_region and not is_china_region:
                        in_skip_region = True
                    else:
                        # 既不是中国也不是海外，是章节标题
                        if not in_skip_region:
                            current_section_title = title_text

            elif element.name == 'table':
                # 跳过非中国区域的表格
                if in_skip_region:
                    continue

                # 解析表格 - 保持原结构，保留 colspan/rowspan
                table_data = self._parse_table(
                    element, current_section_title, table_count)
                if table_data:
                    tables.append(table_data)
                    table_count += 1

        print(f"  ✓ 抓取到 {len(tables)} 个表格（仅中国区域）")
        return tables

    def _parse_table(self, table_element, section_title: str, table_index: int) -> Dict[str, Any]:
        """
        解析单个表格，保持原表结构，保留合并信息

        Args:
            table_element: BeautifulSoup的table元素
            section_title: 当前章节标题
            table_index: 表格索引

        Returns:
            表格数据字典，包含:
                - rows: 二维数组，存储单元格文本
                - merges: 合并单元格信息列表 [(start_row, start_col, end_row, end_col), ...]
                - header_row_count: 表头行数
                - is_table: True
        """
        rows = table_element.find_all('tr')
        if len(rows) < 1:
            return None

        # 检测表头行数
        header_row_count = self._detect_header_rows(rows)

        # 解析表格，包含合并信息
        all_rows_data, total_cols, merges = self._parse_rows_with_merges(
            rows[:header_row_count]
        )

        if not all_rows_data:
            return None

        # 解析数据行
        for row in rows[header_row_count:]:
            row_cells = self._parse_data_row(row, total_cols)
            if row_cells:
                all_rows_data.append(row_cells)

        if not all_rows_data:
            return None

        # 处理 Model ID 列 - 如果是多行，只取第一行
        if header_row_count >= 1 and all_rows_data:
            header_row = all_rows_data[0]
            model_id_col_idx = None
            for i, header in enumerate(header_row):
                if '模型 ID' in header or 'Model ID' in header or 'model_id' in header.lower():
                    model_id_col_idx = i
                    break

            # 处理每个数据行（跳过表头行）
            for i in range(header_row_count, len(all_rows_data)):
                row = all_rows_data[i]
                if model_id_col_idx is not None and model_id_col_idx < len(row):
                    cell_value = row[model_id_col_idx]
                    # 如果是多行（包含换行），只取第一行
                    if '\n' in cell_value:
                        first_line = cell_value.split('\n')[0].strip()
                        row[model_id_col_idx] = first_line

        # 表格名称：使用章节标题 + 索引（避免重名）
        table_name = f"{section_title}"

        return {
            "section_title": table_name,
            "rows": all_rows_data,
            "merges": merges,  # 合并单元格信息
            "is_table": True,
            "header_row_count": header_row_count,
        }

    def _parse_rows_with_merges(self, rows) -> tuple:
        """
        解析表格行，返回数据和合并信息

        Args:
            rows: tr元素列表（仅表头行）

        Returns:
            (rows_data, total_cols, merges)
            - rows_data: 二维数组
            - total_cols: 总列数
            - merges: 合并列表 [(start_row, start_col, end_row, end_col), ...]
        """
        if not rows:
            return [], 0, []

        # 第一步：基于第一行计算总列数
        first_row = rows[0]
        first_cells = first_row.find_all(['th', 'td'])
        total_cols = 0
        for cell in first_cells:
            colspan = int(cell.get('colspan', 1))
            total_cols += colspan

        # 初始化数据和合并记录
        all_rows_data = []
        merges = []  # [(start_row, start_col, end_row, end_col), ...]

        # 第二步：逐行解析，记录合并信息
        # 用于跟踪每列的占用情况：(row, col) -> (rowspan)
        col_row_rowspan = [[] for _ in range(total_cols)]

        for row_idx, row in enumerate(rows):
            cells = row.find_all(['th', 'td'])
            row_data = [''] * total_cols
            current_col = 0

            for cell in cells:
                colspan = int(cell.get('colspan', 1))
                rowspan = int(cell.get('rowspan', 1))
                text = self.clean_text(cell.get_text())

                # 找到下一个空位（已被前面 rowspan 占用的)
                while current_col < total_cols and row_idx in col_row_rowspan[current_col]:
                    current_col += 1

                if current_col >= total_cols:
                    break

                # 填充单元格内容
                if current_col < total_cols:
                    row_data[current_col] = text
                    # 标记该列被哪些行占用
                    for r in range(row_idx, row_idx + rowspan):
                        if r not in col_row_rowspan[current_col]:
                            col_row_rowspan[current_col].append(r)

                    # 记录合并信息（colspan 或 rowspan > 1）
                    if colspan > 1 or rowspan > 1:
                        end_row = row_idx + rowspan - 1
                        end_col = current_col + colspan - 1
                        merges.append({
                            'start_row': row_idx,
                            'start_col': current_col,
                            'end_row': end_row,
                            'end_col': end_col,
                        })

                current_col += colspan

            all_rows_data.append(row_data)

        return all_rows_data, total_cols, merges

    def _parse_data_row(self, row, total_cols: int) -> List[str]:
        """
        解析数据行，根据 colspan 对齐列

        Args:
            row: tr元素
            total_cols: 总列数

        Returns:
            单元格文本列表（长度等于total_cols）
        """
        cells = row.find_all(['td', 'th'])
        if not cells:
            return None

        row_data = [''] * total_cols
        current_col = 0

        for cell in cells:
            colspan = int(cell.get('colspan', 1))
            text = self.clean_text(cell.get_text())

            # 找到下一个空位
            while current_col < total_cols and row_data[current_col]:
                current_col += 1

            if current_col >= total_cols:
                break

            # 填充内容（colspan 展开：第一列填充，后续列为空）
            if current_col < total_cols:
                row_data[current_col] = text

            current_col += colspan

        return row_data

    def _detect_header_rows(self, rows) -> int:
        """
        检测表头有多少行

        通过以下方式判断：
        1. 检查是否包含 <th> 元素
        2. 检查内容是否像表头（包含"模型"、"价格"、"Token"等关键词）

        Args:
            rows: tr元素列表

        Returns:
            表头行数（通常是1或2）
        """
        if not rows:
            return 1

        header_count = 0
        for i, row in enumerate(rows):
            # 检查是否为表头行
            th_cells = row.find_all('th')
            all_cells = row.find_all(['th', 'td'])

            # 判断条件：
            # 1. 包含 th 元素
            # 2. 单元格内容像表头
            if th_cells or self._looks_like_header(all_cells):
                header_count += 1
            else:
                # 遇到数据行就停止
                break

        # 至少1行表头
        return max(header_count, 1)

    def _looks_like_header(self, cells) -> bool:
        """
        判断单元格内容是否像表头

        Args:
            cells: th/td元素列表

        Returns:
            是否像表头
        """
        if not cells:
            return False

        header_keywords = [
            '模型', 'ID', '价格', 'token', 'Token', '输入', '输出',
            '模式', '免费额度', '范围', '部署', '服务'
        ]

        # 计算匹配的关键词数量
        match_count = 0
        for cell in cells:
            text = cell.textContent if hasattr(
                cell, 'textContent') else cell.get_text()
            text = self.clean_text(text).lower()
            for keyword in header_keywords:
                if keyword.lower() in text:
                    match_count += 1
                    break

        # 如果超过一半的单元格像表头，就认为是表头行
        return match_count >= len(cells) / 2
