import os

if __name__ == "__main__":
    import uvicorn
    port = os.getenv("PORT", 8999)
    uvicorn.run(
        "src.api:app",
        host="0.0.0.0",
        port=int(port),
        h11_max_incomplete_event_size=10 * 1024 * 1024,  # 10MB，支持大体积 Shiki 脚本内联
    )
