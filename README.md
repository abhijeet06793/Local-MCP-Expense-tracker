# 💰 Expense Tracker MCP Server

A fully-featured **Model Context Protocol (MCP) server** built with [FastMCP](https://gofastmcp.com) that lets AI assistants (like Claude) add, edit, delete, list, and summarise personal expenses — all stored in a local **SQLite** database.

---

## 📁 Project Structure

```
expense-tracker-mcp-server/
├── main.py            # MCP server — tools, resources, DB setup
├── test.py            # Demo server with roll_dice & add_two_numbers tools
├── categories.json    # Predefined expense categories
├── expenses.db        # SQLite database (auto-created on first run)
├── pyproject.toml     # Project metadata & dependencies
├── requirements.txt   # Pip-compatible dependency list
└── README.md          # This file
```

---

## 🚀 Getting Started

### Prerequisites

- [Python 3.12+](https://www.python.org/downloads/)
- [uv](https://docs.astral.sh/uv/) — fast Python package manager
- [Node.js](https://nodejs.org/) — required only for `npx`-based MCP Inspector

### Installation

```bash
# Clone or open the project folder, then install dependencies
uv sync
```

---

## ▶️ Running the Server

### Standard run (stdio transport — for Claude Desktop etc.)
```bash
uv run fastmcp run main.py
```

### HTTP transport (for network/multi-client access)
```bash
uv run fastmcp run main.py --transport http --port 8000
# MCP endpoint: http://localhost:8000/mcp
```

### Development mode with MCP Inspector
```bash
uv run fastmcp dev inspector main.py
```
This launches a browser-based UI at **http://localhost:6274** for interactive testing.
> In the Inspector UI, select **STDIO** from the transport dropdown and click **Connect**.

### Alternative — run Inspector via npx
```bash
# Terminal 1 — start server over HTTP
uv run fastmcp run main.py --transport http --port 8000

# Terminal 2 — open Inspector
npx @modelcontextprotocol/inspector@latest
# Connect to: http://localhost:8000/mcp
```

---

## 🗄️ Database

The server uses **SQLite** (`expenses.db`) which is created automatically on first run.

### Schema

```sql
CREATE TABLE IF NOT EXISTS expenses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL,           -- Short name of the expense
    amount      REAL    NOT NULL,           -- Amount spent (e.g. 45.50)
    category    TEXT    NOT NULL DEFAULT 'General',
    date        TEXT    NOT NULL,           -- Stored as YYYY-MM-DD string
    description TEXT                        -- Optional longer note
);
```

### How it is initialised

`init_db()` is called inside the `if __name__ == "__main__"` block, so the table is created (if missing) every time the server starts:

```python
def init_db() -> None:
    """Create the expenses table if it doesn't already exist."""
    with get_connection() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS expenses ( ... )")
        conn.commit()
```

`get_connection()` sets `row_factory = sqlite3.Row` so every returned row behaves like a dictionary — you can access columns by name (e.g. `row["title"]`) instead of by index.

---

## 🛠️ MCP Tools

Tools are Python functions decorated with `@mcp.tool`. The AI assistant calls them to perform actions.

### 1. `add_expense`

Adds a new expense record.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `title` | `str` | ✅ | — | Short name (e.g. `"Grocery shopping"`) |
| `amount` | `float` | ✅ | — | Amount spent (e.g. `45.50`) |
| `category` | `str` | ❌ | `"General"` | Category label |
| `date` | `str` | ❌ | Today | Date in `YYYY-MM-DD` format |
| `description` | `str` | ❌ | `None` | Optional longer note |

**Example response:**
```
✅ Expense added successfully with ID 3: 'Grocery shopping' — $45.50 [Food] on 2026-03-05.
```

**How it works:**
```python
@mcp.tool
def add_expense(title, amount, category="General", date=None, description=None):
    if date is None:
        date = datetime.today().strftime("%Y-%m-%d")  # Default to today

    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO expenses (title, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
            (title, amount, category, date, description),
        )
        conn.commit()
        new_id = cursor.lastrowid  # Grab the auto-generated ID
```

---

### 2. `edit_expense`

Updates an existing expense. **Only the fields you pass are changed** — everything else stays the same (partial update pattern).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `expense_id` | `int` | ✅ | ID of the expense to edit |
| `title` | `str` | ❌ | New title |
| `amount` | `float` | ❌ | New amount |
| `category` | `str` | ❌ | New category |
| `date` | `str` | ❌ | New date (`YYYY-MM-DD`) |
| `description` | `str` | ❌ | New description |

**How the partial-update pattern works:**
```python
# Fetch existing row first
row = conn.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()

# Use new value if provided, otherwise keep the old one
updated_title  = title  if title  is not None else row["title"]
updated_amount = amount if amount is not None else row["amount"]
# ... same for other fields
```

---

### 3. `delete_expense`

Deletes an expense by ID. Checks existence first and returns an error if not found.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `expense_id` | `int` | ✅ | ID of the expense to delete |

**Example response:**
```
🗑️ Expense ID 3 ('Grocery shopping') deleted successfully.
```

---

### 4. `list_expenses`

Lists all expenses with optional filters. Results are sorted by date (newest first).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `category` | `str` | ❌ | Filter by category (case-insensitive) |
| `start_date` | `str` | ❌ | Show expenses on or after this date |
| `end_date` | `str` | ❌ | Show expenses on or before this date |

**Example output:**
```
📋 Expense List

ID    Date         Title                     Category         Amount  Description
--------------------------------------------------------------------------------
3     2026-03-05   Grocery shopping          Food             $45.50  Weekly shop
2     2026-03-04   Netflix                   Entertainment    $15.99
1     2026-03-01   Bus pass                  Transport        $30.00  Monthly pass
```

**How dynamic filtering works:**
```python
query = "SELECT * FROM expenses WHERE 1=1"  # Always-true base clause
params = []

if category:
    query += " AND LOWER(category) = LOWER(?)"  # Case-insensitive match
    params.append(category)
if start_date:
    query += " AND date >= ?"
    params.append(start_date)
# Parameters are built up dynamically — only applied when provided
```

---

### 5. `summarize_expenses`

Returns aggregated totals — overall count, total spend, and a per-category breakdown.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `category` | `str` | ❌ | Limit to one category |
| `start_date` | `str` | ❌ | Start of date range |
| `end_date` | `str` | ❌ | End of date range |

**Example output:**
```
📊 Expense Summary

  Total Expenses : 3
  Total Amount   : $91.49

  Category               Count       Total
  ------------------------------------------
  Food                       1      $45.50
  Entertainment              1      $15.99
  Transport                  1      $30.00
```

---

## 📦 MCP Resources

Resources are **read-only data endpoints** the AI can fetch at any time without calling a tool. They are decorated with `@mcp.resource("uri://...")`.

| URI | Name | Description |
|-----|------|-------------|
| `expense-tracker://categories` | Expense Categories | All categories from `categories.json` |
| `expense-tracker://expenses/all` | All Expenses | Every expense as a JSON array |
| `expense-tracker://expenses/{expense_id}` | Single Expense | One expense record by ID |
| `expense-tracker://summary` | Expense Summary | Totals + per-category breakdown |

### Example — reading a resource in the Inspector

1. Open the **Resources** tab in the MCP Inspector.
2. Click `expense-tracker://categories` to see all available categories.
3. Click `expense-tracker://summary` to see your current spending summary.

### How resource templates work

The `expense-tracker://expenses/{expense_id}` resource uses a **URI template** — the `{expense_id}` placeholder maps directly to a function parameter:

```python
@mcp.resource("expense-tracker://expenses/{expense_id}")
def get_expense_by_id(expense_id: int) -> str:
    # FastMCP extracts the ID from the URI and passes it here
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
    return json.dumps(dict(row), indent=2)
```

---

## 🗂️ Categories

Defined in `categories.json` and exposed via the `expense-tracker://categories` resource.

| Category | Description |
|----------|-------------|
| Food | Groceries, restaurants, takeaway, snacks |
| Transport | Fuel, public transit, taxi, parking |
| Housing | Rent, mortgage, repairs, maintenance |
| Utilities | Electricity, water, gas, internet, phone |
| Health | Doctor visits, medicines, gym, insurance |
| Entertainment | Movies, games, subscriptions, hobbies |
| Shopping | Clothing, electronics, household items |
| Travel | Flights, hotels, vacation expenses |
| Education | Courses, books, training, tuition fees |
| General | Miscellaneous or uncategorised expenses |

---

## 🧪 Test Server (`test.py`)

A minimal demo server with two basic tools — useful for testing MCP connectivity before using the full expense tracker.

```bash
uv run fastmcp dev inspector test.py
```

| Tool | Description |
|------|-------------|
| `roll_dice(sides)` | Returns a random number between 1 and `sides` |
| `add_two_numbers(a, b)` | Returns `a + b` |

---

## 📦 Dependencies

Defined in `pyproject.toml`:

```toml
[project]
name = "expense-tracker-mcp-server"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["fastmcp"]
```

| Package | Purpose |
|---------|---------|
| `fastmcp` | MCP server framework — handles protocol, tool/resource registration, transports |
| `sqlite3` | Built-in Python library — no install needed |

---

## 🔌 Transport Options

| Transport | Command | Use Case |
|-----------|---------|----------|
| `stdio` (default) | `uv run fastmcp run main.py` | Claude Desktop, local clients |
| `http` | `uv run fastmcp run main.py --transport http --port 8000` | Network/remote/multi-client |
| `sse` (legacy) | `uv run fastmcp run main.py --transport sse --port 8000` | Older clients only |

---

## 💡 How MCP Works (Quick Primer)

```
┌─────────────────┐        MCP Protocol        ┌──────────────────────┐
│   AI Assistant  │ ◄─────────────────────────► │  Expense Tracker     │
│  (Claude etc.)  │   tools/call, resources/read │  MCP Server          │
└─────────────────┘                             └──────────────────────┘
                                                         │
                                                    SQLite DB
                                                  (expenses.db)
```

1. The AI assistant discovers available **tools** and **resources** from the server.
2. When the user says _"add a $50 grocery expense"_, the AI calls `add_expense`.
3. When the user says _"show me my spending summary"_, the AI reads `expense-tracker://summary`.
4. The server executes the logic, queries SQLite, and returns a response.
