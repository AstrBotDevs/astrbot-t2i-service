# AstrBot Text2Image Service

[中文](README_zh-CN.md) | English | [日本語](README_ja.md)

## Features

A simple web service that converts HTML/templates to images, with image lifecycle management support.

## Environment Variables

- `PORT`: Service port, default is 8999
- `IMAGE_LIFETIME_HOURS`: Image lifetime in hours, default is 24 hours. Images older than this will be automatically cleaned up

## API Endpoints

### POST /text2img/generate

Convert HTML to image

> Choose either html or tmpl. Provide tmpl and tmpldata together.

- `str` html: HTML text
- `str` tmpl: Jinja2 HTML template
- `dict` tmpldata: Jinja2 template data
- `bool` json: Whether to return JSON format (returns an id)
- `dict` `optional` options
  - timeout (float, optional): Screenshot timeout.
  - type (Literal["jpeg", "png"], optional): Screenshot image type.
  - quality (int, optional): Screenshot quality, only applicable to JPEG format.
  - omit_background (bool, optional): Whether to hide the default white background, allowing transparent screenshots (PNG only).
  - full_page (bool, optional): Whether to capture the entire page instead of just the viewport, default is True.
  - clip (FloatRect, optional): Area to clip after screenshot, xy is the starting point.
  - animations: (Literal["allow", "disabled"], optional): Whether to allow CSS animations.
  - caret: (Literal["hide", "initial"], optional): When set to `hide`, the text caret will be hidden during screenshot, default is `hide`.
  - scale: (Literal["css", "device"], optional): Page scaling settings. When set to `css`, device resolution maps 1:1 with CSS pixels, making screenshots smaller on high-DPI screens. When set to `device`, scales according to device screen scaling or the device_scale_factor parameter in the current Playwright Page/Context.
  - viewport_width (int, optional): Custom viewport width to control screenshot width.
  - device_scale_factor_level (Literal["normal", "high", "ultra"], optional): Device pixel ratio level, default is "normal". Different levels use independent browser context pools for better performance and resource isolation.
    - `normal`: Device pixel ratio 1.0 (default)
    - `high`: Device pixel ratio 1.3
    - `ultra`: Device pixel ratio 1.8

### GET /text2img/data/{id}

Returns the corresponding image by id.
