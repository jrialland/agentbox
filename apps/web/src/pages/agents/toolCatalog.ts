export type ToolCategory =
  | "filesystem-read"
  | "filesystem-write"
  | "web"
  | "terminal";

export type ToolMeta = {
  name: string;
  label: string;
  description: string;
  category: ToolCategory;
  risk: "read" | "write";
};

export const TOOL_META: Record<string, ToolMeta> = {
  read_text_file: { name: "read_text_file", label: "Read text file", description: "Read a text file from the project.", category: "filesystem-read", risk: "read" },
  read_media_file: { name: "read_media_file", label: "Read media file", description: "Read an image, audio, or video file.", category: "filesystem-read", risk: "read" },
  read_multiple_files: { name: "read_multiple_files", label: "Read multiple files", description: "Read several files in one call.", category: "filesystem-read", risk: "read" },
  list_directory: { name: "list_directory", label: "List directory", description: "List files and folders in a directory.", category: "filesystem-read", risk: "read" },
  list_directory_with_sizes: { name: "list_directory_with_sizes", label: "List directory with sizes", description: "List entries with file sizes.", category: "filesystem-read", risk: "read" },
  directory_tree: { name: "directory_tree", label: "Directory tree", description: "Show a recursive directory tree.", category: "filesystem-read", risk: "read" },
  search_files: { name: "search_files", label: "Search files", description: "Find files by name.", category: "filesystem-read", risk: "read" },
  get_file_info: { name: "get_file_info", label: "File info", description: "Read file metadata.", category: "filesystem-read", risk: "read" },
  list_allowed_directories: { name: "list_allowed_directories", label: "Allowed roots", description: "Show directories the agent may access.", category: "filesystem-read", risk: "read" },
  write_file: { name: "write_file", label: "Write file", description: "Create or overwrite a file.", category: "filesystem-write", risk: "write" },
  append_file: { name: "append_file", label: "Append file", description: "Append content to a file.", category: "filesystem-write", risk: "write" },
  edit_file: { name: "edit_file", label: "Edit file", description: "Apply a targeted edit to a file.", category: "filesystem-write", risk: "write" },
  create_directory: { name: "create_directory", label: "Create directory", description: "Create a directory.", category: "filesystem-write", risk: "write" },
  move_file: { name: "move_file", label: "Move file", description: "Move or rename a file.", category: "filesystem-write", risk: "write" },
  copy_file: { name: "copy_file", label: "Copy file", description: "Copy a file.", category: "filesystem-write", risk: "write" },
  delete_path: { name: "delete_path", label: "Delete path", description: "Delete a file or directory.", category: "filesystem-write", risk: "write" },
  web_search: { name: "web_search", label: "Web search", description: "Search the web.", category: "web", risk: "read" },
  fetch_url: { name: "fetch_url", label: "Fetch URL", description: "Fetch content from a URL.", category: "web", risk: "read" },
  terminal: { name: "terminal", label: "Terminal", description: "Run shell commands and manage jobs.", category: "terminal", risk: "write" },
};

export const TOOL_GROUPS = [
  { category: "filesystem-read", title: "Filesystem read", description: "Inspect project files." },
  { category: "filesystem-write", title: "Filesystem write", description: "Modify files and directories." },
  { category: "web", title: "Web", description: "Search and fetch web content." },
  { category: "terminal", title: "Terminal", description: "Run commands and manage jobs." },
] as const;
