from typing import Literal

from pydantic import BaseModel, Field, field_validator

Region = Literal["americas", "europe", "asia", "sea"]
Role = Literal["ALL", "TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]


class AnalysisRequest(BaseModel):
    gameName: str = Field(min_length=1, max_length=100)
    tagLine: str = Field(min_length=1, max_length=100)
    region: Region = "americas"
    queue: Literal[420, 440] = 420
    count: int = Field(default=20, ge=5, le=50)

    @field_validator("gameName", "tagLine")
    @classmethod
    def not_blank(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Preencha o nome e a tag.")
        return value
