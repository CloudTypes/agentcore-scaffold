"""
Database query tool for data retrieval.

This module provides a mock database query tool for demonstration purposes.
It simulates a simple database with in-memory data structures. This is intended
for testing and development, not production use.

The mock database contains sample tables:
- users: User records with id, name, and email
- products: Product records with id, name, and price

For production use, this should be replaced with actual database connectivity
(e.g., SQLAlchemy, psycopg2, or a database client library).
"""

from typing import List, Dict, Any, Union
from strands.tools import tool

# Mock database for demonstration purposes only
# In production, this would connect to an actual database
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
    Query the mock database for records.
    
    This is a demonstration tool that queries an in-memory mock database.
    It supports filtering records by field and value. The filtering is
    case-insensitive for string comparisons.
    
    Args:
        table: Table name to query. Currently supported tables:
            - "users": User records
            - "products": Product records
        filter_field: Optional field name to filter by (e.g., "name", "email").
            If provided, filter_value must also be provided.
        filter_value: Optional value to filter for. The comparison is
            case-insensitive for string fields. If provided, filter_field
            must also be provided.
        
    Returns:
        On success: List of matching record dictionaries. If no filters are
            provided, returns all records from the table. If filters are
            provided, returns only records where the specified field matches
            the filter value (case-insensitive).
            
        On error: Dictionary with a single "error" key containing an error
            message. This occurs when:
            - The specified table does not exist
            
    Note:
        This is a mock implementation for demonstration. In production,
        this would connect to an actual database and support more complex
        queries, parameterized statements, and proper error handling.
        
    Example:
        >>> database_query("users")
        [
            {"id": 1, "name": "Alice", "email": "alice@example.com"},
            {"id": 2, "name": "Bob", "email": "bob@example.com"}
        ]
        
        >>> database_query("users", "name", "Alice")
        [{"id": 1, "name": "Alice", "email": "alice@example.com"}]
        
        >>> database_query("nonexistent")
        {"error": "Table 'nonexistent' not found"}
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
