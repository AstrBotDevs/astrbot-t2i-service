import asyncio
import re
import time

from .util import generate_data_path
from playwright.async_api import async_playwright
from jinja2.sandbox import SandboxedEnvironment
from pydantic import BaseModel
from typing_extensions import TypedDict
from typing import Literal
from loguru import logger
from playwright.async_api import BrowserContext, Browser, Playwright
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
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
            优先级：
            1. 显式指定此参数；
            2. 从 HTML 的 <meta name="viewport" content="width=..."> 自动解析；
            3. 未指定时默认为 800px.
        viewport_height: (int, optional): 自定义视口高度，用于控制截图高度.
            优先级：
            1. 显式指定此参数；
            2. 从 HTML 的 <meta name="viewport" content="height=..."> 自动解析；
            3. 未指定时默认为 720px.
        device_scale_factor_level: (Literal["normal", "high", "ultra"], optional): 设备像素比等级.
            - normal: 1.0
            - high: 1.3
            - ultra: 1.8
        selector: (str, optional): CSS 选择器。设置后优先对匹配的元素截图，而不是整页截图.
        fallback_selector: (str, optional): selector 未命中时使用的备用 CSS 选择器.
        selector_timeout: (int, optional): 等待 selector 出现的超时时间，单位毫秒.
        wait_until: (Literal["commit", "domcontentloaded", "load", "networkidle"], optional):
            页面导航等待状态。未指定时使用 Playwright 默认值.
        wait_for_resources: (bool, optional): 是否在截图前等待网络空闲、图片解码和字体加载.
        resource_timeout: (int, optional): 等待资源加载的超时时间，单位毫秒，默认 5000.

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
    viewport_height: int | None = None
    device_scale_factor_level: Literal["normal", "high", "ultra", None] = None
    selector: str | None = None
    fallback_selector: str | None = None
    selector_timeout: int | None = None
    wait_until: Literal["commit", "domcontentloaded", "load", "networkidle", None] = None
    wait_for_resources: bool | None = None
    resource_timeout: int | None = None


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
        """Ensure that Playwright, Browser and BrowserContext are initialized.

        Args:
            level: Device scale factor level ("normal", "high", or "ultra").
                   Defaults to "normal" if not specified.

        Returns:
            The BrowserContext for the specified level.
        """
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

        # ensure context available for the specified level
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

    def _resolve_viewport_size(
            self, html_file_path: str, screenshot_options: ScreenshotOptions
    ) -> tuple[int | None, int | None]:
        """根据截图参数与 HTML 内容推断 viewport 大小（宽, 高）。

        优先级：
        1. 调用方在 ScreenshotOptions 中显式指定 `viewport_width` / `viewport_height`；
        2. 从 HTML 中的 `<meta name="viewport" content="width=...; height=...">` 自动解析；
        3. 未能解析到时返回对应的 None（调用方可选择使用 Playwright 默认值）。

        将逻辑集中到独立方法，便于后续扩展：
        - 支持更多 meta 语法 / 自定义 data-* 属性；
        - 支持从额外配置源中读取默认宽度等。
        """

        viewport_width: int | None = screenshot_options.viewport_width
        viewport_height: int | None = screenshot_options.viewport_height

        # 如果两者都有显式值，直接返回
        if viewport_width is not None and viewport_height is not None:
            return viewport_width, viewport_height

        # 未指定时，尝试从 HTML meta 中解析（只读前几 KB 即可命中 <head> 区域）
        try:
            with open(html_file_path, "r", encoding="utf-8") as f:
                head_snippet = f.read(4096)

            # 尝试解析宽度和高度（允许任意顺序出现在 content 中）
            if viewport_width is None:
                pattern = (
                    r'<meta\s+[^>]*name=["\']viewport["\'][^>]*'
                    r'content=["\'][^"\']*width\s*=\s*(\d+)[^"\']*["\'][^>]*>'
                )
                if m := re.search(pattern, head_snippet, re.IGNORECASE):
                    viewport_width = int(m[1])

            if viewport_height is None:
                pattern = (
                    r'<meta\s+[^>]*name=["\']viewport["\'][^>]*'
                    r'content=["\'][^"\']*height\s*=\s*(\d+)[^"\']*["\'][^>]*>'
                )
                if m := re.search(pattern, head_snippet, re.IGNORECASE):
                    viewport_height = int(m[1])
        except (OSError, UnicodeDecodeError, re.error, ValueError) as e:
            logger.debug(f"Adjust viewport from meta tag failed: {e}")

        return viewport_width, viewport_height

    async def terminate(self) -> None:
        """Terminate Playwright and close browser."""
        # Close all contexts in the pool
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
        # Determine which context to use based on device_scale_factor_level
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
            # Close and remove the specific context, then recreate it
            if level in self.contexts:
                try:
                    await self.contexts[level].close()
                except Exception:
                    pass
                del self.contexts[level]
            context = await self._ensure_context(level)
            page = await context.new_page()

        viewport_width, viewport_height = self._resolve_viewport_size(
            html_file_path, screenshot_options
        )

        width = viewport_width if viewport_width is not None else 800
        height = viewport_height if viewport_height is not None else 720
        # Always set viewport size to ensure defaults are applied
        await page.set_viewport_size({"width": width, "height": height})
        logger.info(f"html2pic: set viewport size to {width}x{height}")

        try:
            goto_kwargs = {"timeout": screenshot_options.timeout}
            if screenshot_options.wait_until:
                goto_kwargs["wait_until"] = screenshot_options.wait_until
            await page.goto(f"file://{html_file_path}", **goto_kwargs)

            if screenshot_options.wait_for_resources:
                await self._wait_for_resources(page, screenshot_options)

            screenshot_kwargs = screenshot_options.model_dump(exclude_none=True)
            screenshot_kwargs.pop("viewport_width", None)
            screenshot_kwargs.pop("viewport_height", None)
            screenshot_kwargs.pop("device_scale_factor_level", None)
            screenshot_kwargs.pop("selector", None)
            screenshot_kwargs.pop("fallback_selector", None)
            screenshot_kwargs.pop("selector_timeout", None)
            screenshot_kwargs.pop("wait_until", None)
            screenshot_kwargs.pop("wait_for_resources", None)
            screenshot_kwargs.pop("resource_timeout", None)

            # Robustness: Remove quality if type is png, as Playwright errors out
            if screenshot_options.type == "png":
                screenshot_kwargs.pop("quality", None)

            element = await self._resolve_screenshot_element(page, screenshot_options)
            if element is not None:
                element_screenshot_kwargs = screenshot_kwargs.copy()
                element_screenshot_kwargs.pop("full_page", None)
                element_screenshot_kwargs.pop("clip", None)
                await element.screenshot(path=result_path, **element_screenshot_kwargs)
            else:
                await page.screenshot(path=result_path, **screenshot_kwargs)
        finally:
            # Ensure the page is closed to free resources
            await page.close()

        logger.info(f"Rendered {html_file_path} to {result_path}")

        return result_path

    async def _resolve_screenshot_element(self, page, screenshot_options: ScreenshotOptions):
        """Resolve an element target for screenshot when selector options are provided."""

        if not screenshot_options.selector:
            return None

        element = None
        if screenshot_options.selector_timeout is not None:
            try:
                element = await page.wait_for_selector(
                    screenshot_options.selector,
                    timeout=screenshot_options.selector_timeout,
                )
            except PlaywrightTimeoutError as e:
                logger.debug(
                    f"html2pic: wait for selector '{screenshot_options.selector}' failed: {e}"
                )
        else:
            try:
                element = await page.query_selector(screenshot_options.selector)
            except PlaywrightError as e:
                logger.warning(
                    f"html2pic: invalid selector '{screenshot_options.selector}', "
                    f"skip element screenshot: {e}"
                )

        if element is not None:
            logger.info(
                f"html2pic: screenshot element matched selector '{screenshot_options.selector}'"
            )
            return element

        if screenshot_options.fallback_selector:
            try:
                fallback = await page.query_selector(screenshot_options.fallback_selector)
            except PlaywrightError as e:
                logger.warning(
                    "html2pic: invalid fallback selector "
                    f"'{screenshot_options.fallback_selector}', fallback to page screenshot: {e}"
                )
                fallback = None
            if fallback is not None:
                logger.info(
                    f"html2pic: selector '{screenshot_options.selector}' not found, "
                    f"screenshot fallback selector '{screenshot_options.fallback_selector}'"
                )
                return fallback

        logger.warning(
            f"html2pic: selector '{screenshot_options.selector}' not found, fallback to page screenshot"
        )
        return None

    async def _wait_for_resources(self, page, screenshot_options: ScreenshotOptions):
        """Wait for common remote resources before taking a screenshot."""

        timeout = screenshot_options.resource_timeout
        if timeout is None:
            timeout = screenshot_options.timeout if screenshot_options.timeout is not None else 5000
        if timeout <= 0:
            return

        deadline = time.monotonic() + timeout / 1000

        def remaining_timeout() -> int:
            return max(0, int((deadline - time.monotonic()) * 1000))

        try:
            network_timeout = remaining_timeout()
            if network_timeout > 0:
                await page.wait_for_load_state("networkidle", timeout=network_timeout)
        except Exception as e:
            logger.warning(f"html2pic: wait for networkidle failed: {e}")

        resource_timeout = remaining_timeout()
        if resource_timeout <= 0:
            logger.warning(f"html2pic: wait for resources timed out after {timeout}ms")
            return

        try:
            eval_timeout = resource_timeout
            if screenshot_options.timeout is not None and screenshot_options.timeout > 0:
                eval_timeout = min(resource_timeout, int(screenshot_options.timeout))

            result = await asyncio.wait_for(
                page.evaluate(
                    """
                async (timeout) => {
                  const images = Array.from(document.images || []);
                  const waitImage = (img) => {
                    if (img.complete) {
                      return Promise.resolve();
                    }
                    if (typeof img.decode === "function") {
                      return img.decode().catch(() => undefined);
                    }
                    return new Promise((resolve) => {
                      img.addEventListener("load", resolve, { once: true });
                      img.addEventListener("error", resolve, { once: true });
                    });
                  };
                  const waitFonts = () => {
                    if (document.fonts && document.fonts.ready) {
                      return document.fonts.ready.catch(() => undefined);
                    }
                    return Promise.resolve();
                  };
                  let timedOut = false;
                  const allResources = Promise.all([
                    ...images.map(waitImage),
                    waitFonts(),
                  ]);
                  const timeoutPromise = new Promise((resolve) => {
                    setTimeout(() => {
                      timedOut = true;
                      resolve();
                    }, timeout);
                  });
                  await Promise.race([allResources, timeoutPromise]);
                  return {
                    imageCount: images.length,
                    completeCount: images.filter((img) => img.complete).length,
                    brokenCount: images.filter((img) => img.complete && img.naturalWidth === 0).length,
                    timedOut,
                  };
                }
                """,
                    eval_timeout,
                ),
                timeout=eval_timeout / 1000,
            )
            if not isinstance(result, dict):
                logger.warning("html2pic: wait for resources returned invalid result")
                return

            if result.get("timedOut"):
                logger.warning(
                    "html2pic: wait for resources timed out after "
                    f"{timeout}ms, images={result.get('completeCount')}/"
                    f"{result.get('imageCount')}"
                )
            elif result.get("brokenCount"):
                logger.warning(
                    "html2pic: resources loaded with broken images, "
                    f"broken={result.get('brokenCount')}/"
                    f"{result.get('imageCount')}"
                )
            else:
                logger.info(
                    "html2pic: resources ready, "
                    f"images={result.get('completeCount')}/"
                    f"{result.get('imageCount')}"
                )
        except Exception as e:
            logger.warning(f"html2pic: wait for image/font resources failed: {e}")
