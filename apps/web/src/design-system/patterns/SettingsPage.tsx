import type { ReactNode } from "react";

import { PageHeader } from "../primitives/PageHeader";
import { Section } from "../primitives/Section";

export function SettingsPage({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <div>
      <PageHeader title={title} subtitle={subtitle} />
      <Section>{children}</Section>
    </div>
  );
}
