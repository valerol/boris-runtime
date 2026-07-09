import os

from openai import OpenAI


def main():
    api_key = os.getenv("OPENAI_API_KEY")
    server_url = os.getenv("BORIS_REMOTE_MCP_URL")
    require_approval = os.getenv("BORIS_REMOTE_MCP_REQUIRE_APPROVAL", "never")

    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required")
    if not server_url:
        raise RuntimeError("BORIS_REMOTE_MCP_URL is required, for example https://<domain>/mcp")

    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        input="Ask BORIS Runtime to explain BOIS Runtime v0",
        tools=[
            {
                "type": "mcp",
                "server_label": "boris_runtime",
                "server_description": (
                    "Connects ChatGPT to BORIS Runtime through the BOIS/SIMA/BORIS protocol runtime."
                ),
                "server_url": server_url,
                "require_approval": require_approval,
            }
        ],
    )

    print(getattr(response, "output_text", ""))
    for item in getattr(response, "output", []) or []:
        item_type = getattr(item, "type", "")
        if item_type.startswith("mcp"):
            print(item)


if __name__ == "__main__":
    main()
