#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Excel导出工具
将抓取到的模型数据导出到Excel文件
所有表格存放在同一页签中（"模型价格汇总"），每个表格之间留出间距

支持两种数据格式：
1. 模型列表格式（旧）：每个模型是一个字典，section_title 字段标识分类
2. 表格格式（新）：每个表格是一个字典，包含 rows 字段（保持原表结构）

支持单元格合并（colspan/rowspan）。
"""

from typing import List, Dict, Any
from datetime import datetime
import os
import re

# 提前导入以避免循环引用问题
from openpyxl.styles import Alignment
from openpyxl.utils import get_column_letter


class ExcelExporter:
    """Excel导出类"""

    def __init__(self):
        # 默认表头（用于旧格式数据）
        self.default_headers = [
            "模型名称",
            "模型ID（API调用用）",
            "输入价格",
            "输出价格",
            "缓存命中价格",
            "缓存存储价格",
            "计费方式",
            "备注说明",
            "数据来源"
        ]

    def _sanitize_sheet_name(self, name: str) -> str:
        """清理工作表名称，确保符合Excel规范"""
        # Excel工作表名称最多31个字符，不能包含: \\/?*[]
        sanitized = re.sub(r'[\\/?*\[\]:]', '_', name)
        if len(sanitized) > 31:
            sanitized = sanitized[:31]
        return sanitized

    def _detect_columns(self, models: List[Dict[str, Any]]) -> List[str]:
        """
        检测模型数据中实际包含的字段

        Args:
            models: 模型数据列表

        Returns:
            字段列表
        """
        if not models:
            return self.default_headers

        # 收集所有出现的字段
        all_fields = set()
        for model in models:
            all_fields.update(model.keys())

        # 按预定义顺序排列
        preferred_order = [
            "platform_name", "model_name", "model_id",
            "input_price", "output_price",
            "cache_hit_price", "cache_storage_price",
            "pricing_type", "notes", "section_title",
            "source_url", "data_source"
        ]

        headers = []
        for field in preferred_order:
            if field in all_fields:
                headers.append(field)

        # 添加其他未在预定义列表中的字段
        for field in sorted(all_fields):
            if field not in headers:
                headers.append(field)

        return headers

    def _get_field_label(self, field: str) -> str:
        """获取字段的中文标签"""
        labels = {
            "platform_name": "平台名称",
            "model_name": "模型名称",
            "model_id": "模型ID（API调用用）",
            "input_price": "输入价格",
            "output_price": "输出价格",
            "cache_hit_price": "缓存命中价格",
            "cache_storage_price": "缓存存储价格",
            "pricing_type": "计费方式",
            "notes": "备注说明",
            "section_title": "分类标题",
            "source_url": "数据来源",
            "data_source": "数据来源"
        }
        return labels.get(field, field)

    def _write_table_rows(self, ws, rows: List[List[str]], header_font, header_fill, header_alignment, thin_border, header_row_count: int = 1, merges: List[Dict] = None):
        """
        写入表格数据（保持原表结构），支持单元格合并

        Args:
            ws: openpyxl worksheet
            rows: 表格行数据（第一行为表头）
            header_row_count: 表头行数（1或2）
            merges: 合并单元格信息 [{start_row, start_col, end_row, end_col}, ...]
        """
        from openpyxl.styles import Alignment as OpenpyxlAlignment
        from openpyxl.utils import get_column_letter

        if not rows:
            return

        if merges is None:
            merges = []

        # 计算最大列数
        max_cols = max(len(row) for row in rows) if rows else 0

        # 写入所有数据
        for row_idx, row in enumerate(rows, 1):
            for col_idx in range(1, max_cols + 1):
                cell_value = row[col_idx - 1] if col_idx - 1 < len(row) else ""

                cell = ws.cell(row=row_idx, column=col_idx, value=cell_value)
                cell.border = thin_border

                if row_idx <= header_row_count:
                    # 表头样式（包括多行表头）
                    cell.font = header_font
                    cell.fill = header_fill
                    cell.alignment = header_alignment
                else:
                    # 数据样式
                    cell.alignment = OpenpyxlAlignment(
                        wrap_text=True, vertical='top')

        # 应用单元格合并
        for merge in merges:
            try:
                start_row = merge['start_row'] + 1  # openpyxl 是 1-based
                start_col = merge['start_col'] + 1
                end_row = merge['end_row'] + 1
                end_col = merge['end_col'] + 1

                # 合并范围
                range_str = f"{get_column_letter(start_col)}{start_row}:{get_column_letter(end_col)}{end_row}"
                ws.merge_cells(range_str)

                # 设置合并后单元格的对齐方式（使用主单元格样式）
                master_cell = ws.cell(row=start_row, column=start_col)
                master_cell.alignment = header_alignment
            except Exception as e:
                # 合并失败不影响其他操作
                pass

        # 调整列宽
        for col_idx in range(1, max_cols + 1):
            # 根据列内容自适应列宽
            max_len = 0
            for row in rows:
                if col_idx - 1 < len(row):
                    cell_text = str(row[col_idx - 1])
                    # 处理换行，计算最长行
                    line_lengths = [len(line)
                                    for line in cell_text.split('\n')]
                    if line_lengths:
                        max_len = max(max_len, max(line_lengths))

            # 设置列宽（最大50，最小12）
            col_width = min(max(max_len + 2, 12), 50)
            ws.column_dimensions[get_column_letter(col_idx)].width = col_width

    def export_single_platform(self, models: List[Dict[str, Any]], output_path: str, source_url: str = ""):
        """
        导出单个平台的模型数据到Excel

        支持两种数据格式：
        1. 旧格式：[{section_title: ..., model_name: ..., ...}, ...]
           按 section_title 分组到不同工作表
        2. 新格式：[{section_title: ..., rows: [[...], [...]], merges: [...], is_table: True}, ...]
           每个表格数据单独一个工作表，保持原表结构，支持单元格合并

        Args:
            models: 模型数据列表
            output_path: 输出文件路径
            source_url: 数据来源URL
        """
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
        except ImportError:
            print("请先安装 openpyxl: pip install openpyxl")
            raise

        # 创建Excel工作簿
        wb = Workbook()
        # 删除默认创建的Sheet
        wb.remove(wb.active)

        # 定义样式
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(
            start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_alignment = Alignment(
            horizontal="center", vertical="center", wrap_text=True)
        thin_border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

        # 检查数据格式
        is_table_format = models and models[0].get("is_table", False)

        if is_table_format:
            # 新格式：每个表格单独一个工作表
            self._export_tables(wb, models, header_font, header_fill,
                                header_alignment, thin_border, source_url)
        else:
            # 旧格式：按 section_title 分组
            self._export_model_lists(wb, models, header_font, header_fill,
                                     header_alignment, thin_border, source_url)

        # 如果没有任何工作表，创建一个默认工作表
        if not wb.sheetnames:
            ws = wb.create_sheet(title="空数据")
            ws.cell(row=1, column=1, value="未抓取到任何数据")

        # 保存文件
        wb.save(output_path)
        print(f"  ✓ 已导出到: {output_path}")
        print(f"    包含 {len(wb.sheetnames)} 个工作表: {', '.join(wb.sheetnames)}")

    def _export_tables(self, wb, tables, header_font, header_fill,
                       header_alignment, thin_border, source_url):
        """
        导出表格格式数据，所有表格放在同一工作表中，表格之间留出空行间距

        Args:
            wb: Workbook对象
            tables: 表格数据列表
            其他样式参数
        """
        from openpyxl.styles import Font as OpenpyxlFont

        # 创建单一工作表
        sheet_name = "模型价格汇总"
        ws = wb.create_sheet(title=sheet_name)

        # 表格之间的间距行数
        GAP_ROWS = 3

        # 当前写入行号
        current_row = 1

        for table_idx, table in enumerate(tables):
            section_title = table.get("section_title", "模型列表")
            rows = table.get("rows", [])
            header_row_count = table.get("header_row_count", 1)
            merges = table.get("merges", [])

            if not rows:
                continue

            # 计算此表格的最大列数（用于调整列宽）
            max_cols = max(len(row) for row in rows) if rows else 0

            # 写入表格标题行（在表格上方）
            if section_title and section_title != "模型列表":
                title_cell = ws.cell(
                    row=current_row, column=1, value=section_title)
                title_cell.font = OpenpyxlFont(
                    bold=True, size=14, color="333333")
                title_cell.alignment = header_alignment
                current_row += 1

            # 写入表格数据
            start_row = current_row
            for row_idx, row in enumerate(rows):
                for col_idx in range(1, max_cols + 1):
                    cell_value = row[col_idx - 1] if col_idx - \
                        1 < len(row) else ""

                    cell = ws.cell(row=start_row + row_idx,
                                   column=col_idx, value=cell_value)
                    cell.border = thin_border

                    if row_idx < header_row_count:
                        cell.font = header_font
                        cell.fill = header_fill
                        cell.alignment = header_alignment
                    else:
                        cell.alignment = Alignment(
                            wrap_text=True, vertical='top')

            # 应用单元格合并（需要根据起始行调整）
            for merge in merges:
                try:
                    s_row = start_row + merge['start_row']
                    s_col = merge['start_col'] + 1
                    e_row = start_row + merge['end_row']
                    e_col = merge['end_col'] + 1

                    range_str = f"{get_column_letter(s_col)}{s_row}:{get_column_letter(e_col)}{e_row}"
                    ws.merge_cells(range_str)

                    master_cell = ws.cell(row=s_row, column=s_col)
                    master_cell.alignment = header_alignment
                except Exception:
                    pass

            # 调整列宽（只在第一个表格时设置，后续表格沿用）
            if table_idx == 0:
                for col_idx in range(1, max_cols + 1):
                    max_len = 0
                    for row in rows:
                        if col_idx - 1 < len(row):
                            cell_text = str(row[col_idx - 1])
                            line_lengths = [len(line)
                                            for line in cell_text.split('\n')]
                            if line_lengths:
                                max_len = max(max_len, max(line_lengths))

                    col_width = min(max(max_len + 2, 12), 50)
                    ws.column_dimensions[get_column_letter(
                        col_idx)].width = col_width

            # 更新当前行：表格占用行数 + 间距
            current_row = start_row + len(rows) + GAP_ROWS

        # 如果有数据来源，添加到最后一行的下一行
        if source_url and tables:
            source_cell = ws.cell(row=current_row, column=1, value="数据来源")
            source_cell.font = OpenpyxlFont(
                bold=True, italic=True, color="666666")
            ws.cell(row=current_row, column=2, value=source_url).font = OpenpyxlFont(
                italic=True, color="666666")

        # 设置表头行高
        if tables:
            # 为每个表头行设置较高行高
            for row_idx in range(1, current_row):
                if ws.cell(row=row_idx, column=1).fill and ws.cell(row=row_idx, column=1).fill.start_color.rgb == "004472C4":
                    ws.row_dimensions[row_idx].height = 30

    def _export_model_lists(self, wb, models, header_font, header_fill,
                            header_alignment, thin_border, source_url):
        """
        导出模型列表格式数据，按 section_title 分组

        Args:
            wb: Workbook对象
            models: 模型数据列表
            其他样式参数
        """
        from openpyxl.styles import Alignment as OpenpyxlAlignment

        # 按分类分组
        sections = {}
        for model in models:
            section_title = model.get("section_title", "模型列表")
            if section_title not in sections:
                sections[section_title] = []
            sections[section_title].append(model)

        # 为每个分类创建一个工作表
        for idx, (section_title, section_models) in enumerate(sections.items()):
            sheet_name = self._sanitize_sheet_name(section_title)
            # 防止重名
            original_name = sheet_name
            counter = 1
            while sheet_name in wb.sheetnames:
                sheet_name = self._sanitize_sheet_name(
                    f"{original_name[:27]}_{counter}")
                counter += 1

            ws = wb.create_sheet(title=sheet_name)

            # 检测该分类使用的字段
            fields = self._detect_columns(section_models)

            # 写入表头
            for col_idx, field in enumerate(fields, 1):
                label = self._get_field_label(field)
                cell = ws.cell(row=1, column=col_idx, value=label)
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = header_alignment
                cell.border = thin_border

            # 写入数据
            for row_idx, model in enumerate(section_models, 2):
                for col_idx, field in enumerate(fields, 1):
                    value = model.get(field, "")
                    # 如果是数据来源字段且为空，使用传入的URL
                    if field in ("source_url", "data_source") and not value:
                        value = source_url
                    cell = ws.cell(row=row_idx, column=col_idx, value=value)
                    cell.border = thin_border
                    cell.alignment = OpenpyxlAlignment(
                        wrap_text=True, vertical='top')

            # 调整列宽
            for col_idx, field in enumerate(fields, 1):
                # 根据字段类型设置列宽
                if field in ("model_id", "source_url", "data_source"):
                    width = 45
                elif field in ("model_name", "section_title", "platform_name"):
                    width = 30
                elif "price" in field or "pricing" in field:
                    width = 35
                else:
                    width = 30
                ws.column_dimensions[chr(64 + col_idx)].width = width

    def export_all(self, scrapers_data: List[Dict[str, Any]], output_dir: str):
        """
        导出所有平台的数据，每个平台一个Excel文件

        Args:
            scrapers_data: 包含平台名称、模型数据和URL的列表
            output_dir: 输出目录
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        for item in scrapers_data:
            platform_name = item.get("platform_name", "unknown")
            models = item.get("models", [])
            source_url = item.get("url", "")

            safe_name = platform_name.replace(
                "/", "_").replace(" ", "_").replace("（", "(").replace("）", ")")
            output_path = os.path.join(
                output_dir, f"{safe_name}_{timestamp}.xlsx")
            self.export_single_platform(models, output_path, source_url)
