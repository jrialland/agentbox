import { Textarea as MantineTextarea, type TextareaProps } from "@mantine/core";

export function Textarea(props: TextareaProps) {
  return <MantineTextarea radius="sm" {...props} />;
}
