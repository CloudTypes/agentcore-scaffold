"""
Unit tests for database tool.
"""

import pytest
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from tools.database import database_query


class TestDatabase:
    """Test cases for database tool."""
    
    def test_query_users_table(self):
        """Test querying users table."""
        result = database_query("users")
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["name"] == "Alice"
        assert result[1]["name"] == "Bob"
    
    def test_query_products_table(self):
        """Test querying products table."""
        result = database_query("products")
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["name"] == "Widget"
        assert result[1]["name"] == "Gadget"
    
    def test_filter_by_name(self):
        """Test filtering by name field."""
        result = database_query("users", "name", "Alice")
        assert len(result) == 1
        assert result[0]["name"] == "Alice"
        assert result[0]["email"] == "alice@example.com"
    
    def test_filter_by_email(self):
        """Test filtering by email field."""
        result = database_query("users", "email", "bob@example.com")
        assert len(result) == 1
        assert result[0]["name"] == "Bob"
    
    def test_case_insensitive_filtering(self):
        """Test case-insensitive filtering."""
        result = database_query("users", "name", "alice")
        assert len(result) == 1
        assert result[0]["name"] == "Alice"
        
        result = database_query("users", "name", "ALICE")
        assert len(result) == 1
        assert result[0]["name"] == "Alice"
    
    def test_filter_products_by_name(self):
        """Test filtering products by name."""
        result = database_query("products", "name", "Widget")
        assert len(result) == 1
        assert result[0]["name"] == "Widget"
        assert result[0]["price"] == 29.99
    
    def test_filter_products_by_price(self):
        """Test filtering products by price."""
        result = database_query("products", "price", "29.99")
        assert len(result) == 1
        assert result[0]["name"] == "Widget"
    
    def test_no_matching_filter(self):
        """Test filter with no matching records."""
        result = database_query("users", "name", "Charlie")
        assert len(result) == 0
        assert isinstance(result, list)
    
    def test_non_existent_table(self):
        """Test querying non-existent table."""
        result = database_query("nonexistent")
        assert isinstance(result, dict)
        assert "error" in result
        assert "not found" in result["error"].lower()
    
    def test_filter_without_value(self):
        """Test filter field without value."""
        result = database_query("users", "name", None)
        assert len(result) == 2  # Should return all records
    
    def test_filter_without_field(self):
        """Test filter value without field."""
        result = database_query("users", None, "Alice")
        assert len(result) == 2  # Should return all records
    
    def test_empty_filter(self):
        """Test empty filter parameters."""
        result = database_query("users", "", "")
        assert len(result) == 2  # Should return all records
    
    def test_numeric_filter_value(self):
        """Test filtering with numeric value as string."""
        result = database_query("products", "id", "1")
        assert len(result) == 1
        assert result[0]["id"] == 1

