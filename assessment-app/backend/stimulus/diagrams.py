class DiagramProvider:
    @staticmethod
    def format_mermaid_diagram(syntax: str, title: str):
        return {"stimulus_type": "diagram", "format": "mermaid", "content": syntax.strip(), "attribution": f"Diagram: {title}"}

    @staticmethod
    def format_data_table(markdown_table: str, title: str):
        return {"stimulus_type": "data_table", "format": "markdown_table", "content": markdown_table.strip(), "attribution": f"Data: {title}"}
