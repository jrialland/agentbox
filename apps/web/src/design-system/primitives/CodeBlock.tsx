import styles from "./feedback.module.css";

export function CodeBlock({
  code,
  language,
}: {
  code: string;
  language?: string;
}) {
  return (
    <figure className={styles.codeBlock}>
      {language && <figcaption>{language}</figcaption>}
      <pre>
        <code>{code}</code>
      </pre>
    </figure>
  );
}
