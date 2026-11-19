import { Button, Select, Textarea } from "@mantine/core";
import { useRef, useState } from "react";

import { uploadAttachment } from "../api/endpoints";
import { useSkills } from "../api/queries";
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
  onSelectSkill,
}: {
  sessionId: string;
  value: string;
  setValue: React.Dispatch<React.SetStateAction<string>>;
  mode: string | null;
  setMode: (m: string | null) => void;
  running: boolean;
  onSend: (attachmentIds: string[]) => void;
  onSelectSkill: (name: string) => void;
}) {
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [listening, setListening] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const stopSpeechRef = useRef<(() => void) | null>(null);
  const { data: skills } = useSkills();

  const slash = value.startsWith("/") ? value.slice(1) : null;
  const matches =
    slash === null
      ? []
      : (skills ?? []).filter((s) => s.name.includes(slash)).slice(0, 8);

  async function onFiles(files: FileList | null) {
    if (!files) return;
    for (const file of Array.from(files)) {
      try {
        const a = await uploadAttachment(sessionId, file);
        setAttachments((prev) => [...prev, { id: a.id, filename: a.filename }]);
      } catch {
        // upload failure is surfaced by the send path
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
    onSend(attachments.map((a) => a.id));
    setAttachments([]);
    if (listening) {
      stopSpeechRef.current?.();
      setListening(false);
    }
  }

  return (
    <div className="box">
      <Textarea
        label="Message"
        value={value}
        onChange={(e) => setValue(e.currentTarget.value)}
        rows={3}
      />
      {slash !== null && matches.length > 0 && (
        <div className="box" data-testid="skill-menu">
          {matches.map((s) => (
            <button
              key={s.name}
              type="button"
              className="is-block"
              onClick={() => {
                setValue(`/${s.name} `);
                onSelectSkill(s.name);
              }}
            >
              /{s.name} — {s.description}
            </button>
          ))}
        </div>
      )}
      <div className="mt-2">
        {attachments.map((a) => (
          <span key={a.id} className="tag is-light mr-2">
            {a.filename}
          </span>
        ))}
      </div>
      <div className="is-flex is-justify-content-space-between mt-2">
        <div className="is-flex">
          <Select data={["ask", "agent"]} value={mode} onChange={setMode} w={120} />
          <Button
            ml="xs"
            variant="light"
            aria-label="Add attachments"
            onClick={() => fileRef.current?.click()}
          >
            Attach
          </Button>
          {speechAvailable() && (
            <Button ml="xs" variant="light" aria-label="Speech to text" onClick={toggleMic}>
              Dictate
            </Button>
          )}
        </div>
        <Button onClick={submit} loading={running}>
          Send
        </Button>
      </div>
      <input
        ref={fileRef}
        type="file"
        multiple
        hidden
        aria-label="Attach files"
        onChange={(e) => onFiles(e.currentTarget.files)}
      />
    </div>
  );
}
