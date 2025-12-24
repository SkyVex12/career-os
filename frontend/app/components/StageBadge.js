export default function StageBadge({ stage }) {
  const s = (stage || "applied").toLowerCase();
  return <span className={`badge ${s}`}>{s}</span>;
}
