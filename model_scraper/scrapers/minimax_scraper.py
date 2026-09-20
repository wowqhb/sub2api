#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MiniMax 模型价格抓取器
数据来源：https://platform.minimax.cn/docs/guides/pricing-paygo

抓取策略：
- 保持原表格的格式和内容
- 按分类存入不同的页签，表头不同的表格分开存储
- 支持单元格合并（colspan/rowspan）
"""

from typing import List, Dict, Any
from utils.scraper import BaseScraper
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class MinimaxScraper(BaseScraper):
    """MiniMax 模型价格抓取器（中国区域）"""

    # 分类关键词
    CATEGORY_KEYWORDS = {
        "语言模型": ["语言模型", "文本", "模型"],
        "语音模型": ["语音", "音频", "ASR", "TTS", "speech"],
        "视频模型": ["视频", "video"],
        "图像模型": ["图像", "图片", "image"],
        "音乐模型": ["音乐", "music"],
        "音色管理": ["音色"],
        "MCP工具": ["MCP"],
        "服务端工具": ["工具", "server"],
    }

    def __init__(self):
        super().__init__(
            url="https://platform.minimax.cn/docs/guides/pricing-paygo",
            platform_name="MiniMax"
        )
        self.region = "中国"

    def scrape(self) -> List[Dict[str, Any]]:
        """
        抓取 MiniMax 模型价格数据

        Returns:
            模型数据列表，每个表格是一个独立的section
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
        # 表格索引
        table_count = 0
        # 跟踪上一个表格的表头签名
        last_header_signature = None

        for element in all_elements:
            if element.name in ['h1', 'h2', 'h3', 'h4', 'h5']:
                # 提取章节标题
                title_text = self.clean_text(element.get_text())

                if title_text and len(title_text) < 100:
                    # 识别分类
                    current_section_title = self._identify_category(title_text)

            elif element.name == 'table':
                # 解析表格 - 保持原结构
                table_data = self._parse_table(
                    element, current_section_title, table_count)
                if table_data:
                    tables.append(table_data)
                    table_count += 1

        print(f"  ✓ 抓取到 {len(tables)} 个表格（中国区域）")
        return tables

    def _identify_category(self, title_text: str) -> str:
        """
        根据标题文本识别分类

        Args:
            title_text: 章节标题

        Returns:
            分类名称
        """
        for category, keywords in self.CATEGORY_KEYWORDS.items():
            for keyword in keywords:
                if keyword in title_text:
                    return category
        return title_text

    def _get_header_signature(self, rows) -> str:
        """
        获取表头签名，用于判断两个表格是否表头相同

        Args:
            rows: 表头行

        Returns:
            表头签名字符串
        """
        signature_parts = []
        for row in rows:
            cells = row.find_all(['th', 'td'])
            row_parts = []
            for cell in cells:
                text = self.clean_text(cell.get_text())
                cs = cell.get('colspan', '1')
                rs = cell.get('rowspan', '1')
                row_parts.append(f"{text}|{cs}|{rs}")
            signature_parts.append(','.join(row_parts))
        return '||'.join(signature_parts)

    def _parse_table(self, table_element, section_title: str, table_index: int) -> Dict[str, Any]:
        """
        解析单个表格，保持原表结构

        Args:
            table_element: BeautifulSoup的table元素
            section_title: 当前章节标题
            table_index: 表格索引

        Returns:
            表格数据字典，包含:
                - rows: 二维数组
                - merges: 合并单元格信息
                - header_row_count: 表头行数
                - is_table: True
        """
        rows = table_element.find_all('tr')
        if len(rows) < 1:
            return None

        # 检测表头行数
        header_row_count = self._detect_header_rows(rows)
        if header_row_count == 0:
            header_row_count = 1

        # 解析表头，包含合并信息
        header_data, total_cols, header_merges = self._parse_header_rows_with_merges(
            rows[:header_row_count]
        )

        if not header_data:
            return None

        # 解析数据行
        all_rows_data = list(header_data)
        for row in rows[header_row_count:]:
            row_cells = self._parse_data_row(row, total_cols)
            if row_cells:
                all_rows_data.append(row_cells)

        if not all_rows_data:
            return None

        # 表格名称：使用分类标题
        table_name = f"{section_title}"

        return {
            "section_title": table_name,
            "rows": all_rows_data,
            "merges": header_merges,
            "is_table": True,
            "header_row_count": header_row_count,
        }

    def _parse_header_rows_with_merges(self, rows) -> tuple:
        """
        解析表头行，返回数据和合并信息

        Args:
            rows: 表头tr元素列表

        Returns:
            (rows_data, total_cols, merges)
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
        merges = []

        # 第二步：逐行解析，记录合并信息
        col_row_rowspan = [[] for _ in range(total_cols)]

        for row_idx, row in enumerate(rows):
            cells = row.find_all(['th', 'td'])
            row_data = [''] * total_cols
            current_col = 0

            for cell in cells:
                colspan = int(cell.get('colspan', 1))
                rowspan = int(cell.get('rowspan', 1))
                # 表头不使用删除线，但为了一致也调用一次
                text = self._get_cell_text_without_strike(cell)

                # 找到下一个空位
                while current_col < total_cols and row_idx in col_row_rowspan[current_col]:
                    current_col += 1

                if current_col >= total_cols:
                    break

                # 填充单元格内容
                if current_col < total_cols:
                    row_data[current_col] = text
                    for r in range(row_idx, row_idx + rowspan):
                        if r not in col_row_rowspan[current_col]:
                            col_row_rowspan[current_col].append(r)

                    # 记录合并信息
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
        自动过滤掉删除线（<del>、<strike>）标记的价格

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
            # 获取去除删除线后的文本
            text = self._get_cell_text_without_strike(cell)

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

    def _get_cell_text_without_strike(self, cell) -> str:
        """
        获取单元格文本，自动过滤掉删除线（<del>、<strike>）标记的内容

        Args:
            cell: BeautifulSoup的td/th元素

        Returns:
            去除删除线内容后的文本
        """
        # 复制cell内容
        from copy import copy
        cell_copy = copy(cell)

        # 移除所有删除线元素（<del>, <strike>, <s>, 以及有 line-through 样式的元素）
        for tag_name in ['del', 'strike', 's']:
            for elem in cell_copy.find_all(tag_name):
                elem.decompose()

        # 移除有 line-through 样式的元素
        for elem in cell_copy.find_all(style=True):
            style = elem.get('style', '')
            if 'line-through' in style:
                elem.decompose()

        return self.clean_text(cell_copy.get_text())

    def _detect_header_rows(self, rows) -> int:
        """
        检测表头有多少行

        Args:
            rows: tr元素列表

        Returns:
            表头行数
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
            # 2. 单元格内容像表头（包含特定关键词）
            if th_cells or self._looks_like_header(all_cells):
                header_count += 1
            else:
                # 遇到数据行就停止
                break

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
            '模型', '价格', 'token', 'Token', '输入', '输出',
            '缓存', '接口', '单价', '计费', '说明', 'RPM', 'TPM',
            '元', '字符', '小时', '秒', '张'
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
