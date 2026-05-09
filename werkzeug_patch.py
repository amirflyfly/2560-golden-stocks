import werkzeug.urls

# 为Werkzeug添加url_quote函数
if not hasattr(werkzeug.urls, 'url_quote'):
    from urllib.parse import quote
    werkzeug.urls.url_quote = quote