#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
加价处理脚本（新版本）
读取已生成的Excel价格表，生成一个新表：
- 新表的价格 = 原表价格 × 1.3（+30%毛利）
- 在表格后面追加新列，计算每个token等于多少个元宝
- 列与列之间没有间隔

计算规则：
- 加成 30%：新价 = 原价 × 1.3
- 1 元 = 1000 元宝
- 1 token = (新价 × 1.3) / 1000 元宝（基于"元/百万token"换算）
"""

import os
import re
import sys
import glob
from typing import List, Dict, Any, Optional, Tuple
from openpyxl import load_workbook, Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter


# 利润率（30%）
PROFIT_MARGIN = 0.30
# 1 元 = 1000 元宝
YUANBAO_PER_YUAN = 1000


def is_price_column(header_text: str) -> bool:
    """判断是否是价格列"""
    if not header_text:
        return False
    header_text = str(header_text).strip()
    if not header_text:
        return False

    price_keywords = [
        "单价", "刊例价", "价格", "金额", "费用",
        "元/百万", "元/百万token", "元/百万 tokens",
        "元/次", "元/小时", "元/万字符", "元/首", "元/张", "元/秒", "元/音色",
        "（元/百万", "（元/次）", "（元/小时）", "（元/万字符）", "（元/首）", "（元/张）", "（元/秒）",
        "(元/百万", "(元/次)", "(元/小时)", "(元/万字符)", "(元/首)", "(元/张)", "(元/秒)",
    ]

    exclude_keywords = [
        "条件", "输入长度", "输出长度", "Token数", "Token 范围", "长度",
        "模式", "状态", "类型", "名称", "区域", "地域", "服务部署范围",
        "免费额度", "模型 ID", "Model ID", "模型名称", "接口", "接口说明",
        "计费方式", "计费规则", "计费项", "计费区间",
        "倍率", "比例", "RPM", "TPM",
    ]

    has_price_keyword = False
    for kw in price_keywords:
        if kw in header_text:
            has_price_keyword = True
            break

    if not has_price_keyword:
        return False

    for exclude in exclude_keywords:
        if exclude in header_text:
            return False

    return True


UNIT_KEYWORDS = {
    "token": ["token", "Token", "TOKEN", "tokens", "Tokens", "TOKENS"],
    "次": ["元/次", "（元/次）", "(元/次)", "/次"],
    "秒": ["元/秒", "（元/秒）", "(元/秒)"],
    "张": ["元/张", "（元/张）", "(元/张)"],
    "首": ["元/首", "（元/首）", "(元/首)"],
    "万字符": ["元/万字符", "（元/万字符）", "(元/万字符)"],
    "小时": ["元/小时", "（元/小时）", "(元/小时)"],
    "音色": ["元/音色", "（元/音色）", "(元/音色)"],
}


def detect_unit(header_text: str) -> str:
    """检测价格单位"""
    if not header_text:
        return "token"

    header_text = str(header_text).strip()

    for unit, keywords in UNIT_KEYWORDS.items():
        for kw in keywords:
            if kw in header_text:
                return unit

    if "token" in header_text.lower():
        return "token"

    return "token"


def parse_price(price_text: str) -> Optional[float]:
    """从单元格文本中解析价格数值"""
    if not price_text:
        return None

    text = str(price_text).strip()
    if not text or text == "-":
        return None

    text = re.sub(r'~~[^~]+~~', '', text).strip()
    if not text:
        return None

    text = re.sub(r'原价', '', text)
    text = re.sub(r'\*\*[^*]+\*\*', '', text)

    match = re.search(r'(\d+(?:\.\d+)?)', text)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None

    return None


def apply_markup_to_price(original_price: float) -> float:
    """对原价格加30%毛利"""
    return original_price * (1 + PROFIT_MARGIN)


def format_price(price: float) -> str:
    """格式化价格数字，去除浮点误差"""
    # 四舍五入到4位小数
    rounded = round(price, 4)
    # 转为字符串（自动去除末尾的0）
    if rounded == int(rounded):
        return str(int(rounded))
    else:
        return str(rounded)


def calculate_yuanbao_per_unit(original_price: float, unit: str, original_unit_text: str = "") -> str:
    """
    计算 1 个模型单位等于多少元宝
    基于"原价 × 1.3"后的新价

    计算规则：
    - 加价 30% 后，新价 = 原价 × 1.3
    - 基础公式：1 元宝 = 0.001 元，所以 1 元 = 1000 元宝
    - 当单位中出现"百万"字样（如"元/百万token"）时，额外除以 100万
    - 当单位中出现"万"字样（如"元/万字符"）时，额外除以 1万
    - 其他单位（如"元/秒"、"元/张"、"元/首"等）只除以 1000

    例如：
    - 原价 7.8 元/百万token → 新价 10.14 元/百万token
      1 token = 10.14 / 1000000 / 1000 = 1.014e-8 元宝/token
    - 原价 2.5 元/万字符 → 新价 3.25 元/万字符
      1 字符 = 3.25 / 10000 / 1000 = 3.25e-10 元宝/字符
    - 原价 0.5 元/秒 → 新价 0.65 元/秒
      1 秒 = 0.65 / 1000 = 6.5e-4 元宝/秒
    """
    if original_price <= 0:
        return ""

    marked_up_price = apply_markup_to_price(original_price)

    # 判断是否需要额外除以 100万 或 1万
    extra_divisor = 1
    if original_unit_text:
        if "百万" in original_unit_text:
            extra_divisor = 1000000
        elif "万" in original_unit_text:
            extra_divisor = 10000
        # 其他情况不额外除

    # 总除数 = extra_divisor * 1000
    total_divisor = extra_divisor * 1000

    # 显示用的单位标签
    if unit == "万字符":
        display_unit = "字符"
    else:
        display_unit = unit

    yuanbao = marked_up_price / total_divisor
    return f"{yuanbao:.12f} 元宝/{display_unit}"


def find_latest_excel_files(output_dir: str) -> List[str]:
    """查找每个平台最新的Excel文件"""
    all_files = glob.glob(os.path.join(output_dir, "*.xlsx"))
    all_files = [f for f in all_files if not os.path.basename(
        f).startswith(".~")]

    platform_files = {}
    for f in all_files:
        basename = os.path.basename(f)
        match = re.match(r'^(.+?)_\d{8}_\d{6}\.xlsx$', basename)
        if match:
            platform = match.group(1)
            if platform not in platform_files:
                platform_files[platform] = f
            else:
                if os.path.getmtime(f) > os.path.getmtime(platform_files[platform]):
                    platform_files[platform] = f

    return list(platform_files.values())


def extract_tables_from_source(wb_src) -> List[Dict[str, Any]]:
    """从源工作簿中提取所有表格数据"""
    HEADER_RGB = "4472C4"
    ws_src = wb_src.active

    # 识别表格分组
    table_groups = []
    in_table = False
    current_start = None
    current_header_rows = []

    for row_idx in range(1, ws_src.max_row + 1):
        cell = ws_src.cell(row=row_idx, column=1)
        is_header = False
        if cell.fill and cell.fill.start_color:
            try:
                rgb = str(cell.fill.start_color.rgb or "").upper()
                if rgb.endswith(HEADER_RGB):
                    is_header = True
            except:
                pass

        if is_header:
            if not in_table:
                current_start = row_idx
                current_header_rows = [row_idx]
                in_table = True
            else:
                current_header_rows.append(row_idx)
        else:
            if in_table:
                next_row = row_idx + 1
                if next_row <= ws_src.max_row:
                    next_cell = ws_src.cell(row=next_row, column=1)
                    try:
                        next_rgb = str(next_cell.fill.start_color.rgb or "").upper(
                        ) if next_cell.fill and next_cell.fill.start_color else ""
                        if next_rgb.endswith(HEADER_RGB):
                            table_groups.append(
                                (current_start, row_idx - 1, current_header_rows))
                            in_table = False
                            continue
                    except:
                        pass

    if in_table:
        table_groups.append(
            (current_start, ws_src.max_row, current_header_rows))

    # 提取每个表格的数据
    tables_data = []
    for table_start, table_end, header_rows in table_groups:
        max_cols = 0
        for row_idx in range(table_start, table_end + 1):
            for col_idx in range(1, ws_src.max_column + 1):
                val = ws_src.cell(row=row_idx, column=col_idx).value
                if val is not None:
                    max_cols = max(max_cols, col_idx)

        # 收集表头
        header_row_data = []
        for header_row_idx in header_rows:
            header_data = []
            for col_idx in range(1, max_cols + 1):
                val = ws_src.cell(row=header_row_idx, column=col_idx).value
                header_data.append(val if val is not None else "")
            header_row_data.append(header_data)

        # 收集数据行
        data_rows = []
        for row_idx in range(table_start, table_end + 1):
            if row_idx in header_rows:
                continue
            row_data = []
            for col_idx in range(1, max_cols + 1):
                val = ws_src.cell(row=row_idx, column=col_idx).value
                row_data.append(val if val is not None else "")
            data_rows.append(row_data)

        # 收集合并
        merges_for_table = []
        for merged_range in list(ws_src.merged_cells.ranges):
            merge_start_row = merged_range.min_row
            merge_end_row = merged_range.max_row
            merge_start_col = merged_range.min_col
            merge_end_col = merged_range.max_col

            if merge_start_row >= table_start and merge_end_row <= table_end:
                rel_start_row = merge_start_row - table_start
                rel_end_row = merge_end_row - table_start
                merges_for_table.append({
                    'start_row': rel_start_row,
                    'start_col': merge_start_col - 1,
                    'end_row': rel_end_row,
                    'end_col': merge_end_col - 1
                })

        tables_data.append({
            'table_start': table_start,
            'table_end': table_end,
            'header_rows': header_rows,
            'header_row_count': len(header_rows),
            'header_row_data': header_row_data,
            'data_rows': data_rows,
            'merges': merges_for_table,
            'max_cols': max_cols
        })

    return tables_data


def build_new_workbook(tables_data: List[Dict[str, Any]], source_url: str, output_path: str):
    """
    重新构建Excel工作簿：
    - 第一步：所有价格字段替换为 原值×1.3
    - 第二步：在表格**后面**追加新列，与原价格列一对一对应，值为"每个token等于多少元宝"
    - 列与列之间紧凑无空隙
    - 表格之间保留3行间距
    """
    wb_new = Workbook()
    wb_new.remove(wb_new.active)
    ws_new = wb_new.create_sheet(title="模型价格汇总（加价）")

    # 样式
    new_col_header_font = Font(bold=True, color="FFFFFF", size=11)
    new_col_header_fill = PatternFill(
        start_color="E67E22", end_color="E67E22", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill(
        start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_alignment = Alignment(
        horizontal="center", vertical="center", wrap_text=True)
    title_font = Font(bold=True, size=14, color="333333")
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )

    GAP_ROWS = 3
    current_row = 1

    for table_idx, table in enumerate(tables_data):
        section_title = f"表格{table_idx + 1}"
        header_row_data = table['header_row_data']
        data_rows = table['data_rows']
        header_row_count = table['header_row_count']
        merges = table['merges']
        original_max_cols = table['max_cols']

        # 找出价格列（基于最后一行表头）
        last_header_row = header_row_data[-1]
        price_columns = []  # [(col_idx_0_based, unit, header_text), ...]

        for col_idx, header_text in enumerate(last_header_row):
            if is_price_column(str(header_text or "")):
                unit = detect_unit(str(header_text or ""))
                price_columns.append((col_idx, unit, str(header_text or "")))

        # 新的最大列数 = 原列数（保持原列结构，价格只替换不增加列）
        # 元宝列追加在所有原列之后
        new_max_cols = original_max_cols + len(price_columns)

        # 写入标题行
        title_cell = ws_new.cell(
            row=current_row, column=1, value=section_title)
        title_cell.font = title_font
        title_cell.alignment = header_alignment
        current_row += 1

        # =====================
        # 第一步：替换价格列
        # =====================
        # 复制表头行（保持原样）
        new_header_rows = [list(row) for row in header_row_data]

        # 复制数据行，但替换价格字段
        new_data_rows = []
        for data_row in data_rows:
            new_row = []
            for col_idx, cell_value in enumerate(data_row):
                if col_idx < len(last_header_row) and is_price_column(str(last_header_row[col_idx] or "")):
                    price = parse_price(cell_value)
                    if price is not None:
                        # 替换为加价30%后的价格
                        new_price = apply_markup_to_price(price)
                        new_row.append(format_price(new_price))
                    else:
                        new_row.append(cell_value)
                else:
                    new_row.append(cell_value)
            new_data_rows.append(new_row)

        # =====================
        # 第二步：在表格**后面**追加元宝列
        # =====================
        # 在每个表头行末尾追加对应的元宝列表头
        for header_row_idx in range(header_row_count):
            for col_idx, unit, header_text in price_columns:
                display_unit = "字符" if unit == "万字符" else unit
                # 追加列标题：每个token=多少元宝
                yuanbao_header = f"元宝/{display_unit}" if header_text else f"元宝/{display_unit}"
                new_header_rows[header_row_idx].append(yuanbao_header)

        # 在每个数据行末尾追加对应的元宝值
        for data_row_idx, data_row in enumerate(data_rows):
            for col_idx, unit, header_text in price_columns:
                # 从原始数据中找价格
                original_value = data_row[col_idx] if col_idx < len(
                    data_row) else None
                price = parse_price(original_value)
                if price is not None:
                    # 传入原始单位文本（header_text），用于判断是否需要额外除以100万/1万
                    yuanbao_text = calculate_yuanbao_per_unit(
                        price, unit, header_text)
                else:
                    yuanbao_text = ""
                new_data_rows[data_row_idx].append(yuanbao_text)

        # 写入新表头（原表头部分）
        for header_row_idx, header_data in enumerate(new_header_rows):
            for col_idx, cell_value in enumerate(header_data):
                cell = ws_new.cell(
                    row=current_row + header_row_idx,
                    column=col_idx + 1,
                    value=cell_value)
                cell.border = thin_border
                if col_idx >= original_max_cols:
                    # 元宝列：橙色背景
                    cell.font = new_col_header_font
                    cell.fill = new_col_header_fill
                else:
                    # 原表头：蓝色背景
                    cell.font = header_font
                    cell.fill = header_fill
                cell.alignment = header_alignment

        # 写入新数据
        for data_row_idx, data_row in enumerate(new_data_rows):
            for col_idx, cell_value in enumerate(data_row):
                cell = ws_new.cell(
                    row=current_row + header_row_count + data_row_idx,
                    column=col_idx + 1,
                    value=cell_value)
                cell.border = thin_border
                if col_idx >= original_max_cols:
                    # 元宝列：橙色字体
                    cell.font = Font(color="E67E22", size=10)
                cell.alignment = Alignment(wrap_text=True, vertical='top')

        # 调整列宽
        for col_idx in range(new_max_cols):
            max_len = 0
            for header_data in new_header_rows:
                if col_idx < len(header_data):
                    cell_text = str(header_data[col_idx] or "")
                    max_len = max(max_len, len(cell_text))
            for data_row in new_data_rows:
                if col_idx < len(data_row):
                    cell_text = str(data_row[col_idx] or "")
                    for line in cell_text.split('\n'):
                        max_len = max(max_len, len(line))

            col_width = min(max(max_len + 2, 12), 50)
            ws_new.column_dimensions[get_column_letter(
                col_idx + 1)].width = col_width

        # 应用合并
        for merge in merges:
            try:
                s_row = current_row + merge['start_row']
                s_col = merge['start_col'] + 1
                e_row = current_row + merge['end_row']
                e_col = merge['end_col'] + 1

                if e_col <= new_max_cols and s_row >= current_row:
                    range_str = f"{get_column_letter(s_col)}{s_row}:{get_column_letter(e_col)}{e_row}"
                    ws_new.merge_cells(range_str)
                    master_cell = ws_new.cell(row=s_row, column=s_col)
                    master_cell.alignment = header_alignment
            except Exception:
                pass

        # 设置表头行高
        for header_row_idx in range(header_row_count):
            ws_new.row_dimensions[current_row + header_row_idx].height = 30

        # 更新current_row
        current_row += header_row_count + len(new_data_rows) + GAP_ROWS

    # 数据来源
    if source_url and tables_data:
        source_cell = ws_new.cell(row=current_row, column=1, value="数据来源")
        source_cell.font = Font(bold=True, italic=True, color="666666")
        ws_new.cell(row=current_row, column=2, value=source_url).font = Font(
            italic=True, color="666666")

    wb_new.save(output_path)


def process_excel_file(input_path: str, output_path: str) -> bool:
    """处理单个Excel文件"""
    print(f"\n处理: {os.path.basename(input_path)}")
    print(f"  输入: {input_path}")
    print(f"  输出: {output_path}")

    try:
        wb_src = load_workbook(input_path)
    except Exception as e:
        print(f"  ✗ 加载失败: {e}")
        return False

    # 读取源URL
    source_url = ""
    for ws in wb_src.worksheets:
        for row in ws.iter_rows(values_only=True):
            for val in row:
                if val and isinstance(val, str) and "http" in val:
                    source_url = val
                    break
            if source_url:
                break
        if source_url:
            break

    try:
        tables_data = extract_tables_from_source(wb_src)
        print(f"  提取到 {len(tables_data)} 个表格")

        build_new_workbook(tables_data, source_url, output_path)
        print(f"  ✓ 已保存: {output_path}")
        return True
    except Exception as e:
        print(f"  ✗ 处理失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main_func():
    """主函数"""
    print("=" * 70)
    print("加价处理程序（新版本）")
    print("=" * 70)
    print(f"规则：")
    print(f"  - 成本加成 {PROFIT_MARGIN*100:.0f}%：新表价格 = 原价 × {1 + PROFIT_MARGIN}")
    print(f"  - 1 元 = {YUANBAO_PER_YUAN} 元宝")
    print(f"  - 输出：每个 token/秒/张/首/字符 等于多少元宝")
    print("=" * 70)

    output_dir = os.path.join(os.path.dirname(
        os.path.abspath(__file__)), "output")
    processed_dir = os.path.join(output_dir, "processed")
    os.makedirs(processed_dir, exist_ok=True)

    excel_files = find_latest_excel_files(output_dir)

    if not excel_files:
        print(f"✗ 未在 {output_dir} 找到Excel文件")
        print("请先运行 main.py 生成价格Excel文件")
        return

    print(f"\n找到 {len(excel_files)} 个Excel文件:")
    for f in excel_files:
        print(f"  - {os.path.basename(f)}")

    success_count = 0
    for input_path in excel_files:
        basename = os.path.basename(input_path)
        name_without_ts = re.sub(r'_\d{8}_\d{6}', '', basename)
        name_without_ext = os.path.splitext(name_without_ts)[0]
        output_filename = f"{name_without_ext}_加价.xlsx"
        output_path = os.path.join(processed_dir, output_filename)

        if process_excel_file(input_path, output_path):
            success_count += 1

    print("\n" + "=" * 70)
    print(f"处理完成: {success_count}/{len(excel_files)} 个文件")
    print(f"输出目录: {processed_dir}")
    print("=" * 70)


if __name__ == "__main__":
    main_func()
