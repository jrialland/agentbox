import { Drawer } from "../design-system/overlays/Drawer";
import styles from "./help.module.css";
import { getHelpEntry } from "./content";
import { HelpLink } from "./HelpLink";
import type { HelpId } from "./types";

export function HelpDrawer({
  active,
  onClose,
}: {
  active: HelpId | null;
  onClose: () => void;
}) {
  const entry = active ? getHelpEntry(active) : null;

  return (
    <Drawer
      opened={active !== null}
      onClose={onClose}
      title={entry?.title ?? "Help"}
      size="md"
    >
      {entry && (
        <>
          <p className={styles.drawerSection}>{entry.summary}</p>
          {entry.sections.map((section) => (
            <section key={section.heading} className={styles.drawerSection}>
              <h3>{section.heading}</h3>
              {section.paragraphs?.map((paragraph) => (
                <p key={paragraph}>{paragraph}</p>
              ))}
              {section.bullets && (
                <ul>
                  {section.bullets.map((bullet) => (
                    <li key={bullet}>{bullet}</li>
                  ))}
                </ul>
              )}
              {section.code && (
                <pre>
                  <code>{section.code}</code>
                </pre>
              )}
            </section>
          ))}
          {entry.related && entry.related.length > 0 && (
            <section className={styles.drawerSection}>
              <h3>Related</h3>
              {entry.related.map((id) => (
                <HelpLink key={id} id={id}>
                  {getHelpEntry(id).title}
                </HelpLink>
              ))}
            </section>
          )}
        </>
      )}
    </Drawer>
  );
}
