from packages.contracts.canonical import BlockKind, CanonicalSOP


def canonical_to_markdown(document: CanonicalSOP) -> str:
    lines = [f"# {document.title}", ""]
    for section in document.sections:
        prefix = "#" * min(6, section.heading_level + 1)
        lines.extend([f"{prefix} {section.heading}", ""])
        for block in section.blocks:
            if block.kind is BlockKind.PARAGRAPH and block.text:
                lines.extend([block.text, ""])
            elif block.kind in {BlockKind.ORDERED_LIST, BlockKind.UNORDERED_LIST}:
                for index, item in enumerate(block.list_items, start=1):
                    marker = f"{index}." if block.kind is BlockKind.ORDERED_LIST else "-"
                    lines.append(f"{'  ' * item.level}{marker} {item.text}")
                lines.append("")
            elif block.kind is BlockKind.TABLE and block.table:
                lines.append(" | ".join(cell.text for cell in block.table.cells if cell.is_header))
                lines.append("")
    return "\n".join(lines).strip() + "\n"
