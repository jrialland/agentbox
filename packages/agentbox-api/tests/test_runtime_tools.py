from agentbox_api.runtime import build_registry
from agentbox_harness.spec import Mode


def test_registry_exposes_all_tools_with_flags():
    reg = build_registry(".")
    ask = Mode(name="ask", flags={"write": False})
    agent = Mode(name="agent", flags={"write": True})
    names_ask = {t.__name__ for t in reg.select_tools(ask)}  # ty: ignore[missing-attribute]
    names_agent = {t.__name__ for t in reg.select_tools(agent)}  # ty: ignore[missing-attribute]
    read = {
        "read_text_file",
        "read_file",
        "read_media_file",
        "read_multiple_files",
        "list_directory",
        "list_directory_with_sizes",
        "directory_tree",
            "search_files",
            "grep",
            "get_file_info",
        "list_allowed_directories",
        "web_search",
        "fetch_url",
    }
    write = {
        "write_file",
        "append_file",
        "edit_file",
        "create_directory",
        "move_file",
        "copy_file",
        "delete_path",
    }
    assert names_ask == read
    assert names_agent == read | write
