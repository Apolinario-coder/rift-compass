import httpx
from fastapi import HTTPException


async def fetch(client, method, url, **kwargs):
    try:
        response = await client.request(method, url, **kwargs)
    except httpx.TimeoutException:
        raise HTTPException(504, "O serviço demorou para responder. Tente novamente.") from None
    except httpx.RequestError:
        raise HTTPException(
            503, "Um serviço está indisponível. Verifique se todos estão executando."
        ) from None
    if response.is_error:
        try:
            detail = response.json().get("detail", "Não foi possível concluir a consulta.")
        except (ValueError, AttributeError):
            detail = "Não foi possível concluir a consulta."
        headers = {}
        retry = response.headers.get("Retry-After", "")
        if retry.isdigit():
            headers["Retry-After"] = retry
        raise HTTPException(response.status_code, detail, headers=headers)
    try:
        return response.json()
    except ValueError:
        raise HTTPException(502, "O serviço retornou dados inválidos.") from None
