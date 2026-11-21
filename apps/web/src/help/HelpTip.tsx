import { Popover } from "@mantine/core";
import { RiQuestionLine } from "@remixicon/react";

import { useState } from "react";
import { Button } from "../design-system/primitives/Button";
import { IconButton } from "../design-system/icons/IconButton";
import styles from "./help.module.css";
import { getHelpEntry } from "./content";
import { useHelp } from "./HelpProvider";
import type { HelpId } from "./types";

export function HelpTip({ id }: { id: HelpId }) {
  const { openHelp } = useHelp();
  const entry = getHelpEntry(id);
  const [opened, setOpened] = useState(false);

  return (
    <Popover
      position="top"
      withArrow
      shadow="md"
      opened={opened}
      onChange={setOpened}
    >
      <Popover.Target>
        <IconButton
          label={`Help: ${entry.title}`}
          icon={RiQuestionLine}
          size={16}
          variant="subtle"
          tooltip={false}
          onClick={() => setOpened((value) => !value)}
        />
      </Popover.Target>
      <Popover.Dropdown>
        <p className={styles.popoverText}>{entry.summary}</p>
        <Button size="compact-xs" onClick={() => openHelp(id)}>
          Learn more
        </Button>
      </Popover.Dropdown>
    </Popover>
  );
}

