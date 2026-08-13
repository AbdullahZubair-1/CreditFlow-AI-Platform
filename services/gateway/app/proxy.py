import httpx
from fastapi import Request, Response

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=30.0)
    return _client


HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "transfer-encoding",
    "content-length",
    "content-encoding",
}


async def forward(request: Request, base_url: str, path: str, extra_headers: dict[str, str] | None = None) -> Response:
    url = f"{base_url}/{path}"
    headers = {k: v for k, v in request.headers.items() if k.lower() not in {"host", *HOP_BY_HOP_HEADERS}}
    if extra_headers:
        headers.update(extra_headers)

    body = await request.body()
    upstream = await get_client().request(
        request.method,
        url,
        params=request.query_params,
        headers=headers,
        content=body,
    )

    response_headers = {
        k: v for k, v in upstream.headers.items() if k.lower() not in HOP_BY_HOP_HEADERS
    }
    return Response(content=upstream.content, status_code=upstream.status_code, headers=response_headers)
