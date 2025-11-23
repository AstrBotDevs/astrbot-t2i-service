import re

from .util import generate_data_path
from playwright.async_api import async_playwright
from jinja2.sandbox import SandboxedEnvironment
from pydantic import BaseModel
from typing_extensions import TypedDict
from typing import Literal
from loguru import logger
from playwright.async_api import BrowserContext, Browser, Playwright
from playwright._impl._errors import TargetClosedError


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
        self.playwright: Playwright | None = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None

    async def _ensure_context(self) -> None:
        """Ensure that Playwright, Browser and BrowserContext are initialized."""
        if self.playwright is None:
            self.playwright = await async_playwright().start()

        # ensure browser launched
        if self.browser is None or not self.browser.is_connected():
            if self.browser is not None:
                try:
                    await self.browser.close()
                except Exception as e:
                    logger.debug(f"Close old browser failed: {e}")
            self.browser = await self.playwright.chromium.launch(headless=True)

        # ensure context available
        if self.context is None:
            self.context = await self.browser.new_context(
                device_scale_factor=1.0,
            )

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

    async def terminate(self) -> None:
        """Terminate Playwright and close browser."""
        if self.context is not None:
            try:
                await self.context.close()
            except Exception as e:
                logger.debug(f"Close context failed: {e}")
            self.context = None

        if self.browser is not None:
            try:
                await self.browser.close()
            except Exception as e:
                logger.debug(f"Close browser failed: {e}")
            self.browser = None

        if self.playwright is not None:
            try:
                await self.playwright.stop()
            except Exception as e:
                logger.debug(f"Stop Playwright failed: {e}")
            self.playwright = None

    async def html2pic(
        self, html_file_path: str, screenshot_options: ScreenshotOptions
    ) -> str:
        await self._ensure_context()

        if self.context is None:
            raise RuntimeError("BrowserContext is not initialized.")

        suffix = screenshot_options.type if screenshot_options.type else "png"
        result_path, _ = generate_data_path(suffix=suffix, namespace="rendered")

        try:
            page = await self.context.new_page()
        except TargetClosedError as e:
            logger.warning(
                f"html2pic: Failed to create new page, restarting browser context: {e}"
            )
            await self.terminate()
            await self._ensure_context()
            page = await self.context.new_page()

        viewport_width = self._resolve_viewport_width(
            html_file_path, screenshot_options
        )
        if viewport_width is not None:
            # set viewport size to control the width of the screenshot
            await page.set_viewport_size({"width": viewport_width, "height": 720})
            logger.info(f"html2pic: set viewport width to {viewport_width}")

        try:
            await page.goto(f"file://{html_file_path}")
            screenshot_kwargs = screenshot_options.model_dump(exclude_none=True)
            screenshot_kwargs.pop("viewport_width", None)
            await page.screenshot(path=result_path, **screenshot_kwargs)
        finally:
            # Ensure the page is closed to free resources
            await page.close()

        logger.info(f"Rendered {html_file_path} to {result_path}")

        return result_path
