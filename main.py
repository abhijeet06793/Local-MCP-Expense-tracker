import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional
from fastmcp import FastMCP

DB_PATH = "expenses.db"
CATEGORIES_PATH = Path(__file__).parent / "categories.json"

## ── Database setup ──────────────────────────────────────────────────────────

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the expenses table if it doesn't already exist."""
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS expenses (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT    NOT NULL,
                amount      REAL    NOT NULL,
                category    TEXT    NOT NULL DEFAULT 'General',
                date        TEXT    NOT NULL,
                description TEXT
            )
            """
        )
        conn.commit()


## ── FastMCP server ───────────────────────────────────────────────────────────

mcp = FastMCP(name="Expense Tracker")


## ── Resources ────────────────────────────────────────────────────────────────

@mcp.resource(
    "expense-tracker://categories",
    name="Expense Categories",
    description="List of all available expense categories with descriptions.",
    mime_type="application/json",
)
def get_categories() -> str:
    """Return all available expense categories from categories.json."""
    return CATEGORIES_PATH.read_text(encoding="utf-8")


## ── Tools ────────────────────────────────────────────────────────────────────

@mcp.tool
def add_expense(
    title: str,
    amount: float,
    category: str = "General",
    date: Optional[str] = None,
    description: Optional[str] = None,
) -> str:
    """
    Add a new expense to the database.

    Args:
        title:       Short name for the expense (e.g. 'Grocery shopping').
        amount:      Amount spent (e.g. 45.50).
        category:    Category label (e.g. 'Food', 'Travel'). Defaults to 'General'.
        date:        Date in YYYY-MM-DD format. Defaults to today if omitted.
        description: Optional longer note about the expense.

    Returns:
        Confirmation message with the new expense ID.
    """
    if date is None:
        date = datetime.today().strftime("%Y-%m-%d")

    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO expenses (title, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
            (title, amount, category, date, description),
        )
        conn.commit()
        new_id = cursor.lastrowid

    return f"✅ Expense added successfully with ID {new_id}: '{title}' — ${amount:.2f} [{category}] on {date}."


@mcp.tool
def edit_expense(
    expense_id: int,
    title: Optional[str] = None,
    amount: Optional[float] = None,
    category: Optional[str] = None,
    date: Optional[str] = None,
    description: Optional[str] = None,
) -> str:
    """
    Edit an existing expense. Only the fields you provide will be updated.

    Args:
        expense_id:  ID of the expense to edit.
        title:       New title (optional).
        amount:      New amount (optional).
        category:    New category (optional).
        date:        New date in YYYY-MM-DD format (optional).
        description: New description (optional).

    Returns:
        Confirmation or error message.
    """
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
        if row is None:
            return f"❌ No expense found with ID {expense_id}."

        updated_title       = title       if title       is not None else row["title"]
        updated_amount      = amount      if amount      is not None else row["amount"]
        updated_category    = category    if category    is not None else row["category"]
        updated_date        = date        if date        is not None else row["date"]
        updated_description = description if description is not None else row["description"]

        conn.execute(
            """
            UPDATE expenses
            SET title = ?, amount = ?, category = ?, date = ?, description = ?
            WHERE id = ?
            """,
            (updated_title, updated_amount, updated_category, updated_date, updated_description, expense_id),
        )
        conn.commit()

    return f"✅ Expense ID {expense_id} updated successfully."


@mcp.tool
def delete_expense(expense_id: int) -> str:
    """
    Delete an expense by its ID.

    Args:
        expense_id: ID of the expense to delete.

    Returns:
        Confirmation or error message.
    """
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
        if row is None:
            return f"❌ No expense found with ID {expense_id}."

        conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
        conn.commit()

    return f"🗑️ Expense ID {expense_id} ('{row['title']}') deleted successfully."


@mcp.tool
def list_expenses(
    category: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> str:
    """
    List all expenses, optionally filtered by category and/or date range.

    Args:
        category:   Filter by category name (optional).
        start_date: Show expenses on or after this date — YYYY-MM-DD (optional).
        end_date:   Show expenses on or before this date — YYYY-MM-DD (optional).

    Returns:
        Formatted list of expenses or a message if none are found.
    """
    query = "SELECT * FROM expenses WHERE 1=1"
    params: list = []

    if category:
        query += " AND LOWER(category) = LOWER(?)"
        params.append(category)
    if start_date:
        query += " AND date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date <= ?"
        params.append(end_date)

    query += " ORDER BY date DESC, id DESC"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()

    if not rows:
        return "📭 No expenses found matching the given filters."

    lines = ["📋 **Expense List**\n"]
    lines.append(f"{'ID':<5} {'Date':<12} {'Title':<25} {'Category':<15} {'Amount':>10}  Description")
    lines.append("-" * 80)
    for row in rows:
        desc = row["description"] or ""
        lines.append(
            f"{row['id']:<5} {row['date']:<12} {row['title']:<25} {row['category']:<15} ${row['amount']:>9.2f}  {desc}"
        )

    return "\n".join(lines)


@mcp.tool
def summarize_expenses(
    category: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> str:
    """
    Summarize expenses — total spend, count, and per-category breakdown.

    Args:
        category:   Limit summary to a single category (optional).
        start_date: Start of the date range — YYYY-MM-DD (optional).
        end_date:   End of the date range — YYYY-MM-DD (optional).

    Returns:
        A formatted summary report.
    """
    base_filter = " WHERE 1=1"
    params: list = []

    if category:
        base_filter += " AND LOWER(category) = LOWER(?)"
        params.append(category)
    if start_date:
        base_filter += " AND date >= ?"
        params.append(start_date)
    if end_date:
        base_filter += " AND date <= ?"
        params.append(end_date)

    with get_connection() as conn:
        totals = conn.execute(
            f"SELECT COUNT(*) as cnt, SUM(amount) as total FROM expenses{base_filter}", params
        ).fetchone()

        by_category = conn.execute(
            f"SELECT category, COUNT(*) as cnt, SUM(amount) as total FROM expenses{base_filter} GROUP BY category ORDER BY total DESC",
            params,
        ).fetchall()

    if totals["cnt"] == 0:
        return "📭 No expenses found for the given filters."

    lines = ["📊 **Expense Summary**\n"]
    lines.append(f"  Total Expenses : {totals['cnt']}")
    lines.append(f"  Total Amount   : ${totals['total']:.2f}\n")
    lines.append(f"  {'Category':<20} {'Count':>6}  {'Total':>10}")
    lines.append("  " + "-" * 42)
    for row in by_category:
        lines.append(f"  {row['category']:<20} {row['cnt']:>6}  ${row['total']:>9.2f}")

    return "\n".join(lines)


## ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    mcp.run()


## Run the MCP inspector : uv run fastmcp dev inspector main.py
## Run the server        : uv run fastmcp run main.py