# AstrBot Text2Image Service

中文 | [English](README.md) | [日本語](README_ja.md)

## 功能

一个简单的将 HTML/模板转换为图片的 Web 服务，支持图片生命周期管理。

## 环境变量配置

- `PORT`: 服务端口，默认 8999
- `IMAGE_LIFETIME_HOURS`: 图片生命时间（小时），默认 24 小时。超过此时间的图片文件将被自动清理

## API 接口

### POST /text2img/generate

html 转 img

> html 和 tmpl 任选一个。tmpl 和 tmpldata 一起提供。

- `str` html: html 文本
- `str` tmpl: jinja2 html 模板
- `dict` tmpldata: jinja2 模板 data
- `bool` json: 是否返回 json 格式（返回一个 id）
- `dict` `optional` options
  - timeout (float, optional): 截图超时时间.
  - type (Literal["jpeg", "png"], optional): 截图图片类型.
  - quality (int, optional): 截图质量，仅适用于 JPEG 格式图片.
  - omit_background (bool, optional): 是否允许隐藏默认的白色背景，这样就可以截透明图了，仅适用于 PNG 格式
  - full_page (bool, optional): 是否截整个页面而不是仅设置的视口大小，默认为 True.
  - clip (FloatRect, optional): 截图后裁切的区域，xy为起点.
  - animations: (Literal["allow", "disabled"], optional): 是否允许播放 CSS 动画.
  - caret: (Literal["hide", "initial"], optional): 当设置为 `hide` 时，截图时将隐藏文本插入符号，默认为 `hide`.
  - scale: (Literal["css", "device"], optional): 页面缩放设置. 当设置为 `css` 时，则将设备分辨率与 CSS 中的像素一一对应，在高分屏上会使得截图变小. 当设置为 `device` 时，则根据设备的屏幕缩放设置或当前 Playwright 的 Page/Context 中的 device_scale_factor 参数来缩放.
  - viewport_width (int, optional): 自定义视口宽度，用于控制截图宽度.
  - device_scale_factor_level (Literal["normal", "high", "ultra"], optional): 设备像素比等级，默认为 "normal". 不同等级使用独立的浏览器上下文池，提供更好的性能和资源隔离.
    - `normal`: 设备像素比 1.0（默认）
    - `high`: 设备像素比 1.3
    - `ultra`: 设备像素比 1.8

### GET /text2img/data/{id}

根据 id 返回对应的图像。
