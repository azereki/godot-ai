from godot_ai.handlers import custom
from godot_ai.tools._meta_tool import register_manage_tool

_DESCRIPTION = """List or invoke custom tools registered by third-party addons.

Active session only. Use op="list" to discover registered tools.
"""


def register_custom_tools(mcp) -> None:
    register_manage_tool(
        mcp,
        tool_name="custom_manage",
        description=_DESCRIPTION,
        ops={
            "list": custom.custom_list,
            "invoke": custom.custom_invoke,
        },
        read_resource_forms={
            "list": "godot://custom-tools",
            "invoke": None,  # write op, no read resource
        },
    )
