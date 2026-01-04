"""Database query tool for data retrieval."""

from typing import List, Dict, Any, Union
from strands.tools import tool

# Mock database for demonstration
MOCK_DATABASE = {
    "users": [
        {"id": 1, "name": "Alice", "email": "alice@example.com"},
        {"id": 2, "name": "Bob", "email": "bob@example.com"},
    ],
    "products": [
        {"id": 1, "name": "Widget", "price": 29.99},
        {"id": 2, "name": "Gadget", "price": 49.99},
    ]
}

@tool
def database_query(table: str, filter_field: str = None, filter_value: str = None) -> Union[List[Dict[str, Any]], Dict[str, str]]:
    """
    Query the database for records.
    
    Args:
        table: Table name to query (e.g., "users", "products")
        filter_field: Optional field to filter by
        filter_value: Optional value to filter for
        
    Returns:
        List of matching records on success, or a dictionary with an "error" key
        containing the error message if the table is not found.
        
    Example:
        >>> database_query("users", "name", "Alice")
        [{"id": 1, "name": "Alice", "email": "alice@example.com"}]
    """
    if table not in MOCK_DATABASE:
        return {"error": f"Table '{table}' not found"}
    
    records = MOCK_DATABASE[table]
    
    if filter_field and filter_value:
        records = [
            r for r in records 
            if str(r.get(filter_field, "")).lower() == filter_value.lower()
        ]
    
    return records
