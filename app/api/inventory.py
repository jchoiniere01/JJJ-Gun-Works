from fastapi import APIRouter, HTTPException, Request, status

from app.schemas import InventoryCreate, InventoryUpdate, PaginatedResponse
from app.services.crud_service import create_row, delete_row, get_row, list_rows, update_row
from app.table_config import INVENTORY_TABLES

router = APIRouter(prefix="/inventory", tags=["inventory"])


def resolve_table(table_key: str):
    mapping = INVENTORY_TABLES.get(table_key)
    if not mapping:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown inventory table '{table_key}'. Valid values: {', '.join(INVENTORY_TABLES)}",
        )
    return mapping


@router.get("/tables")
def list_inventory_tables() -> dict:
    return {
        key: {
            "schema": mapping.schema,
            "table": mapping.table,
            "primary_key": mapping.primary_key,
            "allowed_columns": mapping.allowed_columns,
            "searchable_columns": mapping.searchable_columns,
        }
        for key, mapping in INVENTORY_TABLES.items()
    }


@router.get("/{table_key}", response_model=PaginatedResponse)
def list_inventory_rows(table_key: str, request: Request, page: int = 1, page_size: int = 50) -> dict:
    return list_rows(resolve_table(table_key), request, page, page_size)


@router.get("/{table_key}/{row_id}")
def get_inventory_row(table_key: str, row_id: int) -> dict:
    return get_row(resolve_table(table_key), row_id)


@router.post("/{table_key}", status_code=status.HTTP_201_CREATED)
def create_inventory_row(table_key: str, payload: InventoryCreate) -> dict:
    return create_row(resolve_table(table_key), payload.data)


@router.patch("/{table_key}/{row_id}")
def update_inventory_row(table_key: str, row_id: int, payload: InventoryUpdate) -> dict:
    return update_row(resolve_table(table_key), row_id, payload.data)


@router.delete("/{table_key}/{row_id}")
def delete_inventory_row(table_key: str, row_id: int) -> dict:
    return delete_row(resolve_table(table_key), row_id)
