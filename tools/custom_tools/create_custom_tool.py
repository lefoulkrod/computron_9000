"""Tool for creating and persisting new custom tools."""

from __future__ import annotations

import json
import logging

from sdk.events import AssistantResponse, ToolCreatedPayload, publish_event

from tools._truncation import truncate_args

from . import registry

logger = logging.getLogger(__name__)


@truncate_args(command_template=300, program_code=0)
async def create_custom_tool(
    name: str,
    description: str,
    tool_type: str,
    language: str = "bash",
    command_template: str = "",
    program_code: str = "",
    parameters_json: str = "[]",
    dependencies: str = "",
    tags: str = "",
    overwrite: str = "false",
) -> dict[str, object]:
    """Create and save a new custom tool that persists across sessions.

    Creates either a "command" tool (shell one-liner with {param} placeholders)
    or a "program" tool (a Python or Bash script you write). All tools run
    inside the container environment.

    For program-type tools, write scripts that read arguments from stdin as JSON:
        import json, sys
        args = json.load(sys.stdin)

    Args:
        name: Unique tool name (snake_case, e.g. "fetch_weather").
        description: What the tool does, shown when listing/searching.
        tool_type: Either "command" or "program".
        language: "python" or "bash" (only for program type, defaults to bash).
        command_template: Shell command with {param} placeholders (command type).
        program_code: Full source code of the script (program type).
        parameters_json: JSON array of parameter defs, each with name, type, description, required.
        dependencies: Comma-separated package names to install before execution
            (e.g. "requests,pandas").
        tags: Comma-separated tags for searchability (e.g. "utility,file,csv").
        overwrite: Set to "true" to replace an existing tool with the same name.

    Returns:
        dict with tool id, name, and status.
    """
    try:
        if tool_type not in ("command", "program"):
            return {"status": "error", "message": "tool_type must be 'command' or 'program'"}

        if tool_type == "command" and not command_template.strip():
            return {"status": "error", "message": "command_template is required for command-type tools"}

        if tool_type == "program" and not program_code.strip():
            return {"status": "error", "message": "program_code is required for program-type tools"}

        if tool_type == "program" and language not in ("python", "bash"):
            return {"status": "error", "message": "language must be 'python' or 'bash'"}

        try:
            raw_params = json.loads(parameters_json)
        except json.JSONDecodeError as exc:
            return {"status": "error", "message": f"Invalid parameters_json: {exc}"}

        parameters = [registry.CustomToolParameter.model_validate(p) for p in raw_params]
        dep_list = [d.strip() for d in dependencies.split(",") if d.strip()]
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]

        definition = registry.CustomToolDefinition(
            id="",
            name=name,
            description=description,
            type=tool_type,
            language=language,
            command_template=command_template if tool_type == "command" else "",
            script_filename=None,
            parameters=parameters,
            dependencies=dep_list,
            tags=tag_list,
            created_at="",
            updated_at="",
        )

        saved = registry.add_tool(definition, overwrite=overwrite.strip().lower() == "true")

        if tool_type == "program":
            filename = registry.save_script(saved.id, program_code, language)
            # Update the registry entry with the script filename
            all_tools = registry.load_registry()
            for i, t in enumerate(all_tools):
                if t.id == saved.id:
                    all_tools[i] = t.model_copy(update={"script_filename": filename})
                    break
            registry.save_registry(all_tools)
            saved = saved.model_copy(update={"script_filename": filename})

        logger.info("Created custom tool '%s' (id=%s)", saved.name, saved.id)
        publish_event(AssistantResponse(event=ToolCreatedPayload(type="tool_created", name=saved.name)))
        return {"status": "created", "id": saved.id, "name": saved.name, "type": saved.type}

    except ValueError as exc:
        return {"status": "error", "message": str(exc)}
    except Exception as exc:
        logger.exception("Failed to create custom tool '%s'", name)
        return {"status": "error", "message": str(exc)}


__all__ = ["create_custom_tool"]
