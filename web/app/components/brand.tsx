export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <span className="brand" aria-label="AIMusicMed">
      <span className="brand-mark" aria-hidden="true"><i /><i /><i /></span>
      {!compact && <span className="brand-name">AIMusicMed</span>}
    </span>
  );
}
