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


class Text2ImgRender:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None

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

    async def html2pic(
        self, html_file_path: str, screenshot_options: ScreenshotOptions
    ) -> str:
        if self.context is None:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch()
            self.context = await self.browser.new_context(
                device_scale_factor=1.8,
            )

        suffix = screenshot_options.type if screenshot_options.type else "png"
        result_path, _ = generate_data_path(suffix=suffix, namespace="rendered")
        page = await self.context.new_page()

        # 若 HTML 中声明了 meta viewport 宽度，则按该宽度调整浏览器视口，
        # 使 full_page 截图的宽度与页面内容一致，避免右侧出现多余留白。
        try:
            with open(html_file_path, "r", encoding="utf-8") as f:
                # 只读前几 KB 即可命中 <head> 区域
                head_snippet = f.read(4096)
            m = re.search(
                r'content="width=(\d+),\s*initial-scale=1.0"', head_snippet
            )
            if m:
                vw = int(m.group(1))
                # 高度给一个合理默认值，full_page=True 时会自动扩展高度
                await page.set_viewport_size({"width": vw, "height": 720})
                logger.info(f"html2pic: set viewport width from meta to {vw}")
        except Exception as e:
            logger.debug(f"Adjust viewport from meta tag failed: {e}")

        await page.goto(f"file://{html_file_path}")
        await page.screenshot(path=result_path, **screenshot_options.model_dump())
        await page.close()

        logger.info(f"Rendered {html_file_path} to {result_path}")

        return result_path
