import {
  RiAttachment2,
  RiCloseLine,
  RiMicLine,
  RiMicOffLine,
  RiSendPlane2Line,
  RiStopLine,
} from "@remixicon/react";
import { SegmentedControl, Tooltip } from "@mantine/core";
import { useRef, useState } from "react";

import { uploadAttachment } from "../api/endpoints";
import { useSessionFiles, useSkills } from "../api/queries";
import { Textarea } from "../design-system/forms/Textarea";
import { Icon } from "../design-system/icons/Icon";
import { IconButton } from "../design-system/icons/IconButton";
import styles from "./composer.module.css";
import { speechAvailable, startSpeech } from "./speech";

type Attachment = { id: string; filename: string };

export function Composer({
  sessionId,
  value,
  setValue,
  mode,
  setMode,
  running,
  onSend,
  onStop,
  onSelectSkill,
}: {
  sessionId: string;
  value: string;
  setValue: React.Dispatch<React.SetStateAction<string>>;
  mode: string | null;
  setMode: (m: string | null) => void;
  running: boolean;
  onSend: (attachmentIds: string[]) => void;
  onStop?: () => void;
  onSelectSkill: (name: string) => void;
}) {
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [listening, setListening] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const stopSpeechRef = useRef<(() => void) | null>(null);
  const { data: skills } = useSkills();

  const slash = value.startsWith("/") ? value.slice(1) : null;
  const matches =
    slash === null
      ? []
      : (skills ?? []).filter((s) => s.name.includes(slash)).slice(0, 8);

  const at = value.lastIndexOf("@");
  const atQuery = at >= 0 ? value.slice(at + 1) : null;
  const atActive =
    slash === null && atQuery !== null && atQuery !== "" && !/\s/.test(atQuery);
  const { data: files } = useSessionFiles(sessionId, atActive ? atQuery : "");
  const fileMatches = atActive ? (files ?? []).slice(0, 8) : [];

  function pickFile(path: string) {
    if (at < 0) return;
    setValue(`${value.slice(0, at)}@${path} `);
  }

  async function onFiles(files: FileList | null) {
    if (!files) return;
    setUploadError(null);
    for (const file of Array.from(files)) {
      try {
        const a = await uploadAttachment(sessionId, file);
        setAttachments((prev) => [...prev, { id: a.id, filename: a.filename }]);
      } catch {
        setUploadError(`Could not upload ${file.name}`);
      }
    }
    if (fileRef.current) fileRef.current.value = "";
  }

  function toggleMic() {
    if (listening) {
      stopSpeechRef.current?.();
      stopSpeechRef.current = null;
      setListening(false);
      return;
    }
    stopSpeechRef.current = startSpeech((t) => setValue((v) => v + t));
    setListening(true);
  }

  function submit() {
    if (running || !value.trim()) return;
    onSend(attachments.map((a) => a.id));
    setAttachments([]);
    if (listening) {
      stopSpeechRef.current?.();
      setListening(false);
    }
  }

  function stop() {
    onStop?.();
  }

  return (
    <div
      className={`${styles.composer} ${dragging ? styles.dragging : ""}`}
      data-testid="composer"
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        void onFiles(event.dataTransfer.files);
      }}
    >
      <Textarea
        aria-label="Message"
        rows={2}
        value={value}
        onChange={(event) => setValue(event.currentTarget.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            submit();
          }
        }}
        placeholder="Message the agent. Use / for skills and @ for files."
        classNames={{ input: styles.input }}
      />
      {slash !== null && matches.length > 0 && (
        <div className={styles.menu} data-testid="skill-menu">
          {matches.map((s) => (
            <button
              key={s.name}
              type="button"
              className={styles.menuItem}
              onClick={() => {
                setValue(`/${s.name} `);
                onSelectSkill(s.name);
              }}
            >
              <span className={styles.menuTitle}>/{s.name}</span>
              <span className={styles.menuHint}>{s.description}</span>
            </button>
          ))}
        </div>
      )}
      {atActive && fileMatches.length > 0 && (
        <div className={styles.menu} data-testid="file-menu">
          {fileMatches.map((p) => (
            <button
              key={p}
              type="button"
              className={styles.menuItem}
              aria-label={`@${p}`}
              onClick={() => pickFile(p)}
            >
              <span className={styles.menuTitle}>@{p}</span>
            </button>
          ))}
        </div>
      )}
      {attachments.length > 0 && (
        <div className={styles.attachments}>
          {attachments.map((a) => (
            <span key={a.id} className={styles.attachment}>
              <Icon as={RiAttachment2} size={16} />
              {a.filename}
              <button
                type="button"
                aria-label={`Remove ${a.filename}`}
                onClick={() =>
                  setAttachments((prev) => prev.filter((item) => item.id !== a.id))
                }
              >
                <Icon as={RiCloseLine} size={16} />
              </button>
            </span>
          ))}
        </div>
      )}
      {uploadError && (
        <p className={styles.error} role="alert">
          {uploadError}
        </p>
      )}
      <div className={styles.toolbar}>
        <div className={styles.tools}>
          <SegmentedControl
            size="xs"
            data={[
              { label: "Ask", value: "ask" },
              { label: "Agent", value: "agent" },
            ]}
            value={mode ?? "agent"}
            onChange={(next) => setMode(next)}
          />
          <IconButton
            label="Add attachments"
            icon={RiAttachment2}
            size={18}
            onClick={() => fileRef.current?.click()}
          />
          {speechAvailable() && (
            <IconButton
              label={listening ? "Stop dictation" : "Speech to text"}
              icon={listening ? RiMicOffLine : RiMicLine}
              size={18}
              onClick={toggleMic}
            />
          )}
        </div>
        <div className={styles.sendArea}>
          {running ? (
            <Tooltip label="Stop" withArrow>
              <IconButton
                label="Stop"
                icon={RiStopLine}
                size={20}
                variant="filled"
                color="danger"
                onClick={stop}
              />
            </Tooltip>
          ) : (
            <Tooltip label="Send" withArrow>
              <IconButton
                label="Send"
                icon={RiSendPlane2Line}
                size={20}
                variant="filled"
                color="phosphor"
                disabled={!value.trim()}
                onClick={submit}
              />
            </Tooltip>
          )}
        </div>
      </div>
      <input
        ref={fileRef}
        type="file"
        multiple
        hidden
        aria-label="Attach files"
        onChange={(event) => onFiles(event.currentTarget.files)}
      />
    </div>
  );
}
