from pydantic import BaseModel


class ForecastingPlaceholder(BaseModel):
    message: str = "Forecasting features will be implemented in this module."
