import asyncio
import os

import fastapi
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from jinja2.exceptions import SecurityError
from loguru import logger
from pydantic import BaseModel

from .render import ScreenshotOptions, Text2ImgRender
from .util import cleanup_expired_files

app = fastapi.FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
render = Text2ImgRender()


class GenerateRequest(BaseModel):
    html: str | None = None
    tmpl: str | None = None
    tmplname: str | None = None
    tmpldata: dict | None = None
    options: ScreenshotOptions | None = None
    json: bool = False


# 启动时创建清理任务
@app.on_event("startup")
async def startup_event():
    """应用启动时的事件处理"""
    # 启动定期清理任务
    asyncio.create_task(periodic_cleanup())
    logger.info("Started periodic cleanup task")


async def periodic_cleanup():
    """定期清理过期文件的后台任务"""
    while True:
        try:
            cleanup_expired_files()
        except Exception as e:
            logger.error(f"Error during periodic cleanup: {e}")
        # 每小时执行一次清理
        await asyncio.sleep(3600)


@app.get("/text2img/data/{id}")
async def text2img_image(id: str):
    pic = f"data/{id}"
    if os.path.exists(pic):
        return fastapi.responses.FileResponse(pic, media_type="image/jpeg")
    else:
        return JSONResponse(
            status_code=404,
            content={"code": 1, "message": "file not found", "data": {}},
        )


@app.post("/text2img/generate")
async def text2img(request: GenerateRequest):
    """
    html: str
    options: ScreenshotOptions
    """

    is_json_return = request.json or False
    if request.tmpl or request.tmplname:
        if request.tmpl:
            tmpl = request.tmpl
        else:
            tmpl = open(f"tmpl/{request.tmplname}.html", "r", encoding="utf-8").read()
        try:
            _, abs_path = await render.from_jinja_template(tmpl, request.tmpldata or {})
        except SecurityError as e:
            return JSONResponse(
                status_code=400,
                content={"code": 1, "message": f"security error: {str(e)}", "data": {}},
            )
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={
                    "code": 1,
                    "message": f"template render error: {str(e)}",
                    "data": {},
                },
            )
    elif request.html:
        html = request.html
        _, abs_path = await render.from_html(html)
    else:
        return JSONResponse(
            status_code=400,
            content={"code": 1, "message": "html or tmpl not found", "data": {}},
        )
    options = (
        request.options
        if request.options
        else ScreenshotOptions(
            timeout=None,
            type="png",
            quality=None,
            omit_background=None,
            full_page=True,
            clip=None,
            animations=None,
            caret=None,
            scale="device",
        )
    )

    pic = await render.html2pic(abs_path, options)

    media_type = "image/png" if pic.endswith(".png") else "image/jpeg"

    if is_json_return:
        return JSONResponse(
            content={
                "code": 0,
                "message": "success",
                "data": {"id": pic.replace("\\", "/")},
            },
        )
    else:
        return fastapi.responses.FileResponse(pic, media_type=media_type)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8999)))
