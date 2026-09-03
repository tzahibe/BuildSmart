from fastapi import APIRouter, HTTPException

from app.localities.data import CITIES, CITY_STREETS

router = APIRouter(prefix="/localities", tags=["localities"])


@router.get("", response_model=list[str])
def list_localities() -> list[str]:
    """Cities/settlements a project's `city` field must match — see app/localities/data.py."""
    return CITIES


@router.get("/{city}/streets", response_model=list[str])
def list_streets(city: str) -> list[str]:
    """Streets known for `city`, used to populate the street autocomplete once a city is chosen."""
    streets = CITY_STREETS.get(city)
    if streets is None:
        raise HTTPException(status_code=404, detail="City not recognized")
    return streets
