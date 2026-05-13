"""
Sample SQL DSL module for reproduction testing.

Contains SQL query builder patterns - tests DSL reproduction.
"""

from typing import List, Optional, Dict, Any, Union
from dataclasses import dataclass
from enum import Enum


class SQLOperator(Enum):
    """SQL comparison operators."""

    EQ = "="
    NE = "!="
    LT = "<"
    GT = ">"
    LTE = "<="
    GTE = ">="
    LIKE = "LIKE"
    IN = "IN"
    IS_NULL = "IS NULL"
    IS_NOT_NULL = "IS NOT NULL"


class JoinType(Enum):
    """SQL join types."""

    INNER = "INNER JOIN"
    LEFT = "LEFT JOIN"
    RIGHT = "RIGHT JOIN"
    FULL = "FULL OUTER JOIN"


@dataclass
class Condition:
    """SQL WHERE condition."""

    column: str
    operator: SQLOperator
    value: Any = None

    def to_sql(self) -> str:
        """Convert to SQL string."""
        if self.operator in (SQLOperator.IS_NULL, SQLOperator.IS_NOT_NULL):
            return f"{self.column} {self.operator.value}"
        elif self.operator == SQLOperator.IN:
            values = ", ".join(
                f"'{v}'" if isinstance(v, str) else str(v) for v in self.value
            )
            return f"{self.column} IN ({values})"
        elif isinstance(self.value, str):
            return f"{self.column} {self.operator.value} '{self.value}'"
        return f"{self.column} {self.operator.value} {self.value}"


@dataclass
class Join:
    """SQL JOIN clause."""

    table: str
    on_left: str
    on_right: str
    join_type: JoinType = JoinType.INNER

    def to_sql(self) -> str:
        """Convert to SQL string."""
        return (
            f"{self.join_type.value} {self.table} ON {self.on_left} = {self.on_right}"
        )


class QueryBuilder:
    """Fluent SQL query builder."""

    def __init__(self, table: str):
        self._table = table
        self._columns: List[str] = ["*"]
        self._conditions: List[Condition] = []
        self._joins: List[Join] = []
        self._order_by: List[str] = []
        self._group_by: List[str] = []
        self._limit: Optional[int] = None
        self._offset: Optional[int] = None

    def select(self, *columns: str) -> "QueryBuilder":
        """Set columns to select."""
        self._columns = list(columns) if columns else ["*"]
        return self

    def where(
        self, column: str, operator: Union[SQLOperator, str], value: Any = None
    ) -> "QueryBuilder":
        """Add WHERE condition."""
        if isinstance(operator, str):
            operator = SQLOperator(operator)
        self._conditions.append(Condition(column, operator, value))
        return self

    def join(
        self,
        table: str,
        on_left: str,
        on_right: str,
        join_type: JoinType = JoinType.INNER,
    ) -> "QueryBuilder":
        """Add JOIN clause."""
        self._joins.append(Join(table, on_left, on_right, join_type))
        return self

    def order_by(self, *columns: str) -> "QueryBuilder":
        """Set ORDER BY columns."""
        self._order_by = list(columns)
        return self

    def group_by(self, *columns: str) -> "QueryBuilder":
        """Set GROUP BY columns."""
        self._group_by = list(columns)
        return self

    def limit(self, count: int) -> "QueryBuilder":
        """Set LIMIT."""
        self._limit = count
        return self

    def offset(self, count: int) -> "QueryBuilder":
        """Set OFFSET."""
        self._offset = count
        return self

    def build(self) -> str:
        """Build the SQL query string."""
        parts = [f"SELECT {', '.join(self._columns)}"]
        parts.append(f"FROM {self._table}")

        for join in self._joins:
            parts.append(join.to_sql())

        if self._conditions:
            conditions = " AND ".join(c.to_sql() for c in self._conditions)
            parts.append(f"WHERE {conditions}")

        if self._group_by:
            parts.append(f"GROUP BY {', '.join(self._group_by)}")

        if self._order_by:
            parts.append(f"ORDER BY {', '.join(self._order_by)}")

        if self._limit is not None:
            parts.append(f"LIMIT {self._limit}")

        if self._offset is not None:
            parts.append(f"OFFSET {self._offset}")

        return " ".join(parts)


class InsertBuilder:
    """SQL INSERT query builder."""

    def __init__(self, table: str):
        self._table = table
        self._columns: List[str] = []
        self._values: List[List[Any]] = []

    def columns(self, *cols: str) -> "InsertBuilder":
        """Set columns for insert."""
        self._columns = list(cols)
        return self

    def values(self, *vals: Any) -> "InsertBuilder":
        """Add values row."""
        self._values.append(list(vals))
        return self

    def build(self) -> str:
        """Build the INSERT query."""
        cols = ", ".join(self._columns)

        value_rows = []
        for row in self._values:
            formatted = []
            for v in row:
                if isinstance(v, str):
                    formatted.append(f"'{v}'")
                elif v is None:
                    formatted.append("NULL")
                else:
                    formatted.append(str(v))
            value_rows.append(f"({', '.join(formatted)})")

        return f"INSERT INTO {self._table} ({cols}) VALUES {', '.join(value_rows)}"


class UpdateBuilder:
    """SQL UPDATE query builder."""

    def __init__(self, table: str):
        self._table = table
        self._sets: Dict[str, Any] = {}
        self._conditions: List[Condition] = []

    def set(self, column: str, value: Any) -> "UpdateBuilder":
        """Set column value."""
        self._sets[column] = value
        return self

    def where(
        self, column: str, operator: SQLOperator, value: Any = None
    ) -> "UpdateBuilder":
        """Add WHERE condition."""
        self._conditions.append(Condition(column, operator, value))
        return self

    def build(self) -> str:
        """Build the UPDATE query."""
        sets = []
        for col, val in self._sets.items():
            if isinstance(val, str):
                sets.append(f"{col} = '{val}'")
            elif val is None:
                sets.append(f"{col} = NULL")
            else:
                sets.append(f"{col} = {val}")

        query = f"UPDATE {self._table} SET {', '.join(sets)}"

        if self._conditions:
            conditions = " AND ".join(c.to_sql() for c in self._conditions)
            query += f" WHERE {conditions}"

        return query


# Convenience functions
def select(table: str) -> QueryBuilder:
    """Create SELECT query builder."""
    return QueryBuilder(table)


def insert(table: str) -> InsertBuilder:
    """Create INSERT query builder."""
    return InsertBuilder(table)


def update(table: str) -> UpdateBuilder:
    """Create UPDATE query builder."""
    return UpdateBuilder(table)
