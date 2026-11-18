import { useParams } from "react-router-dom";

export function SessionPage() {
  const { id } = useParams();
  return (
    <div>
      <h1 className="title">Session</h1>
      <p className="subtitle">{id}</p>
    </div>
  );
}
