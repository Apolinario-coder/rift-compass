from pydantic import BaseModel, Field


class Account(BaseModel):
    puuid: str = Field(min_length=1)
    # ACCOUNT-V1 pode omitir nomes. Não inventamos valores ausentes.
    gameName: str | None = None
    tagLine: str | None = None
