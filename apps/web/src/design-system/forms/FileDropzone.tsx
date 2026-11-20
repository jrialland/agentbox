import { RiUploadCloud2Line } from "@remixicon/react";
import { useRef } from "react";

import { Icon } from "../icons/Icon";
import styles from "./forms.module.css";

export function FileDropzone({
  onFiles,
  accept,
  multiple,
}: {
  onFiles: (files: FileList) => void;
  accept?: string;
  multiple?: boolean;
}) {
  const ref = useRef<HTMLInputElement>(null);

  return (
    <div
      className={styles.dropzone}
      onClick={() => ref.current?.click()}
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        e.preventDefault();
        if (e.dataTransfer.files.length) onFiles(e.dataTransfer.files);
      }}
    >
      <Icon as={RiUploadCloud2Line} size={24} />
      <span>Drop files or click to browse</span>
      <input
        ref={ref}
        type="file"
        accept={accept}
        multiple={multiple}
        hidden
        onChange={(e) => e.currentTarget.files && onFiles(e.currentTarget.files)}
      />
    </div>
  );
}
