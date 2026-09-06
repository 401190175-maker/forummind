"""API 路由层包：承载业务 router 注册模块。

`app.main` 只负责导入并注册本包中的 router，不承载业务逻辑；
启动级端点（/、/health、/version）保持在 `app.main` 中。
"""
