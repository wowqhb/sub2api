#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网页抓取器基类
提供统一的网页抓取接口
"""

import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional
import time
import re


class BaseScraper:
    """网页抓取器基类"""

    def __init__(self, url: str, platform_name: str):
        self.url = url
        self.platform_name = platform_name
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        })

    def fetch_page(self, url: Optional[str] = None) -> Optional[BeautifulSoup]:
        """
        获取页面内容

        Args:
            url: 可选的URL，默认使用初始化时的URL

        Returns:
            BeautifulSoup对象或None
        """
        target_url = url or self.url
        try:
            print(f"  正在请求: {target_url}")
            response = self.session.get(target_url, timeout=30)
            response.raise_for_status()
            # 优先使用响应头中的编码，其次尝试utf-8，最后使用自动检测
            if response.encoding and response.encoding.lower() in ('utf-8', 'utf8'):
                pass  # 已经是utf-8
            elif response.apparent_encoding and response.apparent_encoding.lower().startswith('utf'):
                response.encoding = response.apparent_encoding
            elif response.apparent_encoding:
                response.encoding = response.apparent_encoding
            return BeautifulSoup(response.content, 'lxml', from_encoding=response.encoding)
        except Exception as e:
            print(f"  ✗ 请求失败: {e}")
            return None

    def scrape(self) -> List[Dict[str, Any]]:
        """
        抓取数据

        Returns:
            模型数据列表
        """
        raise NotImplementedError("子类必须实现此方法")

    @staticmethod
    def clean_text(text: str) -> str:
        """清理文本，去除多余空白"""
        if not text:
            return ""
        return re.sub(r'\s+', ' ', text).strip()

    @staticmethod
    def safe_get(element, default: str = "") -> str:
        """安全获取元素文本"""
        try:
            if element is None:
                return default
            text = element.get_text() if hasattr(element, 'get_text') else str(element)
            return BaseScraper.clean_text(text)
        except Exception:
            return default