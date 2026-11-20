import { Avatar, Menu } from "@mantine/core";
import { RiLogoutBoxRLine, RiUserLine } from "@remixicon/react";

import { Icon } from "../icons/Icon";

export function UserMenu({
  username,
  onLogout,
}: {
  username: string;
  onLogout: () => void;
}) {
  return (
    <Menu position="right-end" withArrow>
      <Menu.Target>
        <button
          type="button"
          aria-label={`User menu for ${username}`}
          style={{
            display: "grid",
            placeItems: "center",
            width: 36,
            height: 36,
            border: "1px solid var(--ab-border)",
            background: "var(--ab-surface)",
            color: "var(--ab-text)",
            cursor: "pointer",
          }}
        >
          <Avatar size={24} radius={0} color="phosphor">
            {username.slice(0, 1).toUpperCase()}
          </Avatar>
        </button>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Label>{username}</Menu.Label>
        <Menu.Item leftSection={<Icon as={RiUserLine} size={16} />} disabled>
          Operator
        </Menu.Item>
        <Menu.Divider />
        <Menu.Item
          color="red"
          leftSection={<Icon as={RiLogoutBoxRLine} size={16} />}
          onClick={onLogout}
        >
          Logout
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  );
}
