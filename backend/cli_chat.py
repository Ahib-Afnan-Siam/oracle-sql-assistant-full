# cli_chat.py

import requests
import json
import readline
from typing import Dict, List
import logging

# ✅ Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

# ✅ Enable vector_store_chroma logs
logging.getLogger("app.vector_store_chroma").setLevel(logging.INFO)
logging.getLogger("chromadb").setLevel(logging.WARNING)  # Optional: silence Chroma internals

class SchemaChatCLI:
    def __init__(self, api_url: str = "http://localhost:8090"):
        self.api_url = api_url
        self.session_id = None
        self.history = []

    def display_welcome(self):
        print("\n" + "=" * 60)
        print("DATABASE SCHEMA ASSISTANT (CLI VERSION)".center(60))
        print("=" * 60)
        print("\nType your questions about your database.")
        print("Examples:")
        print("  - show department name and total employees")
        print("  - list product names and prices")
        print("\nType 'quit' or 'exit' to end the session.\n")

    def format_response(self, response: Dict) -> str:
        """Format the assistant's API response for terminal output"""
        output = []

        if response.get("status") == "error":
            output.append(f"\n❌ Error: {response.get('message', 'Unknown error')}")
            for tip in response.get("suggestions", []):
                output.append(f"- {tip}")
            return "\n".join(output)

        if response.get("status") == "success":
            output.append("✅ Query executed successfully!")

            # Show SQL
            sql = response.get("sql", "")
            if sql:
                output.append(f"\n📄 Generated SQL:\n{sql}")

            # Show schema context
            schema_chunks = response.get("schema_context", [])
            if schema_chunks:
                output.append("\n📘 Schema Context Used:")
                for i, chunk in enumerate(schema_chunks, 1):
                    output.append(f"\n--- Schema #{i} ---\n{chunk}")

            # Show results
            result = response.get("results", {})
            columns = result.get("columns", [])
            rows = result.get("rows", [])
            row_count = result.get("row_count", 0)

            output.append(f"\n📊 Query Result (Rows: {row_count})")

            if columns:
                header = "  |  ".join(columns)
                output.append(header)
                output.append("-" * len(header))

                for row in rows:
                    line = "  |  ".join(str(val) if val is not None else "NULL" for val in row)
                    output.append(line)
            else:
                output.append("No data returned.")

            return "\n".join(output)

        # Unexpected structure fallback
        return f"[Raw Response Fallback]\n{json.dumps(response, indent=2)}"

    def chat_loop(self):
        self.display_welcome()

        while True:
            try:
                question = input("\nYou: ").strip()

                if question.lower() in ("quit", "exit", "q"):
                    print("\n👋 Goodbye!\n")
                    break

                if not question:
                    continue

                self.history.append(f"You: {question}")

                print("\nAssistant: ", end='', flush=True)

                try:
                    res = requests.post(
                        f"{self.api_url}/chat",
                        json={"question": question},
                        timeout=180
                    )
                    res.raise_for_status()
                    response_json = res.json()

                    logger.info(f"📦 Full raw response: {json.dumps(response_json)}")

                    formatted = self.format_response(response_json)
                    print(formatted)

                    self.history.append(f"Assistant: {formatted}")

                except requests.exceptions.RequestException as e:
                    error_msg = f"❌ Connection error: {str(e)}"
                    print(error_msg)
                    logger.error(error_msg)
                    self.history.append(f"Error: {error_msg}")

            except KeyboardInterrupt:
                print("\n\n⚠️ Use 'quit' or 'exit' to end the session.")
                continue

            except Exception as e:
                error_msg = f"❌ Unexpected error: {str(e)}"
                print(error_msg)
                logger.error(error_msg)
                self.history.append(f"Error: {error_msg}")


if __name__ == "__main__":
    chat = SchemaChatCLI(api_url="http://localhost:8090")
    chat.chat_loop()
