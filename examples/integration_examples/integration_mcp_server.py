from pathlib import Path

from mcp.server.fastmcp import FastMCP

# Create an MCP server
mcp = FastMCP("Kailash Service")


@mcp.tool()
def get_nodes(node_types: list) -> list:
    """
    Get nodes of the specified types.
    :param node_types: List of node types to get.
    :return: List of nodes of the specified types.
    """
    # Assuming you have a function to get nodes by type
    # return mcp.get_nodes_by_type(node_types)
    return ["ai", "code", "data", "logic", "transform"]


@mcp.resource("kailash://{document}")
def get_document(document: str = "customer_value.csv") -> dict:
    """
    Get a document by its name.
    :param document: Name of the document to get.
    :return: The document.
    """
    from kailash.nodes.data import CSVReader

    sample_directory = Path("tests/sample_data")

    csv_reader_node = CSVReader(
        file_path=sample_directory / document, headers=True, delimiter=","
    )

    return {"name": document, "content": csv_reader_node.execute}


@mcp.prompt()
def registry_report() -> str:
    """
    Create a kailash running registry prompt.
    :return: The generated prompt.
    """
    return """
    You are a Kailash administrator. 
    Generate the registry report for the current run."""


if __name__ == "__main__":
    mcp.run()
