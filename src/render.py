import re

from .util import generate_data_path
from playwright.async_api import async_playwright
from jinja2.sandbox import SandboxedEnvironment
from pydantic import BaseModel
from typing_extensions import TypedDict
from typing import Literal
from loguru import logger


class FloatRect(TypedDict):
    x: float
    y: float
    width: float
    height: float


class ScreenshotOptions(BaseModel):
    """Playwright 截图参数

    详见：https://playwright.dev/python/docs/api/class-page#page-screenshot

    Args:
        timeout (float, optional): 截图超时时间.
        type (Literal["jpeg", "png"], optional): 截图图片类型.
        path (Union[str, Path]], optional): 截图保存路径，如不需要则留空.
        quality (int, optional): 截图质量，仅适用于 JPEG 格式图片.
        omit_background (bool, optional): 是否允许隐藏默认的白色背景，这样就可以截透明图了，仅适用于 PNG 格式.
        full_page (bool, optional): 是否截整个页面而不是仅设置的视口大小，默认为 True.
        clip (FloatRect, optional): 截图后裁切的区域，xy为起点.
        animations: (Literal["allow", "disabled"], optional): 是否允许播放 CSS 动画.
        caret: (Literal["hide", "initial"], optional): 当设置为 `hide` 时，截图时将隐藏文本插入符号，默认为 `hide`.
        scale: (Literal["css", "device"], optional): 页面缩放设置.
            当设置为 `css` 时，则将设备分辨率与 CSS 中的像素一一对应，在高分屏上会使得截图变小.
            当设置为 `device` 时，则根据设备的屏幕缩放设置或当前 Playwright 的 Page/Context 中的
            device_scale_factor 参数来缩放.

    @author: Redlnn(https://github.com/GraiaCommunity/graiax-text2img-playwright)
    """

    timeout: float | None = None
    type: Literal["jpeg", "png", None] = None
    quality: int | None = None
    omit_background: bool | None = None
    full_page: bool | None = True
    clip: FloatRect | None = None
    animations: Literal["allow", "disabled", None] = None
    caret: Literal["hide", "initial", None] = None
    scale: Literal["css", "device", None] = None
    viewport_width: int | None = None


class Text2ImgRender:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        # 默认缩放因子：保持与旧行为一致，逻辑宽度与 CSS 宽度相同
        self._default_device_scale_factor: float = 1.0
        # 当前 Context 所采用的缩放因子，用于在需要时重建 Context
        self._current_device_scale_factor: float | None = None

    async def _ensure_context(self) -> None:
        """确保 Playwright Browser/Context 可用。

        - 懒加载 playwright 实例和浏览器实例；
        - 若 context 不存在或已关闭，则重新创建；
        - 将所有初始化逻辑集中在一处，避免 html2pic 中散落判断。
        """

        # 仅使用服务端默认缩放因子
        target_dsf: float = self._default_device_scale_factor

        if self.playwright is None:
            self.playwright = await async_playwright().start()

        if self.browser is None:
            self.browser = await self.playwright.chromium.launch()

        context_closed = False
        if self.context is not None:
            # Playwright 的 BrowserContext 提供 is_closed 方法；为兼容性
            # 使用 getattr 安全访问，避免未来实现细节变化导致 AttributeError。
            is_closed = getattr(self.context, "is_closed", None)
            if callable(is_closed):
                context_closed = bool(is_closed())

        # 若 Context 不存在、已关闭，或缩放因子不匹配，则重建 Context
        if (
            self.context is None
            or context_closed
            or self._current_device_scale_factor != target_dsf
        ):
            # 尝试关闭旧的 Context，避免资源泄漏
            if self.context is not None and not context_closed:
                try:
                    await self.context.close()
                except Exception as e:
                    logger.debug(f"Close old browser context failed: {e}")

            self.context = await self.browser.new_context(
                device_scale_factor=target_dsf,
            )
            self._current_device_scale_factor = target_dsf

    async def from_jinja_template(self, template: str, data: dict) -> tuple[str, str]:
        env = SandboxedEnvironment()
        html = env.from_string(template).render(data)
        return await self.from_html(html)

    async def from_html(self, html: str) -> tuple[str, str]:
        html_file_path, abs_path = generate_data_path(
            suffix="html", namespace="rendered"
        )
        with open(html_file_path, "w", encoding="utf-8") as f:
            f.write(html)
        return html_file_path, abs_path

    def _resolve_viewport_width(
        self, html_file_path: str, screenshot_options: ScreenshotOptions
    ) -> int | None:
        """根据截图参数与 HTML 内容推断 viewport 宽度。

        优先级：
        1. 调用方在 ScreenshotOptions 中显式指定 `viewport_width`；
        2. 从 HTML 中的 `<meta name="viewport" content="width=xxx">` 自动解析；
        3. 未能解析到时返回 None（调用方可选择使用 Playwright 默认值）。

        将逻辑集中到独立方法，便于后续扩展：
        - 支持更多 meta 语法 / 自定义 data-* 属性；
        - 支持从额外配置源中读取默认宽度等。
        """

        # 1) 调用方显式指定，直接使用
        viewport_width: int | None = screenshot_options.viewport_width
        if viewport_width is not None:
            return viewport_width

        # 2) 未指定时，从 HTML meta viewport 中推断
        try:
            with open(html_file_path, "r", encoding="utf-8") as f:
                # 只读前几 KB 即可命中 <head> 区域
                head_snippet = f.read(4096)

            pattern = (
                r'<meta\s+[^>]*name=["\']viewport["\'][^>]*'
                r'content=["\'][^"\']*width\s*=\s*(\d+)[^"\']*["\'][^>]*>'
            )
            if m := re.search(pattern, head_snippet, re.IGNORECASE):
                viewport_width = int(m[1])
        except (OSError, UnicodeDecodeError, re.error, ValueError) as e:
            logger.debug(f"Adjust viewport from meta tag failed: {e}")

        return viewport_width

    async def html2pic(
        self, html_file_path: str, screenshot_options: ScreenshotOptions
    ) -> str:
        # 使用默认的 BrowserContext 缩放因子（当前固定为 1.0）渲染页面
        await self._ensure_context()
        suffix = screenshot_options.type if screenshot_options.type else "png"
        result_path, _ = generate_data_path(suffix=suffix, namespace="rendered")
        page = await self.context.new_page()

        viewport_width = self._resolve_viewport_width(
            html_file_path, screenshot_options
        )
        if viewport_width is not None:
            # 高度给一个合理默认值，full_page=True 时会自动扩展高度
            await page.set_viewport_size({"width": viewport_width, "height": 720})
            logger.info(
                f"html2pic: set viewport width to {viewport_width}"
            )

        try:
            await page.goto(f"file://{html_file_path}")
            # ScreenshotOptions 中的 viewport_width 仅用于内部控制 viewport，
            # 不透传给 Playwright.screenshot，以免出现未知参数错误。
            screenshot_kwargs = screenshot_options.model_dump(exclude_none=True)
            screenshot_kwargs.pop("viewport_width", None)
            screenshot_kwargs.pop("device_scale_factor", None)
            await page.screenshot(path=result_path, **screenshot_kwargs)
        finally:
            # 确保在异常情况下也能关闭 page，避免资源泄漏。
            await page.close()

        logger.info(f"Rendered {html_file_path} to {result_path}")

        return result_path
