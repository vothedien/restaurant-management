from pydantic import BaseModel


class CatalogPlaceholder(BaseModel):
    message: str = "Catalog features will be implemented in this module."
