import random
from fastmcp import FastMCP

## Create a FastMCP server instance
mcp = FastMCP(name="Demo Server")


@mcp.tool
def roll_dice(sides: int) -> int:
    """Roll a dice with the given number of sides."""
    return random.randint(1, sides)


@mcp.tool
def add_two_numbers(a: int, b: int) -> int:
    """Add two numbers together."""
    return a + b


if __name__ == "__main__":
    mcp.run()


## Run the MCP inspector : uv run fastmcp dev inspector test.py
## Run the server        : uv run fastmcp run test.py
