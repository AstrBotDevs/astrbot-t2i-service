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
        viewport_width: (int, optional): 自定义视口宽度，用于控制截图宽度.
        device_scale_factor_level: (Literal["normal", "high", "ultra"], optional): 设备像素比等级.
            - normal: 1.0
            - high: 1.3
            - ultra: 1.8

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
    device_scale_factor_level: Literal["normal", "high", "ultra", None] = None


class Text2ImgRender:
    # Mapping from device_scale_factor_level to actual device_scale_factor
    SCALE_FACTOR_MAP = {
        "normal": 1.0,
        "high": 1.3,
        "ultra": 1.8,
    }

    def __init__(self):
        self.playwright: Playwright | None = None
        self.browser: Browser | None = None
        # Context pool: {"normal": context, "high": context, "ultra": context}
        self.contexts: dict[str, BrowserContext] = {}

    async def _ensure_context(self, level: str = "normal") -> BrowserContext:
        """Ensure that Playwright, Browser and BrowserContext are initialized."""
        if self.playwright is None:
            self.playwright = await async_playwright().start()

        if self.browser is None or not self.browser.is_connected():
            if self.browser is not None:
                try:
                    await self.browser.close()
                except Exception as e:
                    logger.debug(f"Close old browser failed: {e}")
            self.browser = await self.playwright.chromium.launch(headless=True)

        if level not in self.contexts:
            scale_factor = self.SCALE_FACTOR_MAP.get(level, 1.0)
            self.contexts[level] = await self.browser.new_context(
                device_scale_factor=scale_factor,
            )
            logger.info(
                f"Created context for level '{level}' with device_scale_factor={scale_factor}"
            )

        return self.contexts[level]

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
        viewport_width: int | None = screenshot_options.viewport_width
        if viewport_width is not None:
            return viewport_width

        try:
            with open(html_file_path, "r", encoding="utf-8") as f:
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
        for level, context in list(self.contexts.items()):
            try:
                await context.close()
                logger.debug(f"Closed context for level '{level}'")
            except Exception as e:
                logger.debug(f"Close context for level '{level}' failed: {e}")
        self.contexts.clear()

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
        level = screenshot_options.device_scale_factor_level or "normal"
        context = await self._ensure_context(level)

        suffix = screenshot_options.type if screenshot_options.type else "png"
        result_path, _ = generate_data_path(suffix=suffix, namespace="rendered")

        try:
            page = await context.new_page()
        except TargetClosedError as e:
            logger.warning(
                f"html2pic: Failed to create new page, restarting browser context: {e}"
            )
            if level in self.contexts:
                try:
                    await self.contexts[level].close()
                except Exception:
                    pass
                del self.contexts[level]
            context = await self._ensure_context(level)
            page = await context.new_page()

        viewport_width = self._resolve_viewport_width(
            html_file_path, screenshot_options
        )
        if viewport_width is not None:
            await page.set_viewport_size({"width": viewport_width, "height": 720})
            logger.info(f"html2pic: set viewport width to {viewport_width}")

        try:
            # 读取 HTML 内容，用 set_content() 加载而非 file:// 协议
            # file:// 协议下 Chromium 会因跨域策略阻断 CDN 脚本（marked.js 等），
            # 导致 JS 不执行，#content 永远为空。
            # set_content() + base_url="https://cdn.jsdelivr.net" 可让 CDN 正常加载。
            with open(html_file_path, "r", encoding="utf-8") as f:
                html_content = f.read()

            await page.set_content(
                html_content,
                wait_until="networkidle",
            )

            # 等待 JS 渲染 Markdown 完成（marked.js 异步执行）
            try:
                content_el = await page.query_selector("#content")
                if content_el is not None:
                    await page.wait_for_selector(
                        "#content:not(:empty)", timeout=10000
                    )
                    # 额外等待 500ms，确保 marked.js 完整渲染所有内容
                    await page.wait_for_timeout(500)
            except Exception as e:
                logger.debug(f"html2pic: wait_for_selector skipped: {e}")

            screenshot_kwargs = screenshot_options.model_dump(exclude_none=True)
            screenshot_kwargs.pop("viewport_width", None)
            screenshot_kwargs.pop("device_scale_factor_level", None)

            if screenshot_options.type == "png":
                screenshot_kwargs.pop("quality", None)

            await page.screenshot(path=result_path, **screenshot_kwargs)
        finally:
            await page.close()

        logger.info(f"Rendered {html_file_path} to {result_path}")

        return result_path
