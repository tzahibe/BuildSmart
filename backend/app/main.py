from fastapi import FastAPI

app = FastAPI(title="sddproject API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}