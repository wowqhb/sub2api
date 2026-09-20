#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
豆包（Volcengine ARK）模型价格抓取器
数据来源：https://docs.volcengine.com/docs/ark/model-pricing
只抓取中国区域（北京cn-beijing）的模型数据

抓取策略：
- 保持原表格格式和内容
- 按分类存入不同的页签，表头不同的表格分开存储
- 支持单元格合并（colspan/rowspan）

由于豆包页面是JavaScript动态渲染的，需要使用Playwright抓取
"""

from typing import List, Dict, Any
from utils.scraper import BaseScraper
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class DoubaoScraper(BaseScraper):
    """豆包模型价格抓取器（中国区域）"""

    # 分类关键词映射
    CATEGORY_KEYWORDS = {
        "大语言模型": ["大语言模型"],
        "在线推理（常规）": ["在线推理（常规）"],
        "在线推理（低延迟）": ["在线推理（低延迟）"],
        "在线推理（低优）": ["在线推理（低优）"],
        "批量推理": ["批量推理"],
        "TPM保障包": ["TPM 保障包", "TPM保障包"],
        "视频生成模型": ["视频生成", "视频生成模型"],
        "图片生成模型": ["图片生成", "图片生成模型"],
        "语音合成": ["语音合成"],
        "历史模型": ["历史模型"],
        "工具及插件": ["工具及插件"],
        "联网内容插件": ["联网内容插件"],
        "豆包助手": ["豆包助手"],
        "知识库": ["知识库"],
        "Coding Plan": ["Coding Plan", "Coding Plan 个人版"],
        "Agent Plan": ["Agent Plan", "Agent Plan 个人版"],
        "精调模型": ["精调模型"],
        "模型单元": ["模型单元"],
        "应用实验室": ["应用实验室"],
    }

    def __init__(self):
        super().__init__(
            url="https://docs.volcengine.com/docs/ark/model-pricing?lang=zh",
            platform_name="火山方舟（豆包）"
        )
        self.region = "中国（华北2-北京）"

    def fetch_page_with_playwright(self) -> str:
        """
        使用Playwright获取动态渲染后的页面HTML

        Returns:
            页面HTML内容
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print("  ✗ 请先安装 playwright: pip install playwright")
            print("  ✗ 然后运行: python -m playwright install chromium")
            return None

        print(f"  正在请求（Playwright）: {self.url}")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                )
                page = context.new_page()
                page.goto(self.url, timeout=60000, wait_until='networkidle')
                # 等待表格加载
                page.wait_for_selector('table', timeout=30000)
                # 获取完整的HTML
                html = page.content()
                browser.close()
                return html
        except Exception as e:
            print(f"  ✗ Playwright 请求失败: {e}")
            return None

    def scrape(self) -> List[Dict[str, Any]]:
        """
        抓取豆包模型价格数据（仅中国区域）

        Returns:
            模型数据列表，每个表格是一个独立的section
        """
        print(f"\n正在抓取 {self.platform_name} 模型价格数据 [{self.region}]...")
        # 由于页面是JavaScript动态渲染的，使用Playwright获取
        html = self.fetch_page_with_playwright()
        if html is None:
            return []

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'lxml')

        tables = []

        # 当前所在的章节标题（用于命名工作表）
        current_section_title = "豆包模型"
        # 表格索引
        table_count = 0

        # 按文档顺序遍历 body 的直接子元素和后代元素
        # 使用迭代器，实时跟踪分类标题
        all_elements = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5',
                                      'p', 'div', 'span', 'strong', 'b',
                                      'table'])

        # 分类标题候选：长度在 2-30 之间，且能识别为分类
        # 用于去重，避免同一个分类被多次设置
        last_section_set = None

        for element in all_elements:
            if element.name == 'table':
                # 处理表格
                table_data = self._parse_table(
                    element, current_section_title, table_count)
                if table_data:
                    tables.append(table_data)
                    table_count += 1
            else:
                # 检查是否为分类标题
                # 只处理较短的文本（标题通常不超过30字符）
                title_text = self.clean_text(element.get_text())
                if title_text and 2 <= len(title_text) <= 30:
                    category = self._identify_category(title_text)
                    if category != title_text:
                        # 只在分类变化时更新
                        if category != last_section_set:
                            current_section_title = category
                            last_section_set = category

        print(f"  ✓ 抓取到 {len(tables)} 个表格（仅中国区域）")
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

        # 表格名称：使用分类标题 + 索引（避免重名）
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
        from copy import copy
        cell_copy = copy(cell)

        # 移除所有删除线元素
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
            # 2. 单元格内容像表头
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
            '模型', '价格', 'token', 'Token', '输入', '输出', '缓存',
            '模式', '条件', '计费', '分辨率', '宽高', '时长',
            '元', '秒', 'RPM', 'TPM'
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
