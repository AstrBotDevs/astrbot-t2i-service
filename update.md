# T2I 渲染配置更新说明

本次新增两组可选配置：

- `selector screenshot`：按指定 HTML 元素截图，避免整页截图出现多余边缘。
- `resource wait`：在截图前等待远程图片等资源加载完成。

## Selector Screenshot 配置项

| 配置项 | 类型 | 不配置时的默认值 | 说明 |
| --- | --- | --- | --- |
| `selector` | `str` | `None` | CSS 选择器。配置后优先对匹配到的元素执行截图，而不是对整个页面截图。 |
| `fallback_selector` | `str` | `None` | `selector` 未匹配到元素时使用的备用 CSS 选择器。建议配置为 `body`。 |
| `selector_timeout` | `int` | `None` | 等待 `selector` 出现的超时时间，单位为毫秒。未配置时不会额外等待，只会立即查询当前页面中是否存在该元素。 |

### 不配置时的默认行为

如果不配置 `selector`，服务端保持原来的行为，继续使用 `page.screenshot()` 对页面截图。

如果配置了 `selector`，但没有配置 `fallback_selector`，并且 `selector` 没有匹配到元素，服务端会记录 warning，然后回退到原来的页面截图行为。

### JSON 请求示例

```json
{
  "tmpl": "<div id=\"container\">Hello</div>",
  "tmpldata": {},
  "json": true,
  "options": {
    "selector": "#container",
    "fallback_selector": "body",
    "selector_timeout": 1000
  }
}
```

### AstrBot 插件调用示例

```python
await self.html_render(
    tmpl,
    data,
    return_url=False,
    options={
        "selector": "#container",
        "fallback_selector": "body",
        "selector_timeout": 1000,
    },
)
```

## Resource Wait 配置项

| 配置项 | 类型 | 不配置时的默认值 | 说明 |
| --- | --- | --- | --- |
| `wait_for_resources` | `bool` | `None`，等效于 `False` | 是否启用截图前资源等待。未配置时不启用额外等待，保持原来的渲染行为。 |
| `resource_timeout` | `int` | `None` | 资源等待总超时时间，单位为毫秒。仅在 `wait_for_resources` 为 `true` 时生效。未配置时优先使用已有的 `timeout`；如果 `timeout` 也未配置，则默认使用 `5000` 毫秒。 |

### 配置方法

这两个配置项放在 t2i 请求体的 `options` 字段中，不放在 `tmpldata` 中。

### JSON 请求示例

```json
{
  "tmpl": "<div id=\"container\"><img src=\"{{ image_url }}\"></div>",
  "tmpldata": {
    "image_url": "https://example.com/image.png"
  },
  "json": true,
  "options": {
    "wait_for_resources": true,
    "resource_timeout": 10000
  }
}
```

### AstrBot 插件调用示例

```python
await self.html_render(
    tmpl,
    data,
    return_url=False,
    options={
        "wait_for_resources": True,
        "resource_timeout": 10000,
    },
)
```

### 行为说明

启用 `wait_for_resources` 后，服务端会在截图前等待以下资源状态：

- Playwright `networkidle`
- 页面内所有 `<img>` 元素加载或解码完成
- `document.fonts.ready`

如果资源很快加载完成，会立即继续截图，不会固定等待到 `resource_timeout`。

如果超过 `resource_timeout` 仍未加载完成，会记录 warning 并继续截图，避免单个慢速或失效资源导致整个渲染请求永久阻塞。
