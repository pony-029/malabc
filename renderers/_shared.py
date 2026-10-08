# -*- coding: utf-8 -*-
"""浏览站点共享页面骨架与纯模板（从 matlabc.py 迁出）。

承载 _browse_page 统一骨架，供 metrics / unresolved / func_detail / directory 等页面复用，
使各渲染函数不再逐份手抄 <!DOCTYPE>/<head>/<style> 样板。
"""


def _browse_page(title, brand, body_html):
    """拼装 browse 站标准页。body_html = 正文各行以 '\\n' 连接的字符串
    （含 <h1> 首行、不含 <main> 样板与 </main></body></html> 收尾）。"""
    prefix = "\n".join([
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<script>(function(){try{var t=localStorage.getItem('gs-theme');"
        "if(!t){t=(window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches)?'dark':'light';}"
        "if(t==='dark'){document.documentElement.setAttribute('data-theme','dark');}}catch(e){}})();</script>",
        '<title>%s</title>' % title,
        '<link rel="stylesheet" href="browse.css">',
        '</head><body>',
        '<a class="skip-link" href="#main-content">跳到主内容</a>',
        '<header><span class="brand">%s</span>'
        '<a href="index.html">&larr; 返回索引</a></header>' % brand,
        '<main id="main-content">'])
    return prefix + "\n" + body_html + "\n" + "</main></body></html>"


