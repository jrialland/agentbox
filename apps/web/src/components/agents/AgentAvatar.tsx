import { Avatar } from "@mantine/core";

import { API_URL } from "../../config";

export function AgentAvatar({
  name,
  version = 0,
  size = "md",
}: {
  name: string;
  version?: number;
  size?: number | string;
}) {
  const src = `${API_URL}/agents/${encodeURIComponent(name)}/avatar?v=${version}`;
  return <Avatar src={src} alt={name} name={name} radius="xl" size={size} />;
}
